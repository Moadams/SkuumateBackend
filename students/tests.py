import io
import shutil
import tempfile
import zipfile
from datetime import date

import openpyxl
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APITestCase

from academics.models import AcademicYear, Class, Term
from accounts.models import User
from core.models import AuditLog
from schools.models import School
from students.models import Enrollment, Guardian, Student
from subscriptions.models import (
    Feature,
    Package,
    PackageFeature,
    PackageLimit,
    Subscription,
)
from subscriptions.utils import check_limit


def create_school(name="Quota School", code="QS"):
    return School.objects.create(
        name=name,
        school_code=code,
        email=f"{code.lower()}@example.com",
    )


def create_admin_user(school, email="admin@quota.com"):
    return User.objects.create_user(
        email=email,
        password="password123",
        first_name="Quota",
        last_name="Admin",
        role=User.Role.ADMIN,
        school=school,
    )


class StudentQuotaTests(TestCase):
    """The student cap must be enforced from PackageLimit, not the display column."""

    def setUp(self):
        self.school = create_school()
        self.package = Package.objects.create(
            name="Lite",
            code="lite-quota",
            price="100.00",
            billing_period=Package.BillingPeriod.TERM,
            maximum_students=250,
        )
        PackageFeature.objects.create(
            package=self.package, feature=self._feature("student_management"), is_enabled=True
        )
        PackageLimit.objects.create(
            package=self.package,
            key="max_students",
            name="Maximum Students",
            value=2,
        )
        Subscription.objects.create(
            school=self.school,
            plan=self.package,
            status=Subscription.Status.ACTIVE,
            start_date="2020-01-01T00:00:00Z",
            end_date="2099-01-01T00:00:00Z",
            is_paid=True,
            is_current=True,
        )

    @staticmethod
    def _feature(code):
        feature, _ = Feature.objects.get_or_create(
            code=code,
            defaults={"name": code, "category": "core", "is_active": True},
        )
        return feature

    def _add_students(self, count, student_status=Student.Status.ACTIVE):
        for index in range(count):
            Student.objects.create(
                school=self.school,
                first_name=f"First{index}",
                last_name=f"Last{index}",
                gender=Student.Gender.MALE,
                status=student_status,
            )

    def test_under_the_cap_is_allowed(self):
        self._add_students(1)
        check_limit(self.school, "students")

    def test_reaching_the_cap_is_blocked(self):
        """The Package column says 250; the PackageLimit row (2) is authoritative."""
        self._add_students(2)
        with self.assertRaises(PermissionDenied) as ctx:
            check_limit(self.school, "students")
        self.assertIn("limit (2)", str(ctx.exception))

    def test_inactive_students_do_not_consume_the_cap(self):
        self._add_students(1, Student.Status.ACTIVE)
        self._add_students(5, Student.Status.WITHDRAWN)
        check_limit(self.school, "students")

    def test_a_package_with_no_limit_row_falls_back_to_the_column(self):
        PackageLimit.objects.filter(package=self.package, key="max_students").delete()
        self._add_students(249)
        check_limit(self.school, "students")
        self._add_students(1)
        with self.assertRaises(PermissionDenied):
            check_limit(self.school, "students")

    def test_no_subscription_blocks_the_request(self):
        Subscription.objects.filter(school=self.school).delete()
        with self.assertRaises(PermissionDenied) as ctx:
            check_limit(self.school, "students")
        self.assertIn("No active subscription", str(ctx.exception))

    def test_locked_subscription_blocks_the_request(self):
        Subscription.objects.filter(school=self.school).update(
            status=Subscription.Status.LOCKED
        )
        with self.assertRaises(PermissionDenied) as ctx:
            check_limit(self.school, "students")
        self.assertIn("expired", str(ctx.exception))


