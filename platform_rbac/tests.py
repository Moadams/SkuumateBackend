from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APITestCase, force_authenticate

from accounts.models import User
from core.models import AuditLog
from schools.models import School

from .models import (
    PlatformPermission,
    PlatformRole,
    PlatformRolePermission,
    PlatformUserRole,
)
from .permission_registry import PERMISSION_SPECS
from .services import (
    get_user_platform_permissions,
    has_platform_permission,
    is_platform_user,
    validate_assignable_permissions,
    validate_assignable_roles,
)
from .sync import seed_platform_permissions


def permission(code):
    return PlatformPermission.objects.get(code=code)


def make_role(code, *perm_codes):
    role = PlatformRole.objects.create(code=code, name=code.replace("_", " ").title())
    for p in perm_codes:
        PlatformRolePermission.objects.create(role=role, permission=permission(p))
    return role


def assign_role(user, role):
    PlatformUserRole.objects.create(user=user, role=role)


class PlatformBase:

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        seed_platform_permissions()

    def make_root(self):
        return User.objects.create_superuser(
            email="root@skuumate.io",
            password="rootpass123",
            first_name="Root",
            last_name="Admin",
        )

    def make_staff(self, email="staff@skuumate.io", roles=()):
        user = User.objects.create_user(
            email=email,
            password="staffpass123",
            first_name="Staff",
            last_name="User",
            role=User.Role.SUPERADMIN,
        )
        for role in roles:
            assign_role(user, role)
        return user

    def make_school_admin(self, school=None):
        if school is None:
            school = School.objects.create(name="Test School")
        return User.objects.create_user(
            email="admin@school.edu",
            password="adminpass123",
            first_name="School",
            last_name="Admin",
            role=User.Role.ADMIN,
            school=school,
        )

    def make_teacher(self):
        return User.objects.create_user(
            email="teacher@school.edu",
            password="teacherpass123",
            first_name="Mr",
            last_name="Teacher",
            role=User.Role.TEACHER,
        )

    def auth(self, client, user):
        client.force_authenticate(user=user)


class PlatformServiceTests(PlatformBase, TestCase):

    def test_anonymous_false(self):
        class FakeUser:
            is_authenticated = False
            is_active = True
        self.assertFalse(has_platform_permission(FakeUser(), "packages.view"))

    def test_inactive_platform_user_false(self):
        staff = self.make_staff()
        staff.is_active = False
        staff.save(update_fields=["is_active"])
        self.assertFalse(has_platform_permission(staff, "packages.view"))
        self.assertFalse(is_platform_user(staff))

    def test_root_passes_every_permission(self):
        root = self.make_root()
        self.assertTrue(is_platform_user(root))
        self.assertTrue(has_platform_permission(root, "packages.view"))
        self.assertTrue(has_platform_permission(root, "role_that_does_not_exist.yet"))

    def test_school_admin_and_teacher_false(self):
        admin = self.make_school_admin()
        teacher = self.make_teacher()
        self.assertFalse(is_platform_user(admin))
        self.assertFalse(has_platform_permission(admin, "packages.view"))
        self.assertFalse(is_platform_user(teacher))
        self.assertFalse(has_platform_permission(teacher, "roles.view"))

    def test_platform_staff_with_and_without_permission(self):
        role = make_role("pkg_manager", "packages.view", "packages.create")
        staff = self.make_staff(roles=[role])
        self.assertTrue(is_platform_user(staff))
        self.assertTrue(has_platform_permission(staff, "packages.view"))
        self.assertFalse(has_platform_permission(staff, "schools.view"))

    def test_multiple_roles_combine_permissions(self):
        r1 = make_role("r_viewer", "packages.view", "schools.view")
        r2 = make_role("r_editor", "schools.update", "subscriptions.view")
        staff = self.make_staff(roles=[r1, r2])
        self.assertEqual(
            get_user_platform_permissions(staff),
            {"packages.view", "schools.view", "schools.update", "subscriptions.view"},
        )

    def test_inactive_role_ignored(self):
        role = make_role("inactive_role", "packages.view")
        role.is_active = False
        role.save(update_fields=["is_active"])
        staff = self.make_staff(roles=[role])
        self.assertFalse(has_platform_permission(staff, "packages.view"))
        self.assertEqual(get_user_platform_permissions(staff), frozenset())

    def test_inactive_permission_ignored(self):
        role = make_role("perm_off", "packages.view")
        perm = permission("packages.view")
        perm.is_active = False
        perm.save(update_fields=["is_active"])
        staff = self.make_staff(roles=[role])
        self.assertFalse(has_platform_permission(staff, "packages.view"))
        perm.is_active = True
        perm.save(update_fields=["is_active"])

    def test_root_effective_permissions_empty_but_passes(self):
        root = self.make_root()
        self.assertEqual(get_user_platform_permissions(root), frozenset())
        self.assertTrue(has_platform_permission(root, "packages.view"))

    def test_validation_assignable_permissions(self):
        role = make_role("full_perm", "packages.view", "packages.create")
        staff = self.make_staff(roles=[role])
        validate_assignable_permissions(staff, ["packages.view"])
        with self.assertRaises(PermissionError):
            validate_assignable_permissions(staff, ["schools.view"])

    def test_validation_assignable_roles(self):
        rich = make_role("rich_role", "packages.view", "schools.view")
        poor = make_role("poor_role", "packages.view")
        staff = self.make_staff(roles=[poor])
        validate_assignable_roles(staff, [poor])
        with self.assertRaises(PermissionError):
            validate_assignable_roles(staff, [rich])

    def test_non_authenticated_not_platform(self):
        class Anon:
            is_authenticated = False
            is_active = True
        self.assertFalse(is_platform_user(Anon()))


