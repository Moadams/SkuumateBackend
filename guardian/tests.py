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
            {"id", "student_id", "full_name", "profile_photo", "school", "class_name"},
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


class MyStudentDetailEndpointTests(TestCase):
    def setUp(self):
        from datetime import date

        from academics.models import AcademicYear, Class
        from students.models import Enrollment

        self.school = School.objects.create(name="Test School", school_code="TST")
        self.ama = self._student("Ama")
        self.kofi = self._student("Kofi")
        self.stranger = self._student("Yaw")
        service = GuardianService()
        self.guardian = service.create_guardian(
            {
                "first_name": "Efua", "last_name": "Mensah", "email": "efua@example.com",
                "phone": "0240000000", "gender": "female",
                "students": [
                    {"student": self.ama, "relationship": "mother"},
                    {"student": self.kofi, "relationship": "grandparent"},
                ],
            },
            self.school,
        )
        service.create_guardian(
            {
                "first_name": "Other", "last_name": "Parent", "email": "other@example.com",
                "phone": "0240000001", "gender": "male",
                "students": [{"student": self.stranger, "relationship": "father"}],
            },
            self.school,
        )
        year = AcademicYear.objects.create(
            school=self.school, name="2026", is_current=True,
            start_date=date(2026, 1, 1), end_date=date(2026, 12, 31),
        )
        self.klass = Class.objects.create(school=self.school, name="Primary 3")
        Enrollment.objects.create(
            school=self.school, student=self.ama, klass=self.klass, academic_year=year
        )
        self.client = APIClient()
        self.client.force_authenticate(self.guardian.user_account)

    def _student(self, first_name):
        return Student.objects.create(
            school=self.school, first_name=first_name, last_name="Mensah", gender="female"
        )

    def _url(self, student):
        return reverse("guardian-account-my-student-detail", args=[student.pk])

    def test_returns_linked_student_with_relationship_and_current_class(self):
        response = self.client.get(self._url(self.ama))

        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertEqual(data["id"], str(self.ama.pk))
        self.assertEqual(data["student_id"], self.ama.student_id)
        self.assertEqual(data["full_name"], "Ama Mensah")
        self.assertEqual(data["school"], {"id": str(self.school.pk), "name": "Test School"})
        self.assertEqual(data["relationship"], "mother")
        self.assertEqual(data["current_enrollment"]["class_name"], "Primary 3")
        self.assertEqual(data["current_enrollment"]["academic_year_name"], "2026")
        self.assertIsNone(data["profile_photo"])

    def test_relationship_is_specific_to_each_student(self):
        data = self.client.get(self._url(self.kofi)).data["data"]

        self.assertEqual(data["relationship"], "grandparent")

    def test_student_without_current_enrollment_has_null_class(self):
        data = self.client.get(self._url(self.kofi)).data["data"]

        self.assertIsNone(data["current_enrollment"])

    def test_another_guardians_student_is_not_found(self):
        self.assertEqual(self.client.get(self._url(self.stranger)).status_code, 404)

    def test_unknown_student_is_not_found(self):
        import uuid

        url = reverse("guardian-account-my-student-detail", args=[uuid.uuid4()])

        self.assertEqual(self.client.get(url).status_code, 404)

    def test_unlinked_student_is_not_found_after_unlinking(self):
        GuardianService().unlink_students(self.guardian, [self.ama.pk])

        self.assertEqual(self.client.get(self._url(self.ama)).status_code, 404)

    def test_non_guardian_is_forbidden(self):
        admin = User.objects.create_user(
            email="admin@example.com", password="x", first_name="Ad", last_name="Min",
            role=User.Role.ADMIN, school=self.school,
        )
        self.client.force_authenticate(admin)

        self.assertEqual(self.client.get(self._url(self.ama)).status_code, 403)

    def test_anonymous_is_rejected(self):
        self.client.force_authenticate(None)

        self.assertIn(self.client.get(self._url(self.ama)).status_code, (401, 403))


