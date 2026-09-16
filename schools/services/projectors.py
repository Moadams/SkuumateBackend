"""
Read-model projectors — one class per aggregate that selects data from
the persistence layer and projects it into an immutable DTO.

These sit in the application layer: they own ORM queries and DTO
construction, but are completely ignorant of HTTP and response format.
"""
from datetime import date

from django.db import models
from django.db.models import Count

from .attendance import AttendanceStatsService
from .dto import (
    AcademicYearDTO,
    AcademicsDTO,
    AssessmentTypeDTO,
    ClassEnrollmentDTO,
    ClassSummaryDTO,
    CommunicationsDTO,
    ExamsDTO,
    FinanceDTO,
    GradeScaleDTO,
    GradingSystemDTO,
    NotificationTemplateDTO,
    PlanDetailsDTO,
    PlanUsageDTO,
    PositionCountDTO,
    ProviderDTO,
    RecentStaffDTO,
    ReportSchemeDTO,
    ReportsDTO,
    SchoolSummaryDTO,
    StaffDTO,
    StaffPositionDTO,
    StaffTotalsDTO,
    StudentTotalsDTO,
    StudentsDTO,
    SubjectDTO,
    SubscriptionDTO,
    SubscriptionPaymentDTO,
    TermDTO,
    TermRefDTO,
    TimetableDTO,
)
from .finance import SchoolFinanceService
from .onboarding import OnboardingService
from .term_progress import TermProgressService

from subscriptions.services.packages import get_package_features


class SchoolProjector:
    @staticmethod
    def build(school) -> SchoolSummaryDTO:
        return SchoolSummaryDTO(
            id=str(school.id),
            name=school.name,
            school_code=school.school_code or "",
            logo=school.logo.url if school.logo else None,
            email=school.email,
            school_email_domain=school.school_email_domain or "",
            phone=school.phone,
            address=school.address,
            city=school.city,
            country=school.country,
            currency="GHS",
            status=school.status,
            joined=school.joined,
            onboarding_completed=school.onboarding_completed,
            user_count=school.users.filter(is_active=True).count(),
        )


class SubscriptionProjector:
    @staticmethod
    def build(school) -> SubscriptionDTO:
        subscription = (
            school.subscriptions
            .filter(is_current=True)
            .select_related("plan")
            .first()
        )
        if subscription is None:
            subscription = school.subscriptions.select_related("plan").first()

        payments = (
            subscription.payments.order_by("-created_at")[:5]
            if subscription else []
        )

        term_ref = None
        if subscription and subscription.term:
            term_ref = TermRefDTO(
                id=str(subscription.term_id),
                name=subscription.term.get_name_display(),
            )

        return SubscriptionDTO(
            status=subscription.status if subscription else None,
            is_paid=subscription.is_paid if subscription else None,
            is_trial=subscription.is_on_trial if subscription else None,
            is_accessible=subscription.is_accessible if subscription else None,
            is_read_only=subscription.is_read_only if subscription else None,
            is_locked=subscription.is_locked if subscription else None,
            days_remaining=subscription.days_remaining if subscription else None,
            start_date=subscription.start_date if subscription else None,
            end_date=subscription.end_date if subscription else None,
            grace_end_date=subscription.grace_end_date if subscription else None,
            term=term_ref,
            plan=SubscriptionProjector._plan(subscription),
            usage=SubscriptionProjector._usage(school, subscription),
            recent_payments=[
                SubscriptionPaymentDTO(
                    id=str(payment.id),
                    amount=payment.amount,
                    payment_reference=payment.payment_reference or "",
                    provider=payment.provider or "",
                    status=payment.status,
                    created_at=payment.created_at,
                )
                for payment in payments
            ],
        )

    @staticmethod
    def _plan(subscription) -> PlanDetailsDTO | None:
        if not subscription or not subscription.plan:
            return None
        plan = subscription.plan
        return PlanDetailsDTO(
            name=plan.name,
            plan_type=plan.plan_type,
            description=plan.description,
            tagline=plan.tagline,
            price_per_term=plan.price,
            setup_fee=plan.setup_fee,
            features=get_package_features(plan),
        )

    @staticmethod
    def _usage(school, subscription) -> PlanUsageDTO | None:
        if not subscription or not subscription.plan:
            return None
        max_students = subscription.plan.maximum_students
        active = school.students.filter(status="active").count()
        return PlanUsageDTO(
            active_students=active,
            max_students=max_students,
            remaining_slots=(
                max_students - active if max_students is not None else None
            ),
            is_at_limit=(
                max_students is not None and active >= max_students
            ),
        )