class StudentCreateQuotaGateTests(APITestCase):
    """The quota has to be wired into the create path, not just be implemented."""

    def setUp(self):
        self.school = create_school(name="Quota Gate School", code="QG")
        self.admin = create_admin_user(self.school)
        self.url = reverse("student-list")
        self.package = Package.objects.create(
            name="Lite",
            code="lite-gate",
            price="100.00",
            billing_period=Package.BillingPeriod.TERM,
            maximum_students=250,
        )
        PackageLimit.objects.create(
            package=self.package,
            key="max_students",
            name="Maximum Students",
            value=1,
        )
        Subscription.objects.create(
            school=self.school,
            plan=self.package,
            status=Subscription.Status.ACTIVE,
            start_date="2020-01-01T00:00:00Z",
            end_date="2099-01-01T00:00:00Z",
            is_paid=True,
            is_current=True,
        )
        self.client.force_authenticate(self.admin)

    def _payload(self, first_name="Ada"):
        return {
            "first_name": first_name,
            "last_name": "Lovelace",
            "gender": Student.Gender.FEMALE,
            "email": f"{first_name.lower()}@quota-gate.com",
        }

    def test_student_is_created_below_the_cap(self):
        response = self.client.post(self.url, self._payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_student_creation_is_refused_at_the_cap(self):
        self.assertEqual(
            self.client.post(self.url, self._payload(), format="json").status_code,
            status.HTTP_201_CREATED,
        )
        response = self.client.post(self.url, self._payload("Grace"), format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Student.objects.filter(school=self.school).count(), 1)


class StudentExportGateTests(APITestCase):
    """The export gate has to deny a real request, not just sit in the list."""

    def setUp(self):
        self.school = create_school(name="Export Gate School", code="EG")
        self.admin = create_admin_user(self.school)
        self.url = reverse("student-export")
        self.package = Package.objects.create(
            name="Lite",
            code="lite-export",
            price="100.00",
            billing_period=Package.BillingPeriod.TERM,
            maximum_students=250,
        )
        Subscription.objects.create(
            school=self.school,
            plan=self.package,
            status=Subscription.Status.ACTIVE,
            start_date="2020-01-01T00:00:00Z",
            end_date="2099-01-01T00:00:00Z",
            is_paid=True,
            is_current=True,
        )
        self.client.force_authenticate(self.admin)

    def _grant_export(self, code="export", package=None):
        feature, _ = Feature.objects.get_or_create(
            code=code,
            defaults={"name": code, "category": "core", "is_active": True},
        )
        PackageFeature.objects.create(
            package=package or self.package, feature=feature, is_enabled=True
        )

    def test_export_is_refused_without_the_feature(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("Upgrade to Advantage", response.data["message"])

    def test_export_is_allowed_once_the_feature_is_granted(self):
        self._grant_export()
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_200_OK)

    def test_export_is_refused_while_the_subscription_is_locked(self):
        self._grant_export()
        Subscription.objects.filter(school=self.school).update(
            status=Subscription.Status.LOCKED
        )
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("expired", response.data["message"])


class ClassBulkStudentsViewTests(APITestCase):
    """Bulk import into one class: parsing, persistence, photos and errors."""

    BASE_HEADERS = ["first_name", "last_name", "date_of_birth", "gender"]

    def setUp(self):
        self.temp_media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.temp_media, True)
        override = override_settings(MEDIA_ROOT=self.temp_media)
        override.enable()
        self.addCleanup(override.disable)

        self.school = create_school(name="Bulk School", code="BULK")
        self.admin = create_admin_user(self.school, email="bulk-admin@example.com")
        self.client.force_authenticate(self.admin)

        self.year = AcademicYear.objects.create(
            school=self.school, name="2026",
            start_date=date(2026, 1, 1), end_date=date(2026, 12, 31),
        )
        self.term = Term.objects.create(
            school=self.school, academic_year=self.year, name="term_1",
            start_date=date(2026, 1, 1), end_date=date(2026, 4, 1),
            is_current=True,
        )
        self.klass = Class.objects.create(school=self.school, name="Primary 1")
        self.url = reverse("student-class-bulk")

    # ── helpers ────────────────────────────────────────────────────

    def _xlsx(self, rows, headers=None):
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.append(headers or self.BASE_HEADERS)
        for row in rows:
            sheet.append(row)
        buffer = io.BytesIO()
        workbook.save(buffer)
        buffer.seek(0)
        return SimpleUploadedFile(
            "students.xlsx",
            buffer.getvalue(),
            content_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
        )

    def _zip(self, files, name="photos.zip"):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            for filename, content in files.items():
                archive.writestr(filename, content)
        buffer.seek(0)
        return SimpleUploadedFile(name, buffer.getvalue(), content_type="application/zip")

    def _post(self, xlsx=None, class_id=None, photos=None):
        data = {"class_id": str(class_id or self.klass.id)}
        if xlsx is not None:
            data["file"] = xlsx
        if photos is not None:
            data["photos"] = photos
        return self.client.post(self.url, data, format="multipart")

    # ── happy path ─────────────────────────────────────────────────

    def test_successful_import_creates_students_guardians_and_enrollments(self):
        headers = self.BASE_HEADERS + [
            "guardian_first_name",
            "guardian_last_name",
            "guardian_relationship",
            "guardian_phone",
        ]
        rows = [
            ["Ekow", "Mensah", "2010-05-14", "male", "Kwame", "Mensah", "father", "0244000002"],
            ["Ama", "Boakye", "2011-03-02", "female"],
        ]

        response = self._post(xlsx=self._xlsx(rows, headers))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        summary = response.data["data"]["summary"]
        self.assertEqual(summary["class_name"], "Primary 1")
        self.assertEqual(summary["academic_year"], "2026")
        self.assertEqual(summary["total_submitted"], 2)
        self.assertEqual(summary["created"], 2)
        self.assertEqual(summary["failed"], 0)
        self.assertEqual(summary["success_rate"], "100%")

        self.assertEqual(Student.objects.filter(school=self.school).count(), 2)
        self.assertEqual(Guardian.objects.filter(school=self.school).count(), 1)
        self.assertEqual(Enrollment.objects.filter(klass=self.klass).count(), 2)
        self.assertTrue(
            all(e.academic_year_id == self.year.id for e in Enrollment.objects.all())
        )

        log = AuditLog.objects.get(resource="Student")
        self.assertEqual(log.metadata["created_count"], 2)
        self.assertEqual(log.metadata["class_id"], str(self.klass.id))

    def test_photo_in_zip_is_attached_to_the_student(self):
        headers = self.BASE_HEADERS + ["photo_filename"]
        rows = [["Ada", "Lovelace", "2015-01-01", "female", "ada.jpg"]]

        response = self._post(
            xlsx=self._xlsx(rows, headers),
            photos=self._zip({"ada.jpg": b"fake-image-bytes"}),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        student = Student.objects.get(first_name="Ada")
        self.assertTrue(student.profile_photo)
        self.assertTrue(student.profile_photo.name.endswith("ada.jpg"))

    # ── partial / complete failures ────────────────────────────────

    def test_partial_failure_reports_valid_and_invalid_rows(self):
        rows = [
            ["Ekow", "Mensah", "2010-05-14", "male"],
            ["Bad", "Row", "not-a-date", "alien"],
        ]

        response = self._post(xlsx=self._xlsx(rows))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]
        self.assertEqual(data["summary"]["created"], 1)
        self.assertEqual(data["summary"]["failed"], 1)
        self.assertEqual(data["summary"]["total_submitted"], 2)
        self.assertEqual(len(data["created"]), 1)
        self.assertEqual(len(data["failed"]), 1)
        self.assertIn("errors", data["failed"][0])

    def test_all_rows_invalid_returns_400_with_parse_errors(self):
        rows = [["", "", "", "alien"]]

        response = self._post(xlsx=self._xlsx(rows))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["message"], "All rows failed validation.")
        summary = response.data["errors"]["summary"]
        self.assertEqual(summary["created"], 0)
        self.assertEqual(summary["failed"], 1)
        self.assertEqual(len(summary["parse_errors"]), 1)

    # ── request validation ─────────────────────────────────────────

    def test_missing_current_term_returns_400(self):
        Term.objects.filter(pk=self.term.pk).update(is_current=False)

        response = self._post(
            xlsx=self._xlsx([["Ekow", "Mensah", "2010-05-14", "male"]])
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("No active academic year", response.data["message"])

    def test_missing_file_returns_400(self):
        response = self._post()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("No file uploaded", response.data["message"])

    def test_non_xlsx_file_returns_400(self):
        bad_file = SimpleUploadedFile("students.csv", b"a,b,c", content_type="text/csv")

        response = self._post(xlsx=bad_file)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Invalid file type", response.data["message"])

    def test_unknown_class_returns_400(self):
        import uuid

        response = self._post(
            xlsx=self._xlsx([["Ekow", "Mensah", "2010-05-14", "male"]]),
            class_id=uuid.uuid4(),
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("class_id", response.data["errors"])

    def test_foreign_school_class_is_rejected(self):
        other_school = create_school(name="Other School", code="OTHER")
        foreign_class = Class.objects.create(school=other_school, name="Foreign")

        response = self._post(
            xlsx=self._xlsx([["Ekow", "Mensah", "2010-05-14", "male"]]),
            class_id=foreign_class.id,
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("class_id", response.data["errors"])

    # ── photo archive validation ───────────────────────────────────

    def test_non_zip_photos_returns_400(self):
        photos = SimpleUploadedFile("notes.txt", b"nope", content_type="text/plain")

        response = self._post(
            xlsx=self._xlsx([["Ekow", "Mensah", "2010-05-14", "male"]]),
            photos=photos,
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn(".zip", response.data["message"])

    def test_corrupt_zip_returns_400(self):
        photos = SimpleUploadedFile(
            "photos.zip", b"definitely-not-a-zip", content_type="application/zip"
        )

        response = self._post(
            xlsx=self._xlsx([["Ekow", "Mensah", "2010-05-14", "male"]]),
            photos=photos,
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Invalid ZIP file", response.data["message"])

    def test_zip_slip_member_is_rejected(self):
        photos = self._zip({"../evil.txt": b"escape"})

        response = self._post(
            xlsx=self._xlsx([["Ekow", "Mensah", "2010-05-14", "male"]]),
            photos=photos,
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Invalid ZIP file", response.data["message"])
        self.assertEqual(Student.objects.filter(school=self.school).count(), 0)

    # ── template download ──────────────────────────────────────────

    def test_get_downloads_the_excel_template(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn("spreadsheetml.sheet", response["Content-Type"])
