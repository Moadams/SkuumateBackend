"""Package domain services and reusable feature/limit helpers.

These helpers are the single source of truth for reading a package's
entitlements and usage restrictions. The Subscription module (and other
apps) should call these instead of reaching into PackageFeature
directly.
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from subscriptions.models import Feature, Package, PackageFeature, PackageLimit


# ─────────────────────────────────────────────────────────────────────
# Read-side helpers
# ─────────────────────────────────────────────────────────────────────

def get_enabled_feature_codes(package) -> set:
    """Return the set of feature codes currently enabled for a package."""
    if package is None:
        return set()
    return set(
        PackageFeature.objects
        .filter(package=package, is_enabled=True)
        .values_list("feature__code", flat=True)
    )


def get_package_features(package) -> Dict[str, bool]:
    """Return ``{feature_code: is_enabled}`` for a package."""
    if package is None:
        return {}
    return {
        row.feature.code: bool(row.is_enabled)
        for row in PackageFeature.objects
        .filter(package=package)
        .select_related("feature")
    }


def package_has_feature(package, feature_code: str) -> bool:
    """Return True if the package enables the given feature code."""
    if package is None or not feature_code:
        return False
    row = (
        PackageFeature.objects
        .filter(package=package, feature__code=feature_code)
        .first()
    )
    return bool(row is not None and row.is_enabled)


def package_feature_details(package) -> List[dict]:
    """Return ``[{code, name, enabled}]`` ordered by category then name."""
    if package is None:
        return []
    return [
        {
            "code": row.feature.code,
            "name": row.feature.name,
            "enabled": bool(row.is_enabled),
        }
        for row in PackageFeature.objects
        .filter(package=package)
        .select_related("feature")
        .order_by("feature__category", "feature__name")
    ]


def get_package_limit(package, limit_key: str) -> Optional[int]:
    """Return the numeric value of a package limit, or None if not set."""
    if package is None or not limit_key:
        return None
    row = PackageLimit.objects.filter(package=package, key=limit_key).first()
    return row.value if row is not None else None


def package_limit_details(package) -> List[dict]:
    """Return ``[{key, name, value, description}]`` for a package."""
    if package is None:
        return []
    return [
        {
            "key": row.key,
            "name": row.name,
            "value": str(row.value),
            "description": row.description,
        }
        for row in PackageLimit.objects.filter(package=package).order_by("key")
    ]


# ─────────────────────────────────────────────────────────────────────
# Write-side helpers
# ─────────────────────────────────────────────────────────────────────

class PackageService:
    """Coordinates configuration changes for a package."""

    @staticmethod
    def apply_features(package, assignments: Iterable[dict]):
        """(Re)build the package's feature entitlements.

        ``assignments`` is an iterable of ``{"code": str, "enabled": bool}``.
        Replaces the full entitlement set so behaviour is predictable.
        """
        assignments = list(assignments)

        codes = [item["code"] for item in assignments]
        duplicates = sorted({c for c in codes if codes.count(c) > 1})
        if duplicates:
            from rest_framework.serializers import ValidationError
            raise ValidationError(
                {"features": f"Duplicate feature codes: {duplicates}"}
            )

        features = {
            f.code: f
            for f in Feature.objects.filter(code__in=codes)
            if f.is_active
        }

        unknown = set(codes) - set(features)
        if unknown:
            from rest_framework.serializers import ValidationError
            raise ValidationError(
                {"features": f"Unknown or inactive feature codes: {sorted(unknown)}"}
            )

        PackageFeature.objects.filter(package=package).delete()
        PackageFeature.objects.bulk_create(
            PackageFeature(
                package=package,
                feature=features[item["code"]],
                is_enabled=bool(item.get("enabled", True)),
            )
            for item in assignments
            if item["code"] in features
        )
        return package

    @staticmethod
    def apply_limits(package, limits: Iterable[dict]):
        """(Re)build the package's usage limits.

        Each item is ``{"key", "name", "value", "description"}``. Keys are
        unique per package (enforced here and by a DB constraint).
        """
        limits = list(limits)

        seen = set()
        for item in limits:
            key = item["key"]
            if key in seen:
                from rest_framework.serializers import ValidationError
                raise ValidationError(
                    {"limits": f"Duplicate limit key: {key}"}
                )
            seen.add(key)

        PackageLimit.objects.filter(package=package).delete()
        PackageLimit.objects.bulk_create(
            PackageLimit(
                package=package,
                key=item["key"],
                name=item.get("name", item["key"]),
                value=item["value"],
                description=item.get("description", ""),
            )
            for item in limits
        )
        return package

    @staticmethod
    def set_active(package, is_active: bool) -> Package:
        """Activate or deactivate a package."""
        package.is_active = bool(is_active)
        package.save(update_fields=["is_active", "updated_at"])
        return package