class AcademicsProjector:
    @staticmethod
    def build(school) -> AcademicsDTO:
        today = date.today()

        current_year = school.academic_years.filter(is_current=True).first()
        current_term = school.terms.filter(is_current=True).first()

        classes = (
            school.classes.all()
            .prefetch_related("class_teachers", "subject_teachers")
            .annotate(
                enrollment_count=Count(
                    "enrollments",
                    filter=(
                        models.Q(enrollments__is_active=True)
                        & models.Q(enrollments__academic_year__is_current=True)
                    ),
                )
            )
        )

        slots = school.timetable_slots.select_related("klass", "subject").all()
        slots_per_day: dict = {}
        for slot in slots:
            slots_per_day[slot.day_of_week] = slots_per_day.get(slot.day_of_week, 0) + 1

        return AcademicsDTO(
            has_current_year=current_year is not None,
            has_current_term=current_term is not None,
            current_academic_year=(
                AcademicYearDTO(
                    id=str(current_year.id),
                    name=current_year.name,
                    start_date=current_year.start_date,
                    end_date=current_year.end_date,
                    is_current=current_year.is_current,
                    terms=current_year.terms.count(),
                )
                if current_year else None
            ),
            current_term=TermProgressService.build(current_term, today),
            academic_years=[
                AcademicYearDTO(
                    id=str(year.id),
                    name=year.name,
                    start_date=year.start_date,
                    end_date=year.end_date,
                    is_current=year.is_current,
                    terms=year.terms.count(),
                )
                for year in school.academic_years.all()
            ],
            terms=[
                TermDTO(
                    id=str(term.id),
                    name=term.get_name_display(),
                    start_date=term.start_date,
                    end_date=term.end_date,
                    next_reopening_date=term.next_reopening_date,
                    is_current=term.is_current,
                    academic_year=term.academic_year.name,
                )
                for term in school.terms.select_related("academic_year").all()
            ],
            classes=[
                ClassSummaryDTO(
                    id=str(klass.id),
                    name=klass.name,
                    description=klass.description,
                    capacity=klass.capacity,
                    is_active=klass.is_active,
                    student_count=klass.enrollment_count,
                    class_teachers=klass.class_teachers.filter(
                        is_active=True
                    ).count(),
                    subject_count=klass.subject_teachers.count(),
                )
                for klass in classes
            ],
            subjects=[
                SubjectDTO(
                    id=str(subject.id),
                    name=subject.name,
                    code=subject.code,
                    is_active=subject.is_active,
                )
                for subject in school.subjects.all()
            ],
            grading_systems=[
                GradingSystemDTO(
                    id=str(system.id),
                    name=system.name,
                    description=system.description,
                    max_score=system.max_score,
                    pass_mark=system.pass_mark,
                    grade_scales=[
                        GradeScaleDTO(
                            grade=scale.grade,
                            label=scale.label,
                            min_score=float(scale.min_score),
                            max_score=float(scale.max_score),
                            is_passing=scale.is_passing,
                        )
                        for scale in system.grade_scales.all()
                    ],
                )
                for system in school.grading_systems.prefetch_related("grade_scales").all()
            ],
            timetable=TimetableDTO(
                total_slots=len(slots),
                slots_per_day=slots_per_day,
            ),
        )


class StaffProjector:
    @staticmethod
    def build(school) -> StaffDTO:
        from staff.models import StaffPosition, StaffProfile

        totals = (
            StaffProfile.objects
            .filter(school=school)
            .aggregate(
                total=Count("id"),
                active=Count("id", filter=models.Q(status="active")),
                on_leave=Count("id", filter=models.Q(status="on_leave")),
                suspended=Count("id", filter=models.Q(status="suspended")),
                inactive=Count("id", filter=models.Q(status="inactive")),
                terminated=Count("id", filter=models.Q(status="terminated")),
            )
        )

        recent = (
            StaffProfile.objects
            .filter(school=school)
            .prefetch_related("positions")
            .order_by("-created_at")[:5]
        )

        return StaffDTO(
            totals=StaffTotalsDTO(**totals),
            by_position=[
                PositionCountDTO(
                    id=str(position.id),
                    name=position.name,
                    is_system=position.is_system,
                    member_count=position.member_count,
                )
                for position in (
                    StaffPosition.objects
                    .filter(school=school)
                    .annotate(member_count=Count("staff_members"))
                    .order_by("-is_system", "name")
                )
            ],
            positions=[
                StaffPositionDTO(
                    id=str(position.id),
                    name=position.name,
                    description=position.description,
                    is_system=position.is_system,
                    permissions=list(
                        position.permissions.values_list("key", flat=True)
                    ),
                    permission_count=position.permissions.count(),
                )
                for position in school.staff_positions.all()
            ],
            class_teacher_assignments=school.class_teachers.filter(
                is_active=True
            ).count(),
            subject_teacher_assignments=school.subject_teachers.filter(
                is_active=True
            ).count(),
            recent_staff=[
                RecentStaffDTO(
                    id=str(member.id),
                    full_name=member.full_name,
                    employee_id=member.employee_id,
                    status=member.status,
                    employment_type=member.employment_type,
                    positions=[position.name for position in member.positions.all()],
                )
                for member in recent
            ],
        )


