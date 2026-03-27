from rest_framework import serializers
from .models import School


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
        return obj.students.filter(status="active").count()

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

        return school
