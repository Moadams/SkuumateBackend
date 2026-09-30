"""Grant the Enterprise tier the two display-only service entitlements.

``onboarding_support`` and ``priority_support`` are commercial benefits with
no API gate, so they only need to exist in the feature registry and be enabled
on the Enterprise package. The registry rows are also created by the
post_migrate catalog sync, but they are upserted here so the migration is
correct on its own and stays idempotent on re-run.
"""
from django.db import migrations


SERVICE_FEATURES = [
    (
        "onboarding_support",
        "Data Migration & Dedicated Onboarding",
        "Data migration of existing records plus dedicated onboarding sessions.",
    ),
    (
        "priority_support",
        "Priority SLA Support & Operational Reviews",
        "Priority response SLA plus scheduled operational review sessions.",
    ),
]

ENTERPRISE_CODES = ["enterprise", "enterprise_tier", "enterprise_plan"]


def forward(apps, schema_editor):
    Feature = apps.get_model("subscriptions", "Feature")
    PackageFeature = apps.get_model("subscriptions", "PackageFeature")
    Package = apps.get_model("subscriptions", "Package")

    enterprise_packages = [
        p for p in Package.objects.all() if (p.code or "") in ENTERPRISE_CODES
    ]
    if not enterprise_packages:
        # Nothing to grant against; a custom database with no Enterprise tier
        # is a valid state, so this is not an error.
        return

    for code, name, description in SERVICE_FEATURES:
        feature, _ = Feature.objects.get_or_create(
            code=code,
            defaults={
                "name": name,
                "description": description,
                "category": "service",
                "is_active": True,
            },
        )
        for package in enterprise_packages:
            PackageFeature.objects.get_or_create(
                package=package,
                feature=feature,
                defaults={"is_enabled": True},
            )


def backward(apps, schema_editor):
    """Remove only the entitlements added here, leaving the registry rows.

    The Feature rows are left in place on purpose: they may already be
    referenced by custom packages, and the post_migrate catalog sync would
    simply recreate them anyway.
    """
    PackageFeature = apps.get_model("subscriptions", "PackageFeature")
    Package = apps.get_model("subscriptions", "Package")

    enterprise_packages = [
        p for p in Package.objects.all() if (p.code or "") in ENTERPRISE_CODES
    ]
    if not enterprise_packages:
        return

    PackageFeature.objects.filter(
        package__in=enterprise_packages,
        feature__code__in=[code for code, _, _ in SERVICE_FEATURES],
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("subscriptions", "0009_subscriptionpayment_discount_applied_coupon_and_more"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
