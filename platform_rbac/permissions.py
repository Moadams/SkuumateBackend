"""DRF permission classes for the platform (superadmin) authorization layer."""
from rest_framework.permissions import BasePermission

from .services import has_platform_permission


class HasPlatformPermission(BasePermission):
    """Grants access when the user holds ``required_platform_permission``.

    Root Django superusers always pass. ``required_platform_permission=None``
    means "any platform actor" (root or superadmin-role staff user).
    """
    required_platform_permission = None

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if user is None or not getattr(user, "is_authenticated", False):
            return False
        return has_platform_permission(user, self.required_platform_permission)


def require_platform_permission(code):
    """Factory for a permission class bound to one ``module.action`` code."""
    return type(
        f"RequirePlatform{''.join(p.title() for p in code.split('.'))}",
        (HasPlatformPermission,),
        {"required_platform_permission": code},
    )


class HasAnyPlatformPermission(BasePermission):
    """Grants access when the user holds any of ``required_platform_permissions``."""
    required_platform_permissions = ()

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if user is None or not getattr(user, "is_authenticated", False):
            return False
        return any(
            has_platform_permission(user, code)
            for code in self.required_platform_permissions
        )