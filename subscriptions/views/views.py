from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework import generics
from core.mixins import AuditLogMixin

from core.responses import ApiResponse
from core.cache import CacheKeys
from schools.utils import check_and_complete_onboarding
from subscriptions.models import Plan, Subscription

from django.utils import timezone
from django.core.cache import cache
from datetime import timedelta

from core.permissions import IsAdmin
from core.models import AuditLog
from core.utils import log_action


from ..serializers import (
    PlanSerializer, SubscribeToPlanSerializer, SubscriptionSerializer,
    ManualActivationSerializer, InitiatePaymentSerializer,
)
from ..utils import get_active_subscription


class PlanListView(APIView):
    """Public — list all available plans (for signup/upgrade pages)."""
    permission_classes = [AllowAny]

    def get(self, request):
        cached = cache.get(CacheKeys.PLAN_LIST)
        if cached is not None:
            return ApiResponse.success(data=cached)

        plans = Plan.objects.filter(is_active=True)
        data = PlanSerializer(plans, many=True).data
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
    """
    permission_classes = [IsAdmin]

    def post(self, request):
        serializer = InitiatePaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        plan = Plan.objects.get(id=serializer.validated_data["plan_id"])
        billing_cycle = serializer.validated_data["billing_cycle"]
        provider = serializer.validated_data["provider"]

        amount = (
            plan.annual_price
            if billing_cycle == "annual"
            else plan.monthly_price
        )

        # Build metadata to pass to the provider
        metadata = {
            "school_id": str(request.user.school.id),
            "plan_id": str(plan.id),
            "billing_cycle": billing_cycle,
        }

        if provider == "paystack":
            payment_url = self._initiate_paystack(
                request.user.email, amount, metadata
            )
        else:
            payment_url = self._initiate_stripe(
                request.user.email, amount, metadata
            )

        return ApiResponse.success(
            data={"payment_url": payment_url, "amount": amount, "plan": plan.name},
            message="Payment initiated. Redirect user to payment_url.",
        )

    def _initiate_paystack(self, email, amount, metadata):
        # Paystack integration goes here
        # Returns the authorization_url from Paystack's API
        # We'll build this out when wiring payment providers
        return "https://paystack.com/pay/placeholder"

    def _initiate_stripe(self, email, amount, metadata):
        # Stripe integration goes here
        return "https://stripe.com/pay/placeholder"


class PaymentWebhookView(APIView):
    """
    Receives webhook callbacks from Paystack/Stripe after payment.
    Activates the subscription on successful payment.
    """
    permission_classes = [AllowAny]  # webhooks come from providers, not users

    def post(self, request, provider):
        if provider == "paystack":
            return self._handle_paystack(request)
        elif provider == "stripe":
            return self._handle_stripe(request)
        return ApiResponse.error(message="Unknown provider.", status_code=400)

    def _handle_paystack(self, request):
        # 1. Verify webhook signature
        # 2. Extract metadata (school_id, plan_id, billing_cycle)
        # 3. Activate subscription
        # Full implementation when wiring Paystack
        return ApiResponse.success(message="Webhook received.")

    def _handle_stripe(self, request):
        # Full implementation when wiring Stripe
        return ApiResponse.success(message="Webhook received.")

class PlanFeaturesView(APIView):
    """
    Public endpoint — returns all active plans with features
    grouped by category for easy frontend rendering.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        cached = cache.get(CacheKeys.PLAN_FEATURES)
        if cached is not None:
            return ApiResponse.success(data=cached)

        plans = Plan.objects.filter(is_active=True).order_by("price_per_term")

        data = {
            "plans": [self._format_plan(plan) for plan in plans],
            "feature_categories": self._get_feature_categories(),
        }
        cache.set(CacheKeys.PLAN_FEATURES, data, timeout=60 * 60)
        return ApiResponse.success(data=data)

    def _format_plan(self, plan):
        return {
            "id": str(plan.id),
            "name": plan.name,
            "plan_type": plan.plan_type,
            "tagline": plan.tagline,
            "description": plan.description,
            "pricing": {
                "per_term": float(plan.price_per_term),
                "setup_fee": float(plan.setup_fee),
                "currency": "GHS",
                "billing_cycle": "per term",
            },
            "limits": {
                "min_students": plan.min_students,
                "max_students": plan.max_students,
                "student_range": self._student_range(plan),
            },
            "features": self._get_plan_features(plan),
            "is_popular": plan.plan_type == "advantage",
        }

    def _get_plan_features(self, plan):
        """
        Returns features grouped by category.
        Each feature has a label, included flag, and display hint.
        """
        return {
            "core": [
                {
                    "key": "has_student_records",
                    "label": "Student Registration & Digital Records",
                    "included": plan.has_student_records,
                },
                {
                    "key": "has_class_subject_setup",
                    "label": "Class, Subjects & Timetable Setup",
                    "included": plan.has_class_subject_setup,
                },
                {
                    "key": "has_score_entry",
                    "label": "Score Entry & Automated Report Cards",
                    "included": plan.has_score_entry,
                },
                {
                    "key": "has_basic_broadsheet",
                    "label": "Basic Broadsheet Generation",
                    "included": plan.has_basic_broadsheet,
                },
                {
                    "key": "has_fee_billing",
                    "label": "Fee Billing, Payment Tracking & Receipts",
                    "included": plan.has_fee_billing,
                },
                {
                    "key": "has_debtors_list",
                    "label": "Debtors List & Basic Finance Summary",
                    "included": plan.has_debtors_list,
                },
                {
                    "key": "has_sms_alerts",
                    "label": "SMS Alerts (Attendance & Fee Reminders)",
                    "included": plan.has_sms_alerts,
                },
                {
                    "key": "has_admin_teacher_portal",
                    "label": "Admin & Teacher Portal Access",
                    "included": plan.has_admin_teacher_portal,
                },
            ],
            "finance_analytics": [
                {
                    "key": "has_advanced_finance",
                    "label": "Advanced Finance Dashboard & Analytics",
                    "included": plan.has_advanced_finance,
                },
                {
                    "key": "has_income_expense_tracking",
                    "label": "Income, Expense & Revenue Tracking",
                    "included": plan.has_income_expense_tracking,
                },
                {
                    "key": "has_full_broadsheet",
                    "label": "Full Broadsheet & Performance Trends",
                    "included": plan.has_full_broadsheet,
                },
                {
                    "key": "has_term_comparison",
                    "label": "Term-to-Term Academic Comparison",
                    "included": plan.has_term_comparison,
                },
                {
                    "key": "has_export",
                    "label": "Branded Report Exports & Financial Reports",
                    "included": plan.has_export,
                },
            ],
            "access_communication": [
                {
                    "key": "has_audit_logs",
                    "label": "Role-Based Access & Activity Logs",
                    "included": plan.has_audit_logs,
                },
                {
                    "key": "has_announcements",
                    "label": "Announcement Broadcast",
                    "included": plan.has_announcements,
                },
                {
                    "key": "has_extended_sms",
                    "label": "Extended SMS Alerts",
                    "included": plan.has_extended_sms,
                },
                {
                    "key": "has_student_portal",
                    "label": "Student Portal Access (Results & Timetable)",
                    "included": plan.has_student_portal,
                },
            ],
            "enterprise": [
                {
                    "key": "has_advanced_analytics",
                    "label": "Advanced Institutional Analytics Dashboard",
                    "included": plan.has_advanced_analytics,
                },
                {
                    "key": "has_multi_year_tracking",
                    "label": "Multi-Year Academic & Financial Tracking",
                    "included": plan.has_multi_year_tracking,
                },
                {
                    "key": "has_department_access_control",
                    "label": "Hierarchical Admin & Department-Level Access",
                    "included": plan.has_department_access_control,
                },
                {
                    "key": "has_custom_report_cards",
                    "label": "Fully Customized Report Card Design",
                    "included": plan.has_custom_report_cards,
                },
                {
                    "key": "has_custom_branding",
                    "label": "School Branding Across the System",
                    "included": plan.has_custom_branding,
                },
                {
                    "key": "has_data_migration",
                    "label": "Data Migration & Dedicated Onboarding",
                    "included": plan.has_data_migration,
                },
                {
                    "key": "has_priority_support",
                    "label": "Priority SLA Support & Operational Reviews",
                    "included": plan.has_priority_support,
                },
            ],
        }

    def _get_feature_categories(self):
        """
        Returns category metadata so the frontend can render
        section headers without hardcoding them.
        """
        return [
            {
                "key": "core",
                "label": "Core Features",
                "description": "Available on all plans",
            },
            {
                "key": "finance_analytics",
                "label": "Finance & Analytics",
                "description": "Advanced reporting and financial tools",
            },
            {
                "key": "access_communication",
                "label": "Access & Communication",
                "description": "Portals, announcements and extended SMS",
            },
            {
                "key": "enterprise",
                "label": "Enterprise",
                "description": "For large institutions needing full control",
            },
        ]

    @staticmethod
    def _student_range(plan):
        if plan.max_students is None:
            return f"{plan.min_students}+ Students"
        return f"{plan.min_students}–{plan.max_students} Students"


