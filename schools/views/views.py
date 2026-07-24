from django.core.cache import cache
from django.db import transaction
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from core.cache import CacheKeys
from core.mixins import AuditLogMixin, ExportMixin
from core.models import AuditLog
from core.permissions import IsAdmin, IsAdminOrReadOnly, IsSuperAdmin
from core.responses import ApiResponse
from schools.serializers.superadmin_serializers import SchoolCreateSerializer
from schools.utils import check_and_complete_onboarding

from ..filters import SchoolFilter
from ..models import School
from ..serializers.serializers import (
    MySchoolUpdateSerializer,
    SchoolListSerializer,
    SchoolProfileSerializer,
    SchoolSerializer,
)


class SchoolListExportView(ExportMixin, generics.ListAPIView):
    """Export all schools — full unpaginated list."""
    serializer_class = SchoolListSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = SchoolFilter
    search_fields = ["name", "email", "city", "country"]
    ordering = ["-created_at"]

    def get_queryset(self):
        if not self.request.user.is_superuser:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied(
                "Only superadmins can export the school list."
            )
        return School.objects.all().order_by("-created_at")

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        queryset = self.filter_queryset(self.get_queryset())
        school_ids = queryset.values_list("id", flat=True)

        from subscriptions.models import Subscription
        subscriptions = (
            Subscription.objects
            .filter(school_id__in=school_ids)
            .select_related("plan")
            .order_by("school_id", "-start_date")
            .distinct("school_id")
        )
        ctx["subscriptions"] = {
            str(sub.school_id): sub for sub in subscriptions
        }
        return ctx

    def get(self, request, *args, **kwargs):
        return self.export(request, *args, **kwargs)