class MyStudentReportDetailEndpointTests(TestCase):
    def setUp(self):
        from datetime import date

        from academics.models import AcademicYear, Class, Subject, Term
        from exams.models import (
            AssessmentType,
            ReportScheme,
            StudentReport,
            StudentReportSubjectScore,
        )

        self.school = School.objects.create(name="Test School", school_code="TST")
        self.other_school = School.objects.create(name="Other School", school_code="OTH")
        self.ama = self._student(self.school, "Ama")
        self.kofi = self._student(self.school, "Kofi")
        self.stranger = self._student(self.school, "Yaw")
        self.foreign = self._student(self.other_school, "Esi")

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
        self.other_guardian = service.create_guardian(
            {
                "first_name": "Other", "last_name": "Parent", "email": "other@example.com",
                "phone": "0240000001", "gender": "male",
                "students": [{"student": self.stranger, "relationship": "father"}],
            },
            self.school,
        )
        self.foreign_guardian = service.create_guardian(
            {
                "first_name": "Away", "last_name": "Parent", "email": "away@example.com",
                "phone": "0240000002", "gender": "female",
                "students": [{"student": self.foreign, "relationship": "mother"}],
            },
            self.other_school,
        )

        year = AcademicYear.objects.create(
            school=self.school, name="2026", is_current=True,
            start_date=date(2026, 1, 1), end_date=date(2026, 12, 31),
        )
        self.term = Term.objects.create(
            school=self.school, academic_year=year, name=Term.TermName.TERM_1,
            start_date=date(2026, 1, 5), end_date=date(2026, 4, 10),
        )
        self.klass = Class.objects.create(school=self.school, name="Primary 3")
        assessment = AssessmentType.objects.create(
            school=self.school, name="End of term exam", max_score=100
        )
        scheme = ReportScheme.objects.create(
            school=self.school, name="Primary scheme", main_exam=assessment,
        )

        self.ama_report = self._report(self.ama, scheme, StudentReport.ReportStatus.PUBLISHED)
        self.kofi_report = self._report(self.kofi, scheme, StudentReport.ReportStatus.DRAFT)
        self.stranger_report = self._report(
            self.stranger, scheme, StudentReport.ReportStatus.PUBLISHED
        )

        subject = Subject.objects.create(school=self.school, name="Mathematics", code="MTH")
        StudentReportSubjectScore.objects.create(
            student_report=self.ama_report, student=self.ama, subject=subject,
            exam_score=80, sba_score=40, total_score=88, grade="A", rank=1,
        )

        self.client = APIClient()
        self.client.force_authenticate(self.guardian.user_account)

    @staticmethod
    def _student(school, first_name):
        return Student.objects.create(
            school=school, first_name=first_name, last_name="Mensah", gender="female"
        )

    def _report(self, student, scheme, status):
        from exams.models import StudentReport

        return StudentReport.objects.create(
            school=self.school, student=student, academic_year=self.term.academic_year,
            term=self.term, student_class=self.klass, report_scheme=scheme,
            overall_score=88, overall_position=1, overall_attendance=55,
            total_school_days=60, status=status,
        )

    def _url(self, student, report):
        return reverse(
            "guardian-account-my-student-report-detail", args=[student.pk, report.pk]
        )

    def test_returns_published_report_with_subject_scores(self):
        response = self.client.get(self._url(self.ama, self.ama_report))

        self.assertEqual(response.status_code, 200, response.data)
        data = response.data["data"]
        self.assertEqual(data["id"], str(self.ama_report.pk))
        self.assertEqual(data["student_name"], "Ama Mensah")
        self.assertEqual(data["student_id"], self.ama.student_id)
        self.assertEqual(data["class_name"], "Primary 3")
        self.assertEqual(data["term_name"], "Term 1")
        self.assertEqual(data["academic_year_name"], "2026")
        self.assertEqual(len(data["subject_scores"]), 1)
        self.assertEqual(data["subject_scores"][0]["subject_name"], "Mathematics")
        self.assertEqual(data["subject_scores"][0]["grade"], "A")

    def test_unpublished_report_is_not_found(self):
        response = self.client.get(self._url(self.kofi, self.kofi_report))

        self.assertEqual(response.status_code, 404)

    def test_report_of_a_different_linked_student_is_not_found(self):
        response = self.client.get(self._url(self.ama, self.kofi_report))

        self.assertEqual(response.status_code, 404)

    def test_report_of_a_student_linked_to_another_guardian_is_not_found(self):
        response = self.client.get(self._url(self.stranger, self.stranger_report))

        self.assertEqual(response.status_code, 404)

    def test_guardian_from_another_school_is_not_found(self):
        self.client.force_authenticate(self.foreign_guardian.user_account)

        response = self.client.get(self._url(self.ama, self.ama_report))

        self.assertEqual(response.status_code, 404)

    def test_student_url_cannot_be_used_to_read_another_school_report(self):
        self.client.force_authenticate(self.foreign_guardian.user_account)

        response = self.client.get(self._url(self.foreign, self.ama_report))

        self.assertEqual(response.status_code, 404)

    def test_unknown_report_is_not_found(self):
        import uuid

        url = reverse(
            "guardian-account-my-student-report-detail",
            args=[self.ama.pk, uuid.uuid4()],
        )

        self.assertEqual(self.client.get(url).status_code, 404)

    def test_non_guardian_is_forbidden(self):
        admin = User.objects.create_user(
            email="admin@example.com", password="x", first_name="Ad", last_name="Min",
            role=User.Role.ADMIN, school=self.school,
        )
        self.client.force_authenticate(admin)

        response = self.client.get(self._url(self.ama, self.ama_report))

        self.assertEqual(response.status_code, 403)

    def test_anonymous_is_rejected(self):
        self.client.force_authenticate(None)

        response = self.client.get(self._url(self.ama, self.ama_report))

        self.assertIn(response.status_code, (401, 403))


