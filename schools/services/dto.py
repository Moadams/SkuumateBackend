"""
Read-model DTOs for the schools application.

These are immutable data-transfer objects produced by the application
layer (services/projectors) and consumed by the presentation layer
(serializers/presenters). They are plain data — no behavior, no
model access, no HTTP awareness.
"""
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Dict, List, Optional, Union

# ── School ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SchoolSummaryDTO:
    id: str
    name: str
    school_code: str
    logo: Optional[str]
    email: Optional[str]
    school_email_domain: str
    phone: str
    address: str
    city: str
    country: str
    currency: str
    status: str
    joined: Optional[datetime]
    onboarding_completed: bool
    user_count: int


# ── Subscription & plan ───────────────────────────────────────────────


@dataclass(frozen=True)
class PlanUsageDTO:
    active_students: int
    max_students: Optional[int]
    remaining_slots: Optional[int]
    is_at_limit: bool


@dataclass(frozen=True)
class PlanDetailsDTO:
    name: str
    plan_type: str
    description: str
    tagline: str
    price_per_term: Decimal
    setup_fee: Decimal
    features: Dict[str, bool]


@dataclass(frozen=True)
class SubscriptionPaymentDTO:
    id: str
    amount: Decimal
    payment_reference: str
    provider: str
    status: str
    created_at: datetime


@dataclass(frozen=True)
class TermRefDTO:
    id: str
    name: str


@dataclass(frozen=True)
class SubscriptionDTO:
    status: Optional[str]
    is_paid: Optional[bool]
    is_trial: Optional[bool]
    is_accessible: Optional[bool]
    is_read_only: Optional[bool]
    is_locked: Optional[bool]
    days_remaining: Optional[int]
    start_date: Optional[datetime]
    end_date: Optional[datetime]
    grace_end_date: Optional[datetime]
    term: Optional[TermRefDTO]
    plan: Optional[PlanDetailsDTO]
    usage: Optional[PlanUsageDTO]
    recent_payments: List[SubscriptionPaymentDTO]


# ── Academics ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AcademicYearDTO:
    id: str
    name: str
    start_date: date
    end_date: date
    is_current: bool
    terms: int


@dataclass(frozen=True)
class TermDTO:
    id: str
    name: str
    start_date: date
    end_date: date
    next_reopening_date: Optional[date]
    is_current: bool
    academic_year: str


@dataclass(frozen=True)
class TermProgressDTO:
    id: str
    name: str
    start_date: date
    end_date: date
    next_reopening_date: Optional[date]
    current_week: int
    total_weeks: int
    days_remaining: int
    progress_percent: int


@dataclass(frozen=True)
class ClassSummaryDTO:
    id: str
    name: str
    description: str
    capacity: int
    is_active: bool
    student_count: int
    class_teachers: int
    subject_count: int


@dataclass(frozen=True)
class SubjectDTO:
    id: str
    name: str
    code: str
    is_active: bool


@dataclass(frozen=True)
class GradeScaleDTO:
    grade: str
    label: str
    min_score: float
    max_score: float
    is_passing: bool


@dataclass(frozen=True)
class GradingSystemDTO:
    id: str
    name: str
    description: str
    max_score: int
    pass_mark: int
    grade_scales: List[GradeScaleDTO]


@dataclass(frozen=True)
class TimetableDTO:
    total_slots: int
    slots_per_day: Dict[str, int]


@dataclass(frozen=True)
class AcademicsDTO:
    has_current_year: bool
    has_current_term: bool
    current_academic_year: Optional[AcademicYearDTO]
    current_term: Optional[TermProgressDTO]
    academic_years: List[AcademicYearDTO]
    terms: List[TermDTO]
    classes: List[ClassSummaryDTO]
    subjects: List[SubjectDTO]
    grading_systems: List[GradingSystemDTO]
    timetable: TimetableDTO


# ── Staff ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class StaffTotalsDTO:
    total: int
    active: int
    on_leave: int
    suspended: int
    inactive: int
    terminated: int


@dataclass(frozen=True)
class PositionCountDTO:
    id: str
    name: str
    is_system: bool
    member_count: int


