from datetime import date

from django.test import TestCase, override_settings
from django.urls import URLResolver, get_resolver, reverse
from rest_framework.test import APITestCase

from accounts.models import User
from core import test_security
from staff.models import PermissionKey, StaffPosition, StaffProfile


class SchoolPermissionTests(APITestCase):
    setUp = test_security.SchoolWorkflowSecurityTests.setUp

    def staff(self, *keys, role="teacher"):
        user = User.objects.create_user(email="staff@example.com", role=role, school=self.school)
        self.profile = StaffProfile.objects.create(school=self.school, user=user, first_name="Staff", last_name="User", date_joined=date(2026, 1, 1))
        for key in keys:
            permission, _ = PermissionKey.objects.get_or_create(key=key, defaults={"label": key, "module": key.split(".")[0]})
            self.profile.permission_grants.add(permission)
        self.client.force_authenticate(user)
        return user

    def test_finance_read_permission_cannot_write(self):
        self.staff("finance.view", role="finance_manager")
        self.assertEqual(self.client.get(reverse("fee-component-list")).status_code, 200)
        self.assertEqual(self.client.post(reverse("fee-component-list"), {"name": "New"}).status_code, 403)
        self.assertEqual(self.client.post(reverse("payment-list"), {}).status_code, 403)

    @override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
    def test_revocation_applies_on_next_request_even_through_reverse_relation(self):
        self.staff("finance.view", role="finance_manager")
        self.assertEqual(self.client.get(reverse("invoice-list")).status_code, 200)
        permission = PermissionKey.objects.get(key="finance.view")
        permission.revoked_from_staff.add(self.profile)
        self.assertEqual(self.client.get(reverse("invoice-list")).status_code, 403)

    def test_unconfigured_staff_is_denied_and_admin_can_assign_access(self):
        user = self.staff(role="finance_manager")
        self.assertEqual(self.client.get(reverse("invoice-list")).status_code, 403)
        permission, _ = PermissionKey.objects.get_or_create(key="finance.view", defaults={"label": "Finance", "module": "Finance"})
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.patch(reverse("staff-access", args=[self.profile.pk]), {"permission_grants": [permission.key]}, format="json").status_code, 200)
        self.client.force_authenticate(user)
        self.assertEqual(self.client.get(reverse("invoice-list")).status_code, 200)

    def test_cannot_assign_foreign_position_or_modify_own_access(self):
        self.staff("staff.manage")
        url = reverse("staff-access", args=[self.profile.pk])
        self.assertEqual(self.client.patch(url, {"permission_grants": ["school.manage"]}, format="json").status_code, 403)
        foreign = StaffPosition.objects.create(school=self.other, name="Foreign")
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.patch(url, {"positions": [str(foreign.pk)]}, format="json").status_code, 400)

    def test_delegated_staff_manager_cannot_create_admin(self):
        self.staff("staff.manage")
        response = self.client.post(reverse("staff-list"), {"first_name": "New", "last_name": "Admin", "role": "admin", "date_joined": "2026-01-01", "email": "new@example.com"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_school_bound_platform_role_is_rejected(self):
        from platform_rbac.services import has_platform_permission, is_platform_user
        user = User.objects.create_user(email="bad-platform@example.com", school=self.school, role="superadmin")
        self.assertFalse(is_platform_user(user))
        self.assertFalse(has_platform_permission(user, None))

    def test_login_payload_contains_effective_permissions(self):
        user = self.staff("finance.view", role="finance_manager")
        response = self.client.get(reverse("me"))
        self.assertEqual(response.data["data"]["effective_permissions"], ["finance.view"])


class PermissionPolicyRegistryTests(TestCase):
    def test_all_declared_school_action_keys_exist(self):
        from staff.permission_registry import PERMISSION_KEYS
        def walk(patterns):
            for pattern in patterns:
                if isinstance(pattern, URLResolver):
                    yield from walk(pattern.url_patterns)
                else:
                    view = getattr(pattern.callback, "view_class", None)
                    if view:
                        yield view
        count = 0
        for view in set(walk(get_resolver().url_patterns)):
            for permission in getattr(view, "permission_classes", []):
                if hasattr(permission, "action_keys"):
                    count += 1
                    for key in permission.action_keys.values():
                        if key:
                            self.assertIn(key, PERMISSION_KEYS, view.__name__)
        self.assertGreater(count, 100)
