from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

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

    def test_rejects_student_from_another_school_and_rolls_back(self):
        payload = self._payload(students=[
            {"student": str(self.student_a.pk), "relationship": "father"},
            {"student": str(self.foreign_student.pk), "relationship": "father"},
        ])

        with self.assertRaises(ValueError):
            self.service.create_guardian(self._validated(payload), self.school)

        self.assertEqual(Guardian.objects.count(), 0)
        self.assertEqual(GuardianStudent.objects.count(), 0)
        self.assertEqual(User.objects.filter(email="efua@example.com").count(), 0)

    def test_rejects_duplicate_students(self):
        payload = self._payload(students=[
            {"student": str(self.student_a.pk), "relationship": "mother"},
            {"student": str(self.student_a.pk), "relationship": "father"},
        ])

        serializer = GuardianSerializer(data=payload)

        self.assertFalse(serializer.is_valid())
        self.assertIn("students", serializer.errors)

    def test_requires_valid_relationship(self):
        payload = self._payload(students=[
            {"student": str(self.student_a.pk), "relationship": "neighbour"},
        ])

        serializer = GuardianSerializer(data=payload)

        self.assertFalse(serializer.is_valid())
        self.assertIn("students", serializer.errors)


class GuardianEndpointTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Test School", school_code="TST")
        self.other_school = School.objects.create(name="Other School", school_code="OTH")
        self.admin = User.objects.create_user(
            email="admin@example.com", password="x", first_name="Ad", last_name="Min",
            role=User.Role.ADMIN, school=self.school,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

        self.ama = self._student(self.school, "Ama")
        self.kofi = self._student(self.school, "Kofi")
        self.kwame = self._student(self.school, "Kwame")
        self.foreign = self._student(self.other_school, "Yaw")

        self.guardian = GuardianService().create_guardian(
            {
                "first_name": "Efua", "last_name": "Mensah", "email": "efua@example.com",
                "phone": "0240000000", "gender": "female",
                "students": [{"student": self.ama, "relationship": "mother"}],
            },
            self.school,
        )
        self.url = reverse("guardian-account-detail", args=[self.guardian.pk])

    @staticmethod
    def _student(school, first_name):
        return Student.objects.create(
            school=school, first_name=first_name, last_name="Mensah", gender="male"
        )

    def _links(self, guardian=None):
        return {
            link.student_id
            for link in GuardianStudent.objects.filter(guardian=guardian or self.guardian)
        }

    def test_retrieve_returns_linked_students(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertEqual(data["email"], "efua@example.com")
        self.assertEqual(len(data["students"]), 1)
        self.assertEqual(data["students"][0]["full_name"], "Ama Mensah")
        self.assertEqual(data["students"][0]["relationship"], "mother")

    def test_guardian_from_another_school_is_not_found(self):
        other_user = User.objects.create_user(
            email="o@example.com", password="x", first_name="O", last_name="A",
            role=User.Role.ADMIN, school=self.other_school,
        )
        client = APIClient()
        client.force_authenticate(other_user)

        self.assertEqual(client.get(self.url).status_code, 404)
        self.assertEqual(client.delete(self.url).status_code, 404)
        self.assertEqual(
            client.post(self.url + "students/unlink/", {"students": [str(self.ama.pk)]}, format="json").status_code,
            404,
        )

    def test_patch_updates_guardian_and_login_account(self):
        response = self.client.patch(
            self.url, {"first_name": "Efua2", "phone": "0551111111", "email": "new@example.com"},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.guardian.refresh_from_db()
        user = User.objects.get(pk=self.guardian.user_account_id)
        self.assertEqual(self.guardian.first_name, "Efua2")
        self.assertEqual(user.first_name, "Efua2")
        self.assertEqual(user.phone, "0551111111")
        self.assertEqual(user.email, "new@example.com")

    def test_patch_rejects_email_used_by_another_user(self):
        response = self.client.patch(self.url, {"email": "admin@example.com"}, format="json")

        self.assertEqual(response.status_code, 400)
        self.guardian.refresh_from_db()
        self.assertEqual(self.guardian.email, "efua@example.com")

    def test_patch_ignores_students_field(self):
        self.client.patch(
            self.url,
            {"students": [{"student": str(self.kofi.pk), "relationship": "mother"}]},
            format="json",
        )

        self.assertEqual(self._links(), {self.ama.pk})

    def test_delete_removes_guardian_links_and_login(self):
        user_id = self.guardian.user_account_id

        response = self.client.delete(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Guardian.objects.filter(pk=self.guardian.pk).exists())
        self.assertFalse(GuardianStudent.objects.exists())
        self.assertFalse(User.objects.filter(pk=user_id).exists())
        self.assertTrue(Student.objects.filter(pk=self.ama.pk).exists())

    def test_bulk_link_students(self):
        response = self.client.post(
            self.url + "students/link/",
            {"students": [
                {"student": str(self.kofi.pk), "relationship": "mother"},
                {"student": str(self.kwame.pk), "relationship": "mother"},
            ]},
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(self._links(), {self.ama.pk, self.kofi.pk, self.kwame.pk})
        self.assertEqual(len(response.data["data"]["students"]), 3)

    def test_link_is_all_or_nothing_when_a_student_is_already_linked(self):
        response = self.client.post(
            self.url + "students/link/",
            {"students": [
                {"student": str(self.kofi.pk), "relationship": "mother"},
                {"student": str(self.ama.pk), "relationship": "father"},
            ]},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self._links(), {self.ama.pk})

    def test_link_rejects_student_from_another_school(self):
        response = self.client.post(
            self.url + "students/link/",
            {"students": [{"student": str(self.foreign.pk), "relationship": "mother"}]},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self._links(), {self.ama.pk})

    def test_link_requires_at_least_one_student(self):
        response = self.client.post(self.url + "students/link/", {"students": []}, format="json")

        self.assertEqual(response.status_code, 400)

    def test_bulk_unlink_students(self):
        GuardianService().link_students(self.guardian, [
            {"student": self.kofi, "relationship": "mother"},
            {"student": self.kwame, "relationship": "mother"},
        ])

        response = self.client.post(
            self.url + "students/unlink/",
            {"students": [str(self.ama.pk), str(self.kofi.pk)]},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self._links(), {self.kwame.pk})
        self.assertEqual(len(response.data["data"]["students"]), 1)
        self.assertTrue(Student.objects.filter(pk=self.ama.pk).exists())

    def test_unlink_is_all_or_nothing_when_a_student_is_not_linked(self):
        response = self.client.post(
            self.url + "students/unlink/",
            {"students": [str(self.ama.pk), str(self.kofi.pk)]},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self._links(), {self.ama.pk})


class MyStudentsEndpointTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Test School", school_code="TST")
        self.ama = self._student("Ama")
        self.kofi = self._student("Kofi")
        self.unrelated = self._student("Yaw")
        service = GuardianService()
        self.guardian = service.create_guardian(
            {
                "first_name": "Efua", "last_name": "Mensah", "email": "efua@example.com",
                "phone": "0240000000", "gender": "female",
                "students": [
                    {"student": self.ama, "relationship": "mother"},
                    {"student": self.kofi, "relationship": "mother"},
                ],
            },
            self.school,
        )
        service.create_guardian(
            {
                "first_name": "Other", "last_name": "Parent", "email": "other@example.com",
                "phone": "0240000001", "gender": "male",
                "students": [{"student": self.unrelated, "relationship": "father"}],
            },
            self.school,
        )
        self.url = reverse("guardian-account-my-students")
        self.client = APIClient()

    def _student(self, first_name):
        return Student.objects.create(
            school=self.school, first_name=first_name, last_name="Mensah", gender="male"
        )

    def test_guardian_gets_only_their_students_unpaginated(self):
        self.client.force_authenticate(self.guardian.user_account)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertIsInstance(data, list)
        self.assertEqual([row["full_name"] for row in data], ["Ama Mensah", "Kofi Mensah"])
        self.assertEqual(
            set(data[0]),
            {"id", "student_id", "full_name", "profile_photo", "school"},
        )
        self.assertEqual(data[0]["school"], {"id": str(self.school.pk), "name": "Test School"})
        self.assertEqual(data[0]["student_id"], self.ama.student_id)
        self.assertIsNone(data[0]["profile_photo"])

    def test_returns_all_students_without_a_page_limit(self):
        for i in range(30):
            student = self._student(f"Child{i:02d}")
            GuardianService().link_students(
                self.guardian, [{"student": student, "relationship": "mother"}]
            )
        self.client.force_authenticate(self.guardian.user_account)

        response = self.client.get(self.url)

        self.assertEqual(len(response.data["data"]), 32)

    def test_search_filters_by_name(self):
        self.client.force_authenticate(self.guardian.user_account)

        response = self.client.get(self.url, {"search": "kofi"})

        self.assertEqual([row["full_name"] for row in response.data["data"]], ["Kofi Mensah"])

    def test_non_guardian_is_forbidden(self):
        admin = User.objects.create_user(
            email="admin@example.com", password="x", first_name="Ad", last_name="Min",
            role=User.Role.ADMIN, school=self.school,
        )
        self.client.force_authenticate(admin)

        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_anonymous_is_rejected(self):
        self.assertIn(self.client.get(self.url).status_code, (401, 403))
