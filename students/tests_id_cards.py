"""Student ID card generation, QR and verification tests."""
import io
from datetime import date
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from academics.models import AcademicYear, Class, Term
from accounts.models import User
from schools.models import School
from students.models import Enrollment, Guardian, Student
from students.services import id_cards
from subscriptions.models import (
    Feature,
    Package,
    PackageFeature,
    Subscription,
)

# Smallest valid PNG (1x1, transparent) used to exercise the photo path.
TINY_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c63000100000500010d0a2db40000000049454e44ae"
    "426082"
)


def create_school(name="ID Card School", code="IDC"):
    return School.objects.create(
        name=name, school_code=code, email=f"{code.lower()}@example.com"
    )


def create_admin_user(school, email="idcard-admin@example.com"):
    return User.objects.create_user(
        email=email,
        password="password123",
        first_name="Ida",
        last_name="Admin",
        role=User.Role.ADMIN,
        school=school,
    )


class StudentIDCardTests(APITestCase):
    def setUp(self):
        self.school = create_school()
        self.admin = create_admin_user(self.school)
        self.package = Package.objects.create(
            name="Advantage",
            code="advantage-idc",
            price="1800.00",
            billing_period=Package.BillingPeriod.TERM,
            maximum_students=500,
        )
        feature, _ = Feature.objects.get_or_create(
            code="id_cards",
            defaults={
                "name": "Student ID Cards",
                "category": "students",
                "is_active": True,
            },
        )
        PackageFeature.objects.create(
            package=self.package, feature=feature, is_enabled=True
        )
        Subscription.objects.create(
            school=self.school,
            plan=self.package,
            status=Subscription.Status.ACTIVE,
            start_date=date(2020, 1, 1),
            end_date=date(2099, 1, 1),
            is_paid=True,
            is_current=True,
        )

        self.year = AcademicYear.objects.create(
            school=self.school, name="2025/2026",
            start_date=date(2025, 9, 1), end_date=date(2026, 7, 31),
            is_current=True,
        )
        self.term = Term.objects.create(
            school=self.school, academic_year=self.year, name=Term.TermName.TERM_1,
            start_date=date(2025, 9, 1), end_date=date(2025, 12, 20),
            is_current=True,
        )
        self.klass = Class.objects.create(school=self.school, name="Primary 5B")

        self.student = self._student("Ekow", "Mensah")
        self.student2 = self._student("Ama", "Owusu")
        for student in (self.student, self.student2):
            Enrollment.objects.create(
                school=self.school, student=student, klass=self.klass,
                academic_year=self.year, is_active=True,
            )

        Guardian.objects.create(
            student=self.student, school=self.school,
            first_name="Kwame", last_name="Mensah",
            relationship=Guardian.Relationship.FATHER if hasattr(
                Guardian, "Relationship"
            ) else "father",
            phone="0244000111", is_primary=True,
        )

    def _student(self, first, last, photo=False):
        return Student.objects.create(
            school=self.school, first_name=first, last_name=last,
            gender=Student.Gender.MALE, admission_date=date(2025, 9, 1),
            profile_photo=(
                SimpleUploadedFile("p.png", TINY_PNG, content_type="image/png")
                if photo else None
            ),
        )

    def _auth(self, user=None):
        self.client.force_authenticate(user or self.admin)

    # ── Generation ────────────────────────────────────────────────
    def test_single_card_returns_pdf(self):
        self._auth()
        response = self.client.get(
            reverse("student-id-card", kwargs={"pk": self.student.pk})
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn(self.student.student_id, response["Content-Disposition"])
        self.assertTrue(response.content.startswith(b"%PDF"))
        self.assertGreater(len(response.content), 10_000)

    def test_bulk_by_class_returns_pdf(self):
        self._auth()
        response = self.client.post(
            reverse("student-id-cards"),
            {"class_id": str(self.klass.pk)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_bulk_by_explicit_ids_returns_pdf(self):
        self._auth()
        response = self.client.post(
            reverse("student-id-cards"),
            {"student_ids": [str(self.student.pk)]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_bulk_batch_cap_is_enforced(self):
        self._auth()
        with patch("students.views.MAX_ID_CARD_BATCH", 1):
            response = self.client.post(
                reverse("student-id-cards"), {}, format="json"
            )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("maximum", response.json()["message"].lower())

    def test_bulk_with_no_matches_returns_400(self):
        self._auth()
        response = self.client.post(
            reverse("student-id-cards"),
            {"student_ids": ["00000000-0000-0000-0000-000000000000"]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_bulk_unknown_term_returns_404(self):
        self._auth()
        response = self.client.post(
            reverse("student-id-cards"),
            {"term_id": "00000000-0000-0000-0000-000000000000"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ── Feature gating ────────────────────────────────────────────
    def test_generation_requires_id_cards_feature(self):
        bare = Package.objects.create(
            name="Lite", code="lite-idc", price="1000.00",
            billing_period=Package.BillingPeriod.TERM,
        )
        PackageFeature.objects.filter(package=self.package).delete()
        Subscription.objects.filter(school=self.school).update(plan=bare)
        self._auth()
        response = self.client.get(
            reverse("student-id-card", kwargs={"pk": self.student.pk})
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # ── Verification ──────────────────────────────────────────────
    def test_verify_is_public_and_case_insensitive(self):
        response = self.client.get(
            reverse(
                "student-verify",
                kwargs={"student_id": self.student.student_id.lower()},
            )
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()["data"]
        self.assertEqual(data["student_id"], self.student.student_id)
        self.assertEqual(data["full_name"], self.student.full_name)
        self.assertEqual(data["class_name"], "Primary 5B")
        self.assertEqual(data["academic_year"], "2025/2026")
        self.assertTrue(data["is_active"])
        self.assertEqual(data["school"]["name"], self.school.name)

    def test_verify_hides_sensitive_fields(self):
        response = self.client.get(
            reverse("student-verify", kwargs={"student_id": self.student.student_id})
        )
        data = response.json()["data"]
        for leaked in ("date_of_birth", "address", "guardians", "email",
                       "phone_number", "previous_school"):
            self.assertNotIn(leaked, data)
        # Anonymous callers never receive the private photo either.
        self.assertIsNone(data["photo_url"])

    def test_verify_unknown_id_returns_404(self):
        response = self.client.get(
            reverse("student-verify", kwargs={"student_id": "NOPE-0000-0000"})
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_verify_exposes_photo_to_same_school_staff(self):
        student = self._student("Kojo", "Boateng", photo=True)
        response = self.client.get(
            reverse("student-verify", kwargs={"student_id": student.student_id})
        )
        # anonymous → no photo
        self.assertIsNone(response.json()["data"]["photo_url"])

        self._auth()
        response = self.client.get(
            reverse("student-verify", kwargs={"student_id": student.student_id})
        )
        self.assertIsNotNone(response.json()["data"]["photo_url"])

    # ── QR payload ────────────────────────────────────────────────
    def test_qr_encodes_raw_student_id(self):
        captured = []
        real_add_data = id_cards.qrcode.QRCode.add_data

        def spy(qr, data, *args, **kwargs):
            captured.append(data)
            return real_add_data(qr, data, *args, **kwargs)

        with patch.object(id_cards.qrcode.QRCode, "add_data", spy):
            id_cards.build_student_card_pdf(self.student, self.school)

        self.assertIn(self.student.student_id, captured)

    def test_pdf_contains_front_and_back_pages(self):
        buffer = id_cards.build_student_card_pdf(self.student, self.school)
        data = buffer.getvalue()
        # Pillow emits one "/MediaBox" per page; a card is front + back.
        self.assertEqual(data.count(b"/MediaBox"), 2)