class PlatformAccessAPITests(PlatformBase, APITestCase):

    def test_unauth_user_listing_denied(self):
        self.client.force_authenticate(user=None)
        response = self.client.get(reverse("platform-user-list-create"))
        self.assertEqual(response.status_code, 401)

    def test_school_admin_cannot_access_platform(self):
        user = self.make_school_admin()
        self.auth(self.client, user)
        for url in (
            reverse("platform-user-list-create"),
            reverse("platform-role-list-create"),
            reverse("platform-permission-list"),
            reverse("platform-me-permissions"),
        ):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 403, url)

    def test_teacher_cannot_access_platform(self):
        user = self.make_teacher()
        self.auth(self.client, user)
        response = self.client.get(reverse("platform-user-list-create"))
        self.assertEqual(response.status_code, 403)

    def test_root_can_access_everything(self):
        root = self.make_root()
        self.auth(self.client, root)
        for url in (
            reverse("platform-user-list-create"),
            reverse("platform-role-list-create"),
            reverse("platform-permission-list"),
            reverse("platform-me-permissions"),
        ):
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_platform_staff_requires_permission_to_list_users(self):
        bare = self.make_staff()  # no roles
        self.auth(self.client, bare)
        self.assertEqual(self.client.get(reverse("platform-user-list-create")).status_code, 403)

        role = make_role("usr_view", "platform_users.view")
        staff = self.make_staff(email="viewer@skuumate.io", roles=[role])
        self.auth(self.client, staff)
        self.assertEqual(self.client.get(reverse("platform-user-list-create")).status_code, 200)

    def test_inactive_platform_staff_denied(self):
        staff = self.make_staff()
        staff.is_active = False
        staff.save(update_fields=["is_active"])
        self.auth(self.client, staff)
        self.assertEqual(self.client.get(reverse("platform-user-list-create")).status_code, 403)


