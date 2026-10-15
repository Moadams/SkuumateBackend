from datetime import timedelta

from django.core.cache import cache
from django.db.models import Count, Sum
from django.utils import timezone
from rest_framework.views import APIView

from core.cache import CacheKeys
from core.logging import get_logger
from core.responses import ApiResponse
from core.school_permissions import school_permission
from dashboard.services import SuperAdminDashboardService
from subscriptions.permissions import HasAdvancedFinance, IsPlatformSuperAdmin

logger = get_logger("dashboard.views")


class SuperadminDashboardView(APIView):
    """
    Superadmin-only platform overview dashboard.
    Returns all metrics needed for the platform overview page.
    """
    permission_classes = (IsPlatformSuperAdmin,)

    def get(self, request):
        cached = cache.get(CacheKeys.SUPERADMIN_DASHBOARD)
        if cached is not None:
            return ApiResponse.success(data=cached)

        superadmin_dashboard_service = SuperAdminDashboardService()
        data = {
            "stats": superadmin_dashboard_service._get_stats(),
            "recent_onboarding": superadmin_dashboard_service._get_recent_onboarding(),
            "prospective_schools": superadmin_dashboard_service._get_pending_prospective_schools(),
            "subscription_distribution": superadmin_dashboard_service._get_subscription_distribution(),
        }
        cache.set(CacheKeys.SUPERADMIN_DASHBOARD, data, timeout=60 * 5)
        return ApiResponse.success(data=data)


# ── Finance Manager Dashboard ────────────────────────────────────────


