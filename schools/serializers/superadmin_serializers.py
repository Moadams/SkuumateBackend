import re
import secrets
from django.db import transaction
from rest_framework import serializers

from accounts.utils.password_reset import generate_password_setup_link
from core.email import send_welcome_school_email
from schools.models import School

class SchoolUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = School
        fields = [
            "name",
            "school_code",
            "logo",
            "email",
            "phone",
            "address",
            "country",
            "status",
        ]

    def validate_name(self, value):
        school_name = value.lower()
        if School.objects.filter(name__iexact=school_name).exclude(id=self.instance.id).exists():
            raise serializers.ValidationError("A school with this name already exists.")
        return value

    def validate_phone(self, value):
        if not re.fullmatch(r"\+233\d{9}", value):
            raise serializers.ValidationError("Phone number must be in the format '+233XXXXXXXXX'")
        return value

    def validate_email(self, value):
        school_id = self.instance.id if self.instance else None
        if School.objects.filter(email=value).exclude(id=school_id).exists():
            raise serializers.ValidationError("A school with this email already exists.")
        return value
    
    def validate_address(self, value):
        if value and len(value) > 255:
            raise serializers.ValidationError("Address cannot exceed 255 characters.")
        return value

class SchoolStatsSerializer(serializers.ModelSerializer):
    total_users = serializers.IntegerField()
    total_active_users = serializers.IntegerField()
    total_students = serializers.IntegerField()
    total_staff = serializers.IntegerField()
    

    class Meta:
        model = School
        fields = ['total_users', 'total_active_users', 'total_students', 'total_staff']

class SchoolDetailSerializer(serializers.ModelSerializer):
    stats = serializers.SerializerMethodField()
    admin = serializers.SerializerMethodField()
    plan = serializers.SerializerMethodField()

    class Meta:
        model = School
        fields = [
            "id",
            "name",
            "email",
            "phone",
            "address",
            "status",
            "joined",
            "plan",
            "admin",
            "stats",
        ]

    def get_stats(self, obj):
        return {
            "total_users": obj.total_users,
            "total_active_users": obj.total_active_users,
            "total_students": obj.total_students,
            "total_staff": obj.total_staff,
        }
    
    def get_admin(self, obj):
        from accounts.models import User
        admin_user = User.objects.filter(school=obj, role = User.Role.ADMIN).first()
        if admin_user:
            return {
                "name": admin_user.full_name,
                "email": admin_user.email,
            }
        return None

    def get_plan(self, obj):
        current_sub = obj.subscriptions.filter(is_current=True).first()
        return current_sub.plan.name if current_sub else None
    

class SchoolCreateSerializer(serializers.ModelSerializer):
    # Admin user fields only
    admin_first_name = serializers.CharField(write_only=True)
    admin_last_name = serializers.CharField(write_only=True)
    admin_email = serializers.EmailField(write_only=True)

    class Meta:
        model = School
        fields = [
            "name",
            "email",
            "phone",
            "school_code",
            "admin_first_name",
            "admin_last_name",
            "admin_email"
        ]

    def validate_name(self, value):
        school_name = value.lower()
        if School.objects.filter(name__iexact=school_name).exists():
            raise serializers.ValidationError("A school with this name already exists.")
        return value

    def validate_phone(self, value):
        if not re.fullmatch(r"\+233\d{9}", value):
            raise serializers.ValidationError("Phone number must be in the format '+233XXXXXXXXX'")
        return value

    def validate_school_code(self, value):
        if value and School.objects.filter(school_code=value).exists():
            raise serializers.ValidationError("A school with this school code already exists.")
        return value
    
    def validate_admin_first_name(self, value):
        if not re.match(r"^[A-Za-zÀ-ÿ\s'-]+$", value):
            raise serializers.ValidationError("First name must contain only letters.")
        return value

    def validate_admin_last_name(self, value):
        if not re.match(r"^[A-Za-zÀ-ÿ\s'-]+$", value):
            raise serializers.ValidationError("Last name must contain only letters.")
        return value

    def validate_admin_email(self, value):
        from accounts.models import User
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate_email(self, value):
        if School.objects.filter(email=value).exists():
            raise serializers.ValidationError("A school with this email already exists.")
        return value
    
    @transaction.atomic
    def create(self, validated_data):
        from accounts.models import User

        # Pop admin fields
        admin_first_name = validated_data.pop("admin_first_name")
        admin_last_name = validated_data.pop("admin_last_name")
        admin_email = validated_data.pop("admin_email")

        # 1. Create the school
        school = School.objects.create(**validated_data)
        
        temporary_password = secrets.token_urlsafe(16)

        # 2. Create the first admin user
        user = User.objects.create_user(
            email=admin_email,
            password=temporary_password,
            first_name=admin_first_name,
            last_name=admin_last_name,
            role=User.Role.ADMIN,
            school=school,
        )

        # Seed system positions for this new school
        self._seed_system_positions(school)

        reset_link = generate_password_setup_link(user)

        send_welcome_school_email(
            admin_name=f"{admin_first_name} {admin_last_name}",
            admin_email=admin_email,
            reset_link=reset_link,
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