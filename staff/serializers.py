import secrets
from django.db import transaction
from accounts.models import User
from core.email import send_staff_welcome_mail
from rest_framework import serializers
from core.validations import validate_date, validate_name, validate_phone_number
from staff.enums.employment_type import EmploymentType
from staff.enums.staff_status import StaffStatus
from students.utils import generate_user_email
from .models import (
    StaffPosition,
    StaffProfile,
    PERMISSION_CHOICES,
    PERMISSION_KEYS
)
from django.core import exceptions
from django.contrib.auth.password_validation import validate_password

class PermissionChoiceSerializer(serializers.Serializer):
    """Returns all available permission keys grouped by module."""

    def to_representation(self, instance):
        grouped = {}
        for key, label in PERMISSION_CHOICES:
            module = key.split(".")[0]
            if module not in grouped:
                grouped[module] = []
            grouped[module].append({"key": key, "label": label})
        return grouped


class StaffPositionSerializer(serializers.ModelSerializer):
    staff_count = serializers.SerializerMethodField()
    permission_labels = serializers.SerializerMethodField()

    class Meta:
        model = StaffPosition
        fields = [
            "id",
            "name",
            "description",
            "permissions",
            "permission_labels",
            "is_system",
            "staff_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id", "is_system", "created_at", "updated_at"
        ]

    def get_staff_count(self, obj):
        return obj.staff_members.filter(
            status=StaffStatus.ACTIVE
        ).count()

    def get_permission_labels(self, obj):
        label_map = dict(PERMISSION_CHOICES)
        return [
            {"key": p, "label": label_map.get(p, p)}
            for p in (obj.permissions or [])
        ]

    def validate_permissions(self, value):
        invalid = [p for p in value if p not in PERMISSION_KEYS]
        if invalid:
            raise serializers.ValidationError(
                f"Invalid permission key(s): {', '.join(invalid)}. "
                f"Use GET /api/v1/staff/permissions/ to see valid keys."
            )
        return list(set(value))  # deduplicate


class StaffPositionWriteSerializer(StaffPositionSerializer):
    """Used for create/update — validates name uniqueness per school."""

    def validate_name(self, value):
        school = self.context["school"]
        qs = StaffPosition.objects.filter(
            school=school,
            name__iexact=value,
        )
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                f"A position named '{value}' already exists."
            )
        return value

class StaffListSerializer(serializers.ModelSerializer):
    user_id = serializers.UUIDField(source="user.id", allow_null=True, required=False)
    class Meta:
        model = StaffProfile
        fields = [
            "id",
            "user_id",
            "employee_id",
            "full_name",
            "email",
            "phone",
            "role",
            "profile_photo",
            "status",
            "employment_type"
        ]

        read_only_fields = ["id", "user_id"]

class StaffProfileSerializer(serializers.ModelSerializer):
    profile_photo_url = serializers.SerializerMethodField()

    class Meta:
        model = StaffProfile
        fields = [
            "id",
            "employee_id",
            "first_name",
            "last_name",
            "full_name",
            "email",
            "phone",
            "employment_type",
            "status",
            "date_joined",
            "phone",
            "address",
            "profile_photo_url",
            "role",
            "user"
        ]
        read_only_fields = [
            "id", "employee_id", "created_at", "updated_at"
        ]

    def get_profile_photo_url(self, obj):
        request = self.context.get("request")
        if obj.profile_photo and request:
            return request.build_absolute_uri(obj.profile_photo.url)
        return None


class StaffCreationSerializer(serializers.ModelSerializer):
    class Meta:
        model = StaffProfile
        fields = [
            "first_name",
            "last_name",
            "employee_id",
            "date_joined",
            "employment_type",
            "email",
            "phone",
            "address",
            "profile_photo",
            "role"
        ]

    def validate(self, attrs):
        if not attrs.get("email"):
            attrs["email"] = generate_user_email(
                attrs.get("first_name", ""),
                attrs.get("last_name", ""),
                domain=self.context["school"].school_email_domain or "school.com"
            )
        return attrs
    
    def validate_first_name(self, value):
        return validate_name(value, "First name")
    
    def validate_last_name(self, value):
        return validate_name(value, "Last name")
    
    def validate_phone(self, value):
        return validate_phone_number(value, "Phone number")
    
    def validate_date_joined(self, value):
        return validate_date(value, "Date joined")
    

class UpdateStaffSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = StaffProfile
        fields = [
            "first_name",
            "last_name",
            "employee_id",
            "date_joined",
            "employment_type",
            "status",
            "email",
            "phone",
            "address",
            "profile_photo",
        ]


class ResetPasswordSerializer(serializers.Serializer):
    password = serializers.CharField(write_only = True, required = True)
    confirm_password = serializers.CharField(write_only = True, required = True)

    def validate_password(self, value):
        try:
            validate_password(value)
        except exceptions.ValidationError as e:
            raise serializers.ValidationError(list(e.messages()))
        return value

    def validate(self, data):
        if data.get('password') != data.get('confirm_password'):
            raise serializers.ValidationError({
                "password":"New password and confirm password do not match"
            })
        return data