class MySchoolRetrieveUpdateView(AuditLogMixin, generics.RetrieveUpdateAPIView):
    """Retrieve or update the current user's school."""
    permission_classes = [IsAdmin]
    serializer_class = SchoolSerializer

    audit_action = AuditLog.Action.UPDATE
    audit_resource = "School"

    def get_object(self):
        return self.request.user.school

    def get_audit_description(self, instance):
        return f"{self.request.user.full_name} updated school details for {instance.name}"

    def update(self, request, *args, **kwargs):
        serializer = MySchoolUpdateSerializer(
            self.get_object(), data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        cache.delete(CacheKeys.school_dashboard(str(request.user.school.id)))
        cache.delete(CacheKeys.school_onboarding(str(request.user.school.id)))
        return ApiResponse.success(data=serializer.data)


class SchoolProfileView(APIView):
    """
    Admin school profile — view and edit school details.
    """
    permission_classes = [IsAdminOrReadOnly]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request):
        school = request.user.school
        if not school:
            return ApiResponse.error(
                message="No school associated with this account.",
                status_code=404,
            )
        serializer = SchoolProfileSerializer(school, context={"request": request})
        return ApiResponse.success(data=serializer.data)

    def patch(self, request):
        school = request.user.school
        if not school:
            return ApiResponse.error(
                message="No school associated with this account.",
                status_code=404,
            )
        serializer = MySchoolUpdateSerializer(
            school, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        cache.delete(CacheKeys.school_dashboard(str(school.id)))
        cache.delete(CacheKeys.school_onboarding(str(school.id)))
        return ApiResponse.success(data=serializer.data)


class SchoolOnboardingStatusView(APIView):
    """
    Returns the current school's onboarding status
    and which steps have been completed.
    """
    permission_classes = [IsAdmin]

    def get(self, request):
        school = request.user.school
        if not school:
            return ApiResponse.error(
                message="No school associated with this account.",
                status_code=404,
            )

        cache_key = CacheKeys.school_onboarding(str(school.id))
        cached = cache.get(cache_key)
        if cached is not None:
            return ApiResponse.success(data=cached)

        check_and_complete_onboarding(school)

        steps = {
            "academic_year": school.academic_years.exists(),
            "term": school.terms.exists(),
            "class": school.classes.exists(),
            "subject": school.subjects.exists(),
            "subscription": school.subscriptions.filter(
                status__in=["active", "trial"]
            ).exists(),
        }

        data = {
            "onboarding_completed": school.onboarding_completed,
            "steps": steps,
            "completed_count": sum(steps.values()),
            "total_steps": len(steps),
        }
        cache.set(cache_key, data, timeout=60 * 2)
        return ApiResponse.success(data=data)


class AdminDashboardView(APIView):
    """
    School admin dashboard — returns all data needed
    for the admin dashboard page in one request.
    """
    permission_classes = [IsAdmin]

    def get(self, request):
        school = request.user.school

        if not school:
            return ApiResponse.error(
                message="No school associated with this account.",
                status_code=404,
            )

        cache_key = CacheKeys.school_dashboard(str(school.id))
        cached = cache.get(cache_key)
        if cached is not None:
            return ApiResponse.success(data=cached)

        data = {
            "stats": self._get_stats(school),
            "academic_overview": self._get_academic_overview(school),
            "recent_activity": self._get_recent_activity(school),
        }
        cache.set(cache_key, data, timeout=60 * 5)
        return ApiResponse.success(data=data)



    # ─── Stats ───────────────────────────────────────────────────

    def _get_stats(self, school):
        import datetime

        from django.utils import timezone

        from accounts.models import User
        from attendance.models import Attendance
        from students.models import Student
        from subscriptions.models import Subscription

        today = datetime.date.today()

        # ── Total students ────────────────────────────────────────
        total_students = Student.objects.filter(
            school=school, status="active"
        ).count()

        # Previous term student count for comparison
        # We use created_at on enrollments as a proxy
        prev_term_students = self._prev_term_student_count(school)

        # ── Daily attendance ──────────────────────────────────────
        try:
            from attendance.models import Attendance
            total_today = Attendance.objects.filter(
                school=school, date=today
            ).count()
            present_today = Attendance.objects.filter(
                school=school,
                date=today,
                status="present",
            ).count()
            attendance_pct = (
                round((present_today / total_today) * 100, 1)
                if total_today > 0 else 0
            )
            prev_attendance_pct = self._prev_term_attendance(school)
        except Exception:
            attendance_pct = 0
            prev_attendance_pct = 0

        # ── Term revenue ──────────────────────────────────────────
        term_revenue = self._get_term_revenue(school)
        prev_term_revenue = self._get_prev_term_revenue(school)

        # ── Active staff ──────────────────────────────────────────
        total_staff = User.objects.filter(
            school=school, is_active=True
        ).count()
        prev_term_staff = User.objects.filter(
            school=school,
            is_active=True,
            created_at__lt=self._current_term_start(school),
        ).count() if self._current_term_start(school) else total_staff

        return {
            "total_students": {
                "value": total_students,
                "change": self._percent_change(
                    prev_term_students, total_students
                ),
                "is_positive": total_students >= prev_term_students,
            },
            "daily_attendance": {
                "value": f"{attendance_pct}%",
                "change": self._percent_change(
                    prev_attendance_pct, attendance_pct
                ),
                "is_positive": attendance_pct >= prev_attendance_pct,
            },
            "term_revenue": {
                "value": float(term_revenue),
                "currency": "GHS",
                "formatted": self._format_currency(term_revenue),
                "change": self._percent_change(
                    prev_term_revenue, term_revenue
                ),
                "is_positive": term_revenue >= prev_term_revenue,
            },
            "active_staff": {
                "value": total_staff,
                "change": self._percent_change(prev_term_staff, total_staff),
                "is_positive": total_staff >= prev_term_staff,
            },
        }

    # ─── Academic Overview ────────────────────────────────────────

    def _get_academic_overview(self, school):
        import datetime

        from academics.models import AcademicYear, Term

        today = datetime.date.today()

        # Current academic year
        current_year = AcademicYear.objects.filter(
            school=school, is_current=True
        ).first()

        # Current term
        current_term = Term.objects.filter(
            school=school, is_current=True
        ).first()

        if not current_year or not current_term:
            return {
                "has_data": False,
                "message": "No active academic year or term configured.",
            }

        # ── Term progress ─────────────────────────────────────────
        term_start = current_term.start_date
        term_end = current_term.end_date
        total_days = (term_end - term_start).days or 1
        elapsed_days = max(0, (today - term_start).days)
        term_progress_pct = min(
            100, round((elapsed_days / total_days) * 100)
        )

        # ── Week calculation ──────────────────────────────────────
        current_week = min(
            (elapsed_days // 7) + 1,
            total_days // 7,
        )
        total_weeks = total_days // 7

        # ── Days until term ends ──────────────────────────────────
        days_until_end = max(0, (term_end - today).days)

        return {
            "has_data": True,
            "academic_year": {
                "id": str(current_year.id),
                "name": current_year.name,
                "start_date": current_year.start_date,
                "end_date": current_year.end_date,
            },
            "current_term": {
                "id": str(current_term.id),
                "name": current_term.get_name_display(),
                "start_date": current_term.start_date,
                "end_date": current_term.end_date,
                "current_week": current_week,
                "total_weeks": total_weeks,
                "days_remaining": days_until_end,
                "progress_percent": term_progress_pct,
            },
        }

    # ─── Recent Activity ──────────────────────────────────────────

    def _get_recent_activity(self, school):
        from core.models import AuditLog

        # Category map — maps audit log resource to frontend category
        category_map = {
            "Student": "Admission",
            "Enrollment": "Admission",
            "Guardian": "Admission",
            "Invoice": "Finance",
            "Payment": "Finance",
            "Attendance": "Academic",
            "Score": "Academic",
            "ExamResult": "Academic",
            "User": "HR",
            "Class": "Academic",
            "Subject": "Academic",
        }

        logs = (
            AuditLog.objects
            .filter(school=school)
            .select_related("actor")
            .order_by("-timestamp")[:4]
        )

        result = []
        for log in logs:
            category = category_map.get(log.resource, "General")
            result.append({
                "id": str(log.id),
                "action": log.description,
                "person": log.actor.full_name if log.actor else "System",
                "category": category,
                "resource": log.resource,
                "time": self._time_ago(log.timestamp),
                "status": self._derive_status(log.action),
            })

        return result

    # ─── Private helpers ──────────────────────────────────────────

    def _current_term_start(self, school):
        from academics.models import Term
        term = Term.objects.filter(
            school=school, is_current=True
        ).first()
        return term.start_date if term else None

    def _prev_term_student_count(self, school):
        from academics.models import Term
        from students.models import Enrollment

        prev_term = (
            Term.objects
            .filter(school=school, is_current=False)
            .order_by("-end_date")
            .first()
        )
        if not prev_term:
            return 0

        return Enrollment.objects.filter(
            school=school,
            academic_year=prev_term.academic_year,
            is_active=True,
        ).values("student").distinct().count()

    def _prev_term_attendance(self, school):
        """Average attendance % for the previous term."""
        from django.db.models import Avg

        from academics.models import Term

        prev_term = (
            Term.objects
            .filter(school=school, is_current=False)
            .order_by("-end_date")
            .first()
        )
        if not prev_term:
            return 0

        try:
            from attendance.models import AttendanceSummary
            result = AttendanceSummary.objects.filter(
                school=school,
                term=prev_term,
            ).aggregate(avg=Avg("attendance_percentage"))
            return float(result["avg"] or 0)
        except Exception:
            return 0

    def _get_term_revenue(self, school):
        from django.db.models import Sum

        from academics.models import Term

        current_term = Term.objects.filter(
            school=school, is_current=True
        ).first()
        if not current_term:
            return 0

        try:
            from finance.models import Payment
            result = Payment.objects.filter(
                school=school,
                date__gte=current_term.start_date,
                date__lte=current_term.end_date,
            ).aggregate(total=Sum("amount"))
            return result["total"] or 0
        except Exception:
            return 0

    def _get_prev_term_revenue(self, school):
        from django.db.models import Sum

        from academics.models import Term

        prev_term = (
            Term.objects
            .filter(school=school, is_current=False)
            .order_by("-end_date")
            .first()
        )
        if not prev_term:
            return 0

        try:
            from finance.models import Payment
            result = Payment.objects.filter(
                school=school,
                date__gte=prev_term.start_date,
                date__lte=prev_term.end_date,
            ).aggregate(total=Sum("amount"))
            return result["total"] or 0
        except Exception:
            return 0

    @staticmethod
    def _time_ago(timestamp):
        from django.utils import timezone
        now = timezone.now()
        diff = now - timestamp

        seconds = diff.total_seconds()
        if seconds < 60:
            return "Just now"
        elif seconds < 3600:
            mins = int(seconds // 60)
            return f"{mins} min{'s' if mins > 1 else ''} ago"
        elif seconds < 86400:
            hours = int(seconds // 3600)
            return f"{hours} hour{'s' if hours > 1 else ''} ago"
        elif seconds < 604800:
            days = int(seconds // 86400)
            return f"{days} day{'s' if days > 1 else ''} ago"
        else:
            return timestamp.strftime("%b %d, %Y")

    @staticmethod
    def _derive_status(action):
        status_map = {
            "create": "Completed",
            "update": "Updated",
            "delete": "Removed",
            "login": "Verified",
            "logout": "Verified",
        }
        return status_map.get(action, "Completed")

    @staticmethod
    def _format_currency(amount):
        """Returns GH₵124K style formatted string."""
        amount = float(amount)
        if amount >= 1_000_000:
            return f"GH₵{amount / 1_000_000:.1f}M"
        elif amount >= 1_000:
            return f"GH₵{amount / 1_000:.0f}K"
        return f"GH₵{amount:.2f}"

    @staticmethod
    def _percent_change(previous, current):
        previous = float(previous or 0)
        current = float(current or 0)
        if previous == 0:
            return "+100%" if current > 0 else "0%"
        change = ((current - previous) / previous) * 100
        sign = "+" if change >= 0 else ""
        return f"{sign}{change:.1f}%"
