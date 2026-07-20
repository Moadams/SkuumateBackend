from datetime import date

from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import User
from schools.models import School
from staff.models import StaffProfile


class ActivateStaffUserAccountViewTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Test School",
            school_code="TS",
            email="school@example.com",
        )
        self.admin_user = User.objects.create_user(
            email="admin@example.com",
            password="password123",
            first_name="Admin",
            last_name="User",
            role="admin",
            school=self.school,
        )
        self.client.force_authenticate(self.admin_user)
        self.staff_profile = StaffProfile.objects.create(
            school=self.school,
            first_name="Jane",
            last_name="Doe",
            role=User.Role.TEACHER,
            date_joined=date(2024, 1, 1),
            email="duplicate@example.com",
        )

    def test_activate_staff_user_account_returns_400_for_duplicate_email(self):
        User.objects.create_user(
            email="duplicate@example.com",
            password="password123",
            first_name="Existing",
            last_name="User",
            role="teacher",
            school=self.school,
        )

        url = reverse(
            "activate-staff-user-account",
            kwargs={"pk": self.staff_profile.pk},
        )
        response = self.client.post(url)

        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.json()["message"].lower())
