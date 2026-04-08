from rest_framework.permissions import BasePermission


class IsAdmin(BasePermission):
    """Only school admins can access."""
    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.role == "admin" and 
            request.user.school is not None
        )


class IsTeacher(BasePermission):
    """Only teachers can access."""
    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.role == "teacher"
        )


class IsAdminOrTeacher(BasePermission):
    """Admins and teachers can access."""
    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.role in ("admin", "teacher")
        )
    
class IsSuperAdmin(BasePermission):
    """Only super admins can access."""
    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.role == "superadmin"
        )