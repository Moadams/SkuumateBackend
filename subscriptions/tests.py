from datetime import timedelta
from importlib import import_module
from types import SimpleNamespace

from django.apps import apps as django_apps
from django.contrib.auth.models import AnonymousUser
from django.db import IntegrityError
from django.test import SimpleTestCase, TestCase, TransactionTestCase
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIRequestFactory, APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User
from schools.models import School
from students.models import Student
from subscriptions.feature_catalog import FEATURES, declared_feature_codes
from subscriptions.models import (
    Feature,
    Package,
    PackageFeature,
    PackageLimit,
    Subscription,
)
from subscriptions.permissions import _make_feature_permission
from subscriptions.services.packages import (
    PackageService,
    feature_entitlement_map,
    get_package_features,
    get_package_limit,
    package_has_feature,
    resolve_package_limits,
    subscription_entitlements,
)
from subscriptions.state import (
    ALWAYS_REACHABLE_URL_NAMES,
    evaluate_request_state,
)
from subscriptions.sync import sync_feature_catalog


def create_school(name="Test School", code="TS"):
    return School.objects.create(
        name=name,
        school_code=code,
        email=f"{code.lower()}@example.com",
    )


def create_admin_user(school, email="admin@school.com"):
    return User.objects.create_user(
        email=email,
        password="password123",
        first_name="Admin",
        last_name="User",
        role=User.Role.ADMIN,
        school=school,
    )


def create_superadmin_user():
    return User.objects.create_user(
        email="superadmin@skuumate.com",
        password="password123",
        first_name="Super",
        last_name="Admin",
        role=User.Role.SUPERADMIN,
    )


def create_feature(code="attendance", name="Attendance"):
    feature, _ = Feature.objects.get_or_create(
        code=code,
        defaults={"name": name, "category": "core", "is_active": True},
    )
    if feature.name != name:
        feature.name = name
        feature.save(update_fields=["name", "updated_at"])
    return feature


def valid_package_payload(**overrides):
    payload = {
        "name": "Premium",
        "code": "premium",
        "tagline": "Custom package",
        "description": "A configurable package",
        "price": "500.00",
        "setup_fee": "100.00",
        "billing_period": "TERM",
        "currency": "GHS",
        "minimum_students": 0,
        "maximum_students": 100,
        "is_active": True,
        "is_public": True,
        "display_order": 4,
        "features": [
            {"code": "attendance", "enabled": True},
            {"code": "sms", "enabled": False},
        ],
        "limits": [
            {"key": "max_staff", "name": "Maximum Staff", "value": 25},
        ],
    }
    payload.update(overrides)
    return payload


class PackageServiceTests(TestCase):
    def setUp(self):
        self.package = Package.objects.create(name="Test Lite", code="test-lite", price="1000.00")
        self.attendance = create_feature()
        self.sms = create_feature(code="sms", name="SMS Alerts")
        PackageFeature.objects.create(
            package=self.package, feature=self.attendance, is_enabled=True
        )
        PackageFeature.objects.create(
            package=self.package, feature=self.sms, is_enabled=False
        )
        PackageLimit.objects.create(
            package=self.package, key="max_students", name="Maximum Students", value=250
        )

    def test_package_has_feature_honors_enabled_flag(self):
        self.assertTrue(package_has_feature(self.package, "attendance"))
        self.assertFalse(package_has_feature(self.package, "sms"))
        self.assertFalse(package_has_feature(self.package, "missing"))
        self.assertFalse(package_has_feature(None, "attendance"))

    def test_get_package_features_returns_mapping(self):
        features = get_package_features(self.package)
        self.assertEqual(features.get("attendance"), True)
        self.assertEqual(features.get("sms"), False)

    def test_get_package_limit_returns_value_or_none(self):
        self.assertEqual(get_package_limit(self.package, "max_students"), 250)
        self.assertIsNone(get_package_limit(self.package, "monthly_sms"))
        self.assertIsNone(get_package_limit(None, "max_students"))

    def test_apply_features_rejects_duplicates(self):
        with self.assertRaises(Exception):
            PackageService.apply_features(self.package, [
                {"code": "attendance", "enabled": True},
                {"code": "attendance", "enabled": True},
            ])

    def test_apply_features_rejects_unknown_code(self):
        with self.assertRaises(Exception):
            PackageService.apply_features(self.package, [{"code": "nope", "enabled": True}])

    def test_apply_limits_rejects_duplicate_key(self):
        with self.assertRaises(Exception):
            PackageService.apply_limits(self.package, [
                {"key": "max_staff", "name": "Max Staff", "value": 1},
                {"key": "max_staff", "name": "Max Staff", "value": 2},
            ])


