from rest_framework.permissions import BasePermission

from accounts.models import User
from core.access import school_access_allowed

# Legacy role → key mapping used ONLY during the transition, for
# users who do not yet have positions/grants attached.
LEGACY_ROLE_KEYS = {
    "admin": {"school.manage"},
    "teacher": {"class.teach", "students.view", "attendance.view", "attendance.mark", "attendance.edit", "academics.view", "exams.view", "exams.enter_scores", "reports.view", "dashboard.teacher", "settings.view"},
    "finance_manager": {"students.view", "finance.view", "finance.manage_fees", "finance.record_payments", "finance.export", "reports.view", "dashboard.finance", "settings.view"},
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
    if not school_access_allowed(user):
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
        if not school_access_allowed(request.user):
            return False
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
        if not school_access_allowed(request.user):
            return False
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
            school_access_allowed(request.user) and
            request.user.role == "admin" and
            request.user.school is not None
        )

class IsAdminOrReadOnly(BasePermission):
    """Admins can access, others can only read."""
    def has_permission(self, request, view):
        if school_access_allowed(request.user):
            if request.user.role == "admin":
                return True

            return request.method in ("GET", "HEAD", "OPTIONS")
        return False


class IsTeacher(BasePermission):
    """Only teachers can access."""
    def has_permission(self, request, view):
        return bool(
            request.user and
            school_access_allowed(request.user) and
            request.user.role == "teacher"
        )

class IsStudent(BasePermission):
    """Only students can access."""
    def has_permission(self, request, view):
        return bool(
            request.user and
            school_access_allowed(request.user) and
            request.user.role == "student"
        )

class IsFinanceManager(BasePermission):
    """Only finance managers can access."""
    def has_permission(self, request, view):
        return bool(
            request.user and
            school_access_allowed(request.user) and
            request.user.role == "finance_manager"
        )

class IsAdminOrTeacher(BasePermission):
    """Admins and teachers can access."""
    def has_permission(self, request, view):
        return bool(
            request.user and
            school_access_allowed(request.user) and
            request.user.role in ("admin", "teacher")
        )

class IsAdminOrTeacherReadOnly(BasePermission):
    """Admins and teachers can access, but teachers have read-only access."""
    def has_permission(self, request, view):
        if school_access_allowed(request.user):
            if request.user.role == "admin":
                return True
            elif request.user.role == "teacher":
                return request.method in ("GET", "HEAD", "OPTIONS")
        return False

def is_platform_superadmin(user):
    """A platform actor: root superuser or a school-less superadmin-role user."""
    return bool(
        user and
        getattr(user, "is_authenticated", False) and
        user.is_active and
        (user.is_superuser or (user.role == "superadmin" and user.school_id is None))
    )


class IsSuperAdmin(BasePermission):
    """Only super admins can access."""
    def has_permission(self, request, view):
        return is_platform_superadmin(request.user)

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
            if perm().has_permission(request, view)
        )


class CanAccessAuditLogs(OrPermission):

    permissions = [
        IsAdmin,
        IsSuperAdmin,
    ]


class IsAdminOrSuperAdmin(OrPermission):
    """School admins and super admins can access.

    Row scoping is left to the view queryset: school admins are limited to
    their own school, super admins see every user.
    """

    permissions = [
        IsAdmin,
        IsSuperAdmin,
    ]


class IsSuperAdminOrReadOnly(BasePermission):
    """Super admins can access, others can only read."""
    def has_permission(self, request, view):
        if is_platform_superadmin(request.user):
            return True
        return request.method in ("GET", "HEAD", "OPTIONS")


class IsGuardian(BasePermission):
    """Guardians can access."""
    def has_permission(self, request, view):
        return request.user.role == User.Role.GUARDIAN
