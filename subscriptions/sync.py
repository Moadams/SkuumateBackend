"""Keep the platform Feature registry in sync with the application.

Features are declared once in ``subscriptions.feature_catalog`` — exactly like
Django auto-creates permissions from ``Meta.permissions`` on ``migrate``.
``sync_feature_catalog`` upserts those declarations and is dispatched after
every ``migrate`` (see ``SubscriptionsConfig.ready``), so the super
administrator never has to create standard features one by one.
"""
from django.db import OperationalError

from .feature_catalog import FEATURES
from .models import Feature


def sync_feature_catalog(verbosity=0):
    """Create missing features and refresh metadata for declared codes.

    Idempotent. Never deletes rows: custom features created by the super
    administrator are preserved, and an administrator's ``is_active`` toggle
    on a declared feature is respected (only metadata is refreshed).
    """
    created = updated = 0
    declared = {spec.code: spec for spec in FEATURES}
    existing = {row.code: row for row in Feature.objects.all()}

    for code, spec in declared.items():
        row = existing.get(code)
        if row is None:
            Feature.objects.create(
                code=spec.code,
                name=spec.name,
                description=spec.description,
                category=spec.category,
                is_active=True,
            )
            created += 1
            continue

        if (
            row.name != spec.name
            or row.description != spec.description
            or row.category != spec.category
        ):
            row.name = spec.name
            row.description = spec.description
            row.category = spec.category
            row.save(update_fields=["name", "description", "category", "updated_at"])
            updated += 1

    if verbosity:
        print(f"Feature catalog synced: {created} created, {updated} updated.")
    return {"created": created, "updated": updated}


def sync_features_on_migrate(sender, app_config=None, verbosity=2, **kwargs):
    """post_migrate receiver — auto-populate the registry after every migrate."""
    if app_config is not None and app_config.name != "subscriptions":
        return
    try:
        sync_feature_catalog(verbosity=verbosity)
    except OperationalError:
        # subscriptions tables don't exist yet (partial migrate) — skip.
        pass