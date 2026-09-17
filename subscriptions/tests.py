from datetime import date

from django.db import IntegrityError
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from schools.models import School
from subscriptions.models import (
    Feature,
    Package,
    PackageFeature,
    PackageLimit,
)
from subscriptions.serializers import PackageSerializer
from subscriptions.feature_catalog import FEATURES, declared_feature_codes
from subscriptions.services.packages import (
    PackageService,
    get_package_features,
    get_package_limit,
    package_has_feature,
)
from subscriptions.sync import sync_feature_catalog


def create_school(name="Test School", code="TS"):
    return School.objects.create(
        name=name,
        school_code=code,
        email=f"{code.lower()}@example.com",
    )


def create_admin_user(school):
    return User.objects.create_user(
        email="admin@school.com",
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