class SubscribeToPlanView(APIView):
    """
    School admin — subscribe to a plan.

    Logic:
        - If school has no existing subscription at all
          → create a trial subscription for the current term
        - If school already has an active/trial subscription
          → upgrade/switch plan (requires payment reference)
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

        plan = serializer.validated_data["plan"]
        term = serializer.validated_data.get("term")
        payment_reference = serializer.validated_data.get("payment_reference", "")
        payment_provider = serializer.validated_data.get("payment_provider", "")

        existing = self._get_latest_subscription(school)
        is_new_school = existing is None

        if is_new_school or self._is_eligible_for_trial(existing):
            subscription = self._create_trial(
                school=school,
                plan=plan,
                term=term,
            )
            message = (
                f"Trial subscription started on the {plan.name} plan. "
                f"You have {subscription.days_remaining} days remaining."
            )
        else:
            if not payment_reference:
                return ApiResponse.error(
                    message=(
                        "A payment reference is required to subscribe or "
                        "switch plans. Please complete payment first."
                    ),
                    status_code=400,
                )
            subscription = self._activate(
                school=school,
                plan=plan,
                term=term,
                payment_reference=payment_reference,
                payment_provider=payment_provider,
                activated_by=request.user,
                amount_paid=serializer.validated_data.get("amount_paid"),
            )
            message = (
                f"Successfully subscribed to the {plan.name} plan."
            )

        log_action(
            action=AuditLog.Action.CREATE,
            resource="Subscription",
            resource_id=str(subscription.pk),
            description=f"{school.name} subscribed to {plan.name} ({subscription.status})",
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
        # otherwise falls back to 14 days
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
            payment_provider="trial",
            setup_fee_paid=False,
        )

    @staticmethod
    def _activate(
        school,
        plan,
        term=None,
        payment_reference="",
        payment_provider="",
        activated_by=None,
        amount_paid=None,
    ):
        from subscriptions.utils import activate_subscription
        return activate_subscription(
            school=school,
            plan=plan,
            term=term,
            activated_by=activated_by,
            payment_reference=payment_reference,
            payment_provider=payment_provider,
            amount_paid=amount_paid or plan.price_per_term,
            setup_fee_paid=bool(payment_reference),
        )


def invalidate_plan_cache(**kwargs):
    cache.delete_many([CacheKeys.PLAN_LIST, CacheKeys.PLAN_FEATURES])