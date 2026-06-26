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
            "profile_photo",
            "status",
            "employment_type"
        ]

        read_only_fields = ["id", "user_id"]

class StaffProfileSerializer(serializers.ModelSerializer):
    role = serializers.CharField(source="user.role", read_only=True)
    profile_photo_url = serializers.SerializerMethodField()

    class Meta:
        model = StaffProfile
        fields = [
            "id",
            "employee_id",
            "first_name",
            "last_name",
            "email",
            "phone",
            "employment_type",
            "status",
            "date_joined",
            "phone",
            "address",
            "profile_photo_url",
            "role"
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
    role = serializers.CharField()
    class Meta:
        model = StaffProfile
        fields = [
            "first_name",
            "last_name",
            "positions",
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

    def validate_role(self, value):
        if value not in User.Role.values:
            raise serializers.ValidationError(
                f"Invalid role '{value}'. Must be one of: "
                f"{', '.join(User.Role.values)}."
            )
        return value

    def validate_employment_type(self, value):
        if value not in EmploymentType.values:
            raise serializers.ValidationError(
                f"Invalid employment type '{value}'. Must be one of: "
                f"{', '.join(EmploymentType.values)}."
            )
        return value
    
    def validate_first_name(self, value):
        return validate_name(value, "First name")
    
    def validate_last_name(self, value):
        return validate_name(value, "Last name")
    
    def validate_phone(self, value):
        return validate_phone_number(value, "Phone number")
    
    def validate_date_joined(self, value):
        return validate_date(value, "Date joined")
    
    
    @transaction.atomic
    def create(self, validated_data):
        positions = validated_data.pop("positions", [])
        temporary_password = secrets.token_urlsafe(16)
        user = User.objects.create_user(
            email=validated_data.get("email"),
            password=temporary_password,
            first_name=validated_data.get("first_name"),
            last_name=validated_data.get("last_name"),
            role = validated_data.get("role"),
            must_change_password = True,
            school = self.context["school"]
        )
        validated_data.pop("role", None)  # remove role as it's not a StaffProfile field
        staff = StaffProfile.objects.create(user = user, **validated_data)
        staff.positions.set(positions)
        return staff

class CreateStaffSerializer(serializers.Serializer):
    """Creates a User + StaffProfile + assigns positions in one call."""
    # User fields
    first_name = serializers.CharField(max_length=100)
    last_name = serializers.CharField(max_length=100)
    email = serializers.EmailField() 
    password = serializers.CharField(write_only=True, min_length=8)

    # Profile fields
    position_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=False,
        help_text="List of StaffPosition UUIDs to assign.",
    )
    date_joined = serializers.DateField()
    employment_type = serializers.ChoiceField(
        choices=EmploymentType.choices,
        default=EmploymentType.FULL_TIME,
    )
    phone = serializers.CharField(
        max_length=20, required=False, allow_blank=True
    )
    address = serializers.CharField(
        required=False, allow_blank=True
    )
    
    
    employee_id = serializers.CharField(required=False, allow_blank=True)

    profile_photo = serializers.FileField(required=False)

    def validate_employee_id(self, value):
        if not value:
            return value
        school = self.context['school']
        if StaffProfile.objects.filter(school =school, employee_id = value).exists():
            raise serializers.ValidationError(
                "A staff with this employee id already exists"
            )
        return value
    
    def validate_email(self, value):
        from accounts.models import User
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError(
                "A user with this email already exists."
            )
        return value

    def validate_position_ids(self, value):
        school = self.context["school"]
        positions = StaffPosition.objects.filter(
            id__in=value, school=school
        )
        if positions.count() != len(value):
            raise serializers.ValidationError(
                "One or more positions are invalid or do not "
                "belong to this school."
            )
        return list(positions)

    def create(self, validated_data):
        from accounts.models import User
        from django.db import transaction

        positions = validated_data.pop("position_ids")
        school = self.context["school"]
        password = validated_data.pop("password")

        
        position_names = [p.name.lower() for p in positions]
        role = (
            "admin"
            if "administrator" in position_names
            else "teacher"
        )
        profile_photo = validated_data.pop("profile_photo", None)

        with transaction.atomic():
            user = User.objects.create_user(
                email=validated_data.pop("email"),
                password=password,
                first_name=validated_data.pop("first_name"),
                last_name=validated_data.pop("last_name"),
                role=role,
                school=school,
            )

            profile = StaffProfile.objects.create(
                school=school,
                user=user,
                profile_photo = profile_photo,
                **validated_data,
            )
            
            profile.positions.set(positions)

        send_staff_welcome_mail(f'{user.first_name} {user.last_name}', user.email, password, school.name)

        return profile


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