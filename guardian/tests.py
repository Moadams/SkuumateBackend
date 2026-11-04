from django.test import TestCase

from accounts.models import User
from guardian.models import GuardianStudent
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
