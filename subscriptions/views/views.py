from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework import generics
import json

from core.responses import ApiResponse
from core.cache import CacheKeys
from schools.utils import check_and_complete_onboarding
from subscriptions.models import Package, Subscription

from django.core.cache import cache

from core.permissions import IsAdmin
from core.models import AuditLog
from core.utils import log_action

from subscriptions.services.packages import package_feature_details, package_limit_details
from integrations.registry import get_payment_provider

from ..serializers import (
    PackageSerializer, SubscribeToPlanSerializer, SubscriptionSerializer,
    InitiatePaymentSerializer,
)
from ..utils import get_active_subscription


class PackageListView(generics.ListAPIView):
    """Public — list all active, public packages (for signup pages)."""
    permission_classes = [AllowAny]
    serializer_class = PackageSerializer

    def get_queryset(self):
        return (
            Package.objects
            .filter(is_active=True, is_public=True)
            .order_by("display_order", "price")
        )

    def list(self, request, *args, **kwargs):
        cached = cache.get(CacheKeys.PLAN_LIST)
        if cached is not None:
            return ApiResponse.success(data=cached)

        queryset = self.get_queryset()
        data = self.get_serializer(queryset, many=True).data
        cache.set(CacheKeys.PLAN_LIST, data, timeout=60 * 60)
        return ApiResponse.success(data=data)


class CurrentSubscriptionView(APIView):
    """Returns the current school's subscription status."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        subscription = get_active_subscription(request.user.school)
        if not subscription:
            return ApiResponse.error(
                message="No subscription found.", status_code=404
            )
        return ApiResponse.success(data=SubscriptionSerializer(subscription).data)


class InitiatePaymentView(APIView):
    """
    Initiates a payment with an external provider.
    Returns a payment URL for the frontend to redirect to.

    In development (INTEGRATION_MODE=simulate) the simulated provider
    prints the transaction to the console and returns a reference.
    In production the real Paystack/Stripe/MoMo provider is used.
    """
    permission_classes = [IsAdmin]

    def post(self, request):
        serializer = InitiatePaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        package = Package.objects.get(
            id=serializer.validated_data["plan_id"],
            is_active=True,
        )
        provider_name = serializer.validated_data["provider"]

        amount = float(package.price)
        if serializer.validated_data.get("include_setup_fee"):
            amount += float(package.setup_fee)

        # Build metadata to pass to the provider
        metadata = {
            "school_id": str(request.user.school.id),
            "plan_id": str(package.id),
        }

        provider_service = get_payment_provider(provider_name)
        result = provider_service.initiate(
            email=request.user.email,
            amount=amount,
            currency=package.currency,
            metadata=metadata,
        )

        if not result.success:
            return ApiResponse.error(
                message=f"Payment could not be initiated. {result.message}",
                status_code=400,
            )

        return ApiResponse.success(
            data={
                "payment_url": result.payment_url,
                "reference": result.reference,
                "provider": result.provider,
                "amount": result.amount or amount,
                "currency": result.currency or package.currency,
                "plan": package.name,
            },
            message="Payment initiated. Redirect user to payment_url.",
        )


class PaymentWebhookView(APIView):
    """
    Receives webhook callbacks from Paystack/Stripe after payment.

    The webhook handler reuses the same provider abstraction so the
    signature verification / event parsing lives in one place per provider.
    The actual subscription activation happens in SubscribeToPlanView
    (called by the frontend after payment confirmation).
    """
    permission_classes = [AllowAny]  # webhooks come from providers, not users

    def post(self, request, provider):
        # Read the raw body BEFORE touching request.data (parsing the JSON
        # consumes the stream and would make request.body inaccessible).
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
        return ApiResponse.success(
            data={
                "reference": result.reference,
                "status": result.status,
                "provider": result.provider,
            },
            message=result.message or "Webhook received.",
        )


class PackageFeaturesView(APIView):
    """
    Public endpoint — returns all active packages with entitlements
    grouped by feature category for easy frontend rendering.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        cached = cache.get(CacheKeys.PLAN_FEATURES)
        if cached is not None:
            return ApiResponse.success(data=cached)

        packages = Package.objects.filter(
            is_active=True, is_public=True
        ).order_by("display_order", "price")

        data = {
            "packages": [self._format_package(package) for package in packages],
            "feature_categories": self._get_feature_categories(),
        }
        cache.set(CacheKeys.PLAN_FEATURES, data, timeout=60 * 60)
        return ApiResponse.success(data=data)

    def _format_package(self, package):
        features = package_feature_details(package)
        enabled_codes = {f["code"] for f in features if f["enabled"]}
        return {
            "id": str(package.id),
            "name": package.name,
            "code": package.code,
            "plan_type": package.plan_type,
            "tagline": package.tagline,
            "description": package.description,
            "pricing": {
                "price": float(package.price),
                "setup_fee": float(package.setup_fee),
                "currency": package.currency,
                "billing_period": package.billing_period,
            },
            "limits": {
                "minimum_students": package.minimum_students,
                "maximum_students": package.maximum_students,
                "student_range": self._student_range(package),
                "package_limits": package_limit_details(package),
            },
            "features": features,
            "is_popular": package.code == "advantage",
        }

    def _get_feature_categories(self):
        """
        Returns category metadata so the frontend can render
        section headers without hardcoding them.
        """
        from subscriptions.models import Feature
        categories = (
            Feature.objects
            .filter(is_active=True)
            .exclude(category="")
            .order_by("category")
            .values_list("category", flat=True)
            .distinct()
        )
        return [
            {
                "key": category,
                "label": category.replace("_", " ").title(),
            }
            for category in categories
        ]

    @staticmethod
    def _student_range(package):
        if package.maximum_students is None:
            return f"{package.minimum_students}+ Students"
        return f"{package.minimum_students}–{package.maximum_students} Students"


