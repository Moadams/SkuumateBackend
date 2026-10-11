"""Superadministrator subscription views — cross-school management."""
from rest_framework import generics, serializers
from rest_framework.views import APIView

from core.models import AuditLog
from core.responses import ApiResponse
from core.utils import log_action
from schools.utils import check_and_complete_onboarding
from subscriptions.filters import (
    SubscriptionFilter,
    SubscriptionPaymentFilter,
)
from subscriptions.models import Subscription, SubscriptionPayment
from subscriptions.permissions import IsPlatformSuperAdmin
from subscriptions.serializers import (
    AdminSubscriptionPaymentSerializer,
    AdminSubscriptionSerializer,
    AdminSubscribeSerializer,
)
from subscriptions.services.payments import PaymentService
from subscriptions.services.subscriptions import SubscriptionService


class AdminSubscriptionListView(generics.ListAPIView):
    """
    Super administrator — all schools' subscriptions.

    Filters: ``school``, ``school_name``, ``school_code``, ``plan``,
    ``plan_code``, ``status``, ``is_paid``, ``is_current``, ``term``,
    ``start_date_from/to``, ``end_date_from/to``, ``created_from/to``.
    """

    permission_classes = [IsPlatformSuperAdmin]
    serializer_class = AdminSubscriptionSerializer
    filterset_class = SubscriptionFilter
    search_fields = ["school__name", "school__school_code", "plan__name", "plan__code"]
    ordering_fields = ["start_date", "end_date", "created_at"]
    ordering = ["-start_date"]

    def get_queryset(self):
        return (
            Subscription.objects
            .select_related("school", "plan", "term", "activated_by")
            .prefetch_related("payments")
        )


class AdminSubscriptionDetailView(generics.RetrieveAPIView):
    """Super administrator — retrieve a single school subscription."""

    permission_classes = [IsPlatformSuperAdmin]
    serializer_class = AdminSubscriptionSerializer

    def get_queryset(self):
        return (
            Subscription.objects
            .select_related("school", "plan", "term", "activated_by")
            .prefetch_related("payments")
        )

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        return ApiResponse.success(data=self.get_serializer(instance).data)


class AdminSubscribeView(APIView):
    """
    Super administrator — subscribe a school.

    A trial subscription needs no payment. A paid subscription requires a
    ``payment_mode`` of ``cash`` (offline receipt) or ``virtual`` (gateway
    charge with a verifiable ``payment_reference``).
    """

    permission_classes = [IsPlatformSuperAdmin]

    def post(self, request):
        serializer = AdminSubscribeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        school = data["school"]
        plan = data["plan"]
        term = data.get("term")
        status = data["status"]
        notes = data.get("notes", "")

        if status == Subscription.Status.ACTIVE:
            subscription = SubscriptionService.start_trial(
                school=school,
                plan=plan,
                term=term,
                activated_by=request.user,
            )
            message = (
                f"Free trial started for {school.name} on the {plan.name} package."
            )
        else:
            subscription = self._subscribe_paid(
                request=request,
                school=school,
                plan=plan,
                term=term,
                data=data,
            )
            message = (
                f"Subscribed {school.name} to the {plan.name} package "
                f"({data['payment_mode']} payment)."
            )

        log_action(
            action=AuditLog.Action.CREATE,
            resource="Subscription",
            resource_id=str(subscription.pk),
            description=(
                f"{request.user.first_name} {request.user.last_name} subscribed "
                f"{school.name} to {plan.name} ({subscription.status})"
            ),
            metadata={"payment_mode": data.get("payment_mode")},
            request=request,
        )

        check_and_complete_onboarding(school)

        return ApiResponse.created(
            data=AdminSubscriptionSerializer(subscription).data,
            message=message,
        )

    def _subscribe_paid(self, request, school, plan, term, data):
        payment_mode = data["payment_mode"]
        reference = data.get("payment_reference") or ""
        provider = data.get("payment_provider") or "cash"

        if payment_mode == SubscriptionPayment.PaymentMode.VIRTUAL:
            result = PaymentService.verify(
                reference=reference,
                provider=provider,
                amount=plan.price,
            )
            if not result.success:
                raise serializers.ValidationError(
                    {
                        "payment_reference": (
                            result.message or "Payment could not be verified."
                        )
                    }
                )

        subscription = SubscriptionService.activate(
            school=school,
            plan=plan,
            term=term,
            activated_by=request.user,
            is_paid=True,
            notes=data.get("notes", ""),
        )

        PaymentService.record_successful_payment(
            subscription=subscription,
            school=school,
            plan=plan,
            term=term,
            amount=plan.price,
            provider=provider,
            reference=reference,
            payment_mode=payment_mode,
            recorded_by=request.user,
        )

        return subscription


class AdminPaymentListView(generics.ListAPIView):
    """
    Super administrator — all subscription payments.

    Filters: ``school``, ``school_name``, ``subscription``, ``plan``, ``status``,
    ``payment_mode``, ``provider``, ``min_amount``, ``max_amount``,
    ``created_from/to``.
    """

    permission_classes = [IsPlatformSuperAdmin]
    serializer_class = AdminSubscriptionPaymentSerializer
    filterset_class = SubscriptionPaymentFilter
    search_fields = ["payment_reference", "provider", "school__name"]
    ordering_fields = ["created_at", "amount"]
    ordering = ["-created_at"]

    def get_queryset(self):
        return SubscriptionPayment.objects.select_related("school", "plan", "subscription")