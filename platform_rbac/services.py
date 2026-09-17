"""Platform authorization services.

Resolution order for ``has_platform_permission`` (section 14):
    1. unauthenticated            -> False
    2. inactive user              -> False
    3. Django ``is_superuser``     -> True (root bypass, no DB records needed)
    4. non-platform user (school)  -> False
    5. any active role permission  -> True

Root (``is_superuser``) is never stored in the join tables and always passes.
Platform staff are identified by the legacy ``User.role == "superadmin"`` marker
(no school). School users always fail platform checks.
"""
from django.core.cache import cache

from core.cache import CacheKeys

from .models import PlatformRolePermission, PlatformUserRole

PLATFORM_STAFF_ROLE = "superadmin"

PLATFORM_ROLES_CACHE_TTL = 15 * 60


def _permission_cache_key(user_id):
    version = cache.get(CacheKeys.PLATFORM_PERMISSIONS_VERSION) or "0"
    return f"{CacheKeys.platform_permissions(user_id)}:v{version}"


def bump_platform_permissions_version():
    """Invalidate every cached platform permission set (monotonic version)."""
    current = cache.get(CacheKeys.PLATFORM_PERMISSIONS_VERSION) or 0
    cache.set(CacheKeys.PLATFORM_PERMISSIONS_VERSION, int(current) + 1, None)


def is_platform_user(user):
    """A platform actor: root superuser or an active superadmin-role staff user."""
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if not user.is_active:
        return False
    if user.is_superuser:
        return True
    return user.role == PLATFORM_STAFF_ROLE and user.school_id is None


def get_user_platform_permissions(user):
    """Effective platform permission codes for a user (empty for non-platform)."""
    if not is_platform_user(user):
        return frozenset()
    if user.is_superuser:
        return frozenset()

    cache_key = _permission_cache_key(user.id)
    cached = cache.get(cache_key)
    if cached is not None:
        return set(cached)

    codes = set(
        PlatformRolePermission.objects.filter(
            role__is_active=True,
            role__user_roles__user=user,
            permission__is_active=True,
        ).values_list("permission__code", flat=True)
    )
    cache.set(cache_key, list(codes), PLATFORM_ROLES_CACHE_TTL)
    return codes


def get_user_platform_roles(user):
    """Assigned platform roles for a user (any ``is_active`` state)."""
    rows = (
        PlatformUserRole.objects.filter(user=user)
        .select_related("role")
        .order_by("role__name")
    )
    return [
        {
            "id": str(row.role.pk),
            "code": row.role.code,
            "name": row.role.name,
            "is_active": row.role.is_active,
        }
        for row in rows
    ]


def user_has_role(user, role_code):
    return PlatformUserRole.objects.filter(
        user=user, role__code=role_code, role__is_active=True
    ).exists()


def has_platform_permission(user, code):
    """Exact per spec section 14 resolution order."""
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if not user.is_active:
        return False
    if user.is_superuser:
        return True
    if user.role != PLATFORM_STAFF_ROLE or user.school_id is not None:
        return False
    if code is None:
        return True
    return code in get_user_platform_permissions(user)


def role_active_permission_codes(role):
    return set(
        role.role_permissions.filter(permission__is_active=True)
        .values_list("permission__code", flat=True)
    )


def roles_active_permission_codes(roles):
    codes = set()
    for role in roles:
        codes |= role_active_permission_codes(role)
    return codes


def validate_assignable_permissions(actor, codes):
    """A non-root actor may only grant permissions they already hold."""
    if actor.is_superuser:
        return
    owned = get_user_platform_permissions(actor)
    missing = set(codes) - owned
    if missing:
        raise PermissionError(
            f"You don't hold permission(s) to grant: {', '.join(sorted(missing))}."
        )


def validate_assignable_roles(actor, roles):
    """A non-root actor may only assign roles whose permissions they hold."""
    if actor.is_superuser:
        return
    owned = get_user_platform_permissions(actor)
    granted = roles_active_permission_codes(roles)
    excess = granted - owned
    if excess:
        raise PermissionError(
            f"Role grants permission(s) you don't hold: {', '.join(sorted(excess))}."
        )


def self_modification_blocked(actor, target_user):
    """Non-root platform staff may not change their own platform access."""
    return target_user.pk == actor.pk and not actor.is_superuser
