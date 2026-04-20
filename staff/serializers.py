from core.email import send_staff_welcome_mail
from rest_framework import serializers
from staff.enums.employment_type import EmploymentType
from staff.enums.staff_status import StaffStatus
from .models import (
    StaffPosition,
    StaffProfile,
    PERMISSION_CHOICES,
    PERMISSION_KEYS,
    SYSTEM_POSITIONS,
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


class StaffProfileSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(
        source="user.full_name", read_only=True
    )
    email = serializers.CharField(
        source="user.email", read_only=True
    )
    positions_detail = StaffPositionSerializer(
        source="positions", many=True, read_only=True
    )
    all_permissions = serializers.ListField(read_only=True)
    profile_photo_url = serializers.SerializerMethodField()

    class Meta:
        model = StaffProfile
        fields = [
            "id",
            "employee_id",
            "full_name",
            "email",
            "positions_detail",
            "all_permissions",
            "employment_type",
            "status",
            "date_joined",
            "phone",
            "address",
            "emergency_contact_name",
            "emergency_contact_phone",
            "profile_photo_url",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id", "employee_id", "created_at", "updated_at"
        ]

    def get_profile_photo_url(self, obj):
        request = self.context.get("request")
        if obj.profile_photo and request:
            return request.build_absolute_uri(obj.profile_photo.url)
        return None


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
    emergency_contact_name = serializers.CharField(
        max_length=100, required=False, allow_blank=True
    )
    emergency_contact_phone = serializers.CharField(
        max_length=20, required=False, allow_blank=True
    )
    notes = serializers.CharField(
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
    position_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
    )

    class Meta:
        model = StaffProfile
        fields = [
            "employment_type",
            "status",
            "date_joined",
            "phone",
            "address",
            "emergency_contact_name",
            "emergency_contact_phone",
            "notes",
            "position_ids",
        ]

    def validate_position_ids(self, value):
        school = self.context["school"]
        positions = StaffPosition.objects.filter(
            id__in=value, school=school
        )
        if positions.count() != len(value):
            raise serializers.ValidationError(
                "One or more positions are invalid."
            )
        return list(positions)

    def update(self, instance, validated_data):
        positions = validated_data.pop("position_ids", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if positions is not None:
            instance.positions.set(positions)

        return instance
    

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