class MyStudentInvoiceEndpointTests(TestCase):
    def setUp(self):
        from datetime import date

        from academics.models import AcademicYear, Class, Term
        from finance.models import FeeComponent, PaymentAllocation, SchoolFeeInvoice

        self.school = School.objects.create(name="Test School", school_code="TST")
        self.other_school = School.objects.create(name="Other School", school_code="OTH")
        self.ama = self._student(self.school, "Ama")
        self.kofi = self._student(self.school, "Kofi")
        self.stranger = self._student(self.school, "Yaw")
        self.foreign = self._student(self.other_school, "Esi")

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
                "students": [{"student": self.stranger, "relationship": "father"}],
            },
            self.school,
        )
        self.foreign_guardian = service.create_guardian(
            {
                "first_name": "Away", "last_name": "Parent", "email": "away@example.com",
                "phone": "0240000002", "gender": "female",
                "students": [{"student": self.foreign, "relationship": "mother"}],
            },
            self.other_school,
        )

        self.year = AcademicYear.objects.create(
            school=self.school, name="2026", is_current=True,
            start_date=date(2026, 1, 1), end_date=date(2026, 12, 31),
        )
        self.term_1 = self._term(self.year, Term.TermName.TERM_1, date(2026, 1, 5), date(2026, 4, 10))
        self.term_2 = self._term(self.year, Term.TermName.TERM_2, date(2026, 4, 20), date(2026, 7, 31))
        self.term_3 = self._term(self.year, Term.TermName.TERM_3, date(2026, 9, 1), date(2026, 12, 10))
        self.previous_year = AcademicYear.objects.create(
            school=self.school, name="2025",
            start_date=date(2025, 1, 1), end_date=date(2025, 12, 31),
        )
        self.previous_term = self._term(
            self.previous_year, Term.TermName.TERM_1, date(2025, 1, 6), date(2025, 4, 11)
        )
        self.klass = Class.objects.create(school=self.school, name="Primary 3")
        self.tuition = FeeComponent.objects.create(school=self.school, name="Tuition")
        self.feeding = FeeComponent.objects.create(school=self.school, name="Feeding")

        self.invoice_term_1 = self._invoice(self.ama, self.year, self.term_1, "1200.00")
        self._line(self.invoice_term_1, self.tuition, "1000.00")
        self._line(self.invoice_term_1, self.feeding, "200.00")
        self.payment = self._pay(self.invoice_term_1, "300.00", date(2026, 2, 1))
        PaymentAllocation.objects.create(
            payment=self.payment,
            line_item=self.invoice_term_1.line_items.get(fee_component=self.tuition),
            amount="200.00",
        )
        PaymentAllocation.objects.create(
            payment=self.payment,
            line_item=self.invoice_term_1.line_items.get(fee_component=self.feeding),
            amount="100.00",
        )

        self.invoice_term_2 = self._invoice(self.ama, self.year, self.term_2, "1100.00")
        self._line(self.invoice_term_2, self.tuition, "1100.00")

        self.invoice_previous_year = self._invoice(
            self.ama, self.previous_year, self.previous_term, "900.00"
        )
        self._line(self.invoice_previous_year, self.tuition, "900.00")
        self._pay(self.invoice_previous_year, "100.00", date(2025, 5, 1))

        self.draft_invoice = self._invoice(
            self.ama, self.year, self.term_3, "500.00",
            status=SchoolFeeInvoice.Status.DRAFT,
        )
        self._line(self.draft_invoice, self.tuition, "500.00")

        self.kofi_invoice = self._invoice(self.kofi, self.year, self.term_1, "700.00")
        self._line(self.kofi_invoice, self.tuition, "700.00")

        self.stranger_invoice = self._invoice(self.stranger, self.year, self.term_1, "650.00")
        self._line(self.stranger_invoice, self.tuition, "650.00")

        self.foreign_year = AcademicYear.objects.create(
            school=self.other_school, name="2026",
            start_date=date(2026, 1, 1), end_date=date(2026, 12, 31),
        )
        self.foreign_term = self._term(
            self.foreign_year, Term.TermName.TERM_1, date(2026, 1, 5), date(2026, 4, 10)
        )
        self.foreign_invoice = self._invoice(
            self.foreign, self.foreign_year, self.foreign_term, "800.00"
        )

        self.client = APIClient()
        self.client.force_authenticate(self.guardian.user_account)

    @staticmethod
    def _student(school, first_name):
        return Student.objects.create(
            school=school, first_name=first_name, last_name="Mensah", gender="female"
        )

    def _term(self, year, name, start, end):
        from academics.models import Term

        return Term.objects.create(
            school=year.school, academic_year=year, name=name,
            start_date=start, end_date=end,
        )

    def _invoice(self, student, year, term, total, status=None):
        from finance.models import SchoolFeeInvoice

        kwargs = {}
        if status:
            kwargs["status"] = status
        klass = self.klass if student.school_id == self.school.pk else None
        return SchoolFeeInvoice.objects.create(
            school=student.school, student=student, academic_year=year, term=term,
            klass=klass, total_amount=total, due_date=term.end_date, **kwargs,
        )

    @staticmethod
    def _line(invoice, component, amount):
        from finance.models import InvoiceLineItem

        return InvoiceLineItem.objects.create(
            school=invoice.school, invoice=invoice, fee_component=component, amount=amount
        )

    @staticmethod
    def _pay(invoice, amount, payment_date, method="cash"):
        from finance.models import FeePayment

        return FeePayment.objects.create(
            school=invoice.school, invoice=invoice, amount_paid=amount,
            payment_date=payment_date, payment_method=method,
            reference_number="REF-1",
        )

    def _url(self, student, invoice=None):
        if invoice is not None:
            return reverse(
                "guardian-account-my-student-invoice-detail",
                args=[student.pk, invoice.pk],
            )
        return reverse("guardian-account-my-student-invoices", args=[student.pk])

    def test_lists_linked_students_visible_invoices_newest_first(self):
        response = self.client.get(self._url(self.ama))

        self.assertEqual(response.status_code, 200, response.data)
        data = response.data["data"]
        self.assertEqual(
            [row["id"] for row in data],
            [
                str(self.invoice_term_2.pk),
                str(self.invoice_term_1.pk),
                str(self.invoice_previous_year.pk),
            ],
        )

    def test_list_includes_paid_and_outstanding_totals(self):
        from decimal import Decimal

        data = self.client.get(self._url(self.ama)).data["data"]
        by_id = {row["id"]: row for row in data}

        paid = by_id[str(self.invoice_term_1.pk)]
        self.assertEqual(Decimal(paid["total_paid"]), Decimal("300.00"))
        self.assertEqual(Decimal(paid["balance_due"]), Decimal("900.00"))
        self.assertEqual(paid["invoice_number"], self.invoice_term_1.invoice_number)
        self.assertEqual(paid["term_name"], "Term 1")

        unpaid = by_id[str(self.invoice_term_2.pk)]
        self.assertEqual(Decimal(unpaid["total_paid"]), Decimal("0.00"))
        self.assertEqual(Decimal(unpaid["balance_due"]), Decimal("1100.00"))

    def test_draft_invoice_is_hidden_from_the_list_and_detail(self):
        response = self.client.get(self._url(self.ama))

        ids = {row["id"] for row in response.data["data"]}
        self.assertNotIn(str(self.draft_invoice.pk), ids)
        self.assertEqual(
            self.client.get(self._url(self.ama, self.draft_invoice)).status_code, 404
        )

    def test_filters_invoices_by_academic_year_and_term(self):
        by_term = self.client.get(self._url(self.ama), {"term": str(self.term_1.pk)}).data["data"]
        self.assertEqual([row["id"] for row in by_term], [str(self.invoice_term_1.pk)])

        by_year = self.client.get(
            self._url(self.ama), {"academic_year": str(self.previous_year.pk)}
        ).data["data"]
        self.assertEqual([row["id"] for row in by_year], [str(self.invoice_previous_year.pk)])

        mismatch = self.client.get(
            self._url(self.ama),
            {"academic_year": str(self.previous_year.pk), "term": str(self.term_1.pk)},
        ).data["data"]
        self.assertEqual(mismatch, [])

    def test_filter_from_another_school_returns_nothing(self):
        data = self.client.get(
            self._url(self.ama), {"academic_year": str(self.foreign_year.pk)}
        ).data["data"]

        self.assertEqual(data, [])

    def test_invoice_detail_returns_component_breakdown(self):
        from decimal import Decimal

        response = self.client.get(self._url(self.ama, self.invoice_term_1))

        self.assertEqual(response.status_code, 200, response.data)
        data = response.data["data"]
        self.assertEqual(data["invoice_number"], self.invoice_term_1.invoice_number)
        self.assertEqual(len(data["line_items"]), 2)
        breakdown = {row["fee_component_name"]: row for row in data["line_items"]}
        self.assertEqual(Decimal(breakdown["Tuition"]["amount"]), Decimal("1000.00"))
        self.assertEqual(Decimal(breakdown["Tuition"]["paid_amount"]), Decimal("200.00"))
        self.assertEqual(Decimal(breakdown["Tuition"]["balance"]), Decimal("800.00"))
        self.assertEqual(Decimal(breakdown["Feeding"]["paid_amount"]), Decimal("100.00"))
        self.assertEqual(Decimal(breakdown["Feeding"]["balance"]), Decimal("100.00"))
        self.assertEqual(Decimal(data["total_paid"]), Decimal("300.00"))
        self.assertEqual(Decimal(data["balance_due"]), Decimal("900.00"))

    def test_invoice_of_a_different_linked_student_is_not_found(self):
        response = self.client.get(self._url(self.kofi, self.invoice_term_1))

        self.assertEqual(response.status_code, 404)

    def test_invoice_of_a_student_linked_to_another_guardian_is_not_found(self):
        response = self.client.get(self._url(self.ama, self.stranger_invoice))

        self.assertEqual(response.status_code, 404)

    def test_other_school_guardian_cannot_read_invoice(self):
        self.client.force_authenticate(self.foreign_guardian.user_account)

        self.assertEqual(self.client.get(self._url(self.ama)).status_code, 404)
        self.assertEqual(
            self.client.get(self._url(self.foreign, self.foreign_invoice)).status_code, 200
        )
        self.assertEqual(self.client.get(self._url(self.foreign, self.invoice_term_1)).status_code, 404)

    def test_unknown_invoice_is_not_found(self):
        import uuid

        url = reverse(
            "guardian-account-my-student-invoice-detail",
            args=[self.ama.pk, uuid.uuid4()],
        )

        self.assertEqual(self.client.get(url).status_code, 404)

    def test_non_guardian_is_forbidden(self):
        admin = User.objects.create_user(
            email="admin@example.com", password="x", first_name="Ad", last_name="Min",
            role=User.Role.ADMIN, school=self.school,
        )
        self.client.force_authenticate(admin)

        self.assertEqual(self.client.get(self._url(self.ama)).status_code, 403)
        self.assertEqual(
            self.client.get(self._url(self.ama, self.invoice_term_1)).status_code, 403
        )

    def test_anonymous_is_rejected(self):
        self.client.force_authenticate(None)

        self.assertIn(self.client.get(self._url(self.ama)).status_code, (401, 403))


