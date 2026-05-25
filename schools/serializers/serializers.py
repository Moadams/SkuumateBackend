from rest_framework import serializers

from core.email import send_welcome_school_email
from ..models import School


class SchoolListSerializer(serializers.ModelSerializer):
    """
    Optimized serializer for the schools list page.
    Flat structure matching exactly what the frontend expects.
    """
    school_id = serializers.UUIDField(source="id", read_only=True)
    school_name = serializers.CharField(source="name", read_only=True)
    school_email = serializers.CharField(source="email", read_only=True)
    school_logo = serializers.SerializerMethodField()
    location = serializers.SerializerMethodField()
    joined = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    package_name = serializers.SerializerMethodField()
    subscription_status = serializers.SerializerMethodField()

    class Meta:
        model = School
        fields = [
            "school_id",
            "school_name",
            "school_email",
            "school_logo",
            "location",
            "joined",
            "status",
            "package_name",
            "subscription_status",
        ]

    def get_school_logo(self, obj):
        request = self.context.get("request")
        if obj.logo and request:
            return request.build_absolute_uri(obj.logo.url)
        return None

    def get_location(self, obj):
        parts = [p for p in [obj.city, obj.country] if p]
        return ", ".join(parts) if parts else "N/A"

    def get_joined(self, obj):
        return obj.created_at.strftime("%b %d, %Y")

    def get_status(self, obj):
        # School is active if it has an accessible subscription
        sub = self.context.get("subscriptions", {}).get(str(obj.id))
        if not sub:
            return "Pending"
        if sub.is_locked:
            return "Inactive"
        if sub.is_accessible:
            return "Active"
        return "Inactive"

    def get_package_name(self, obj):
        sub = self.context.get("subscriptions", {}).get(str(obj.id))
        if sub:
            return sub.plan.name
        return "No Plan"

    def get_subscription_status(self, obj):
        sub = self.context.get("subscriptions", {}).get(str(obj.id))
        if sub:
            return sub.status
        return None


class SchoolSerializer(serializers.ModelSerializer):
    total_students = serializers.SerializerMethodField()
    total_users = serializers.SerializerMethodField()

    class Meta:
        model = School
        fields = [
            "id",
            "name",
            "logo",
            "email",
            "phone",
            "address",
            "city",
            "country",
            "is_active",
            "total_students",
            "total_users",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_total_students(self, obj):
        # return obj.students.filter(status="active").count()
        return 0

    def get_total_users(self, obj):
        return obj.users.filter(is_active=True).count()


class SchoolCreateSerializer(serializers.ModelSerializer):
    # Admin user fields only
    admin_first_name = serializers.CharField(write_only=True)
    admin_last_name = serializers.CharField(write_only=True)
    admin_email = serializers.EmailField(write_only=True)
    admin_password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = School
        fields = [
            "name",
            "email",
            "phone",
            "address",
            "city",
            "country",
            "admin_first_name",
            "admin_last_name",
            "admin_email",
            "admin_password",
        ]

    def validate_admin_email(self, value):
        from accounts.models import User
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate_email(self, value):
        if School.objects.filter(email=value).exists():
            raise serializers.ValidationError("A school with this email already exists.")
        return value

    def create(self, validated_data):
        from accounts.models import User

        # Pop admin fields
        admin_first_name = validated_data.pop("admin_first_name")
        admin_last_name = validated_data.pop("admin_last_name")
        admin_email = validated_data.pop("admin_email")
        admin_password = validated_data.pop("admin_password")

        # 1. Create the school
        school = School.objects.create(**validated_data)

        # 2. Create the first admin user
        User.objects.create_user(
            email=admin_email,
            password=admin_password,
            first_name=admin_first_name,
            last_name=admin_last_name,
            role="admin",
            school=school,
        )

        # Seed system positions for this new school
        self._seed_system_positions(school)

        send_welcome_school_email(
            admin_name=f"{admin_first_name} {admin_last_name}",
            admin_email=admin_email,
            admin_password=admin_password,
            school_name=school.name
        )

        return school

    @staticmethod
    def _seed_system_positions(school):
        from staff.models import StaffPosition
        from staff.management.commands.seed_staff_positions import (
            SYSTEM_POSITIONS,
        )
        for pos_data in SYSTEM_POSITIONS:
            StaffPosition.objects.get_or_create(
                school=school,
                name=pos_data["name"],
                defaults={
                    "description": pos_data["description"],
                    "permissions": pos_data["permissions"],
                    "is_system": True,
                },
            )