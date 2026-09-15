from django.db import migrations


def copy_legacy_permissions(apps, schema_editor):
    """Port each position's JSON key list into registry rows + M2M links."""
    PermissionKey = apps.get_model("staff", "PermissionKey")
    StaffPosition = apps.get_model("staff", "StaffPosition")

    for position in StaffPosition.objects.all().iterator():
        keys = position.legacy_permissions or []
        if not keys:
            continue
        permission_objs = []
        for key in keys:
            obj, _ = PermissionKey.objects.get_or_create(
                key=key,
                defaults={
                    "label": key,
                    "module": key.split(".")[0].capitalize(),
                    "is_system": True,
                },
            )
            permission_objs.append(obj)
        position.permissions.set(permission_objs)


def reverse_migrate(apps, schema_editor):
    """Write M2M keys back into the JSON column."""
    StaffPosition = apps.get_model("staff", "StaffPosition")

    for position in StaffPosition.objects.prefetch_related("permissions").iterator():
        position.legacy_permissions = list(
            position.permissions.values_list("key", flat=True)
        )
        position.save(update_fields=["legacy_permissions"])


class Migration(migrations.Migration):

    dependencies = [
        ("staff", "0005_permissionkey_and_finegrained_access"),
    ]

    operations = [
        migrations.RunPython(copy_legacy_permissions, reverse_migrate),
        migrations.RemoveField(
            model_name="staffposition",
            name="legacy_permissions",
        ),
    ]