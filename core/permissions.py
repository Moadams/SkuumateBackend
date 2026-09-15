from rest_framework.permissions import BasePermission

from subscriptions.permissions import HasAuditLogAccess

# Legacy role → key mapping used ONLY during the transition, for
# users who do not yet have positions/grants attached.
LEGACY_ROLE_KEYS = {
    "admin": {"school.manage"},
    "teacher": {"class.teach"},
    "finance_manager": {"finance.view"},
    "student": set(),
    "superadmin": set(),
}


def effective_keys(user):
    """
    Returns the set of permission keys held by a user.
    Staff use their profile's fine-grained permissions; users without
    a profile fall back to their legacy role mapping.
    """
    if user.is_superuser:
        return set()
    profile = getattr(user, "staff_profile", None)
    if profile is not None:
        return profile.effective_permissions()
    return LEGACY_ROLE_KEYS.get(getattr(user, "role", ""), set())


class HasPermission(BasePermission):
    """
    Requires ALL of the listed permission keys.
    Superusers and school administrators (via school.manage) pass.
    """
    required_keys = ()

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        keys = effective_keys(request.user)
        if "school.manage" in keys:
            return True
        return set(self.required_keys) <= keys


class HasAnyPermission(BasePermission):
    """
    Requires ANY of the listed permission keys.
    Superusers and school administrators (via school.manage) pass.
    """
    required_keys = ()

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        keys = effective_keys(request.user)
        if "school.manage" in keys:
            return True
        return bool(set(self.required_keys) & keys)


def require_permission(*keys):
    """Returns a HasPermission subclass requiring ALL the given keys."""
    return type(
        "RequirePermission",
        (HasPermission,),
        {"required_keys": keys},
    )


def require_any_permission(*keys):
    """Returns a HasAnyPermission subclass requiring ANY of the given keys."""
    return type(
        "RequireAnyPermission",
        (HasAnyPermission,),
        {"required_keys": keys},
    )


class IsAdmin(BasePermission):
    """Only school admins can access."""
    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.role == "admin" and
            request.user.school is not None
        )

class IsAdminOrReadOnly(BasePermission):
    """Admins can access, others can only read."""
    def has_permission(self, request, view):
        if request.user and request.user.is_authenticated:
            if request.user.role == "admin":
                return True

            return request.method in ("GET", "HEAD", "OPTIONS")
        return False


class IsTeacher(BasePermission):
    """Only teachers can access."""
    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.role == "teacher"
        )

class IsStudent(BasePermission):
    """Only students can access."""
    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.role == "student"
        )

class IsFinanceManager(BasePermission):
    """Only finance managers can access."""
    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.role == "finance_manager"
        )

class IsAdminOrTeacher(BasePermission):
    """Admins and teachers can access."""
    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.role in ("admin", "teacher")
        )

class IsAdminOrTeacherReadOnly(BasePermission):
    """Admins and teachers can access, but teachers have read-only access."""
    def has_permission(self, request, view):
        if request.user and request.user.is_authenticated:
            if request.user.role == "admin":
                return True
            elif request.user.role == "teacher":
                return request.method in ("GET", "HEAD", "OPTIONS")
        return False

class IsSuperAdmin(BasePermission):
    """Only super admins can access."""
    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.role == "superadmin"
        )

class OrPermission(BasePermission):
    """
    Grants access if ANY of the listed permission classes pass.
    """

    permissions = []  # override in subclasses

    def has_permission(self, request, view):
        return any(
            perm().has_permission(request, view)
            for perm in self.permissions
        )

    def has_object_permission(self, request, view, obj):
        return any(
            perm().has_object_permission(request, view, obj)
            for perm in self.permissions
            if hasattr(perm(), "has_object_permission")
        )


class CanAccessAuditLogs(OrPermission):

    permissions = [
        IsAdmin,
        IsSuperAdmin,
    ]
