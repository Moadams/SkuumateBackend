"""School-facing subscription views."""
import json

from django.db import transaction
from rest_framework import generics, serializers
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView

from core.exceptions import PaymentGatewayError
from core.models import AuditLog
from core.permissions import IsAdmin, is_platform_superadmin
from core.responses import ApiResponse
from core.utils import log_action
from integrations.registry import get_payment_provider
from schools.utils import check_and_complete_onboarding
from subscriptions.filters import MySubscriptionFilter
from subscriptions.models import Subscription, SubscriptionPayment
from subscriptions.serializers import (
    InitiatePaymentSerializer,
    SchoolSubscribeSerializer,
    SubscriptionListSerializer,
    SubscriptionSerializer,
)
from subscriptions.services.packages import subscription_entitlements
from subscriptions.services.payments import PaymentService
from subscriptions.services.subscriptions import SubscriptionService
from subscriptions.utils import get_active_subscription


class MySubscriptionListView(generics.ListAPIView):
    """
    School user — list the school's subscriptions.

    """

    permission_classes = (IsAuthenticated,)
    serializer_class = SubscriptionListSerializer
    filterset_class = MySubscriptionFilter
    search_fields = ("plan__name", "plan__code")
    ordering_fields = ("start_date", "end_date", "created_at", "plan__name")
    ordering = ("-start_date",)

    def get_queryset(self):
        school = self.request.user.school
        if school is None:
            return Subscription.objects.none()
        return (
            school.subscriptions
            .select_related("plan", "term", "activated_by")
            .prefetch_related("payments")
        )


class CurrentSubscriptionView(APIView):
    """School user — returns the school's current subscription status."""

    permission_classes = (IsAuthenticated,)

    def get(self, request):
        school = request.user.school
        if school is None:
            return ApiResponse.error(message="No school associated with this account.", status_code=404)

        subscription = SubscriptionService.get_current(school)
        if not subscription:
            return ApiResponse.error(message="No subscription found.", status_code=404)

        return ApiResponse.success(data=SubscriptionSerializer(subscription).data)


class InitiatePaymentView(APIView):
    """
    School admin — start a payment with a gateway.

    Creates a pending payment intent and returns the ``payment_url`` (real
    gateways) or a ``reference`` (simulated in development) for the frontend
    to complete via :class:`SchoolSubscribeView`.
    """

    permission_classes = (IsAdmin,)

    def post(self, request):
        school = request.user.school
        serializer = InitiatePaymentSerializer(
            data=request.data, context={"school": school}
        )
        serializer.is_valid(raise_exception=True)

        plan = serializer.validated_data["plan"]
        term = serializer.validated_data.get("term")
        provider = serializer.validated_data.get("provider") or "simulate"
        include_setup_fee = serializer.validated_data.get("include_setup_fee", False)

        # Abandon any previously initiated, uncompleted intents for the school.
        SubscriptionPayment.objects.filter(
            school=school,
            status=SubscriptionPayment.PaymentStatus.PENDING,
        ).update(status=SubscriptionPayment.PaymentStatus.FAILED)

        try:
            result, payment = PaymentService.initiate(
                school=school,
                user=request.user,
                plan=plan,
                term=term,
                provider=provider,
                include_setup_fee=include_setup_fee,
                coupon_code=serializer.validated_data.get("coupon_code"),
            )
        except serializers.ValidationError as exc:
            return ApiResponse.error(
                message=exc.detail[0] if isinstance(exc.detail, list) else str(exc.detail),
                status_code=400,
            )

        return ApiResponse.success(
            data={
                "payment_id": str(payment.id),
                "payment_url": result.payment_url,
                "reference": result.reference,
                "provider": result.provider,
                "amount": str(payment.amount),
                "currency": payment.currency,
                "plan": plan.name,
            },
            message="Payment initiated. Redirect the user to payment_url.",
        )


