import re

from rest_framework import serializers

from accounts.models import User

from .models import PlatformPermission, PlatformRole
from .services import (
    PLATFORM_STAFF_ROLE,
    get_user_platform_permissions,
    get_user_platform_roles,
)

_ROLE_CODE_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class PlatformRoleRefSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    code = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)
    is_active = serializers.BooleanField(read_only=True)


class PlatformUserSerializer(serializers.ModelSerializer):
    """Read representation of a platform user (never exposes credentials)."""

    id = serializers.UUIDField(read_only=True)
    full_name = serializers.CharField(read_only=True)
    role = serializers.CharField(read_only=True)
    is_staff = serializers.BooleanField(read_only=True)
    is_superuser = serializers.BooleanField(read_only=True)
    is_platform_user = serializers.SerializerMethodField()
    roles = serializers.SerializerMethodField()
    effective_permissions = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "phone",
            "role",
            "is_active",
            "is_staff",
            "is_superuser",
            "must_change_password",
            "school",
            "is_platform_user",
            "roles",
            "effective_permissions",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_is_platform_user(self, obj):
        return obj.role == PLATFORM_STAFF_ROLE or obj.is_superuser

    def get_roles(self, obj):
        return get_user_platform_roles(obj)

    def get_effective_permissions(self, obj):
        if obj.is_superuser:
            return ["*"]
        return sorted(get_user_platform_permissions(obj))


class PlatformUserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8, trim_whitespace=False)

    class Meta:
        model = User
        fields = ["email", "first_name", "last_name", "phone", "password"]

    def validate_email(self, value):
        return User.objects.normalize_email(value)

    def create(self, validated_data):
        user = User.objects.create_user(
            role=User.Role.SUPERADMIN,
            school=None,
            is_staff=False,
            is_superuser=False,
            **validated_data,
        )
        return user


class PlatformUserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["email", "first_name", "last_name", "phone"]

    def validate_email(self, value):
        return User.objects.normalize_email(value)


class PlatformPermissionSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)

    class Meta:
        model = PlatformPermission
        fields = [
            "id",
            "code",
            "name",
            "description",
            "module",
            "is_active",
            "is_system",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class PlatformRoleSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    is_system_role = serializers.BooleanField(read_only=True)
    permissions = serializers.SerializerMethodField()
    permission_count = serializers.SerializerMethodField()

    class Meta:
        model = PlatformRole
        fields = [
            "id",
            "name",
            "code",
            "description",
            "is_active",
            "is_system_role",
            "permissions",
            "permission_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "is_system_role", "is_active", "permissions", "permission_count", "created_at", "updated_at"]

    def validate_code(self, value):
        if not _ROLE_CODE_RE.match(value):
            raise serializers.ValidationError(
                "Role code must start with a lowercase letter and contain only lowercase letters, digits or underscores."
            )
        return value

    def get_permissions(self, obj):
        return sorted(obj.role_permissions.values_list("permission__code", flat=True))

    def get_permission_count(self, obj):
        return obj.role_permissions.count()


class PlatformRoleCreateUpdateSerializer(serializers.ModelSerializer):
    """Write shape for roles: metadata only — permissions are managed through
    the dedicated assignment endpoints so escalation checks stay centralized."""

    class Meta:
        model = PlatformRole
        fields = ["name", "code", "description"]
        extra_kwargs = {"description": {"required": False, "allow_blank": True}}

    def validate_code(self, value):
        if not _ROLE_CODE_RE.match(value):
            raise serializers.ValidationError(
                "Role code must start with a lowercase letter and contain only lowercase letters, digits or underscores."
            )
        return value


class CodesPayloadSerializer(serializers.Serializer):
    codes = serializers.ListField(
        child=serializers.CharField(max_length=100),
        allow_empty=True,
    )