class FinanceManagerDashboardView(APIView):
    """Dashboard for finance managers — financial KPIs and transaction history."""
    permission_classes = [
        school_permission(read="dashboard.finance"),
        HasAdvancedFinance,
    ]

    def get(self, request):
        school = request.user.school
        if not school:
            return ApiResponse.error(message="No school associated with user", status_code=400)

        cache_key = CacheKeys.school_dashboard(school.id) + ":finance"
        cached = cache.get(cache_key)
        if cached is not None:
            return ApiResponse.success(data=cached)

        data = {
            "stats": self._get_stats(school),
            "invoice_status_breakdown": self._get_invoice_status_breakdown(school),
            "recent_payments": self._get_recent_payments(school),
            "recent_expenses": self._get_recent_expenses(school),
            "current_term": self._get_current_term(school),
            "subscription": self._get_subscription(school),
        }

        cache.set(cache_key, data, timeout=60 * 5)
        return ApiResponse.success(data=data)

    def _get_stats(self, school):
        from finance.models import FeePayment, OtherIncome, Expense, SchoolFeeInvoice

        now = timezone.now()
        this_month_start = now.replace(day=1)
        last_month_start = (this_month_start - timedelta(days=1)).replace(day=1)

        fee_revenue = FeePayment.objects.filter(
            school=school, payment_date__gte=this_month_start
        ).aggregate(total=Sum("amount_paid"))["total"] or 0

        other_revenue = OtherIncome.objects.filter(
            school=school, date__gte=this_month_start
        ).aggregate(total=Sum("amount"))["total"] or 0

        revenue_this_month = float(fee_revenue) + float(other_revenue)

        fee_revenue_last = FeePayment.objects.filter(
            school=school,
            payment_date__gte=last_month_start,
            payment_date__lt=this_month_start,
        ).aggregate(total=Sum("amount_paid"))["total"] or 0

        other_revenue_last = OtherIncome.objects.filter(
            school=school,
            date__gte=last_month_start,
            date__lt=this_month_start,
        ).aggregate(total=Sum("amount"))["total"] or 0

        revenue_last_month = float(fee_revenue_last) + float(other_revenue_last)

        expenses_this_month = float(
            Expense.objects.filter(
                school=school, date__gte=this_month_start
            ).aggregate(total=Sum("amount"))["total"] or 0
        )

        expenses_last_month = float(
            Expense.objects.filter(
                school=school,
                date__gte=last_month_start,
                date__lt=this_month_start,
            ).aggregate(total=Sum("amount"))["total"] or 0
        )

        outstanding = float(
            SchoolFeeInvoice.objects.filter(
                school=school,
                status__in=["issued", "partially_paid", "overdue"],
            ).aggregate(total=Sum("total_amount"))["total"] or 0
        )

        total_collected_this_term = float(
            FeePayment.objects.filter(
                school=school, invoice__term__is_current=True
            ).aggregate(total=Sum("amount_paid"))["total"] or 0
        )

        return {
            "revenue_this_month": {
                "value": revenue_this_month,
                "change": self._percent_change(revenue_last_month, revenue_this_month),
                "is_positive": revenue_this_month >= revenue_last_month,
            },
            "expenses_this_month": {
                "value": expenses_this_month,
                "change": self._percent_change(expenses_last_month, expenses_this_month),
                "is_positive": expenses_this_month <= expenses_last_month,
            },
            "outstanding_receivables": {"value": outstanding},
            "net_income": {"value": revenue_this_month - expenses_this_month},
            "total_collected_this_term": {"value": total_collected_this_term},
        }

    def _get_invoice_status_breakdown(self, school):
        from finance.models import SchoolFeeInvoice

        statuses = ["draft", "issued", "partially_paid", "paid", "cancelled", "overdue"]
        breakdown = (
            SchoolFeeInvoice.objects
            .filter(school=school)
            .values("status")
            .annotate(count=Count("id"))
        )
        counts = {item["status"]: item["count"] for item in breakdown}
        return [
            {"status": s, "count": counts.get(s, 0)} for s in statuses
        ]

    def _get_recent_payments(self, school):
        from finance.models import FeePayment

        payments = (
            FeePayment.objects
            .filter(school=school)
            .select_related("invoice__student", "received_by")
            .order_by("-created_at")[:10]
        )

        return [
            {
                "id": str(p.id),
                "student_name": p.invoice.student.full_name if p.invoice else "N/A",
                "invoice_number": p.invoice.invoice_number if p.invoice else "N/A",
                "amount": float(p.amount_paid),
                "method": p.payment_method,
                "reference": p.reference_number,
                "date": p.payment_date,
                "received_by": p.received_by.full_name if p.received_by else None,
            }
            for p in payments
        ]

    def _get_recent_expenses(self, school):
        from finance.models import Expense

        expenses = (
            Expense.objects
            .filter(school=school)
            .select_related("expense_type", "created_by")
            .order_by("-date")[:10]
        )

        return [
            {
                "id": str(e.id),
                "type": e.expense_type.name,
                "amount": float(e.amount),
                "description": e.description,
                "reference": e.reference_number,
                "date": e.date,
                "created_by": e.created_by.full_name if e.created_by else None,
            }
            for e in expenses
        ]

    def _get_current_term(self, school):
        from academics.models import AcademicYear, Term

        try:
            year = AcademicYear.objects.get(school=school, is_current=True)
            term = Term.objects.get(school=school, is_current=True)
            now = timezone.now().date()
            if term.start_date <= now <= term.end_date:
                status = "In Progress"
            elif now < term.start_date:
                status = "Upcoming"
            else:
                status = "Ended"
            return {
                "name": term.get_name_display(),
                "academic_year": year.name,
                "status": status,
                "start_date": term.start_date,
                "end_date": term.end_date,
            }
        except (AcademicYear.DoesNotExist, Term.DoesNotExist):
            return None

    def _get_subscription(self, school):
        from subscriptions.models import Subscription

        sub = (
            Subscription.objects
            .filter(school=school)
            .select_related("plan")
            .order_by("-created_at")
            .first()
        )

        if not sub:
            return {"plan": None, "status": "none"}

        return {
            "plan": sub.plan.name if sub.plan else None,
            "plan_type": sub.plan.plan_type if sub.plan else None,
            "status": sub.status,
            "is_paid": sub.is_paid,
            "days_remaining": sub.days_remaining,
            "start_date": sub.start_date,
            "end_date": sub.end_date,
        }

    @staticmethod
    def _percent_change(previous, current):
        if previous == 0:
            return "+100%" if current > 0 else "0%"
        change = ((current - previous) / previous) * 100
        sign = "+" if change >= 0 else ""
        return f"{sign}{change:.1f}%"