@dataclass(frozen=True)
class StaffPositionDTO:
    id: str
    name: str
    description: str
    is_system: bool
    permissions: List[str]
    permission_count: int


@dataclass(frozen=True)
class RecentStaffDTO:
    id: str
    full_name: str
    employee_id: str
    status: str
    employment_type: str
    positions: List[str]


@dataclass(frozen=True)
class StaffDTO:
    totals: StaffTotalsDTO
    by_position: List[PositionCountDTO]
    positions: List[StaffPositionDTO]
    class_teacher_assignments: int
    subject_teacher_assignments: int
    recent_staff: List[RecentStaffDTO]


# ── Students ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class StudentTotalsDTO:
    total: int
    active: int
    inactive: int
    withdrawn: int


@dataclass(frozen=True)
class ClassEnrollmentDTO:
    klass_id: str
    klass_name: str
    count: int


@dataclass(frozen=True)
class StudentsDTO:
    totals: StudentTotalsDTO
    by_gender: Dict[str, int]
    by_class: List[ClassEnrollmentDTO]
    current_year_enrolled: int
    guardians: int
    primary_guardians: int


# ── Finance ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FinanceDTO:
    currency: str
    term_revenue: Decimal
    term_expenses: Decimal
    term_net: Decimal
    outstanding_balance: Decimal
    overdue_invoices: int
    collected_percentage: float
    invoice_status_breakdown: Dict[str, int]
    income_types: List[str]
    expense_types: List[str]
    fee_components: List[str]


# ── Attendance ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AttendanceTodayDTO:
    date: date
    total: int
    present: int
    absent: int
    late: int
    percentage: float


@dataclass(frozen=True)
class AttendanceDayDTO:
    date: date
    percentage: float
    present: int
    total: int


@dataclass(frozen=True)
class AttendanceDTO:
    today: AttendanceTodayDTO
    term_average_percentage: float
    last_7_days: List[AttendanceDayDTO]


# ── Communications ────────────────────────────────────────────────────


@dataclass(frozen=True)
class ProviderDTO:
    id: str
    name: str
    channel: str
    provider_type: str
    is_active: bool
    is_default: bool
    configured: bool


@dataclass(frozen=True)
class NotificationTemplateDTO:
    id: str
    name: str
    channel: str
    subject: str
    is_active: bool


@dataclass(frozen=True)
class CommunicationsDTO:
    providers: List[ProviderDTO]
    providers_configured: int
    templates: List[NotificationTemplateDTO]
    notifications_sent: int
    total_notifications: int


# ── Exams & reporting ────────────────────────────────────────────────


@dataclass(frozen=True)
class AssessmentTypeDTO:
    id: str
    name: str
    max_score: float
    is_active: bool


@dataclass(frozen=True)
class ReportSchemeDTO:
    id: str
    name: str
    sba_scaling: Decimal
    exam_scaling: Decimal
    sba_components: List[str]
    main_exam: Optional[str]


@dataclass(frozen=True)
class ReportsDTO:
    total: int
    published: int
    ready: int
    draft: int
    pending_remarks: int


@dataclass(frozen=True)
class ExamsDTO:
    assessment_types: List[AssessmentTypeDTO]
    report_schemes: List[ReportSchemeDTO]
    reports: ReportsDTO


# ── Onboarding ────────────────────────────────────────────────────────


OnboardingStepsDTO = Dict[str, bool]


@dataclass(frozen=True)
class OnboardingDTO:
    onboarding_completed: bool
    steps: OnboardingStepsDTO
    completed_count: int
    total_steps: int
    current_step: Optional[str]
    profile: Dict
    data: Dict


# ── Aggregate ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SchoolDetailsDTO:
    school: SchoolSummaryDTO
    subscription: SubscriptionDTO
    academics: AcademicsDTO
    staff: StaffDTO
    students: StudentsDTO
    finance: FinanceDTO
    attendance: AttendanceDTO
    communications: CommunicationsDTO
    exams: ExamsDTO
    onboarding: OnboardingDTO