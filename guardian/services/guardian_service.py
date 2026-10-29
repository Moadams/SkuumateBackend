
from decimal import Decimal

from django.db import transaction
from django.db.models import DecimalField, Sum
from django.db.models.functions import Coalesce

from academics.models import AcademicYear
from accounts.models import User
from accounts.services import AccountService
from exams.models import StudentReport
from finance.models import FeePayment, SchoolFeeInvoice
from guardian.models import Guardian, GuardianStudent
from guardian.serializers import GuardianStudentSerializer
from schools.models import School
from students.models import Student


class GuardianService:
    def __init__(self):
        self.account_service = AccountService()

    @transaction.atomic
    def create_guardian(self, data, school: School):
        try:
            students = data.pop("students", None) or []
            self._validate_students(students, school)

            data["role"] = User.Role.GUARDIAN
            data["school"] = school
            user = self.account_service.create_account(data, school)
            data.pop("role")
            data['user_account'] = user
            if Guardian.objects.filter(**data).exists():
                raise ValueError("Guardian already exists")
            guardian = Guardian.objects.create(**data)

            GuardianStudent.objects.bulk_create([
                GuardianStudent(
                    school=school,
                    guardian=guardian,
                    student=item["student"],
                    relationship=item["relationship"],
                )
                for item in students
            ])

            return guardian
        except Exception as e:
            raise ValueError(str(e))

    @staticmethod
    def _validate_students(students, school: School):
        for item in students:
            if item["student"].school_id != school.id:
                raise ValueError("One or more students do not belong to this school")

    @transaction.atomic
    def update_guardian(self, guardian: Guardian, data) -> Guardian:
        """Update the guardian and keep the linked login account in step."""
        user = guardian.user_account

        email = data.get("email")
        if email:
            email = User.objects.normalize_email(email)
            if User.objects.filter(email__iexact=email).exclude(pk=user.pk).exists():
                raise ValueError("A user with this email already exists.")
            user.email = email

        for field, value in data.items():
            setattr(guardian, field, value)
        guardian.save()

        for field in ("first_name", "last_name"):
            if field in data:
                setattr(user, field, data[field])
        if "phone" in data:
            user.phone = data["phone"] or ""
        user.save()

        return guardian

    @transaction.atomic
    def delete_guardian(self, guardian: Guardian):
        """Delete the guardian's login account; the profile and links cascade."""
        guardian.user_account.delete()

    @transaction.atomic
    def link_students(self, guardian: Guardian, students):
        """Link several students to a guardian; all-or-nothing."""
        self._validate_students(students, guardian.school)

        student_ids = [item["student"].pk for item in students]
        already_linked = GuardianStudent.objects.filter(
            guardian=guardian, student_id__in=student_ids
        ).select_related("student")
        if already_linked:
            names = ", ".join(link.student.full_name for link in already_linked)
            raise ValueError(f"Already linked to this guardian: {names}")

        return GuardianStudent.objects.bulk_create([
            GuardianStudent(
                school=guardian.school,
                guardian=guardian,
                student=item["student"],
                relationship=item["relationship"],
            )
            for item in students
        ])

    @transaction.atomic
    def unlink_students(self, guardian: Guardian, student_ids):
        """Unlink several students from a guardian; all-or-nothing."""
        links = GuardianStudent.objects.filter(
            guardian=guardian, student_id__in=student_ids
        )
        linked_ids = set(links.values_list("student_id", flat=True))
        missing = [str(pk) for pk in student_ids if pk not in linked_ids]
        if missing:
            raise ValueError(
                f"Not linked to this guardian: {', '.join(missing)}"
            )
        links.delete()

    @transaction.atomic
    def assign_student(self, data:GuardianStudentSerializer, school: School):
        data['school'] = school
        if GuardianStudent.objects.filter(**data).exists():
            raise ValueError("Student is already assigned to this guardian")
        return GuardianStudent.objects.create(**data)

    def get_guardian_student_link(self, user: User, student_id):
        """The link between ``user``'s guardian profile and one student, or ``None``.

        ``None`` covers both an unknown student and a student linked only to
        someone else, so callers cannot tell the two apart.
        """
        return (
            GuardianStudent.objects.filter(
                guardian__user_account=user, student_id=student_id
            )
            .select_related("student__school")
            .first()
        )

    def get_published_reports(self, student: Student):
        """Published report cards for ``student``, newest first.

        Draft, ready and pending-remarks reports are never shown to guardians.
        """
        return (
            StudentReport.objects.filter(
                student=student,
                school_id=student.school_id,
                status=StudentReport.ReportStatus.PUBLISHED,
            )
            .select_related("academic_year", "term", "student_class")
            .order_by("-academic_year__start_date", "-term__name")
        )

    def get_published_report(self, student: Student, report_id):
        """One published report card for ``student``, or ``None``.

        The report must belong to ``student``: a report for another student,
        even one linked to the same guardian, resolves to ``None`` so the view
        answers 404 rather than leaking it.
        """
        return (
            self.get_published_reports(student)
            .filter(pk=report_id)
            .prefetch_related("subject_scores__subject")
            .first()
        )

    def get_invoices(self, student: Student):
        """Invoices for ``student`` that a guardian may see, newest first.

        Drafts are internal until the school issues them, so they are hidden.
        Payments are summed in the database to avoid a query per invoice.
        """
        return (
            SchoolFeeInvoice.objects.filter(
                school_id=student.school_id, student=student
            )
            .exclude(status=SchoolFeeInvoice.Status.DRAFT)
            .select_related("academic_year", "term", "klass")
            .annotate(
                paid_total=Coalesce(
                    Sum("payments__amount_paid"),
                    Decimal("0.00"),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                )
            )
            .order_by("-academic_year__start_date", "-term__name")
        )

    def get_invoice(self, student: Student, invoice_id):
        """One visible invoice of ``student``, or ``None`` if it is not theirs."""
        return (
            self.get_invoices(student)
            .filter(pk=invoice_id)
            .prefetch_related(
                "line_items__fee_component",
                "line_items__payment_allocations",
            )
            .first()
        )

    def get_payments(self, student: Student):
        """Payments recorded against ``student``'s non-draft invoices, newest first."""
        return (
            FeePayment.objects.filter(
                school_id=student.school_id, invoice__student=student
            )
            .exclude(invoice__status=SchoolFeeInvoice.Status.DRAFT)
            .select_related("invoice", "invoice__academic_year", "invoice__term")
            .order_by("-payment_date", "-created_at")
        )

    def get_academic_years_with_terms(self, student: Student):
        """Academic years of the student's school, with their terms prefetched."""
        return AcademicYear.objects.filter(school_id=student.school_id).prefetch_related(
            "terms"
        )

    def get_guardian_students(self, user: User):
        """Students linked to the guardian account belonging to ``user``."""
        return (
            Student.objects.filter(guardian_links__guardian__user_account=user)
            .select_related("school")
            .distinct()
        )