# ── Teacher Dashboard ────────────────────────────────────────────────


class TeacherDashboardView(APIView):
    """Dashboard for teachers — classes, subjects, attendance."""
    permission_classes = [school_permission(read="dashboard.teacher")]

    def get(self, request):
        from staff.models import StaffProfile

        try:
            profile = StaffProfile.objects.get(user=request.user)
        except StaffProfile.DoesNotExist:
            return ApiResponse.error(message="Teacher profile not found", status_code=400)

        school = profile.school
        teacher_id = profile.id

        data = {
            "stats": self._get_stats(teacher_id),
            "my_classes": self._get_my_classes(teacher_id),
            "my_subjects": self._get_my_subjects(teacher_id),
            "current_term": self._get_current_term(school),
            "today_attendance": self._get_today_attendance(teacher_id),
            "recent_activity": self._get_recent_activity(request.user.id),
        }

        return ApiResponse.success(data=data)

    def _get_stats(self, teacher_id):
        from students.models import Enrollment
        from academics.models import ClassTeacher, SubjectTeacher

        my_class_ids = ClassTeacher.objects.filter(
            teacher_id=teacher_id, is_active=True
        ).values_list("klass_id", flat=True)

        total_students = Enrollment.objects.filter(
            klass_id__in=my_class_ids,
            is_active=True,
            academic_year__is_current=True,
        ).count()

        total_classes = ClassTeacher.objects.filter(
            teacher_id=teacher_id, is_active=True
        ).count()

        total_subjects = SubjectTeacher.objects.filter(
            teacher_id=teacher_id, is_active=True
        ).count()

        return {
            "total_classes": {"value": total_classes},
            "total_subjects": {"value": total_subjects},
            "total_students": {"value": total_students},
        }

    def _get_my_classes(self, teacher_id):
        from academics.models import ClassTeacher

        class_teachers = ClassTeacher.objects.filter(
            teacher_id=teacher_id, is_active=True
        ).select_related("klass", "academic_year")

        return [
            {
                "id": str(ct.klass.id),
                "name": ct.klass.name,
                "capacity": ct.klass.capacity,
                "student_count": ct.klass.current_student_count,
                "academic_year": ct.academic_year.name if ct.academic_year else None,
            }
            for ct in class_teachers
        ]

    def _get_my_subjects(self, teacher_id):
        from academics.models import SubjectTeacher

        subjects = SubjectTeacher.objects.filter(
            teacher_id=teacher_id, is_active=True
        ).select_related("klass", "subject")

        return [
            {
                "id": str(s.id),
                "subject": s.subject.name,
                "class_name": s.klass.name,
                "is_active": s.is_active,
            }
            for s in subjects
        ]

    def _get_current_term(self, school):
        from academics.models import AcademicYear, Term

        try:
            year = AcademicYear.objects.get(school=school, is_current=True)
            term = Term.objects.get(school=school, is_current=True)
            now = timezone.now().date()
            if term.start_date <= now <= term.end_date:
                status = "In Progress"
            elif now < term.start_date:
                status = "Upcoming"
            else:
                status = "Ended"
            return {
                "name": term.get_name_display(),
                "academic_year": year.name,
                "status": status,
                "start_date": term.start_date,
                "end_date": term.end_date,
            }
        except (AcademicYear.DoesNotExist, Term.DoesNotExist):
            return None

    def _get_today_attendance(self, teacher_id):
        from attendance.models import AttendanceSummary
        from academics.models import ClassTeacher

        today = timezone.now().date()
        my_class_ids = ClassTeacher.objects.filter(
            teacher_id=teacher_id, is_active=True
        ).values_list("klass_id", flat=True)

        summaries = AttendanceSummary.objects.filter(
            klass_id__in=list(my_class_ids),
            date=today,
        ).select_related("klass")

        return [
            {
                "class_name": s.klass.name,
                "total": s.total_students,
                "present": s.present_count,
                "absent": s.absent_count,
                "late": s.late_count,
                "percentage": float(s.attendance_percentage),
            }
            for s in summaries
        ]

    def _get_recent_activity(self, user_id):
        from attendance.models import Attendance

        records = (
            Attendance.objects
            .filter(recorded_by_id=user_id)
            .select_related("student", "klass")
            .order_by("-created_at")[:10]
        )

        return [
            {
                "id": str(a.id),
                "student": a.student.full_name,
                "class_name": a.klass.name,
                "status": a.status,
                "date": a.date,
            }
            for a in records
        ]