class SubscribeMySchool(APIView):
    def post(self, request):
        # This is a placeholder endpoint for the frontend to call when
        # subscribing. The actual subscription logic is handled in
        # SubscribeToPlanView which is called after payment confirmation.
        return ApiResponse.success(message="Subscription endpoint placeholder.")


class SubscribeToPlanView(APIView):
    """
    School admin — subscribe to a package.

    Logic:
        - If school has no existing subscription at all
          → create a trial subscription for the current term
        - If school already has an active/trial subscription
          → upgrade/switch package (requires payment reference)
        - If school is in grace or locked
          → reactivate with payment reference
    """
    permission_classes = [IsAdmin]

    def post(self, request):
        school = request.user.school

        if not school:
            return ApiResponse.error(
                message="No school associated with this account.",
                status_code=404,
            )

        serializer = SubscribeToPlanSerializer(
            data=request.data,
            context={"school": school, "request": request},
        )
        serializer.is_valid(raise_exception=True)

        package = serializer.validated_data["plan"]
        term = serializer.validated_data.get("term")
        payment_reference = serializer.validated_data.get("payment_reference", "")
        payment_provider = serializer.validated_data.get("payment_provider", "")

        existing = self._get_latest_subscription(school)
        is_new_school = existing is None

        if is_new_school or self._is_eligible_for_trial(existing):
            subscription = self._create_trial(
                school=school,
                plan=package,
                term=term,
            )
            message = (
                f"Trial subscription started on the {package.name} package. "
                f"You have {subscription.days_remaining} days remaining."
            )
        else:
            if not payment_reference:
                return ApiResponse.error(
                    message=(
                        "A payment reference is required to subscribe or "
                        "switch packages. Please complete payment first."
                    ),
                    status_code=400,
                )
            subscription = self._activate(
                school=school,
                plan=package,
                term=term,
                payment_reference=payment_reference,
                payment_provider=payment_provider,
                activated_by=request.user,
            )
            message = (
                f"Successfully subscribed to the {package.name} package."
            )

        log_action(
            action=AuditLog.Action.CREATE,
            resource="Subscription",
            resource_id=str(subscription.pk),
            description=f"{school.name} subscribed to {package.name} ({subscription.status})",
            request=request,
        )

        check_and_complete_onboarding(self.request.user.school)

        return ApiResponse.created(
            data=SubscriptionSerializer(subscription).data,
            message=message,
        )

    # ─── Helpers ─────────────────────────────────────────────────

    @staticmethod
    def _get_latest_subscription(school):
        return (
            school.subscriptions
            .select_related("plan")
            .order_by("-start_date")
            .first()
        )

    @staticmethod
    def _is_eligible_for_trial(subscription):
        """
        A school is eligible for a trial only if it has never
        had a real (non-trial) subscription before.
        """
        from subscriptions.models import Subscription
        ever_had_paid = (
            Subscription.objects
            .filter(
                school=subscription.school,
                status__in=[
                    Subscription.Status.ACTIVE,
                    Subscription.Status.EXPIRED,
                    Subscription.Status.GRACE,
                    Subscription.Status.LOCKED,
                ]
            )
            .exists()
        )
        return not ever_had_paid

    @staticmethod
    def _get_current_term(school):
        """
        Returns the current active term for the school.
        Returns None if no current term is set.
        """
        from academics.models import Term
        return Term.objects.filter(
            school=school,
            is_current=True,
        ).first()

    def _create_trial(self, school, plan, term=None):
        from subscriptions.models import Subscription
        from django.utils import timezone
        from datetime import timedelta

        # Use provided term or fall back to current active term
        resolved_term = term or self._get_current_term(school)

        # Trial ends at term end date if available,
        # otherwise falls back to 90 days
        if resolved_term:
            end_date = timezone.make_aware(
                timezone.datetime.combine(
                    resolved_term.end_date,
                    timezone.datetime.min.time(),
                )
            )
        else:
            end_date = timezone.now() + timedelta(
                days=Subscription.TRIAL_DAYS
            )

        # Cancel any previous trial if somehow exists
        school.subscriptions.filter(
            status=Subscription.Status.TRIAL
        ).update(status=Subscription.Status.CANCELLED)

        return Subscription.objects.create(
            school=school,
            plan=plan,
            term=resolved_term,
            status=Subscription.Status.TRIAL,
            start_date=timezone.now(),
            end_date=end_date,
            is_paid=False,
        )

    @staticmethod
    def _activate(
        school,
        plan,
        term=None,
        payment_reference="",
        payment_provider="",
        activated_by=None,
    ):
        from subscriptions.utils import activate_subscription
        return activate_subscription(
            school=school,
            plan=plan,
            term=term,
            activated_by=activated_by,
            payment_reference=payment_reference,
            payment_provider=payment_provider,
            is_paid=bool(payment_reference),
        )