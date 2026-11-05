from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import User
from guardian.models import Guardian, GuardianStudent
from guardian.serializers import GuardianSerializer
from guardian.services.guardian_service import GuardianService
from schools.models import School
from students.models import Student


class CreateGuardianWithStudentsTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Test School", school_code="TST")
        self.other_school = School.objects.create(name="Other School", school_code="OTH")
        self.student_a = self._student(self.school, "Ama")
        self.student_b = self._student(self.school, "Kofi")
        self.foreign_student = self._student(self.other_school, "Yaw")
        self.service = GuardianService()

    @staticmethod
    def _student(school, first_name):
        return Student.objects.create(
            school=school, first_name=first_name, last_name="Mensah", gender="male"
        )

    def _payload(self, **extra):
        return {
            "first_name": "Efua",
            "last_name": "Mensah",
            "email": "efua@example.com",
            "phone": "0240000000",
            "gender": "female",
            **extra,
        }

    def _validated(self, payload):
        serializer = GuardianSerializer(data=payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        return serializer.validated_data

    def test_students_are_optional(self):
        guardian = self.service.create_guardian(self._validated(self._payload()), self.school)

        self.assertEqual(guardian.user_account.role, User.Role.GUARDIAN)
        self.assertEqual(GuardianStudent.objects.count(), 0)

    def test_assigns_students_on_creation(self):
        payload = self._payload(students=[
            {"student": str(self.student_a.pk), "relationship": "mother"},
            {"student": str(self.student_b.pk), "relationship": "mother"},
        ])

        guardian = self.service.create_guardian(self._validated(payload), self.school)

        links = GuardianStudent.objects.filter(guardian=guardian)
        self.assertEqual(links.count(), 2)
        self.assertEqual(
            {link.student_id for link in links}, {self.student_a.pk, self.student_b.pk}
        )
        self.assertTrue(all(link.school_id == self.school.pk for link in links))
        self.assertEqual(len(GuardianSerializer(guardian).data["assigned_students"]), 2)

    def test_rejects_duplicate_students(self):
        payload = self._payload(students=[
            {"student": str(self.student_a.pk), "relationship": "mother"},
            {"student": str(self.student_a.pk), "relationship": "father"},
        ])

        serializer = GuardianSerializer(data=payload)

        self.assertFalse(serializer.is_valid())
        self.assertIn("students", serializer.errors)


class GuardianListScopingTests(APITestCase):
    """The guardian list must never leak another school's records."""

    def setUp(self):
        self.school = School.objects.create(
            name="Alpha School", school_code="AL", email="alpha@example.com"
        )
        self.other_school = School.objects.create(
            name="Beta School", school_code="BE", email="beta@example.com"
        )
        self.admin = User.objects.create_user(
            email="admin@alpha.com",
            password="password123",
            first_name="Alpha",
            last_name="Admin",
            role=User.Role.ADMIN,
            school=self.school,
        )
        self.own_guardian = self._guardian(
            self.school, "own@alpha.com", "Own", "Guardian"
        )
        self.foreign_guardian = self._guardian(
            self.other_school, "foreign@beta.com", "Foreign", "Guardian"
        )
        self.client.force_authenticate(self.admin)

    @staticmethod
    def _guardian(school, email, first_name, last_name):
        account = User.objects.create_user(
            email=email,
            password="password123",
            first_name=first_name,
            last_name=last_name,
            role=User.Role.GUARDIAN,
            school=school,
        )
        return Guardian.objects.create(
            school=school,
            user_account=account,
            first_name=first_name,
            last_name=last_name,
            phone="0240000000",
            gender="female",
        )

    def test_list_returns_only_the_callers_school(self):
        response = self.client.get(reverse("guardian-account-list-create"))

        self.assertEqual(response.status_code, 200)
        ids = {row["id"] for row in response.json()["data"]["results"]}
        self.assertEqual(ids, {str(self.own_guardian.id)})
        self.assertNotIn(str(self.foreign_guardian.id), ids)
