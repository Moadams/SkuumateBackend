from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User
from academics.models import AcademicYear, Term, Class
from core.mixins import _make_json_serializable
from finance.models import SchoolFeeInvoice, InvoiceLineItem, FeeComponent, FeePayment, ExpenseType
from schools.models import School
from staff.models import StaffProfile
from students.models import Student
from subscriptions.feature_catalog import declared_feature_codes
from subscriptions.models import Feature, Package, PackageFeature, Subscription


def grant_all_features(school):
    """Put ``school`` on a live subscription that unlocks every feature.

    These tests exercise cross-school isolation and payload validation, so the
    package must never be the reason a request is rejected. Feature gating has
    its own coverage in ``subscriptions.tests``.
    """
    package, _ = Package.objects.get_or_create(
        code="test-unlimited",
        defaults={
            "name": "Test Unlimited",
            "price": "0.00",
            "billing_period": Package.BillingPeriod.TERM,
            "is_active": True,
        },
    )
    for code in declared_feature_codes():
        feature, _ = Feature.objects.get_or_create(
            code=code, defaults={"name": code, "category": "core", "is_active": True}
        )
        PackageFeature.objects.get_or_create(
            package=package, feature=feature, defaults={"is_enabled": True}
        )
    return Subscription.objects.create(
        school=school,
        plan=package,
        status=Subscription.Status.ACTIVE,
        start_date="2020-01-01T00:00:00Z",
        end_date="2099-01-01T00:00:00Z",
        is_paid=True,
        is_current=True,
    )


class SchoolWorkflowSecurityTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name="School A", school_code="A")
        self.other = School.objects.create(name="School B", school_code="B")
        self.admin = User.objects.create_user(email="admin@example.com", password="old-password", role="admin", school=self.school)
        self.foreign_user = User.objects.create_user(email="foreign@example.com", password="old-password", role="admin", school=self.other)
        self.client.force_authenticate(self.admin)
        self.year = AcademicYear.objects.create(school=self.school, name="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
        self.term = Term.objects.create(school=self.school, academic_year=self.year, name="term_1", start_date=date(2026, 1, 1), end_date=date(2026, 4, 1))
        self.klass = Class.objects.create(school=self.school, name="Primary 1")
        self.student = Student.objects.create(school=self.school, first_name="A", last_name="Student", gender="female")
        self.foreign_student = Student.objects.create(school=self.other, first_name="B", last_name="Student", gender="male")
        self.component = FeeComponent.objects.create(school=self.school, name="Tuition")
        self.foreign_component = FeeComponent.objects.create(school=self.other, name="Tuition")
        # Every workflow below is gated by a package feature, so both schools
        # need a live subscription or the assertions would just see 403s.
        grant_all_features(self.school)
        grant_all_features(self.other)

    def invoice(self, school=None, student=None, amount="100.00"):
        school = school or self.school
        invoice = SchoolFeeInvoice.objects.create(school=school, student=student or self.student, academic_year=self.year, term=self.term, total_amount=amount)
        InvoiceLineItem.objects.create(school=school, invoice=invoice, fee_component=self.component if school == self.school else self.foreign_component, amount=amount)
        return invoice

    def invoice_payload(self, **overrides):
        payload = {"student": str(self.student.pk), "academic_year": str(self.year.pk), "term": str(self.term.pk), "klass": str(self.klass.pk), "line_items": [{"fee_component": str(self.component.pk), "amount": "100.00"}]}
        payload.update(overrides)
        return payload

    def pay(self, invoice, amount="40.00", **overrides):
        payload = {"invoice": str(invoice.pk), "amount_paid": amount, "payment_date": "2026-01-15", "payment_method": "cash"}
        payload.update(overrides)
        return self.client.post(reverse("payment-list"), payload, format="json")

    def test_school_admin_cannot_assign_platform_role(self):
        response = self.client.patch(reverse("user-detail", args=[self.admin.pk]), {"role": "superadmin"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.role, "admin")

    def test_password_reset_cannot_target_another_school(self):
        response = self.client.put(reverse("change-user-password"), {"user_id": str(self.foreign_user.pk), "password": "new-password", "confirm_password": "new-password"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.foreign_user.refresh_from_db()
        self.assertTrue(self.foreign_user.check_password("old-password"))

    def test_school_admin_cannot_reset_platform_account(self):
        platform = User.objects.create_user(email="platform@example.com", password="old-password", role="superadmin", school=self.school)
        response = self.client.put(reverse("reset-user-password", args=[platform.pk]), {"password": "new-password", "confirm_password": "new-password"}, format="json")
        self.assertEqual(response.status_code, 404)

    def test_user_detail_is_school_scoped(self):
        response = self.client.get(reverse("user-detail", args=[self.foreign_user.pk]))
        self.assertEqual(response.status_code, 404)

    def test_superadmin_can_retrieve_any_school_user(self):
        platform = User.objects.create_user(email="root@example.com", password="old-password", role="superadmin")
        self.client.force_authenticate(platform)
        response = self.client.get(reverse("user-detail", args=[self.foreign_user.pk]))
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["data"]["id"], str(self.foreign_user.pk))

    def test_user_detail_denies_non_admin_roles(self):
        teacher = User.objects.create_user(email="teacher@example.com", password="old-password", role="teacher", school=self.school)
        self.client.force_authenticate(teacher)
        self.assertEqual(self.client.get(reverse("user-detail", args=[self.admin.pk])).status_code, 403)

    def test_suspended_staff_tokens_and_login_are_rejected(self):
        token = RefreshToken.for_user(self.admin)
        StaffProfile.objects.create(school=self.school, user=self.admin, first_name="Admin", last_name="User", date_joined=date(2026, 1, 1), status="suspended")
        self.client.force_authenticate(user=None)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
        self.assertEqual(self.client.get(reverse("me")).status_code, 401)
        self.client.credentials()
        self.assertEqual(self.client.post(reverse("token-refresh"), {"refresh": str(token)}).status_code, 401)
        self.assertEqual(self.client.post(reverse("login"), {"email": self.admin.email, "password": "old-password"}).status_code, 401)

    def test_suspended_school_cannot_use_existing_token(self):
        token = RefreshToken.for_user(self.admin)
        self.school.status = "suspended"
        self.school.save()
        self.client.force_authenticate(user=None)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
        self.assertEqual(self.client.get(reverse("me")).status_code, 401)

    def test_password_change_revokes_access_and_refresh(self):
        token = RefreshToken.for_user(self.admin)
        response = self.client.put(reverse("change-password"), {"password": "new-password", "confirm_password": "new-password"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.client.force_authenticate(user=None)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
        self.assertEqual(self.client.get(reverse("me")).status_code, 401)
        self.client.credentials()
        self.assertEqual(self.client.post(reverse("token-refresh"), {"refresh": str(token)}).status_code, 401)

    def test_normal_login_and_refresh_still_work(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(reverse("login"), {"email": self.admin.email, "password": "old-password"})
        self.assertEqual(response.status_code, 200)
        refresh = response.data["data"]["refresh"]
        self.assertEqual(self.client.post(reverse("token-refresh"), {"refresh": refresh}).status_code, 200)

    def test_schoolless_finance_account_is_denied(self):
        user = User.objects.create_user(email="orphan@example.com", role="finance_manager")
        self.client.force_authenticate(user)
        self.assertEqual(self.client.get(reverse("invoice-list")).status_code, 403)

    def test_invoice_related_records_must_belong_to_school(self):
        for field, value in [("student", str(self.foreign_student.pk)), ("line_items", [{"fee_component": str(self.foreign_component.pk), "amount": "100.00"}])]:
            with self.subTest(field=field):
                response = self.client.post(reverse("invoice-list"), self.invoice_payload(**{field: value}), format="json")
                self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(SchoolFeeInvoice.objects.count(), 0)

    def test_invoice_creation_and_nested_update(self):
        response = self.client.post(reverse("invoice-list"), self.invoice_payload(), format="json")
        self.assertEqual(response.status_code, 201, response.data)
        invoice = SchoolFeeInvoice.objects.get()
        response = self.client.patch(reverse("invoice-detail", args=[invoice.pk]), {"line_items": [{"fee_component": str(self.component.pk), "amount": "123.45"}]}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        invoice.refresh_from_db()
        self.assertEqual(invoice.total_amount, Decimal("123.45"))
        self.assertEqual(invoice.line_items.count(), 1)

    def test_bulk_invoice_rejects_foreign_component_without_writes(self):
        payload = self.invoice_payload(line_items=[{"fee_component": str(self.foreign_component.pk), "amount": "100.00"}])
        payload["students"] = [payload.pop("student")]
        response = self.client.post(reverse("invoice-bulk-create"), payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(SchoolFeeInvoice.objects.exists())

    def test_bulk_invoice_rejects_mixed_school_students_without_writes(self):
        payload = self.invoice_payload()
        payload["students"] = [payload.pop("student"), str(self.foreign_student.pk)]
        response = self.client.post(reverse("invoice-bulk-create"), payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(SchoolFeeInvoice.objects.exists())

    def test_bulk_invoice_sets_line_school_and_skips_existing(self):
        payload = self.invoice_payload()
        payload["students"] = [payload.pop("student")]
        self.assertEqual(self.client.post(reverse("invoice-bulk-create"), payload, format="json").status_code, 201)
        self.assertEqual(InvoiceLineItem.objects.get().school_id, self.school.pk)
        response = self.client.post(reverse("invoice-bulk-create"), payload, format="json")
        self.assertEqual(response.data["data"]["skipped_count"], 1)

    def test_foreign_invoice_is_not_readable_or_payable(self):
        invoice = self.invoice(school=self.other, student=self.foreign_student)
        self.assertEqual(self.client.get(reverse("invoice-detail", args=[invoice.pk])).status_code, 404)
        self.assertEqual(self.pay(invoice).status_code, 400)
        self.assertFalse(FeePayment.objects.exists())

    def test_allocations_must_match_invoice_and_amount(self):
        invoice = self.invoice()
        other = self.invoice(school=self.other, student=self.foreign_student)
        for allocations in [
            [{"line_item": str(other.line_items.get().pk), "amount": "40.00"}],
            [{"line_item": str(invoice.line_items.get().pk), "amount": "39.99"}],
            [{"line_item": str(invoice.line_items.get().pk), "amount": "20.00"}] * 2,
        ]:
            with self.subTest(allocations=allocations):
                self.assertEqual(self.pay(invoice, allocations=allocations).status_code, 400)
        self.assertFalse(FeePayment.objects.exists())

    def test_allocation_rejects_another_invoice_in_same_school(self):
        invoice = self.invoice()
        student = Student.objects.create(school=self.school, first_name="Second", last_name="Student", gender="male")
        other = self.invoice(student=student)
        response = self.pay(invoice, allocations=[{"line_item": str(other.line_items.get().pk), "amount": "40.00"}])
        self.assertEqual(response.status_code, 400)
        self.assertFalse(FeePayment.objects.exists())

    def test_invoice_number_does_not_collide_after_deleting_earlier_invoice(self):
        first = self.invoice()
        student = Student.objects.create(school=self.school, first_name="Second", last_name="Student", gender="male")
        second = self.invoice(student=student)
        first.delete()
        replacement = self.invoice()
        self.assertNotEqual(second.invoice_number, replacement.invoice_number)

    def test_invoice_rejects_term_from_another_year(self):
        year = AcademicYear.objects.create(school=self.school, name="2027", start_date=date(2027, 1, 1), end_date=date(2027, 12, 31))
        response = self.client.post(reverse("invoice-list"), self.invoice_payload(academic_year=str(year.pk)), format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(SchoolFeeInvoice.objects.exists())

    def test_zero_negative_and_excess_payments_are_rejected(self):
        invoice = self.invoice()
        for amount in ["0.00", "-1.00", "100.01"]:
            with self.subTest(amount=amount):
                self.assertEqual(self.pay(invoice, amount=amount).status_code, 400)
        self.assertFalse(FeePayment.objects.exists())

    def test_payment_allocation_and_deletion_recalculate_invoice(self):
        invoice = self.invoice()
        self.assertEqual(self.pay(invoice).status_code, 201)
        self.assertEqual(self.pay(invoice, amount="60.00").status_code, 201)
        invoice.refresh_from_db()
        self.assertTrue(invoice.is_fully_paid)
        payment = invoice.payments.get(amount_paid="60.00")
        self.assertEqual(payment.allocations.get().amount, Decimal("60.00"))
        self.assertEqual(self.client.delete(reverse("payment-detail", args=[payment.pk])).status_code, 200)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, "partially_paid")
        self.assertFalse(invoice.is_fully_paid)
        self.client.delete(reverse("payment-detail", args=[invoice.payments.get().pk]))
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, "issued")

    def test_payment_financial_fields_cannot_be_changed(self):
        invoice = self.invoice()
        self.pay(invoice)
        payment = FeePayment.objects.get()
        response = self.client.patch(reverse("payment-detail", args=[payment.pk]), {"amount_paid": "99.00"}, format="json")
        self.assertEqual(response.status_code, 400)
        payment.refresh_from_db()
        self.assertEqual(payment.amount_paid, Decimal("40.00"))

    def test_paid_invoice_allows_notes_but_not_line_replacement_or_delete(self):
        invoice = self.invoice()
        self.pay(invoice)
        url = reverse("invoice-detail", args=[invoice.pk])
        self.assertEqual(self.client.patch(url, {"notes": "Checked"}, format="json").status_code, 200)
        self.assertEqual(self.client.patch(url, {"line_items": self.invoice_payload()["line_items"]}, format="json").status_code, 400)
        self.assertEqual(self.client.delete(url).status_code, 400)

    def test_payment_and_audit_failure_roll_back_together(self):
        invoice = self.invoice()
        with patch("finance.views.log_action", side_effect=RuntimeError("Audit unavailable")):
            with self.assertRaises(RuntimeError):
                self.pay(invoice)
        invoice.refresh_from_db()
        self.assertFalse(FeePayment.objects.exists())
        self.assertEqual(invoice.status, "issued")

    def test_expense_rejects_foreign_category(self):
        category = ExpenseType.objects.create(school=self.other, name="Utilities")
        response = self.client.post(reverse("expense-list"), {"expense_type": str(category.pk), "amount": "10.00", "date": "2026-01-15", "description": "Test"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_audit_metadata_redacts_nested_credentials(self):
        data = _make_json_serializable({"password": "private", "config": {"api_key": "private"}, "items": [{"refresh_token": "private"}], "name": "Visible"})
        self.assertNotIn("private", str(data))
        self.assertEqual(data["name"], "Visible")

    def test_staff_activation_cannot_target_another_school(self):
        profile = StaffProfile.objects.create(school=self.other, first_name="Foreign", last_name="Teacher", email="teacher@example.com", date_joined=date(2026, 1, 1))
        self.assertEqual(self.client.post(reverse("activate-staff-user-account", args=[profile.pk])).status_code, 404)
        profile.refresh_from_db()
        self.assertIsNone(profile.user_id)

    def test_staff_activation_creates_account_in_own_school(self):
        profile = StaffProfile.objects.create(school=self.school, first_name="New", last_name="Teacher", email="teacher@example.com", date_joined=date(2026, 1, 1))
        self.assertEqual(self.client.post(reverse("activate-staff-user-account", args=[profile.pk])).status_code, 200)
        profile.refresh_from_db()
        self.assertEqual(profile.user.school_id, self.school.pk)
        self.assertEqual(profile.user.role, "teacher")

    def test_staff_creation_rejects_platform_role(self):
        response = self.client.post(reverse("staff-list"), {"first_name": "Example", "last_name": "Teacher", "date_joined": "2026-01-01", "email": "teacher@example.com", "role": "superadmin"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(StaffProfile.objects.exists())

    def test_staff_status_change_cannot_target_another_school(self):
        profile = StaffProfile.objects.create(school=self.other, first_name="Foreign", last_name="Teacher", date_joined=date(2026, 1, 1))
        response = self.client.post(reverse("update-staff-status", args=[profile.pk]), {"status": "suspended"}, format="json")
        self.assertEqual(response.status_code, 404)
        profile.refresh_from_db()
        self.assertEqual(profile.status, "active")

    def test_finance_overview_reports_actual_unpaid_balance_and_distinct_months(self):
        invoice = self.invoice()
        self.pay(invoice)
        response = self.client.get(reverse("financial-overview"))
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(Decimal(response.data["data"]["summary"]["pending_invoice_amount"]), Decimal("60.00"))
        months = [item["month"] for item in response.data["data"]["monthly_trends"]]
        self.assertEqual(len(set(months)), 12)
        self.assertEqual(months, sorted(months))

    def test_invalid_password_reset_uid_returns_validation_error(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(reverse("reset-password-confirm"), {"uid": "bm90LWEtdXVpZA", "token": "invalid", "password": "new-password", "confirm_password": "new-password"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_term_cannot_link_foreign_academic_year(self):
        year = AcademicYear.objects.create(school=self.other, name="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
        response = self.client.patch(reverse("term-detail", args=[self.term.pk]), {"academic_year": str(year.pk)}, format="json")
        self.assertEqual(response.status_code, 400, response.data)
        self.term.refresh_from_db()
        self.assertEqual(self.term.academic_year_id, self.year.pk)

    def test_partial_academic_year_update_preserves_date_validation(self):
        url = reverse("academic-year-detail", args=[self.year.pk])
        self.assertEqual(self.client.patch(url, {"name": "2026 Academic Year"}, format="json").status_code, 200)
        self.assertEqual(self.client.patch(url, {"end_date": "2025-01-01"}, format="json").status_code, 400)

    def test_partial_term_update_preserves_date_validation(self):
        url = reverse("term-detail", args=[self.term.pk])
        response = self.client.patch(url, {"next_reopening_date": "2026-04-15"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.client.patch(url, {"end_date": "2025-01-01"}, format="json").status_code, 400)

    def test_attendance_rejects_foreign_student_and_duplicates(self):
        from students.models import Enrollment
        from attendance.models import Attendance
        Enrollment.objects.create(school=self.school, student=self.student, klass=self.klass, academic_year=self.year)
        for ids in [[self.foreign_student.pk], [self.student.pk, self.student.pk]]:
            payload = {"class_id": str(self.klass.pk), "term_id": str(self.term.pk), "date": "2026-01-15", "records": [{"student_id": str(pk), "status": "present"} for pk in ids]}
            response = self.client.post(reverse("attendance-mark"), payload, format="json")
            self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(Attendance.objects.exists())

    def test_attendance_repeated_submission_updates_existing_record(self):
        from students.models import Enrollment
        from attendance.models import Attendance
        Enrollment.objects.create(school=self.school, student=self.student, klass=self.klass, academic_year=self.year)
        payload = {"class_id": str(self.klass.pk), "term_id": str(self.term.pk), "date": "2026-01-15", "records": [{"student_id": str(self.student.pk), "status": "present"}]}
        self.assertEqual(self.client.post(reverse("attendance-mark"), payload, format="json").status_code, 201)
        payload["records"][0]["status"] = "absent"
        self.assertEqual(self.client.post(reverse("attendance-mark"), payload, format="json").status_code, 201)
        self.assertEqual(Attendance.objects.get().status, "absent")

    def test_student_cannot_write_marks_or_read_class_reports(self):
        from exams.views import StudentMarkBulkView
        from rest_framework.test import APIRequestFactory, force_authenticate
        user = User.objects.create_user(email="student@example.com", school=self.school, role="student")
        request = APIRequestFactory().post("/", {}, format="json")
        force_authenticate(request, user)
        self.assertEqual(StudentMarkBulkView.as_view()(request).status_code, 403)
        self.client.force_authenticate(user)
        self.assertEqual(self.client.get(reverse("class-students-report", args=[self.klass.pk, self.term.pk])).status_code, 403)

    def test_malformed_bulk_marks_returns_validation_error(self):
        from exams.views import StudentMarkBulkView
        from rest_framework.test import APIRequestFactory, force_authenticate
        request = APIRequestFactory().post("/", {}, format="json")
        force_authenticate(request, self.admin)
        self.assertEqual(StudentMarkBulkView.as_view()(request).status_code, 400)

    def test_report_scheme_rejects_foreign_assessment(self):
        from exams.models import AssessmentType
        foreign = AssessmentType.objects.create(school=self.other, name="Exam", max_score=100)
        response = self.client.post(reverse("report-scheme"), {"name": "Primary", "main_exam": str(foreign.pk), "sba_components": [], "sba_scaling": "0.00", "exam_scaling": "100.00"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_mark_serializer_rejects_foreign_assessment_and_accepts_blank_score(self):
        from academics.models import Subject
        from exams.models import AssessmentType
        from exams.serializers import StudentMarkCreationSerializer
        from students.models import Enrollment
        from types import SimpleNamespace
        Enrollment.objects.create(school=self.school, student=self.student, klass=self.klass, academic_year=self.year)
        subject = Subject.objects.create(school=self.school, name="Math")
        own = AssessmentType.objects.create(school=self.school, name="Exam", max_score=100)
        foreign = AssessmentType.objects.create(school=self.other, name="Exam", max_score=100)
        payload = {"student": str(self.student.pk), "student_class": str(self.klass.pk), "academic_year": str(self.year.pk), "term": str(self.term.pk), "subject": str(subject.pk), "assessment": str(foreign.pk), "score": None}
        context = {"request": SimpleNamespace(user=self.admin)}
        self.assertFalse(StudentMarkCreationSerializer(data=payload, context=context).is_valid())
        payload["assessment"] = str(own.pk)
        serializer = StudentMarkCreationSerializer(data=payload, context=context)
        self.assertTrue(serializer.is_valid(), serializer.errors)