# ── School Admin Dashboard ────────────────────────────────────────────


class AdminDashboardView(APIView):
    """
    School-level admin/finance manager dashboard.
    Returns key metrics scoped to the user's school.
    """
    permission_classes = [school_permission(read="dashboard.admin")]

    def get(self, request):
        school = request.user.school
        if not school:
            return ApiResponse.error(message="No school associated with user", status_code=400)

        cache_key = CacheKeys.school_dashboard(school.id)
        cached = cache.get(cache_key)
        if cached is not None:
            return ApiResponse.success(data=cached)

        data = {
            "stats": self._get_stats(school),
            "finance": self._get_finance_summary(school),
            "current_term": self._get_current_term(school),
            "recent_payments": self._get_recent_payments(school),
            "subscription": self._get_subscription(school),
        }

        cache.set(cache_key, data, timeout=60 * 5)
        return ApiResponse.success(data=data)

    def _get_stats(self, school):
        from students.models import Student, Guardian
        from staff.models import StaffProfile
        from academics.models import Class, Subject

        now = timezone.now()
        this_month_start = now.replace(day=1)
        last_month_start = (this_month_start - timedelta(days=1)).replace(day=1)

        total_students = Student.objects.filter(school=school, status="active").count()
        students_this_month = Student.objects.filter(
            school=school, created_at__gte=this_month_start
        ).count()
        students_last_month = Student.objects.filter(
            school=school,
            created_at__gte=last_month_start,
            created_at__lt=this_month_start,
        ).count()

        total_staff = StaffProfile.objects.filter(school=school, status="active").count()
        staff_this_month = StaffProfile.objects.filter(
            school=school, created_at__gte=this_month_start
        ).count()
        staff_last_month = StaffProfile.objects.filter(
            school=school,
            created_at__gte=last_month_start,
            created_at__lt=this_month_start,
        ).count()

        total_classes = Class.objects.filter(school=school, is_active=True).count()
        total_subjects = Subject.objects.filter(school=school, is_active=True).count()
        total_guardians = Guardian.objects.filter(school=school, student__status="active").count()

        return {
            "total_students": {
                "value": total_students,
                "change": self._percent_change(students_last_month, students_this_month),
                "is_positive": students_this_month >= students_last_month,
            },
            "total_staff": {
                "value": total_staff,
                "change": self._percent_change(staff_last_month, staff_this_month),
                "is_positive": staff_this_month >= staff_last_month,
            },
            "total_classes": {"value": total_classes},
            "total_subjects": {"value": total_subjects},
            "total_guardians": {"value": total_guardians},
        }

    def _get_finance_summary(self, school):
        from finance.models import FeePayment, OtherIncome, Expense, SchoolFeeInvoice

        now = timezone.now()
        this_month_start = now.replace(day=1)
        last_month_start = (this_month_start - timedelta(days=1)).replace(day=1)

        fee_revenue = FeePayment.objects.filter(
            school=school, payment_date__gte=this_month_start
        ).aggregate(total=Sum("amount_paid"))["total"] or 0

        other_revenue = OtherIncome.objects.filter(
            school=school, date__gte=this_month_start
        ).aggregate(total=Sum("amount"))["total"] or 0

        revenue_this_month = float(fee_revenue) + float(other_revenue)

        fee_revenue_last = FeePayment.objects.filter(
            school=school,
            payment_date__gte=last_month_start,
            payment_date__lt=this_month_start,
        ).aggregate(total=Sum("amount_paid"))["total"] or 0

        other_revenue_last = OtherIncome.objects.filter(
            school=school,
            date__gte=last_month_start,
            date__lt=this_month_start,
        ).aggregate(total=Sum("amount"))["total"] or 0

        revenue_last_month = float(fee_revenue_last) + float(other_revenue_last)

        expenses_this_month = float(
            Expense.objects.filter(
                school=school, date__gte=this_month_start
            ).aggregate(total=Sum("amount"))["total"] or 0
        )

        expenses_last_month = float(
            Expense.objects.filter(
                school=school,
                date__gte=last_month_start,
                date__lt=this_month_start,
            ).aggregate(total=Sum("amount"))["total"] or 0
        )

        outstanding = float(
            SchoolFeeInvoice.objects.filter(
                school=school,
                status__in=["issued", "partially_paid", "overdue"],
            ).aggregate(total=Sum("total_amount"))["total"] or 0
        )

        return {
            "revenue_this_month": {
                "value": revenue_this_month,
                "change": self._percent_change(revenue_last_month, revenue_this_month),
                "is_positive": revenue_this_month >= revenue_last_month,
            },
            "expenses_this_month": {
                "value": expenses_this_month,
                "change": self._percent_change(expenses_last_month, expenses_this_month),
                "is_positive": expenses_this_month <= expenses_last_month,
            },
            "outstanding_receivables": {"value": outstanding},
            "net_income": {"value": revenue_this_month - expenses_this_month},
        }

    def _get_current_term(self, school):
        from academics.models import AcademicYear, Term

        try:
            year = AcademicYear.objects.get(school=school, is_current=True)
            term = Term.objects.get(school=school, is_current=True)
            now = timezone.now().date()
            if term.start_date <= now <= term.end_date:
                status = "In Progress"
            elif now < term.start_date:
                status = "Upcoming"
            else:
                status = "Ended"
            return {
                "name": term.get_name_display(),
                "academic_year": year.name,
                "status": status,
                "start_date": term.start_date,
                "end_date": term.end_date,
            }
        except (AcademicYear.DoesNotExist, Term.DoesNotExist):
            return None

    def _get_recent_payments(self, school):
        from finance.models import FeePayment

        payments = (
            FeePayment.objects
            .filter(school=school)
            .select_related("invoice__student", "received_by")
            .order_by("-created_at")[:10]
        )

        return [
            {
                "id": str(p.id),
                "student_name": p.invoice.student.full_name if p.invoice else "N/A",
                "invoice_number": p.invoice.invoice_number if p.invoice else "N/A",
                "amount": float(p.amount_paid),
                "method": p.payment_method,
                "reference": p.reference_number,
                "date": p.payment_date,
                "received_by": p.received_by.full_name if p.received_by else None,
            }
            for p in payments
        ]

    def _get_subscription(self, school):
        from subscriptions.models import Subscription

        sub = (
            Subscription.objects
            .filter(school=school)
            .select_related("plan")
            .order_by("-created_at")
            .first()
        )

        if not sub:
            return {"plan": None, "status": "none"}

        return {
            "plan": sub.plan.name if sub.plan else None,
            "plan_type": sub.plan.plan_type if sub.plan else None,
            "status": sub.status,
            "is_paid": sub.is_paid,
            "days_remaining": sub.days_remaining,
            "start_date": sub.start_date,
            "end_date": sub.end_date,
        }

    @staticmethod
    def _percent_change(previous, current):
        if previous == 0:
            return "+100%" if current > 0 else "0%"
        change = ((current - previous) / previous) * 100
        sign = "+" if change >= 0 else ""
        return f"{sign}{change:.1f}%"