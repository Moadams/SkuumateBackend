"""Keep the platform permission registry in sync with the application.

Platform permissions are declared once in ``platform_rbac.permission_registry`` —
exactly like Django auto-creates permissions from ``Meta.permissions`` on
``migrate``. ``seed_platform_permissions`` upserts those declarations and is
dispatched after every ``migrate`` (see ``PlatformRbacConfig.ready``), so the
super administrator never has to create standard permissions one by one.
"""
from django.db import OperationalError

from .models import PlatformPermission
from .permission_registry import PERMISSION_SPECS

__all__ = ["seed_platform_permissions", "seed_on_migrate"]


def seed_platform_permissions(verbosity=0):
    """Create missing permissions and refresh metadata for declared codes.

    Idempotent. Never deletes rows: an administrator's ``is_active`` toggle on
    a declared permission is respected (only metadata is refreshed). Permissions
    cannot be created arbitrarily through the API — the registry is the only
    source of platform permissions.
    """
    created = updated = 0
    declared = {spec.code: spec for spec in PERMISSION_SPECS}
    existing = {row.code: row for row in PlatformPermission.objects.all()}

    for code, spec in declared.items():
        row = existing.get(code)
        if row is None:
            PlatformPermission.objects.create(
                code=spec.code,
                name=spec.name,
                description=spec.description,
                module=spec.module,
                is_active=True,
                is_system=True,
            )
            created += 1
            continue

        if (
            row.name != spec.name
            or row.description != spec.description
            or row.module != spec.module
        ):
            row.name = spec.name
            row.description = spec.description
            row.module = spec.module
            row.save(update_fields=["name", "description", "module", "updated_at"])
            updated += 1

    if verbosity:
        print(f"Platform permissions synced: {created} created, {updated} updated.")
    return {"created": created, "updated": updated}


def seed_on_migrate(sender, app_config=None, verbosity=2, **kwargs):
    """post_migrate receiver — auto-populate the registry after every migrate."""
    if app_config is not None and app_config.name != "platform_rbac":
        return
    try:
        seed_platform_permissions(verbosity=verbosity)
    except OperationalError:
        # platform tables don't exist yet (partial migrate) — skip.
        pass