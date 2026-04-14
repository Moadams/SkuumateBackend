from rest_framework.permissions import BasePermission
from rest_framework.exceptions import PermissionDenied


class HasStaffPermission(BasePermission):
    """
    Factory-style permission class.

    Usage on a view:
        permission_classes = [HasStaffPermission("students.create")]

    Usage for multiple permissions (ANY):
        permission_classes = [HasStaffPermission("finance.view", "finance.manage_fees")]
    """
    def __init__(self, *required_permissions):
        self.required_permissions = required_permissions
        super().__init__()

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        # Superusers bypass all staff permission checks
        if request.user.is_superuser:
            return True

        # School owner/admin role bypasses staff permission checks
        if request.user.role == "admin":
            return True

        # Staff must have a profile
        if not hasattr(request.user, "staff_profile"):
            raise PermissionDenied(
                "No staff profile found for this account."
            )

        profile = request.user.staff_profile

        # Suspended/terminated staff get no access
        if profile.status in ("suspended", "terminated"):
            raise PermissionDenied(
                "Your account has been suspended or terminated. "
                "Please contact your administrator."
            )

        # Check if user has ANY of the required permissions
        for perm in self.required_permissions:
            if profile.has_permission(perm):
                return True

        raise PermissionDenied(
            f"You do not have permission to perform this action."
        )


def make_permission(*keys):
    """
    Shorthand to create a HasStaffPermission instance.

    Usage:
        permission_classes = [make_permission("students.view")]
    """
    return HasStaffPermission(*keys)