class FeatureCatalogSyncTests(TestCase):
    def setUp(self):
        Feature.objects.all().delete()

    def test_sync_creates_all_declared_features(self):
        result = sync_feature_catalog()
        self.assertEqual(Feature.objects.count(), len(FEATURES))
        self.assertEqual(result["created"], len(FEATURES))
        self.assertEqual(declared_feature_codes(), set(Feature.objects.values_list("code", flat=True)))

    def test_sync_is_idempotent(self):
        sync_feature_catalog()
        result = sync_feature_catalog()
        self.assertEqual(result["created"], 0)
        self.assertEqual(Feature.objects.count(), len(FEATURES))

    def test_sync_preserves_superadmin_custom_features(self):
        custom = Feature.objects.create(code="my_custom_gate", name="Custom Gate")
        sync_feature_catalog()
        self.assertTrue(Feature.objects.filter(code="my_custom_gate").exists())
        self.assertEqual(custom.pk, Feature.objects.get(code="my_custom_gate").pk)

    def test_sync_refreshes_metadata_but_respects_is_active_toggle(self):
        Feature.objects.create(
            code="attendance", name="Old Name", category="old", is_active=False
        )
        sync_feature_catalog()
        row = Feature.objects.get(code="attendance")
        self.assertNotEqual(row.name, "Old Name")
        self.assertEqual(row.category, "core")
        self.assertFalse(row.is_active)

    def test_package_config_features_are_declared(self):
        from subscriptions.services.seeding import PACKAGE_CONFIG
        declared = declared_feature_codes()
        for config in PACKAGE_CONFIG.values():
            for code in config["features"]:
                self.assertIn(code, declared, f"Undefined feature code: {code}")

    # Declared up front so the registry and the entitlement gates can be wired
    # before the feature ships, but deliberately not sold in any tier yet.
    RESERVED_UNASSIGNED = {
        "finance",
        "parent_portal",
        "ges",
        "eyfs",
        "montessori",
    }

    def test_only_reserved_codes_are_declared_without_a_package(self):
        """A declared-but-unassigned code is a reserved code or a dead gate."""
        from subscriptions.services.seeding import PACKAGE_CONFIG
        assigned = {
            code
            for config in PACKAGE_CONFIG.values()
            for code in config["features"]
        }
        self.assertEqual(
            declared_feature_codes() - assigned,
            self.RESERVED_UNASSIGNED,
            "Declared features are neither reserved nor assigned to a package.",
        )

    def test_service_features_are_enterprise_only(self):
        from subscriptions.services.seeding import PACKAGE_CONFIG
        service_codes = {"onboarding_support", "priority_support"}
        for spec in FEATURES:
            if spec.code not in service_codes:
                continue
            tiers = [
                code
                for code, config in PACKAGE_CONFIG.items()
                if spec.code in config["features"]
            ]
            self.assertEqual(tiers, ["enterprise"])

    def test_standard_tier_student_caps(self):
        from subscriptions.services.seeding import PACKAGE_CONFIG
        expected = {"lite": 250, "advantage": 500, "enterprise": 1000}
        for code, cap in expected.items():
            config = PACKAGE_CONFIG[code]
            self.assertEqual(config["maximum_students"], cap)
            self.assertIn(
                ("max_students", "Maximum Students", cap), config["limits"]
            )


class PackageModelConstraintTests(TransactionTestCase):
    def setUp(self):
        self.package = Package.objects.create(name="C", code="c")
        self.feature = create_feature()

    def test_package_feature_unique_constraint(self):
        PackageFeature.objects.create(package=self.package, feature=self.feature)
        with self.assertRaises(IntegrityError):
            PackageFeature.objects.create(package=self.package, feature=self.feature)

    def test_package_limit_unique_key_constraint(self):
        PackageLimit.objects.create(
            package=self.package, key="max_staff", name="Max Staff", value=1
        )
        with self.assertRaises(IntegrityError):
            PackageLimit.objects.create(
                package=self.package, key="max_staff", name="Max Staff", value=2
            )