class PlatformUserManagementTests(PlatformBase, APITestCase):

    def test_root_creates_platform_user(self):
        root = self.make_root()
        self.auth(self.client, root)
        response = self.client.post(
            reverse("platform-user-list-create"),
            {
                "email": "new@skuumate.io",
                "first_name": "New",
                "last_name": "Admin",
                "phone": "+254700000000",
                "password": "supersecret1",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        data = response.data["data"]
        self.assertEqual(data["role"], "superadmin")
        self.assertTrue(data["is_platform_user"])
        self.assertIsNone(data["school"])
        self.assertNotIn("password", data)

    def test_duplicate_email_rejected(self):
        root = self.make_root()
        self.auth(self.client, root)
        payload = {
            "email": "dup@skuumate.io",
            "first_name": "A",
            "last_name": "B",
            "password": "supersecret1",
        }
        self.assertEqual(self.client.post(reverse("platform-user-list-create"), payload, format="json").status_code, 201)
        response = self.client.post(reverse("platform-user-list-create"), payload, format="json")
        self.assertEqual(response.status_code, 400)

    def test_missing_password_rejected(self):
        root = self.make_root()
        self.auth(self.client, root)
        response = self.client.post(
            reverse("platform-user-list-create"),
            {"email": "nopass@skuumate.io", "first_name": "A", "last_name": "B"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_cannot_escalate_to_superuser_via_api(self):
        root = self.make_root()
        self.auth(self.client, root)
        staff = self.make_staff(email="victim@skuumate.io")
        response = self.client.patch(
            reverse("platform-user-detail", kwargs={"pk": staff.pk}),
            {"is_superuser": True, "is_staff": True},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        staff.refresh_from_db()
        self.assertFalse(staff.is_superuser)
        self.assertFalse(staff.is_staff)
        self.assertEqual(response.data["data"]["is_superuser"], False)

    def test_cannot_create_superuser_via_api(self):
        root = self.make_root()
        self.auth(self.client, root)
        response = self.client.post(
            reverse("platform-user-list-create"),
            {
                "email": "trick@skuumate.io",
                "first_name": "T",
                "last_name": "R",
                "password": "supersecret1",
                "is_superuser": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        created = User.objects.get(email="trick@skuumate.io")
        self.assertFalse(created.is_superuser)
        self.assertFalse(created.is_staff)

    def test_update_platform_user_metadata(self):
        root = self.make_root()
        self.auth(self.client, root)
        staff = self.make_staff(email="meta@skuumate.io")
        response = self.client.patch(
            reverse("platform-user-detail", kwargs={"pk": staff.pk}),
            {"first_name": "Updated", "phone": "+254700111111"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        staff.refresh_from_db()
        self.assertEqual(staff.first_name, "Updated")
        self.assertEqual(staff.phone, "+254700111111")

    def test_activate_deactivate_lifecycle(self):
        root = self.make_root()
        self.auth(self.client, root)
        staff = self.make_staff(email="life@skuumate.io")
        detail = reverse("platform-user-detail", kwargs={"pk": staff.pk})

        response = self.client.post(reverse("platform-user-deactivate", kwargs={"pk": staff.pk}))
        self.assertEqual(response.status_code, 200)
        staff.refresh_from_db()
        self.assertFalse(staff.is_active)

        response = self.client.post(reverse("platform-user-activate", kwargs={"pk": staff.pk}))
        self.assertEqual(response.status_code, 200)
        staff.refresh_from_db()
        self.assertTrue(staff.is_active)
        self.assertNotEqual(response.status_code, 404)

    def test_non_root_cannot_deactivate_self(self):
        role = make_role("can_deactivate", "platform_users.deactivate")
        staff = self.make_staff(email="self@skuumate.io", roles=[role])
        self.auth(self.client, staff)
        response = self.client.post(reverse("platform-user-deactivate", kwargs={"pk": staff.pk}))
        self.assertEqual(response.status_code, 403)
        staff.refresh_from_db()
        self.assertTrue(staff.is_active)

    def test_root_cannot_be_deactivated(self):
        root = self.make_root()
        other_root = User.objects.create_superuser(
            email="root2@skuumate.io", password="rootpass123", first_name="R2", last_name="A"
        )
        self.auth(self.client, other_root)
        response = self.client.post(reverse("platform-user-deactivate", kwargs={"pk": root.pk}))
        self.assertEqual(response.status_code, 400)

    def test_platform_user_without_deactivate_permission_blocked(self):
        role = make_role("no_deact", "platform_users.view")
        staff = self.make_staff(roles=[role])
        target = self.make_staff(email="target@skuumate.io")
        self.auth(self.client, staff)
        response = self.client.post(reverse("platform-user-deactivate", kwargs={"pk": target.pk}))
        self.assertEqual(response.status_code, 403)

    def test_user_roles_get_post_delete(self):
        root = self.make_root()
        self.auth(self.client, root)
        staff = self.make_staff(email="roles@skuumate.io")
        r_view = make_role("r_view", "packages.view")
        r_edit = make_role("r_edit", "schools.view")

        roles_url = reverse("platform-user-roles", kwargs={"pk": staff.pk})

        response = self.client.post(roles_url, {"codes": [r_view.code, r_edit.code]}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.data["data"]["roles"]), 2)

        response = self.client.post(roles_url, {"codes": [r_view.code]}, format="json")
        self.assertEqual(response.status_code, 400)  # duplicate role assignment fails

        response = self.client.get(roles_url)
        self.assertEqual(len(response.data["data"]["roles"]), 2)

        response = self.client.delete(roles_url, {"codes": [r_view.code]}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["data"]["roles"]), 1)

        response = self.client.delete(roles_url, {"codes": [r_view.code]}, format="json")
        self.assertEqual(response.status_code, 400)  # not currently assigned

    def test_assign_roles_to_school_user_denied(self):
        root = self.make_root()
        self.auth(self.client, root)
        admin = self.make_school_admin()
        role = make_role("any_role", "packages.view")
        response = self.client.post(
            reverse("platform-user-roles", kwargs={"pk": admin.pk}),
            {"codes": [role.code]},
            format="json",
        )
        self.assertEqual(response.status_code, 404)

    def test_cannot_assign_roles_user_does_not_manage(self):
        limited_role = make_role("limited", "platform_users.assign_roles", "platform_users.view")
        rich_role = make_role("rich", "packages.view")
        staff = self.make_staff(email="limited@skuumate.io", roles=[limited_role])
        target = self.make_staff(email="victim2@skuumate.io")
        self.auth(self.client, staff)
        response = self.client.post(
            reverse("platform-user-roles", kwargs={"pk": target.pk}),
            {"codes": [rich_role.code]},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_non_root_cannot_change_own_roles(self):
        role = make_role("own_roles", "platform_users.assign_roles")
        staff = self.make_staff(email="own@skuumate.io", roles=[role])
        other = make_role("other_role", "platform_users.view")
        self.auth(self.client, staff)
        response = self.client.delete(
            reverse("platform-user-roles", kwargs={"pk": staff.pk}),
            {"codes": [role.code]},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(PlatformUserRole.objects.filter(user=staff, role=role).exists())

    def test_user_effective_permissions_endpoint(self):
        root = self.make_root()
        self.auth(self.client, root)
        r1 = make_role("eff_a", "packages.view", "schools.create")
        r2 = make_role("eff_b", "subscriptions.view")
        staff = self.make_staff(email="eff@skuumate.io", roles=[r1, r2])
        response = self.client.get(reverse("platform-user-permissions", kwargs={"pk": staff.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            set(response.data["data"]["permissions"]),
            {"packages.view", "schools.create", "subscriptions.view"},
        )

    def test_create_platform_user_requires_platform_users_create(self):
        role = make_role("view_only", "platform_users.view")
        staff = self.make_staff(email="cov@skuumate.io", roles=[role])
        self.auth(self.client, staff)
        response = self.client.post(
            reverse("platform-user-list-create"),
            {"email": "nope@skuumate.io", "first_name": "X", "last_name": "Y", "password": "supersecret1"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)


class PlatformRoleManagementTests(PlatformBase, APITestCase):

    def test_create_update_role(self):
        root = self.make_root()
        self.auth(self.client, root)
        url = reverse("platform-role-list-create")
        response = self.client.post(url, {"name": "Package Manager", "code": "pkg_manager", "description": "Manages packages"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        pk = response.data["data"]["id"]

        response = self.client.patch(
            reverse("platform-role-detail", kwargs={"pk": pk}),
            {"description": "New description"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["description"], "New description")

    def test_duplicate_role_code_rejected(self):
        root = self.make_root()
        self.auth(self.client, root)
        make_role("dup_role", "packages.view")
        response = self.client.post(
            reverse("platform-role-list-create"),
            {"name": "Dup", "code": "dup_role"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_invalid_role_code_rejected(self):
        root = self.make_root()
        self.auth(self.client, root)
        for code in ("Bad-Code", "1starts_with_digit", "UPPER"):
            response = self.client.post(
                reverse("platform-role-list-create"),
                {"name": "Bad", "code": code},
                format="json",
            )
            self.assertEqual(response.status_code, 400, code)

    def test_system_role_code_protected(self):
        root = self.make_root()
        self.auth(self.client, root)
        system = make_role("system_guard")
        system.is_system_role = True
        system.save(update_fields=["is_system_role"])
        response = self.client.patch(
            reverse("platform-role-detail", kwargs={"pk": system.pk}),
            {"code": "hacked_code"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        response = self.client.patch(
            reverse("platform-role-detail", kwargs={"pk": system.pk}),
            {"name": "Renamed system role"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)

    def test_system_role_cannot_be_deactivated(self):
        root = self.make_root()
        self.auth(self.client, root)
        system = make_role("system_guard2")
        system.is_system_role = True
        system.save(update_fields=["is_system_role"])
        response = self.client.post(reverse("platform-role-deactivate", kwargs={"pk": system.pk}))
        self.assertEqual(response.status_code, 400)
        response = self.client.post(reverse("platform-role-activate", kwargs={"pk": system.pk}))
        self.assertEqual(response.status_code, 200)

    def test_role_activate_deactivate(self):
        root = self.make_root()
        self.auth(self.client, root)
        role = make_role("toggler", "packages.view")
        self.client.post(reverse("platform-role-deactivate", kwargs={"pk": role.pk}))
        role.refresh_from_db()
        self.assertFalse(role.is_active)

    def test_assign_remove_permissions(self):
        root = self.make_root()
        self.auth(self.client, root)
        role = make_role("perm_bucket")
        url = reverse("platform-role-permissions", kwargs={"pk": role.pk})
        response = self.client.post(url, {"codes": ["packages.view", "packages.create"]}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            set(response.data["data"]["roles"]["permissions"]),
            {"packages.view", "packages.create"},
        )

        response = self.client.post(url, {"codes": ["packages.view"]}, format="json")
        self.assertEqual(response.status_code, 400)  # duplicate permission assignment fails

        response = self.client.delete(url, {"codes": ["packages.create"]}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.data["data"]["roles"]["permissions"]), {"packages.view"})

        response = self.client.delete(url, {"codes": ["packages.create"]}, format="json")
        self.assertEqual(response.status_code, 400)  # not currently assigned

    def test_unknown_permission_code_rejected(self):
        root = self.make_root()
        self.auth(self.client, root)
        role = make_role("unknown_p", "packages.view")
        response = self.client.post(
            reverse("platform-role-permissions", kwargs={"pk": role.pk}),
            {"codes": ["nope.nope"]},
            format="json",
        )
        self.assertEqual(response.status_code, 404)

    def test_inactive_permission_cannot_be_assigned(self):
        root = self.make_root()
        self.auth(self.client, root)
        role = make_role("inactive_p", "packages.view")
        perm = permission("schools.view")
        perm.is_active = False
        perm.save(update_fields=["is_active"])
        response = self.client.post(
            reverse("platform-role-permissions", kwargs={"pk": role.pk}),
            {"codes": ["schools.view"]},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_staff_cannot_grant_permissions_they_lack(self):
        staff_role = make_role("perm_manager", "roles.assign_permissions", "packages.view")
        staff = self.make_staff(email="grantor@skuumate.io", roles=[staff_role])
        target = make_role("target_role", "packages.view")
        self.auth(self.client, staff)
        response = self.client.post(
            reverse("platform-role-permissions", kwargs={"pk": target.pk}),
            {"codes": ["schools.update"]},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_create_role_requires_roles_create(self):
        role = make_role("role_view", "roles.view")
        staff = self.make_staff(email="rv@skuumate.io", roles=[role])
        self.auth(self.client, staff)
        response = self.client.post(
            reverse("platform-role-list-create"),
            {"name": "Nope", "code": "nope_role"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)


class PlatformPermissionAPITests(PlatformBase, APITestCase):

    def setUp(self):
        self.root = self.make_root()
        self.auth(self.client, self.root)

    def test_list_returns_seeded_catalog(self):
        response = self.client.get(reverse("platform-permission-list"), {"page_size": 100})
        self.assertEqual(response.status_code, 200)
        results = response.data["data"]["results"]
        codes = {row["code"] for row in results}
        self.assertEqual(codes, {spec.code for spec in PERMISSION_SPECS})

    def test_filter_by_module(self):
        response = self.client.get(reverse("platform-permission-list"), {"module": "packages"})
        codes = [row["code"] for row in response.data["data"]["results"]]
        self.assertEqual(len(codes), 6)
        self.assertTrue(all(code.startswith("packages.") for code in codes))

    def test_search_by_name(self):
        response = self.client.get(reverse("platform-permission-list"), {"search": "platform users"})
        results = response.data["data"]["results"]
        self.assertTrue(results)
        self.assertIn("platform_users.view", {row["code"] for row in results})

    def test_detail(self):
        perm = permission("roles.view")
        response = self.client.get(reverse("platform-permission-detail", kwargs={"pk": perm.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["code"], "roles.view")

    def test_no_arbitrary_creation(self):
        response = self.client.post(reverse("platform-permission-list"), {"code": "custom.make", "name": "Custom"}, format="json")
        self.assertEqual(response.status_code, 405)

    def test_school_admin_cannot_view_permissions(self):
        admin = self.make_school_admin()
        self.auth(self.client, admin)
        response = self.client.get(reverse("platform-permission-list"))
        self.assertEqual(response.status_code, 403)


class PlatformMePermissionsTests(PlatformBase, APITestCase):

    def test_root_me_permissions(self):
        root = self.make_root()
        self.auth(self.client, root)
        response = self.client.get(reverse("platform-me-permissions"))
        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertTrue(data["is_superuser"])
        self.assertEqual(data["permissions"], ["*"])

    def test_staff_me_permissions(self):
        r1 = make_role("me_a", "packages.view")
        r2 = make_role("me_b", "schools.create", "subscriptions.view")
        staff = self.make_staff(email="me@skuumate.io", roles=[r1, r2])
        self.auth(self.client, staff)
        response = self.client.get(reverse("platform-me-permissions"))
        data = response.data["data"]
        self.assertFalse(data["is_superuser"])
        self.assertEqual(
            set(data["permissions"]),
            {"packages.view", "schools.create", "subscriptions.view"},
        )
        self.assertEqual({r["code"] for r in data["roles"]}, {"me_a", "me_b"})

    def test_school_user_cannot_access_me(self):
        admin = self.make_school_admin()
        self.auth(self.client, admin)
        response = self.client.get(reverse("platform-me-permissions"))
        self.assertEqual(response.status_code, 403)


class PlatformAuditTests(PlatformBase, APITestCase):

    def test_audit_logged_for_create_and_role_assignment(self):
        root = self.make_root()
        self.auth(self.client, root)
        self.client.post(
            reverse("platform-user-list-create"),
            {"email": "audit@skuumate.io", "first_name": "Au", "last_name": "Di", "password": "supersecret1"},
            format="json",
        )
        created = User.objects.get(email="audit@skuumate.io")
        role = make_role("audit_role", "packages.view")
        self.client.post(
            reverse("platform-user-roles", kwargs={"pk": created.pk}),
            {"codes": [role.code]},
            format="json",
        )
        events = AuditLog.objects.filter(actor=root, resource="PlatformUser").count()
        self.assertGreaterEqual(events, 1)
        link = AuditLog.objects.filter(resource="PlatformUserRole").count()
        self.assertEqual(link, 1)

    def test_audit_logged_for_deactivate(self):
        root = self.make_root()
        self.auth(self.client, root)
        staff = self.make_staff(email="deact@skuumate.io")
        self.client.post(reverse("platform-user-deactivate", kwargs={"pk": staff.pk}))
        self.assertTrue(
            AuditLog.objects.filter(
                actor=root,
                resource="PlatformUser",
                metadata__is_active=False,
            ).exists()
        )