class StudentsProjector:
    @staticmethod
    def build(school) -> StudentsDTO:
        from students.models import Guardian, Student

        status_rows = (
            Student.objects
            .filter(school=school)
            .values("status")
            .annotate(count=Count("id"))
        )
        status_map = {row["status"]: row["count"] for row in status_rows}

        gender_rows = (
            Student.objects
            .filter(school=school)
            .values("gender")
            .annotate(count=Count("id"))
        )
        gender_map = {row["gender"]: row["count"] for row in gender_rows}

        by_class = (
            school.enrollments
            .filter(is_active=True, academic_year__is_current=True)
            .values("klass__id", "klass__name")
            .annotate(count=Count("id"))
            .order_by("klass__name")
        )

        guardians = Guardian.objects.filter(school=school)

        return StudentsDTO(
            totals=StudentTotalsDTO(
                total=sum(status_map.values()),
                active=status_map.get("active", 0),
                inactive=status_map.get("inactive", 0),
                withdrawn=status_map.get("withdrawn", 0),
            ),
            by_gender=gender_map,
            by_class=[
                ClassEnrollmentDTO(
                    klass_id=str(row["klass__id"]),
                    klass_name=row["klass__name"],
                    count=row["count"],
                )
                for row in by_class
            ],
            current_year_enrolled=sum(row["count"] for row in by_class),
            guardians=guardians.count(),
            primary_guardians=guardians.filter(is_primary=True).count(),
        )


class CommunicationsProjector:
    @staticmethod
    def build(school) -> CommunicationsDTO:
        templates = school.notification_templates.all()
        notifications = school.notifications.all()

        return CommunicationsDTO(
            providers=[
                ProviderDTO(
                    id=str(provider.id),
                    name=provider.name,
                    channel=provider.channel,
                    provider_type=provider.provider_type,
                    is_active=provider.is_active,
                    is_default=provider.is_default,
                    configured=bool(provider.config),
                )
                for provider in school.notification_providers.all()
            ],
            providers_configured=school.notification_providers.filter(
                is_active=True
            ).count(),
            templates=[
                NotificationTemplateDTO(
                    id=str(template.id),
                    name=template.name,
                    channel=template.channel,
                    subject=template.subject or "",
                    is_active=template.is_active,
                )
                for template in templates
            ],
            notifications_sent=notifications.filter(status="sent").count(),
            total_notifications=notifications.count(),
        )


class ExamsProjector:
    @staticmethod
    def build(school) -> ExamsDTO:
        from exams.models import AssessmentType, ReportScheme, StudentReport

        report_rows = (
            StudentReport.objects
            .filter(school=school)
            .values("status")
            .annotate(count=Count("id"))
        )
        report_map = {row["status"]: row["count"] for row in report_rows}

        return ExamsDTO(
            assessment_types=[
                AssessmentTypeDTO(
                    id=str(assessment.id),
                    name=assessment.name,
                    max_score=float(assessment.max_score),
                    is_active=assessment.is_active,
                )
                for assessment in AssessmentType.objects.filter(
                    school=school, is_active=True
                )
            ],
            report_schemes=[
                ReportSchemeDTO(
                    id=str(scheme.id),
                    name=scheme.name,
                    sba_scaling=scheme.sba_scaling,
                    exam_scaling=scheme.exam_scaling,
                    sba_components=[
                        component.name for component in scheme.sba_components.all()
                    ],
                    main_exam=scheme.main_exam.name if scheme.main_exam else None,
                )
                for scheme in ReportScheme.objects.filter(school=school)
                .prefetch_related("sba_components", "main_exam")
            ],
            reports=ReportsDTO(
                total=sum(report_map.values()),
                published=report_map.get("PUBLISHED", 0),
                ready=report_map.get("READY", 0),
                draft=report_map.get("DRAFT", 0),
                pending_remarks=report_map.get("PENDING_REMARKS", 0),
            ),
        )