class PackageAPITests(APITestCase):
    def setUp(self):
        self.school = create_school()
        self.admin = create_admin_user(self.school)
        self.superadmin = create_superadmin_user()
        self.real_superuser = User.objects.create_superuser(
            email="root@skuumate.com",
            password="password123",
            first_name="Root",
            last_name="User",
        )
        create_feature()
        create_feature(code="sms", name="SMS Alerts")

    def test_superadmin_can_create_package(self):
        self.client.force_authenticate(self.superadmin)
        response = self.client.post(
            reverse("package-list-create"),
            valid_package_payload(),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.json()["data"]
        self.assertEqual(data["code"], "premium")
        self.assertEqual(data["price"], "500.00")
        self.assertEqual(data["maximum_students"], 100)
        enabled = {f["code"] for f in data["features"] if f["enabled"]}
        self.assertIn("attendance", enabled)
        self.assertNotIn("sms", enabled)
        self.assertEqual(data["limits"][0]["key"], "max_staff")

    def test_platform_superuser_can_create_package(self):
        self.client.force_authenticate(self.real_superuser)
        response = self.client.post(
            reverse("package-list-create"),
            valid_package_payload(),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_school_admin_cannot_create_package(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            reverse("package-list-create"),
            valid_package_payload(),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_cannot_access_packages(self):
        response = self.client.post(
            reverse("package-list-create"),
            valid_package_payload(),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        response = self.client.get(reverse("package-list-create"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_package_duplicate_code_rejected(self):
        Package.objects.create(name="Premium", code="premium", price="100.00")
        self.client.force_authenticate(self.superadmin)
        response = self.client.post(
            reverse("package-list-create"),
            valid_package_payload(code="premium"),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_package_negative_price_rejected(self):
        self.client.force_authenticate(self.superadmin)
        response = self.client.post(
            reverse("package-list-create"),
            valid_package_payload(price="-1.00"),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_package_negative_setup_fee_rejected(self):
        self.client.force_authenticate(self.superadmin)
        response = self.client.post(
            reverse("package-list-create"),
            valid_package_payload(setup_fee="-1.00"),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_student_range_validation(self):
        self.client.force_authenticate(self.superadmin)
        response = self.client.post(
            reverse("package-list-create"),
            valid_package_payload(minimum_students=300, maximum_students=100),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_billing_period_rejected(self):
        self.client.force_authenticate(self.superadmin)
        response = self.client.post(
            reverse("package-list-create"),
            valid_package_payload(billing_period="WEEK"),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_duplicate_feature_assignment_rejected(self):
        self.client.force_authenticate(self.superadmin)
        payload = valid_package_payload(
            features=[
                {"code": "attendance", "enabled": True},
                {"code": "attendance", "enabled": True},
            ]
        )
        response = self.client.post(
            reverse("package-list-create"), payload, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unknown_feature_code_rejected(self):
        self.client.force_authenticate(self.superadmin)
        payload = valid_package_payload(
            features=[{"code": "does_not_exist", "enabled": True}]
        )
        response = self.client.post(
            reverse("package-list-create"), payload, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_duplicate_limit_key_rejected(self):
        self.client.force_authenticate(self.superadmin)
        payload = valid_package_payload(
            limits=[
                {"key": "max_staff", "name": "Max Staff", "value": 1},
                {"key": "max_staff", "name": "Max Staff", "value": 2},
            ]
        )
        response = self.client.post(
            reverse("package-list-create"), payload, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_update_package_replaces_configuration(self):
        package = Package.objects.create(
            name="Premium", code="premium", price="500.00"
        )
        PackageService.apply_features(package, [{"code": "attendance", "enabled": True}])
        PackageService.apply_limits(
            package, [{"key": "max_staff", "name": "Max Staff", "value": 25}]
        )

        self.client.force_authenticate(self.superadmin)
        response = self.client.patch(
            reverse("package-retrieve-update", kwargs={"pk": package.pk}),
            {
                "name": "Premium Plus",
                "price": "600.00",
                "features": [{"code": "sms", "enabled": True}],
                "limits": [{"key": "monthly_sms", "name": "Monthly SMS", "value": 1000}],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()["data"]
        self.assertEqual(data["name"], "Premium Plus")
        self.assertEqual(data["price"], "600.00")
        self.assertEqual([f["code"] for f in data["features"]], ["sms"])
        self.assertEqual(data["limits"][0]["key"], "monthly_sms")
        self.assertTrue(package_has_feature(Package.objects.get(pk=package.pk), "sms"))
        self.assertFalse(package_has_feature(Package.objects.get(pk=package.pk), "attendance"))

    def test_activate_and_deactivate_package(self):
        package = Package.objects.create(
            name="Premium", code="premium", price="500.00", is_active=False
        )
        self.client.force_authenticate(self.superadmin)
        response = self.client.post(
            reverse("package-activate", kwargs={"pk": package.pk}),
            {},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(Package.objects.get(pk=package.pk).is_active)

        response = self.client.post(
            reverse("package-deactivate", kwargs={"pk": package.pk}),
            {},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(Package.objects.get(pk=package.pk).is_active)

    def test_packages_filterable_by_is_active(self):
        Package.objects.create(name="Active", code="active", is_active=True)
        Package.objects.create(name="Inactive", code="inactive", is_active=False)
        self.client.force_authenticate(self.superadmin)
        response = self.client.get(
            reverse("package-list-create"), {"is_active": "false"}
        )
        codes = [p["code"] for p in response.json()["data"]]
        self.assertIn("inactive", codes)
        self.assertNotIn("active", codes)

    def test_school_admin_cannot_touch_features(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            reverse("feature-list-create"),
            {"name": "Library", "code": "library"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_superadmin_can_create_and_update_feature(self):
        self.client.force_authenticate(self.superadmin)
        response = self.client.post(
            reverse("feature-list-create"),
            {"name": "Library", "code": "library", "category": "modules"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        feature_id = response.json()["data"]["id"]

        response = self.client.patch(
            reverse("feature-retrieve-update", kwargs={"pk": feature_id}),
            {"is_active": False},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(Feature.objects.get(pk=feature_id).is_active)

    def test_feature_duplicate_code_rejected(self):
        self.client.force_authenticate(self.superadmin)
        response = self.client.post(
            reverse("feature-list-create"),
            {"name": "Attendance Two", "code": "attendance"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_public_plan_list_returns_active_public_packages(self):
        Package.objects.create(
            name="Test Public", code="test-public", price="1000.00",
            is_active=True, is_public=True,
            billing_period=Package.BillingPeriod.TERM,
        )
        Package.objects.create(
            name="Hidden", code="hidden", price="1.00",
            is_active=True, is_public=False,
        )
        response = self.client.get(reverse("plan-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        codes = [p["code"] for p in response.json()["data"]]
        self.assertIn("test-public", codes)
        self.assertNotIn("hidden", codes)


class SubscriptionAPITests(APITestCase):
    """End-to-end coverage for the rebuilt subscription endpoints."""

    def setUp(self):
        from subscriptions.models import Subscription, SubscriptionPayment

        self.Subscription = Subscription
        self.SubscriptionPayment = SubscriptionPayment

        self.school = create_school()
        self.admin = create_admin_user(self.school)
        self.superadmin = create_superadmin_user()

        self.package = Package.objects.create(
            name="Advantage", code="advantage-api",
            price="250.00", setup_fee="50.00",
            billing_period=Package.BillingPeriod.TERM,
            minimum_students=0, maximum_students=500,
            is_active=True, is_public=True,
        )

    def test_trial_eligible_school_subscribes_for_free(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            reverse("school-subscribe"),
            {"plan_id": self.package.pk},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.json()["data"]
        self.assertEqual(data["status"], "trial")
        self.assertTrue(data["is_current"])
        self.assertEqual(data["plan"]["code"], "advantage-api")
        self.assertIn("days_remaining", data)

    def test_paid_subscription_flow_activate_and_link_payment(self):
        # Make the school ineligible for a trial (it already had a real plan).
        self.Subscription.objects.create(
            school=self.school,
            plan=self.package,
            status=self.Subscription.Status.ACTIVE,
            start_date="2020-01-01T00:00:00Z",
            end_date="2099-01-01T00:00:00Z",
            is_paid=True,
        )

        self.client.force_authenticate(self.admin)
        initiate = self.client.post(
            reverse("school-subscribe-initiate"),
            {"plan_id": self.package.pk, "provider": "paystack"},
            format="json",
        )
        self.assertEqual(initiate.status_code, 200)
        reference = initiate.json()["data"]["reference"]
        self.assertTrue(reference.startswith("SIM-"))

        response = self.client.post(
            reverse("school-subscribe"),
            {
                "plan_id": self.package.pk,
                "payment_reference": reference,
                "payment_provider": "paystack",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.json()["data"]
        self.assertEqual(data["status"], "active")
        self.assertTrue(data["is_paid"])

        payment = self.SubscriptionPayment.objects.get(payment_reference=reference)
        self.assertEqual(payment.status, "successful")
        self.assertEqual(payment.school, self.school)
        self.assertEqual(str(payment.subscription_id), data["id"])

    def test_paid_school_without_reference_is_rejected(self):
        self.Subscription.objects.create(
            school=self.school,
            plan=self.package,
            status=self.Subscription.Status.ACTIVE,
            start_date="2020-01-01T00:00:00Z",
            end_date="2099-01-01T00:00:00Z",
            is_paid=True,
        )
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            reverse("school-subscribe"),
            {"plan_id": self.package.pk},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_school_admin_can_list_own_subscriptions(self):
        from subscriptions.services.subscriptions import SubscriptionService

        SubscriptionService.start_trial(
            school=self.school, plan=self.package, activated_by=self.admin
        )
        self.client.force_authenticate(self.admin)
        response = self.client.get(reverse("subscription-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.json()["data"]["results"]
        self.assertTrue(any(r["status"] == "trial" for r in results))

    def test_school_admin_cannot_access_admin_subscriptions(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get(reverse("admin-subscription-list"))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_superadmin_subscribes_school_with_cash_payment(self):
        self.client.force_authenticate(self.superadmin)
        response = self.client.post(
            reverse("admin-subscription-subscribe"),
            {
                "school_id": self.school.pk,
                "plan_id": self.package.pk,
                "status": "active",
                "payment_mode": "cash",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.json()["data"]
        self.assertEqual(data["status"], "active")
        self.assertTrue(data["is_paid"])

        payment = self.SubscriptionPayment.objects.get(school=self.school)
        self.assertEqual(payment.payment_mode, "cash")
        self.assertEqual(payment.provider, "cash")
        self.assertEqual(payment.status, "successful")

    def test_superadmin_paid_subscription_requires_payment_mode(self):
        self.client.force_authenticate(self.superadmin)
        response = self.client.post(
            reverse("admin-subscription-subscribe"),
            {
                "school_id": self.school.pk,
                "plan_id": self.package.pk,
                "status": "active",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_superadmin_start_trial_for_school(self):
        self.client.force_authenticate(self.superadmin)
        response = self.client.post(
            reverse("admin-subscription-subscribe"),
            {
                "school_id": self.school.pk,
                "plan_id": self.package.pk,
                "status": "trial",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.json()["data"]["status"], "trial")

    def test_admin_subscriptions_filters_by_status(self):
        from subscriptions.services.subscriptions import SubscriptionService

        SubscriptionService.start_trial(
            school=self.school, plan=self.package, activated_by=self.admin
        )
        self.client.force_authenticate(self.superadmin)
        response = self.client.get(
            reverse("admin-subscription-list"), {"status": "trial"}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.json()["data"]["results"]
        self.assertTrue(len(results) >= 1)
        self.assertTrue(all(r["status"] == "trial" for r in results))

    def test_admin_subscription_detail(self):
        from subscriptions.services.subscriptions import SubscriptionService

        sub = SubscriptionService.start_trial(
            school=self.school, plan=self.package, activated_by=self.admin
        )
        self.client.force_authenticate(self.superadmin)
        response = self.client.get(
            reverse("admin-subscription-detail", kwargs={"pk": sub.pk})
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["data"]["id"], str(sub.pk))
        self.assertEqual(response.json()["data"]["school"]["id"], str(self.school.pk))


class FeaturePermissionTests(APITestCase):
    """The generated feature gates must never 500, whatever the actor looks like."""

    ENABLED_CODE = "attendance"
    DISABLED_CODE = "sms"

    def setUp(self):
        self.school = create_school()
        self.admin = create_admin_user(self.school)
        self.superadmin = create_superadmin_user()

        self.package = Package.objects.create(
            name="Lite", code="lite-perm", price="100.00",
            billing_period=Package.BillingPeriod.TERM,
        )
        self.attendance = create_feature()
        self.sms = create_feature(code=self.DISABLED_CODE, name="SMS Alerts")
        PackageFeature.objects.create(
            package=self.package, feature=self.attendance, is_enabled=True
        )
        PackageFeature.objects.create(
            package=self.package, feature=self.sms, is_enabled=False
        )

        self.granted = _make_feature_permission(
            self.ENABLED_CODE, "Attendance is not in your package."
        )
        self.withheld = _make_feature_permission(
            self.DISABLED_CODE, "SMS is not in your package."
        )

    def _subscribe(self, subscription_status=None, **kwargs):
        return Subscription.objects.create(
            school=self.school,
            plan=self.package,
            status=subscription_status or Subscription.Status.ACTIVE,
            start_date="2020-01-01T00:00:00Z",
            end_date="2099-01-01T00:00:00Z",
            is_paid=True,
            is_current=True,
            **kwargs,
        )

    def _decision(self, gate, user, method="GET"):
        request = APIRequestFactory().generic(method, "/")
        request.user = user
        return gate().has_permission(request, SimpleNamespace())

    def test_school_admin_without_the_feature_is_denied(self):
        self._subscribe()
        with self.assertRaises(PermissionDenied) as ctx:
            self._decision(self.withheld, self.admin)
        self.assertIn("SMS is not in your package.", str(ctx.exception))

    def test_school_admin_with_the_feature_is_allowed(self):
        self._subscribe()
        self.assertTrue(self._decision(self.granted, self.admin))

    def test_schoolless_superadmin_bypasses_the_gate(self):
        self.assertTrue(self._decision(self.granted, self.superadmin))
        self.assertTrue(self._decision(self.withheld, self.superadmin))

    def test_anonymous_user_is_denied_without_raising(self):
        self.assertFalse(self._decision(self.granted, AnonymousUser()))

    def test_school_without_a_subscription_is_denied_not_crashed(self):
        with self.assertRaises(PermissionDenied) as ctx:
            self._decision(self.granted, self.admin)
        self.assertIn("No active subscription", str(ctx.exception))

    def test_package_without_the_feature_row_is_denied(self):
        self._subscribe()
        PackageFeature.objects.filter(
            package=self.package, feature=self.attendance
        ).delete()
        with self.assertRaises(PermissionDenied):
            self._decision(self.granted, self.admin)

    def test_subscription_without_a_plan_is_denied_not_crashed(self):
        Subscription.objects.create(
            school=self.school, plan=None,
            status=Subscription.Status.ACTIVE,
            start_date="2020-01-01T00:00:00Z",
            end_date="2099-01-01T00:00:00Z",
            is_paid=False, is_current=True,
        )
        with self.assertRaises(PermissionDenied):
            self._decision(self.granted, self.admin)

    def test_locked_subscription_is_denied_before_the_feature_check(self):
        self._subscribe(Subscription.Status.LOCKED)
        with self.assertRaises(PermissionDenied) as ctx:
            self._decision(self.granted, self.admin)
        self.assertIn("expired", str(ctx.exception))

    def test_grace_period_blocks_writes_but_allows_reads(self):
        self._subscribe(Subscription.Status.GRACE)
        self.assertTrue(self._decision(self.granted, self.admin, method="GET"))
        with self.assertRaises(PermissionDenied) as ctx:
            self._decision(self.granted, self.admin, method="POST")
        self.assertIn("grace period", str(ctx.exception))


class EntitlementMapTests(TestCase):
    """The map the frontend reads must be complete and reflect real rows."""

    def setUp(self):
        self.school = create_school(name="Entitlement School", code="ES")
        self.package = Package.objects.create(
            name="Lite", code="lite-ent", price="100.00",
            billing_period=Package.BillingPeriod.TERM, maximum_students=250,
        )
        self.attendance = create_feature()
        PackageFeature.objects.create(
            package=self.package, feature=self.attendance, is_enabled=True
        )
        PackageLimit.objects.create(
            package=self.package, key="max_students", name="Maximum Students", value=250
        )

    def _subscription(self, **kwargs):
        subscription = Subscription.objects.create(
            school=self.school,
            plan=self.package,
            status=Subscription.Status.ACTIVE,
            start_date="2020-01-01T00:00:00Z",
            end_date="2099-01-01T00:00:00Z",
            is_paid=True,
            is_current=True,
            **kwargs,
        )
        # Reload so date fields are real datetimes, matching what the service
        # layer hands to subscription_entitlements() in production.
        subscription.refresh_from_db()
        return subscription

    def test_every_declared_code_is_present(self):
        entitlements = feature_entitlement_map(self.package)
        self.assertEqual(set(entitlements), declared_feature_codes())

    def test_enabled_and_disabled_codes_are_distinguished(self):
        entitlements = feature_entitlement_map(self.package)
        self.assertTrue(entitlements["attendance"])
        self.assertFalse(entitlements["sms"])
        self.assertFalse(entitlements["onboarding_support"])

    def test_none_package_reports_all_declared_codes_as_false(self):
        entitlements = feature_entitlement_map(None)
        self.assertEqual(set(entitlements), declared_feature_codes())
        self.assertFalse(any(entitlements.values()))

    def test_ad_hoc_feature_appears_when_enabled(self):
        custom = create_feature(code="custom_widget", name="Custom Widget")
        PackageFeature.objects.create(
            package=self.package, feature=custom, is_enabled=True
        )
        self.assertTrue(feature_entitlement_map(self.package)["custom_widget"])

    def test_limit_row_wins_over_the_duplicate_package_column(self):
        PackageLimit.objects.filter(
            package=self.package, key="max_students"
        ).update(value=300)
        self.assertEqual(resolve_package_limits(self.package)["max_students"], 300)

    def test_limit_falls_back_to_the_package_column(self):
        PackageLimit.objects.filter(package=self.package, key="max_students").delete()
        self.assertEqual(resolve_package_limits(self.package)["max_students"], 250)

    def test_snapshot_without_a_subscription_is_locked(self):
        snapshot = subscription_entitlements(None)
        self.assertFalse(snapshot["has_subscription"])
        self.assertTrue(snapshot["is_locked"])
        self.assertIsNone(snapshot["package"])
        self.assertEqual(set(snapshot["features"]), declared_feature_codes())

    def test_snapshot_reports_plan_and_state(self):
        snapshot = subscription_entitlements(self._subscription())
        self.assertTrue(snapshot["has_subscription"])
        self.assertFalse(snapshot["is_locked"])
        self.assertEqual(snapshot["package"]["code"], "lite-ent")
        self.assertEqual(snapshot["limits"]["max_students"], 250)


class CurrentEntitlementsAPITests(APITestCase):
    def setUp(self):
        self.school = create_school(name="API Entitlement School", code="AE")
        self.admin = create_admin_user(self.school)
        self.superadmin = create_superadmin_user()
        self.url = reverse("subscription-current-features")

    def test_anonymous_is_rejected(self):
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_school_admin_gets_the_entitlement_map(self):
        package = Package.objects.create(
            name="Lite", code="lite-api", price="100.00",
            billing_period=Package.BillingPeriod.TERM, maximum_students=250,
        )
        PackageFeature.objects.create(
            package=package, feature=create_feature(), is_enabled=True
        )
        Subscription.objects.create(
            school=self.school, plan=package,
            status=Subscription.Status.ACTIVE,
            start_date="2020-01-01T00:00:00Z",
            end_date="2099-01-01T00:00:00Z",
            is_paid=True, is_current=True,
        )

        self.client.force_authenticate(self.admin)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]
        self.assertTrue(data["has_subscription"])
        self.assertEqual(set(data["features"]), declared_feature_codes())
        self.assertTrue(data["features"]["attendance"])
        self.assertFalse(data["features"]["export"])
        self.assertEqual(data["limits"]["max_students"], 250)

    def test_school_without_a_subscription_still_gets_a_well_formed_map(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]
        self.assertFalse(data["has_subscription"])
        self.assertTrue(data["is_locked"])
        self.assertEqual(set(data["features"]), declared_feature_codes())

    def test_platform_superadmin_gets_a_well_formed_map(self):
        self.client.force_authenticate(self.superadmin)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]
        self.assertFalse(data["has_subscription"])
        self.assertEqual(set(data["features"]), declared_feature_codes())

    def test_school_user_without_a_school_is_rejected(self):
        orphan = User.objects.create_user(
            email="orphan@school.com", password="password123",
            first_name="No", last_name="School", role=User.Role.ADMIN,
        )
        self.client.force_authenticate(orphan)
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_404_NOT_FOUND)


class FeatureGateWiringTests(SimpleTestCase):
    """Guards against a gate being dropped from a view by a later refactor.

    These are structural assertions rather than HTTP round-trips: the point is
    that a view never silently loses its entitlement check, which a functional
    test would only catch while some other part of the view happens to fail
    first.
    """

    def _enforced_codes(self, module_path, class_name):
        view = getattr(import_module(module_path), class_name)
        return {
            getattr(permission, "enforced_feature_code", None)
            for permission in view.permission_classes
        }

    def _assert_gated(self, module_path, class_name, feature_code):
        self.assertIn(
            feature_code,
            self._enforced_codes(module_path, class_name),
            f"{module_path}.{class_name} no longer requires '{feature_code}'.",
        )

    def test_export_endpoints_require_the_export_feature(self):
        for module_path, class_name in [
            ("academics.views.academic_year_views", "AcademicYearExportView"),
            ("academics.views.subject_views", "SubjectExportView"),
            ("academics.views.academic_term_views", "TermExportView"),
            ("academics.views.class_views", "ClassExportView"),
            ("attendance.views", "AttendanceExportView"),
            ("attendance.views", "AttendanceSummaryExportView"),
            ("accounts.views", "UserExportView"),
            ("students.views", "StudentExportView"),
            ("staff.views", "StaffExportView"),
        ]:
            with self.subTest(view=class_name):
                self._assert_gated(module_path, class_name, "export")

    def test_every_attendance_endpoint_requires_the_attendance_feature(self):
        for class_name in [
            "BulkMarkAttendanceView",
            "AttendanceListView",
            "AttendanceExportView",
            "AttendanceDetailView",
            "ClassAttendanceSheetView",
            "AttendanceSummaryListView",
            "AttendanceSummaryExportView",
            "StudentAttendanceReportView",
            "ClassAttendanceReportView",
        ]:
            with self.subTest(view=class_name):
                self._assert_gated("attendance.views", class_name, "attendance")

    def test_broadcast_endpoints_require_the_announcements_feature(self):
        for class_name in [
            "NotificationTemplateListCreateView",
            "NotificationTemplateDetailView",
            "NotificationListCreateView",
            "NotificationDetailView",
            "NotificationRecipientsListView",
        ]:
            with self.subTest(view=class_name):
                self._assert_gated(
                    "communications.views", class_name, "announcements"
                )

    def test_audit_log_endpoints_require_the_activity_logs_feature(self):
        for class_name in ["AuditLogListView", "ClearAuditLogsView"]:
            with self.subTest(view=class_name):
                self._assert_gated("core.views", class_name, "activity_logs")

    def test_advanced_finance_gates_the_finance_manager_dashboard(self):
        self._assert_gated(
            "dashboard.views", "FinanceManagerDashboardView", "advanced_finance"
        )

    def test_finance_reports_require_their_own_features(self):
        self._assert_gated(
            "finance.views", "FinancialOverviewView", "finance_analytics"
        )
        for class_name in [
            "IncomeTypeListCreateView",
            "IncomeTypeDetailView",
            "ExpenseTypeListCreateView",
            "ExpenseTypeDetailView",
            "OtherIncomeListCreateView",
            "OtherIncomeDetailView",
            "ExpenseListCreateView",
            "ExpenseDetailView",
        ]:
            with self.subTest(view=class_name):
                self._assert_gated(
                    "finance.views", class_name, "income_expense_tracking"
                )
        for class_name in [
            "IncomeStatementView",
            "IncomeByTypeReportView",
            "ExpenseByTypeReportView",
        ]:
            with self.subTest(view=class_name):
                self._assert_gated(
                    "finance.views", class_name, "financial_reports"
                )


class EnterpriseServiceFeatureMigrationTests(TestCase):
    """The new Enterprise entitlements must reach an existing database."""

    MIGRATION = "subscriptions.migrations.0010_enterprise_service_features"

    def setUp(self):
        self.module = import_module(self.MIGRATION)
        self.apps = django_apps
        self.service_codes = [
            code for code, _, _ in self.module.SERVICE_FEATURES
        ]
        self.enterprise, _ = Package.objects.get_or_create(
            code="enterprise",
            defaults={
                "name": "Enterprise",
                "price": "3000.00",
                "billing_period": Package.BillingPeriod.TERM,
                "maximum_students": 1000,
            },
        )
        self.lite, _ = Package.objects.get_or_create(
            code="lite",
            defaults={
                "name": "Lite",
                "price": "1000.00",
                "billing_period": Package.BillingPeriod.TERM,
                "maximum_students": 250,
            },
        )
        # Earlier migrations and the post_migrate catalog sync may already have
        # granted these, so start from a known-empty state.
        PackageFeature.objects.filter(
            package=self.enterprise, feature__code__in=self.service_codes
        ).delete()
        PackageFeature.objects.filter(
            package=self.lite, feature__code__in=self.service_codes
        ).delete()

    def _enabled_codes(self, package):
        return set(
            PackageFeature.objects.filter(
                package=package, is_enabled=True
            ).values_list("feature__code", flat=True)
        )

    def test_forward_grants_both_service_features_to_enterprise(self):
        self.module.forward(self.apps, None)
        self.assertTrue(
            {"onboarding_support", "priority_support"}
            <= self._enabled_codes(self.enterprise)
        )

    def test_forward_leaves_other_tiers_alone(self):
        self.module.forward(self.apps, None)
        self.assertEqual(
            self._enabled_codes(self.lite)
            & {"onboarding_support", "priority_support"},
            set(),
        )

    def test_forward_is_idempotent(self):
        self.module.forward(self.apps, None)
        self.module.forward(self.apps, None)
        self.assertEqual(
            PackageFeature.objects.filter(
                package=self.enterprise,
                feature__code__in=["onboarding_support", "priority_support"],
            ).count(),
            2,
        )

    def test_forward_is_a_no_op_without_an_enterprise_package(self):
        Package.objects.filter(code="enterprise").delete()
        # Must not raise, and must not grant anything to the other tiers.
        self.module.forward(self.apps, None)
        self.assertEqual(
            self._enabled_codes(self.lite) & set(self.service_codes), set()
        )

    def test_backward_removes_only_the_granted_rows(self):
        keep = create_feature(code="school_branding", name="School Branding")
        PackageFeature.objects.update_or_create(
            package=self.enterprise, feature=keep, defaults={"is_enabled": True}
        )
        self.module.forward(self.apps, None)
        self.module.backward(self.apps, None)

        self.assertTrue(self._enabled_codes(self.enterprise) & {"school_branding"})
        self.assertEqual(
            self._enabled_codes(self.enterprise) & set(self.service_codes), set()
        )

    def test_migrated_features_are_declared_in_the_catalog(self):
        self.assertIn("onboarding_support", declared_feature_codes())
        self.assertIn("priority_support", declared_feature_codes())


class SubscriptionStateEnforcementTests(APITestCase):
    """LOCKED must stop the school entirely, GRACE must stop its writes.

    These drive real bearer tokens rather than ``force_authenticate`` on
    purpose. The API's only authenticator is JWT, so ``request.user`` is
    anonymous at middleware time; a test that skips authentication would pass
    without ever exercising the code that enforces anything.
    """

    def setUp(self):
        self.school = create_school(name="State School", code="ST")
        self.admin = create_admin_user(self.school, email="admin@state.com")
        self.package = Package.objects.create(
            name="Lite", code="lite-state", price="100.00",
            billing_period=Package.BillingPeriod.TERM, maximum_students=250,
        )
        self.subscription = Subscription.objects.create(
            school=self.school, plan=self.package,
            status=Subscription.Status.ACTIVE,
            start_date="2020-01-01T00:00:00Z",
            end_date="2099-01-01T00:00:00Z",
            is_paid=True, is_current=True,
        )
        self._authenticate(self.admin)

    def _authenticate(self, user):
        token = RefreshToken.for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")

    def _set_state(self, subscription_status, **fields):
        self.subscription.status = subscription_status
        for field, value in fields.items():
            setattr(self.subscription, field, value)
        self.subscription.save()

    def _to_grace(self):
        self._set_state(
            Subscription.Status.GRACE,
            end_date=timezone.now() - timedelta(days=200),
            grace_end_date=timezone.now() + timedelta(days=3),
        )

    def _student_payload(self, first_name="Ada"):
        return {
            "first_name": first_name,
            "last_name": "Lovelace",
            "gender": "female",
            "email": f"{first_name.lower()}@state.com",
        }

    # -- ACTIVE: nothing changes -----------------------------------------

    def test_active_school_reads_and_writes_normally(self):
        self.assertEqual(
            self.client.get(reverse("student-list")).status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            self.client.post(
                reverse("student-list"), self._student_payload(), format="json"
            ).status_code,
            status.HTTP_201_CREATED,
        )

    # -- LOCKED: everything gated, billing reachable ----------------------

    def test_locked_school_cannot_read_ungated_endpoints(self):
        """This is the hole the middleware closes: no feature gate on this view."""
        self._set_state(Subscription.Status.LOCKED)
        response = self.client.get(reverse("student-list"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("expired", response.json()["message"])

    def test_locked_school_cannot_write_ungated_endpoints(self):
        self._set_state(Subscription.Status.LOCKED)
        response = self.client.post(
            reverse("student-list"), self._student_payload(), format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Student.objects.filter(school=self.school).exists())

    def test_locked_school_cannot_read_the_user_directory(self):
        self._set_state(Subscription.Status.LOCKED)
        self.assertEqual(
            self.client.get(reverse("user-detail", args=[self.admin.pk])).status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_locked_school_can_still_reach_billing(self):
        """A school that cannot reach the payment page cannot pay its way out."""
        self._set_state(Subscription.Status.LOCKED)
        for url_name in [
            "subscription-current",
            "subscription-current-features",
            "plan-list",
        ]:
            with self.subTest(url=url_name):
                self.assertEqual(
                    self.client.get(reverse(url_name)).status_code,
                    status.HTTP_200_OK,
                )

    def test_locked_school_can_still_bootstrap_the_session(self):
        self._set_state(Subscription.Status.LOCKED)
        self.assertEqual(
            self.client.get(reverse("me")).status_code, status.HTTP_200_OK
        )

    # -- GRACE: reads fine, writes blocked --------------------------------

    def test_grace_school_can_still_read(self):
        self._to_grace()
        self.assertEqual(
            self.client.get(reverse("student-list")).status_code,
            status.HTTP_200_OK,
        )

    def test_grace_school_cannot_write_ungated_endpoints(self):
        self._to_grace()
        response = self.client.post(
            reverse("student-list"), self._student_payload(), format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("grace period", response.json()["message"])
        self.assertFalse(Student.objects.filter(school=self.school).exists())

    def test_grace_school_can_still_reach_billing(self):
        self._to_grace()
        self.assertEqual(
            self.client.get(reverse("plan-list")).status_code,
            status.HTTP_200_OK,
        )

    # -- No subscription: must stay able to sign up -----------------------

    def test_school_with_no_subscription_can_still_reach_subscribe_flow(self):
        """Registration does not provision a subscription; subscribe is the entry."""
        self.subscription.delete()
        for url_name in ["me", "plan-list", "plan-features"]:
            with self.subTest(url=url_name):
                self.assertEqual(
                    self.client.get(reverse(url_name)).status_code,
                    status.HTTP_200_OK,
                )

    def test_school_with_no_subscription_is_still_denied_gated_features(self):
        """State stays permissive, entitlements do not."""
        self.subscription.delete()
        PackageFeature.objects.create(
            package=self.package, feature=create_feature("export", "Export"),
            is_enabled=False,
        )
        self.assertEqual(
            self.client.get(reverse("student-export")).status_code,
            status.HTTP_403_FORBIDDEN,
        )

    # -- Actors outside the state machine ---------------------------------

    def test_platform_superadmin_is_unaffected(self):
        self._set_state(Subscription.Status.LOCKED)
        self._authenticate(create_superadmin_user())
        self.assertEqual(
            self.client.get(reverse("school-list")).status_code,
            status.HTTP_200_OK,
        )

    def test_anonymous_requests_are_left_to_the_view(self):
        self.client.credentials()
        self._set_state(Subscription.Status.LOCKED)
        self.assertIn(
            self.client.get(reverse("student-list")).status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

    def test_expired_token_is_reported_as_unauthorized_not_locked(self):
        """Middleware must not turn a bad token into a subscription error."""
        self.client.credentials(HTTP_AUTHORIZATION="Bearer not-a-real-token")
        self._set_state(Subscription.Status.LOCKED)
        self.assertEqual(
            self.client.get(reverse("student-list")).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_middleware_attaches_the_subscription_to_the_request(self):
        self.assertEqual(
            self.client.get(reverse("subscription-current-features")).status_code,
            status.HTTP_200_OK,
        )

    def test_active_school_is_not_blocked_anywhere(self):
        """Regression guard for the middleware itself.

        The rest of this module's suite, and most of the project's, uses
        ``force_authenticate`` -- which bypasses the authenticator, so the
        middleware sees an anonymous request and does nothing. A bug that broke
        every real bearer-token request would sail through all of those. This
        drives a real token across a spread of apps and asserts the state gate
        never fires, whatever the view's own permissions decide.
        """
        feature = create_feature("export", "Export")
        PackageFeature.objects.get_or_create(
            package=self.package, feature=feature, defaults={"is_enabled": True}
        )
        targets = [
            "me",
            "student-list",
            "school-profile",
            "school-onboarding",
            "audit-logs",
            "academic-year-list",
            "subject-list",
            "attendance-list",
            "fee-component-list",
            "staff-list",
            "notification-list",
            "plan-list",
        ]
        for url_name in targets:
            with self.subTest(url=url_name):
                try:
                    url = reverse(url_name)
                except NoReverseMatch:
                    continue
                response = self.client.get(url)
                body = response.content.decode()
                self.assertNotIn(
                    "subscription has expired", body, f"{url_name} was state-blocked."
                )
                self.assertNotIn(
                    "grace period", body, f"{url_name} was state-blocked."
                )


class SubscriptionMiddlewareUnitTests(SimpleTestCase):
    """The exemption list is the safety valve; it needs to stay correct."""

    def _request(self, method="GET", path="/api/v1/students/"):
        request = SimpleNamespace(
            method=method,
            path_info=path,
            user=SimpleNamespace(is_authenticated=True, school=object()),
        )
        return request

    def test_ungated_path_is_reachable_while_active(self):
        self.assertIsNone(
            evaluate_request_state(
                self._request(), user=self._request().user, subscription=SimpleNamespace(
                    is_locked=False, is_read_only=False, days_remaining=10
                )
            )
        )

    def test_locked_blocks_a_plain_read(self):
        denial = evaluate_request_state(
            self._request(),
            user=self._request().user,
            subscription=SimpleNamespace(
                is_locked=True, is_read_only=False, days_remaining=0
            ),
        )
        self.assertIn("expired", denial)

    def test_every_always_reachable_name_resolves_to_a_real_url(self):
        """A typo in the exemption list is a silently bypassed gate."""
        for url_name in sorted(ALWAYS_REACHABLE_URL_NAMES):
            with self.subTest(url_name=url_name):
                try:
                    reverse(url_name)
                except NoReverseMatch:
                    # Parameterised route (e.g. the provider webhooks).
                    try:
                        reverse(url_name, args=["stub"])
                    except NoReverseMatch:
                        self.fail(
                            f"ALWAYS_REACHABLE_URL_NAMES lists '{url_name}', "
                            "which no route defines."
                        )
