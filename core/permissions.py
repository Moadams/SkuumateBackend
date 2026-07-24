from rest_framework.permissions import BasePermission

from subscriptions.permissions import HasAuditLogAccess


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
