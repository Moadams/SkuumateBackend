"""Seed the platform's default SMS bundles.

Bundles are editable in the Django admin after this migration runs. Tests run
with migrations disabled, so tests that need a bundle create it themselves.
"""
from django.db import migrations

BUNDLES = (
    {
        "code": "sms-200",
        "name": "Starter 200",
        "credits": 200,
        "price": "20.00",
        "description": "200 SMS credits (about 200 short messages).",
        "display_order": 1,
    },
    {
        "code": "sms-1000",
        "name": "Growth 1,000",
        "credits": 1000,
        "price": "80.00",
        "description": "1,000 SMS credits at a lower unit price.",
        "display_order": 2,
    },
    {
        "code": "sms-5000",
        "name": "Scale 5,000",
        "credits": 5000,
        "price": "350.00",
        "description": "5,000 SMS credits for high-volume schools.",
        "display_order": 3,
    },
)


def seed_bundles(apps, schema_editor):
    SMSBundle = apps.get_model("communications", "SMSBundle")
    for row in BUNDLES:
        SMSBundle.objects.update_or_create(
            code=row["code"],
            defaults={
                "name": row["name"],
                "credits": row["credits"],
                "price": row["price"],
                "description": row["description"],
                "display_order": row["display_order"],
                "currency": "GHS",
                "is_active": True,
            },
        )


def unseed_bundles(apps, schema_editor):
    SMSBundle = apps.get_model("communications", "SMSBundle")
    SMSBundle.objects.filter(code__in=[row["code"] for row in BUNDLES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("communications", "0005_smsbundle_smsledgerentry_smspurchase_smswallet_and_more"),
    ]

    operations = [
        migrations.RunPython(seed_bundles, unseed_bundles),
    ]
