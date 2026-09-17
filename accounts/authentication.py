from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication

from core.access import school_access_allowed


def validate_account_access(user):
    if not user.is_active:
        raise AuthenticationFailed("This account is inactive.")
    if user.is_superuser or (user.role == "superadmin" and not user.school_id):
        return
    if not school_access_allowed(user):
        raise AuthenticationFailed("School access is unavailable for this account.")


class SchoolJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        validate_account_access(user)
        return user
