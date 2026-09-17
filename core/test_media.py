import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import User
from schools.models import School
from students.models import Student


class PrivateMediaTests(APITestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.settings_override = override_settings(MEDIA_ROOT=self.directory.name)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.school = School.objects.create(name="A", school_code="A")
        self.other = School.objects.create(name="B", school_code="B")
        self.admin = User.objects.create_user(email="a@example.com", role="admin", school=self.school)
        self.student = Student.objects.create(school=self.school, first_name="A", last_name="Student", gender="male", profile_photo=SimpleUploadedFile("student.png", b"private-content", content_type="image/png"))
        self.url = reverse("private-media", kwargs={"path": self.student.profile_photo.name})

    def test_private_file_is_not_public_even_with_debug_enabled(self):
        for debug in (True, False):
            with self.subTest(debug=debug), override_settings(DEBUG=debug):
                response = self.client.get(self.student.profile_photo.url)
                self.assertEqual(response.status_code, 404)

    def test_unauthenticated_download_is_denied(self):
        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_school_admin_can_download_without_caching(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), b"private-content")
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertIn("Authorization", response["Vary"])
        response.close()

    def test_other_school_cannot_download(self):
        other = User.objects.create_user(email="b@example.com", role="admin", school=self.other)
        self.client.force_authenticate(other)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_unprivileged_student_cannot_download_peer_photo(self):
        student = User.objects.create_user(email="student@example.com", role="student", school=self.school)
        self.client.force_authenticate(student)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_registered_logo_is_public_but_unknown_files_are_not(self):
        self.school.logo.save("logo.png", SimpleUploadedFile("logo.png", b"logo"))
        response = self.client.get(self.school.logo.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), b"logo")
        response.close()
        self.assertEqual(self.client.get("/media/schools/logos/unknown.png").status_code, 404)

    def test_removed_file_and_traversal_return_not_found(self):
        self.client.force_authenticate(self.admin)
        self.student.profile_photo.storage.delete(self.student.profile_photo.name)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.get(reverse("private-media", kwargs={"path": "students/photos/../../.env"})).status_code, 404)
