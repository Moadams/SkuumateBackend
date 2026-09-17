from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from academics.models import AcademicYear, Term
from schools.models import School
from schools.services.onboarding import OnboardingService
from schools.services.school_details import SchoolDetailsService
from schools.services.term_progress import TermProgressService
from staff.management.commands.seed_permissions import SYSTEM_POSITIONS
from staff.models import PermissionKey, StaffPosition

User = get_user_model()


class TermProgressServiceTests(TestCase):

    def setUp(self):
        self.school = School.objects.create(name="Term School")
        self.year = AcademicYear.objects.create(
            school=self.school,
            name="2026/27",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )
        today = date.today()
        self.term = Term.objects.create(
            school=self.school,
            academic_year=self.year,
            name=Term.TermName.TERM_1,
            start_date=today - timedelta(days=10),
            end_date=today + timedelta(days=19),
        )

    def test_build_returns_none_for_missing_term(self):
        self.assertIsNone(TermProgressService.build(None))

    def test_build_computes_weeks_and_progress(self):
        progress = TermProgressService.build(self.term, today=date.today())
        self.assertEqual(progress.days_remaining, 19)
        self.assertEqual(progress.total_weeks, 4)
        self.assertEqual(progress.current_week, 2)
        self.assertEqual(progress.progress_percent, 34)


class OnboardingServiceTests(TestCase):

    def setUp(self):
        self.school = School.objects.create(name="Onboarding School")

    def test_not_complete_when_steps_missing(self):
        dto = OnboardingService.build(self.school)
        self.assertFalse(dto.onboarding_completed)
        self.assertEqual(dto.completed_count, 0)

    def test_complete_when_all_steps_present(self):
        year = AcademicYear.objects.create(
            school=self.school,
            name="2026/27",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )
        Term.objects.create(
            school=self.school,
            academic_year=year,
            name=Term.TermName.TERM_1,
            start_date=date(2026, 1, 10),
            end_date=date(2026, 4, 10),
        )
        self.school.classes.create(name="Primary 1")
        self.school.subjects.create(name="Mathematics")
        self._create_trial_subscription()

        dto = OnboardingService.build(self.school)
        self.assertTrue(dto.onboarding_completed)
        self.assertEqual(dto.completed_count, dto.total_steps)

    def _create_trial_subscription(self):
        from datetime import timedelta

        from django.utils import timezone

        from subscriptions.models import Package, Subscription

        package = Package.objects.create(name="Lite Test", code="lite-test")
        Subscription.objects.create(
            school=self.school,
            plan=package,
            status=Subscription.Status.TRIAL,
            end_date=timezone.now() + timedelta(days=90),
        )


class SchoolDetailsServiceTests(TestCase):

    def setUp(self):
        self.school = School.objects.create(
            name="Details School", school_code="DSCH"
        )
        self.admin = User.objects.create_user(
            email="admin@school.com",
            password="pass",
            first_name="Ada",
            last_name="Admin",
            role=User.Role.ADMIN,
            school=self.school,
        )

    def test_returns_full_dto_with_all_sections(self):
        dto = SchoolDetailsService().get_details(self.school)
        self.assertEqual(dto.school.name, "Details School")
        self.assertIsNone(dto.subscription.status)
        self.assertEqual(dto.students.totals.total, 0)
        self.assertEqual(dto.staff.totals.total, 0)
        self.assertEqual(dto.finance.outstanding_balance, 0)
        self.assertEqual(dto.attendance.today.total, 0)
        self.assertEqual(dto.exams.reports.total, 0)
        self.assertFalse(dto.onboarding.onboarding_completed)

    def test_endpoint_returns_200_for_admin(self):
        client = APIClient()
        client.force_authenticate(user=self.admin)
        resp = client.get("/api/v1/schools/me/details/")
        self.assertEqual(resp.status_code, 200)

        payload = resp.json()["data"]
        for section in (
            "school", "subscription", "academics", "staff", "students",
            "finance", "attendance", "communications", "exams", "onboarding",
        ):
            self.assertIn(section, payload)

    def test_endpoint_rejects_non_admin(self):
        teacher = User.objects.create_user(
            email="teacher@school.com",
            password="pass",
            first_name="Tea",
            last_name="Cher",
            role=User.Role.TEACHER,
            school=self.school,
        )
        client = APIClient()
        client.force_authenticate(user=teacher)
        resp = client.get("/api/v1/schools/me/details/")
        self.assertEqual(resp.status_code, 403)


class SchoolCreateSystemPositionsTests(TestCase):
    """Regression: creating a school seeds system positions via
    StaffPosition.permissions.set() (M2M), not direct assignment."""

    def setUp(self):
        # Seed a minimal permission registry so seeded keys resolve.
        for pos_data in SYSTEM_POSITIONS:
            for key in (pos_data["keys"] or []):
                PermissionKey.objects.get_or_create(
                    key=key,
                    defaults={
                        "label": key,
                        "module": key.split(".")[0],
                    },
                )
        self.superadmin = User.objects.create_user(
            email="superadmin@platform.com",
            password="pass1234",
            is_superuser=True,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.superadmin)

    def test_create_school_seeds_system_positions_without_typeerror(self):
        resp = self.client.post(
            reverse("school-list"),
            {
                "name": "Riverside Academy",
                "email": "info@riverside.edu",
                "phone": "+233241112233",
                "school_code": "RIV-2026",
                "admin_first_name": "Kwame",
                "admin_last_name": "Mensah",
                "admin_email": "kwame@riverside.edu",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201)

        school = School.objects.get(name="Riverside Academy")
        positions = StaffPosition.objects.filter(school=school)
        self.assertEqual(positions.count(), len(SYSTEM_POSITIONS))
        self.assertTrue(all(p.is_system for p in positions))

    def test_administrator_position_gets_all_seeded_keys(self):
        resp = self.client.post(
            reverse("school-list"),
            {
                "name": "Sunrise School",
                "email": "info@sunrise.edu",
                "phone": "+233244556677",
                "school_code": "SUN-2026",
                "admin_first_name": "Ama",
                "admin_last_name": "Asante",
                "admin_email": "ama@sunrise.edu",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201)

        school = School.objects.get(name="Sunrise School")
        seeded_keys = {
            key
            for pos_data in SYSTEM_POSITIONS
            for key in (pos_data["keys"] or [])
        }
        admin_position = StaffPosition.objects.get(
            school=school, name="Administrator"
        )
        self.assertEqual(
            set(admin_position.permissions.values_list("key", flat=True)),
            seeded_keys,
        )