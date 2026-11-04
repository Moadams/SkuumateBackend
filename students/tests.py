
from django.test import TestCase
from rest_framework.exceptions import PermissionDenied

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
        """The Package column says 250; the PackageLimit row (2) is authoritative."""
        self._add_students(2)
        with self.assertRaises(PermissionDenied) as ctx:
            check_limit(self.school, "students")
        self.assertIn("limit (2)", str(ctx.exception))

    def test_inactive_students_do_not_consume_the_cap(self):
        self._add_students(1, Student.Status.ACTIVE)
        self._add_students(5, Student.Status.WITHDRAWN)
        check_limit(self.school, "students")
