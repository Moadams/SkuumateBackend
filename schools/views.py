from django.db import transaction
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from core.responses import ApiResponse
from core.permissions import IsAdmin, IsSuperAdmin

from .models import School
from .serializers import SchoolSerializer, SchoolCreateSerializer

from django.db.models import Count, Sum, Q
from django.db.models.functions import TruncMonth
from django.utils import timezone
from datetime import timedelta
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from core.responses import ApiResponse


class SuperadminDashboardView(APIView):
    """
    Superadmin-only platform overview dashboard.
    Returns all metrics needed for the platform overview page.
    """
    permission_classes = [IsSuperAdmin]

    def get(self, request):

        return ApiResponse.success(
            data={
                "stats": self._get_stats(),
                "revenue_analytics": self._get_revenue_analytics(),
                "recent_onboarding": self._get_recent_onboarding(),
                "subscription_distribution": self._get_subscription_distribution(),
            }
        )

    # ─── Private helpers ──────────────────────────────────────────

    def _get_stats(self):
        from schools.models import School
        from accounts.models import User
        from subscriptions.models import Subscription

        now = timezone.now()
        last_month_start = (now.replace(day=1) - timedelta(days=1)).replace(day=1)
        this_month_start = now.replace(day=1)

        # ── School counts ─────────────────────────────────────────
        total_schools = School.objects.filter(is_active=True).count()
        schools_this_month = School.objects.filter(
            created_at__gte=this_month_start
        ).count()
        schools_last_month = School.objects.filter(
            created_at__gte=last_month_start,
            created_at__lt=this_month_start,
        ).count()

        # ── Active subscriptions ──────────────────────────────────
        active_subscriptions = Subscription.objects.filter(
            status__in=["active", "trial"]
        ).count()
        subscriptions_this_month = Subscription.objects.filter(
            status__in=["active", "trial"],
            created_at__gte=this_month_start,
        ).count()
        subscriptions_last_month = Subscription.objects.filter(
            status__in=["active", "trial"],
            created_at__gte=last_month_start,
            created_at__lt=this_month_start,
        ).count()

        # ── Revenue ───────────────────────────────────────────────
        revenue_this_month = Subscription.objects.filter(
            created_at__gte=this_month_start,
            status__in=["active", "trial"],
            amount_paid__isnull=False,
        ).aggregate(total=Sum("amount_paid"))["total"] or 0

        revenue_last_month = Subscription.objects.filter(
            created_at__gte=last_month_start,
            created_at__lt=this_month_start,
            status__in=["active", "trial"],
            amount_paid__isnull=False,
        ).aggregate(total=Sum("amount_paid"))["total"] or 0

        # ── Active users ──────────────────────────────────────────
        active_users = User.objects.filter(is_active=True).count()
        users_this_month = User.objects.filter(
            created_at__gte=this_month_start,
            is_active=True,
        ).count()
        users_last_month = User.objects.filter(
            created_at__gte=last_month_start,
            created_at__lt=this_month_start,
            is_active=True,
        ).count()

        return {
            "total_schools": {
                "value": total_schools,
                "change": self._percent_change(schools_last_month, schools_this_month),
                "is_positive": schools_this_month >= schools_last_month,
            },
            "active_subscriptions": {
                "value": active_subscriptions,
                "change": self._percent_change(
                    subscriptions_last_month, subscriptions_this_month
                ),
                "is_positive": subscriptions_this_month >= subscriptions_last_month,
            },
            "monthly_revenue": {
                "value": float(revenue_this_month),
                "currency": "GHS",
                "change": self._percent_change(revenue_last_month, revenue_this_month),
                "is_positive": revenue_this_month >= revenue_last_month,
            },
            "active_users": {
                "value": active_users,
                "change": self._percent_change(users_last_month, users_this_month),
                "is_positive": users_this_month >= users_last_month,
            },
        }

    def _get_revenue_analytics(self):
        """Monthly revenue aggregation for the last 6 months."""
        from subscriptions.models import Subscription

        six_months_ago = timezone.now() - timedelta(days=180)

        monthly_data = (
            Subscription.objects
            .filter(
                created_at__gte=six_months_ago,
                amount_paid__isnull=False,
                status__in=["active", "trial"],
            )
            .annotate(month=TruncMonth("created_at"))
            .values("month")
            .annotate(total_revenue=Sum("amount_paid"))
            .order_by("month")
        )

        return [
            {
                "month": entry["month"].strftime("%b").upper(),
                "month_full": entry["month"].strftime("%B %Y"),
                "total_revenue": float(entry["total_revenue"] or 0),
            }
            for entry in monthly_data
        ]

    def _get_recent_onboarding(self):
        """Last 10 schools onboarded with their subscription status."""
        from schools.models import School

        schools = (
            School.objects
            .select_related()
            .prefetch_related("subscriptions__plan")
            .order_by("-created_at")[:10]
        )

        result = []
        for school in schools:
            latest_sub = (
                school.subscriptions
                .order_by("-start_date")
                .first()
            )
            result.append({
                "id": str(school.id),
                "name": school.name,
                "city": school.city,
                "country": school.country,
                "email": school.email,
                "subscription_status": latest_sub.status if latest_sub else "none",
                "plan_name": latest_sub.plan.name if latest_sub else None,
                "registered": school.created_at,
            })

        return result

    def _get_subscription_distribution(self):
        """
        Breakdown of active subscriptions by plan type.
        Returns count and percentage per plan.
        """
        from subscriptions.models import Subscription

        total_active = Subscription.objects.filter(
            status__in=["active", "trial"]
        ).count()

        if total_active == 0:
            return []

        distribution = (
            Subscription.objects
            .filter(status__in=["active", "trial"])
            .values("plan__name", "plan__plan_type")
            .annotate(count=Count("id"))
            .order_by("-count")
        )

        return [
            {
                "plan_name": entry["plan__name"],
                "plan_type": entry["plan__plan_type"],
                "count": entry["count"],
                "percentage": round((entry["count"] / total_active) * 100, 1),
            }
            for entry in distribution
        ]

    @staticmethod
    def _percent_change(previous, current):
        """Returns a formatted percentage change string e.g. '+12.5%'."""
        if previous == 0:
            return "+100%" if current > 0 else "0%"
        change = ((current - previous) / previous) * 100
        sign = "+" if change >= 0 else ""
        return f"{sign}{change:.1f}%"


class SchoolOnboardView(APIView):
    """
    Public endpoint — creates a new school + first admin user.
    Called once during signup. No auth required.
    """
    permission_classes = [AllowAny]

    @transaction.atomic
    def post(self, request):
        serializer = SchoolCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        school = serializer.save()
        return ApiResponse.created(
            data=SchoolSerializer(school).data,
            message="School created successfully. You can now log in.",
        )


class SchoolDetailView(APIView):
    """
    Authenticated endpoint — retrieve or update the current user's school.
    Only admins can update.
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_object(self, request):
        return request.user.school

    def get(self, request):
        school = self.get_object(request)
        if not school:
            return ApiResponse.error(
                message="No school associated with this account.",
                status_code=404,
            )
        return ApiResponse.success(data=SchoolSerializer(school).data)

    def patch(self, request):
        if request.user.role != "admin":
            return ApiResponse.error(
                message="Only admins can update school details.",
                status_code=403,
            )
        school = self.get_object(request)
        serializer = SchoolSerializer(school, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return ApiResponse.success(
            data=serializer.data,
            message="School updated successfully.",
        )