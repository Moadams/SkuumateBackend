from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APITestCase

from accounts.models import User
from schools.models import School
from students.models import Student
from subscriptions.models import (
    Feature,
    Package,
    PackageFeature,
    PackageLimit,
    Subscription,
)
from subscriptions.utils import check_limit


def create_school(name="Quota School", code="QS"):
    return School.objects.create(
        name=name,
        school_code=code,
        email=f"{code.lower()}@example.com",
    )


def create_admin_user(school, email="admin@quota.com"):
    return User.objects.create_user(
        email=email,
        password="password123",
        first_name="Quota",
        last_name="Admin",
        role=User.Role.ADMIN,
        school=school,
    )


class StudentQuotaTests(TestCase):
    """The student cap must be enforced from PackageLimit, not the display column."""

    def setUp(self):
        self.school = create_school()
        self.package = Package.objects.create(
            name="Lite",
            code="lite-quota",
            price="100.00",
            billing_period=Package.BillingPeriod.TERM,
            maximum_students=250,
        )
        PackageFeature.objects.create(
            package=self.package, feature=self._feature("student_management"), is_enabled=True
        )
        PackageLimit.objects.create(
            package=self.package,
            key="max_students",
            name="Maximum Students",
            value=2,
        )
        Subscription.objects.create(
            school=self.school,
            plan=self.package,
            status=Subscription.Status.ACTIVE,
            start_date="2020-01-01T00:00:00Z",
            end_date="2099-01-01T00:00:00Z",
            is_paid=True,
            is_current=True,
        )

    @staticmethod
    def _feature(code):
        feature, _ = Feature.objects.get_or_create(
            code=code,
            defaults={"name": code, "category": "core", "is_active": True},
        )
        return feature

    def _add_students(self, count, student_status=Student.Status.ACTIVE):
        for index in range(count):
            Student.objects.create(
                school=self.school,
                first_name=f"First{index}",
                last_name=f"Last{index}",
                gender=Student.Gender.MALE,
                status=student_status,
            )

    def test_under_the_cap_is_allowed(self):
        self._add_students(1)
        check_limit(self.school, "students")

    def test_reaching_the_cap_is_blocked(self):
        self._add_students(2)
        with self.assertRaises(PermissionDenied) as ctx:
            check_limit(self.school, "students")
        self.assertIn("limit (2)", str(ctx.exception))

    def test_the_limit_row_overrides_the_display_column(self):
        """The Package column says 250; the PackageLimit row is authoritative."""
        self._add_students(2)
        with self.assertRaises(PermissionDenied):
            check_limit(self.school, "students")

    def test_inactive_students_do_not_consume_the_cap(self):
        self._add_students(1, Student.Status.ACTIVE)
        self._add_students(5, Student.Status.WITHDRAWN)
        check_limit(self.school, "students")

    def test_a_package_with_no_limit_row_falls_back_to_the_column(self):
        PackageLimit.objects.filter(package=self.package, key="max_students").delete()
        self._add_students(249)
        check_limit(self.school, "students")
        self._add_students(1)
        with self.assertRaises(PermissionDenied):
            check_limit(self.school, "students")

    def test_unknown_resource_is_a_no_op(self):
        check_limit(self.school, "not_a_tracked_resource")

    def test_no_subscription_blocks_the_request(self):
        Subscription.objects.filter(school=self.school).delete()
        with self.assertRaises(PermissionDenied) as ctx:
            check_limit(self.school, "students")
        self.assertIn("No active subscription", str(ctx.exception))

    def test_locked_subscription_blocks_the_request(self):
        Subscription.objects.filter(school=self.school).update(
            status=Subscription.Status.LOCKED
        )
        with self.assertRaises(PermissionDenied) as ctx:
            check_limit(self.school, "students")
        self.assertIn("expired", str(ctx.exception))


class StudentCreateQuotaGateTests(APITestCase):
    """The quota has to be wired into the create path, not just be implemented."""

    def setUp(self):
        self.school = create_school(name="Quota Gate School", code="QG")
        self.admin = create_admin_user(self.school)
        self.url = reverse("student-list")
        self.package = Package.objects.create(
            name="Lite",
            code="lite-gate",
            price="100.00",
            billing_period=Package.BillingPeriod.TERM,
            maximum_students=250,
        )
        PackageLimit.objects.create(
            package=self.package,
            key="max_students",
            name="Maximum Students",
            value=1,
        )
        Subscription.objects.create(
            school=self.school,
            plan=self.package,
            status=Subscription.Status.ACTIVE,
            start_date="2020-01-01T00:00:00Z",
            end_date="2099-01-01T00:00:00Z",
            is_paid=True,
            is_current=True,
        )
        self.client.force_authenticate(self.admin)

    def _payload(self, first_name="Ada"):
        return {
            "first_name": first_name,
            "last_name": "Lovelace",
            "gender": Student.Gender.FEMALE,
            "email": f"{first_name.lower()}@quota-gate.com",
        }

    def test_student_is_created_below_the_cap(self):
        response = self.client.post(self.url, self._payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_student_creation_is_refused_at_the_cap(self):
        self.assertEqual(
            self.client.post(self.url, self._payload(), format="json").status_code,
            status.HTTP_201_CREATED,
        )
        response = self.client.post(self.url, self._payload("Grace"), format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Student.objects.filter(school=self.school).count(), 1)


class StudentExportGateTests(APITestCase):
    """The export gate has to deny a real request, not just sit in the list."""

    def setUp(self):
        self.school = create_school(name="Export Gate School", code="EG")
        self.admin = create_admin_user(self.school)
        self.url = reverse("student-export")
        self.package = Package.objects.create(
            name="Lite",
            code="lite-export",
            price="100.00",
            billing_period=Package.BillingPeriod.TERM,
            maximum_students=250,
        )
        Subscription.objects.create(
            school=self.school,
            plan=self.package,
            status=Subscription.Status.ACTIVE,
            start_date="2020-01-01T00:00:00Z",
            end_date="2099-01-01T00:00:00Z",
            is_paid=True,
            is_current=True,
        )
        self.client.force_authenticate(self.admin)

    def _grant_export(self, code="export", package=None):
        feature, _ = Feature.objects.get_or_create(
            code=code,
            defaults={"name": code, "category": "core", "is_active": True},
        )
        PackageFeature.objects.create(
            package=package or self.package, feature=feature, is_enabled=True
        )

    def test_export_is_refused_without_the_feature(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("Upgrade to Advantage", response.data["message"])

    def test_export_is_allowed_once_the_feature_is_granted(self):
        self._grant_export()
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_200_OK)

    def test_export_is_refused_while_the_subscription_is_locked(self):
        self._grant_export()
        Subscription.objects.filter(school=self.school).update(
            status=Subscription.Status.LOCKED
        )
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("expired", response.data["message"])