class SchoolSubscribeView(APIView):
    """
    School admin — subscribe to a package.

    - New / never-paid schools get a free trial (no payment needed).
    - Everyone else completes a paid subscription using the ``payment_reference``
      from :class:`InitiatePaymentView` (verified against the gateway).
    """

    permission_classes = (IsAdmin,)
    @transaction.atomic
    def post(self, request):
        school = request.user.school
        if school is None:
            return ApiResponse.error(
                message="No school associated with this account.",
                status_code=404,
            )

        serializer = SchoolSubscribeSerializer(
            data=request.data, context={"school": school, "request": request}
        )
        serializer.is_valid(raise_exception=True)

        try:
            school_subscription = SubscriptionService.subscribe_school(data=serializer, school=school)
        except ValueError as e:
            return ApiResponse.error(
                message=str(e),
                status_code=400,
            )
        except PaymentGatewayError as e:
            return ApiResponse.error(
                message=str(e),
                status_code=400,
            )
        except Exception as e:
            return ApiResponse.error(
                message=str(e),
                status_code=500,
            )

        if school_subscription.created:
            message = f"Successfully subscribed to the {school_subscription.subscription.plan.name} package."
        else:
            message = f"Failed to subscribe to the {school_subscription.subscription.plan.name} package."

        log_action(
            action=AuditLog.Action.CREATE,
            resource="Subscription",
            resource_id=str(school_subscription.subscription.pk),
            description=(
                f"{school.name} subscribed to {school_subscription.subscription.plan.name} "
                f"({school_subscription.subscription.status})"
            ),
            request=request,
        )

        check_and_complete_onboarding(school)

        return ApiResponse.created(
            data=SubscriptionSerializer(school_subscription.subscription).data,
            message=message,
        )

    def _complete_paid_subscription(self, school, plan, term, payment_reference,
                                    payment_provider, user):
        payment = (
            SubscriptionPayment.objects
            .filter(school=school, plan=plan, payment_reference=payment_reference)
            .order_by("-created_at")
            .first()
        )

        if payment is None:
            payment = SubscriptionPayment.objects.create(
                school=school,
                plan=plan,
                term=term,
                amount=plan.price,
                currency=plan.currency,
                payment_reference=payment_reference,
                provider=payment_provider,
                payment_mode=SubscriptionPayment.PaymentMode.VIRTUAL,
                status=SubscriptionPayment.PaymentStatus.PENDING,
                recorded_by=user,
            )
        else:
            payment_provider = payment.provider or payment_provider

        fully_discounted = payment.coupon_id is not None and payment.amount == 0
        if not fully_discounted:
            result = PaymentService.verify(
                reference=payment_reference,
                provider=payment_provider,
                amount=payment.amount,
            )
            if not result.success:
                payment.status = SubscriptionPayment.PaymentStatus.FAILED
                payment.save(update_fields=["status", "updated_at"])
                raise serializers.ValidationError(
                    {"payment_reference": result.message or "Payment could not be verified."}
                )

        activation = SubscriptionService.complete_payment(
            school=school,
            plan=plan,
            term=term,
            payment=payment,
            activated_by=user,
        )
        return activation.subscription


class PaymentWebhookView(APIView):
    """
    Receives webhook callbacks from Paystack/Stripe.

    Signature verification lives in the provider. When the reference matches a
    pending :class:`SubscriptionPayment`, the matching subscription is
    activated automatically; otherwise the callback is acknowledged only.
    """

    permission_classes = (AllowAny,)  # webhooks come from providers, not users

    def post(self, request, provider):
        raw_body = getattr(request, "body", b"") or b"{}"
        try:
            payload = json.loads(raw_body)
        except (ValueError, TypeError):
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        payload["_raw_body"] = raw_body

        provider_service = get_payment_provider(provider)
        result = provider_service.verify_webhook(payload, request.headers)

        if not result.success:
            return ApiResponse.error(
                message=result.message or "Webhook verification failed.",
                status_code=400,
            )

        activated_id = None
        if result.reference:
            activated_id = self._activate_matched_payment(result, provider)

        return ApiResponse.success(
            data={
                "reference": result.reference,
                "status": result.status,
                "provider": result.provider,
                "subscription_id": activated_id,
            },
            message=result.message or "Webhook received.",
        )

    def _activate_matched_payment(self, result, provider):
        payment = (
            SubscriptionPayment.objects
            .filter(payment_reference=result.reference)
            .select_related("school", "plan", "term")
            .order_by("-created_at")
            .first()
        )
        if payment is None or payment.subscription_id:
            return str(payment.subscription_id) if payment else None

        if result.status not in ("success", "paid"):
            payment.status = SubscriptionPayment.PaymentStatus.FAILED
            payment.save(update_fields=["status", "updated_at"])
            return None

        try:
            activation = SubscriptionService.complete_payment(
                school=payment.school,
                plan=payment.plan,
                term=payment.term,
                payment=payment,
                activated_by=None,
            )
        except Exception:  # noqa: BLE001 — never turn a transient error into a 50x to the gateway
            return None

        return str(activation.subscription.pk)