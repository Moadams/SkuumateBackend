from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import User
from schools.models import School


class CouponListPermissionTests(APITestCase):
    """Coupon codes are credentials: only platform staff may enumerate them."""

    def setUp(self):
        self.school = School.objects.create(
            name="Coupon School", school_code="CP", email="coupon@example.com"
        )
        self.school_admin = User.objects.create_user(
            email="admin@coupon.com",
            password="password123",
            first_name="School",
            last_name="Admin",
            role=User.Role.ADMIN,
            school=self.school,
        )
        self.superadmin = User.objects.create_user(
            email="root@platform.com",
            password="password123",
            first_name="Platform",
            last_name="Admin",
            role=User.Role.SUPERADMIN,
            school=None,
        )

    def test_school_admin_cannot_list_coupons(self):
        self.client.force_authenticate(self.school_admin)

        response = self.client.get(reverse("coupon-list"))

        self.assertEqual(response.status_code, 403)

    def test_platform_superadmin_can_list_coupons(self):
        self.client.force_authenticate(self.superadmin)

        response = self.client.get(reverse("coupon-list"))

        self.assertEqual(response.status_code, 200)
