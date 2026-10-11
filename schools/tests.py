from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from academics.models import AcademicYear, Term
from exams.models import AssessmentType, ReportScheme
from schools.models import School
from schools.services.onboarding import OnboardingService
from schools.services.school_details import SchoolDetailsService
from schools.services.term_progress import TermProgressService
from staff.management.commands.seed_permissions import SYSTEM_POSITIONS
from staff.models import PermissionKey, StaffPosition

User = get_user_model()


class SchoolDeletionTests(TestCase):

    def test_force_delete_removes_report_schemes_before_assessment_types(self):
        school = School.objects.create(name="Deletion School")
        assessment_type = AssessmentType.objects.create(
            school=school,
            name="Main Exam",
            max_score=100,
        )
        ReportScheme.objects.create(
            school=school,
            name="Academic Sheet",
            main_exam=assessment_type,
        )

        school.force_delete()

        self.assertFalse(School.objects.filter(pk=school.pk).exists())
        self.assertFalse(AssessmentType.objects.filter(pk=assessment_type.pk).exists())
        self.assertFalse(ReportScheme.objects.filter(school_id=school.pk).exists())


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

    STEPS = OnboardingService.STEPS

    def setUp(self):
        self.school = School.objects.create(name="Onboarding School")

    def _complete_profile(self):
        self.school.email = "info@onboard.edu"
        self.school.phone = "+233240000000"
        self.school.address = "Accra"
        self.school.city = "Accra"
        self.school.school_code = "OBS-001"
        self.school.save()

    def _create_current_year_term(self):
        year = AcademicYear.objects.create(
            school=self.school,
            name="2026/27",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            is_current=True,
        )
        term = Term.objects.create(
            school=self.school,
            academic_year=year,
            name=Term.TermName.TERM_1,
            start_date=date(2026, 1, 10),
            end_date=date(2026, 4, 10),
        )
        term.is_current = True
        term.save()
        return year, term

    def test_not_complete_when_steps_missing(self):
        dto = OnboardingService.build(self.school)
        self.assertFalse(dto.onboarding_completed)
        self.assertEqual(dto.completed_count, 0)
        self.assertEqual(dto.current_step, "school_profile")
        self.assertFalse(dto.profile["done"])
        self.assertIn("email", dto.profile["missing_fields"])
        self.assertIn("school_code", dto.profile["missing_fields"])

    def test_blank_profile_fields_count_as_incomplete(self):
        self.school.email = ""
        self.school.school_code = "  "
        self.school.save(update_fields=["email", "school_code"])
        steps = OnboardingService.steps(self.school)
        self.assertFalse(steps["school_profile"])

    def test_complete_when_all_steps_present(self):
        self._complete_profile()
        self._create_current_year_term()
        self.school.classes.create(name="Primary 1")
        self.school.subjects.create(name="Mathematics")
        self._create_trial_subscription()

        dto = OnboardingService.build(self.school)
        self.assertTrue(dto.onboarding_completed)
        self.assertEqual(dto.completed_count, dto.total_steps)
        self.assertEqual(dto.total_steps, len(self.STEPS))
        self.assertIsNone(dto.current_step)
        self.assertTrue(dto.profile["done"])

    def test_non_current_year_and_term_do_not_count(self):
        self._complete_profile()
        AcademicYear.objects.create(
            school=self.school,
            name="2025/26",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
        )
        self.school.classes.create(name="Primary 1")
        self.school.subjects.create(name="Mathematics")
        self._create_trial_subscription()

        dto = OnboardingService.build(self.school)
        self.assertFalse(dto.completed_count >= dto.total_steps)
        self.assertFalse(dto.steps["academic_year"])
        self.assertFalse(dto.steps["term"])
        self.assertEqual(dto.current_step, "academic_year")

    def test_is_current_term_counts_only_current_terms(self):
        self._complete_profile()
        year = AcademicYear.objects.create(
            school=self.school,
            name="2026/27",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            is_current=True,
        )
        Term.objects.create(
            school=self.school,
            academic_year=year,
            name=Term.TermName.TERM_1,
            start_date=date(2026, 1, 10),
            end_date=date(2026, 4, 10),
        )
        term2 = Term.objects.create(
            school=self.school,
            academic_year=year,
            name=Term.TermName.TERM_2,
            start_date=date(2026, 4, 20),
            end_date=date(2026, 8, 20),
        )
        self.school.classes.create(name="Primary 1")
        self.school.subjects.create(name="Mathematics")
        self._create_trial_subscription()

        self.assertFalse(OnboardingService.build(self.school).steps["term"])

        term2.is_current = True
        term2.save()
        self.assertTrue(OnboardingService.build(self.school).steps["term"])

    def test_class_subject_step_requires_both(self):
        self._complete_profile()
        self._create_current_year_term()
        self.school.classes.create(name="Primary 1")  # no subject
        self._create_trial_subscription()

        dto = OnboardingService.build(self.school)
        self.assertFalse(dto.steps["class_subject"])
        self.assertEqual(dto.current_step, "class_subject")

    def test_resume_data_returns_saved_rows(self):
        self._complete_profile()
        self._create_current_year_term()
        self.school.classes.create(name="Primary 1")
        self.school.subjects.create(name="Mathematics")

        dto = OnboardingService.build(self.school, include_data=True)
        self.assertEqual(dto.data["school"]["school_code"], "OBS-001")
        self.assertEqual(len(dto.data["academic_years"]), 1)
        self.assertEqual(dto.data["academic_years"][0]["name"], "2026/27")
        self.assertEqual(len(dto.data["terms"]), 1)
        self.assertEqual(dto.data["classes"][0]["name"], "Primary 1")
        self.assertEqual(dto.data["subjects"][0]["name"], "Mathematics")

    def test_details_payload_excludes_resume_data(self):
        dto = OnboardingService.build(self.school)
        self.assertEqual(dto.data, {})

    def _create_trial_subscription(self):
        from datetime import timedelta

        from django.utils import timezone

        from subscriptions.models import Package, Subscription

        package = Package.objects.create(name="Lite Test", code="lite-test")
        Subscription.objects.create(
            school=self.school,
            plan=package,
            status=Subscription.Status.ACTIVE,
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

    def test_onboarding_status_endpoint_serializes_without_logo(self):
        """Regression: resume data must not leak ImageFieldFile into JSON."""
        client = APIClient()
        client.force_authenticate(user=self.admin)
        resp = client.get("/api/v1/schools/me/onboarding/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertIn("steps", data)
        self.assertIn("current_step", data)
        self.assertIsNone(data["data"]["school"]["logo"])


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