class MyStudentPaymentEndpointTests(TestCase):
    def setUp(self):
        from datetime import date

        from academics.models import AcademicYear, Term
        from finance.models import FeeComponent, FeePayment, InvoiceLineItem, SchoolFeeInvoice

        self.school = School.objects.create(name="Test School", school_code="TST")
        self.ama = Student.objects.create(
            school=self.school, first_name="Ama", last_name="Mensah", gender="female"
        )
        self.stranger = Student.objects.create(
            school=self.school, first_name="Yaw", last_name="Mensah", gender="male"
        )
        service = GuardianService()
        self.guardian = service.create_guardian(
            {
                "first_name": "Efua", "last_name": "Mensah", "email": "efua@example.com",
                "phone": "0240000000", "gender": "female",
                "students": [{"student": self.ama, "relationship": "mother"}],
            },
            self.school,
        )
        service.create_guardian(
            {
                "first_name": "Other", "last_name": "Parent", "email": "other@example.com",
                "phone": "0240000001", "gender": "male",
                "students": [{"student": self.stranger, "relationship": "father"}],
            },
            self.school,
        )
        self.year = AcademicYear.objects.create(
            school=self.school, name="2026", is_current=True,
            start_date=date(2026, 1, 1), end_date=date(2026, 12, 31),
        )
        self.term_1 = Term.objects.create(
            school=self.school, academic_year=self.year, name=Term.TermName.TERM_1,
            start_date=date(2026, 1, 5), end_date=date(2026, 4, 10),
        )
        self.term_2 = Term.objects.create(
            school=self.school, academic_year=self.year, name=Term.TermName.TERM_2,
            start_date=date(2026, 4, 20), end_date=date(2026, 7, 31),
        )
        component = FeeComponent.objects.create(school=self.school, name="Tuition")

        def invoice(student, term, total):
            created = SchoolFeeInvoice.objects.create(
                school=self.school, student=student, academic_year=self.year,
                term=term, total_amount=total,
            )
            InvoiceLineItem.objects.create(
                school=self.school, invoice=created, fee_component=component, amount=total
            )
            return created

        def pay(invoice_obj, amount, day, method="cash"):
            return FeePayment.objects.create(
                school=self.school, invoice=invoice_obj, amount_paid=amount,
                payment_date=day, payment_method=method,
            )

        self.invoice_term_1 = invoice(self.ama, self.term_1, "1200.00")
        self.invoice_term_2 = invoice(self.ama, self.term_2, "1100.00")
        self.payment_1 = pay(self.invoice_term_1, "300.00", date(2026, 2, 1))
        self.payment_2 = pay(self.invoice_term_2, "200.00", date(2026, 5, 1), method="bank_transfer")
        self.other_payment = pay(invoice(self.stranger, self.term_1, "800.00"), "150.00", date(2026, 3, 1))

        self.url = reverse("guardian-account-my-student-payments", args=[self.ama.pk])
        self.client = APIClient()
        self.client.force_authenticate(self.guardian.user_account)

    def test_lists_payments_across_the_students_invoices_newest_first(self):
        from decimal import Decimal

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200, response.data)
        data = response.data["data"]
        self.assertEqual(
            [row["id"] for row in data], [str(self.payment_2.pk), str(self.payment_1.pk)]
        )
        self.assertEqual(data[0]["invoice_number"], self.invoice_term_2.invoice_number)
        self.assertEqual(data[0]["term_name"], "Term 2")
        self.assertEqual(Decimal(data[0]["amount_paid"]), Decimal("200.00"))
        self.assertEqual(data[0]["payment_method_display"], "Bank Transfer")

    def test_filters_payments_by_invoice_term_and_method(self):
        by_invoice = self.client.get(
            self.url, {"invoice": str(self.invoice_term_1.pk)}
        ).data["data"]
        self.assertEqual([row["id"] for row in by_invoice], [str(self.payment_1.pk)])

        by_term = self.client.get(self.url, {"term": str(self.term_2.pk)}).data["data"]
        self.assertEqual([row["id"] for row in by_term], [str(self.payment_2.pk)])

        by_method = self.client.get(
            self.url, {"payment_method": "bank_transfer"}
        ).data["data"]
        self.assertEqual([row["id"] for row in by_method], [str(self.payment_2.pk)])

    def test_filters_payments_by_date_range(self):
        data = self.client.get(
            self.url,
            {"payment_date_from": "2026-04-01", "payment_date_to": "2026-06-30"},
        ).data["data"]

        self.assertEqual([row["id"] for row in data], [str(self.payment_2.pk)])

    def test_other_students_payments_are_not_included(self):
        data = self.client.get(self.url, {"invoice": str(self.other_payment.invoice_id)}).data["data"]

        self.assertEqual(data, [])

    def test_payment_history_of_another_guardians_student_is_not_found(self):
        url = reverse("guardian-account-my-student-payments", args=[self.stranger.pk])

        self.assertEqual(self.client.get(url).status_code, 404)

    def test_non_guardian_is_forbidden(self):
        admin = User.objects.create_user(
            email="admin@example.com", password="x", first_name="Ad", last_name="Min",
            role=User.Role.ADMIN, school=self.school,
        )
        self.client.force_authenticate(admin)

        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_anonymous_is_rejected(self):
        self.client.force_authenticate(None)

        self.assertIn(self.client.get(self.url).status_code, (401, 403))
