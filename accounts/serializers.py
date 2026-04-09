from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from .models import User


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        email = attrs.get("email")
        password = attrs.get("password")

        user = authenticate(
            request=self.context.get("request"),
            username=email,
            password=password,
        )

        if not user:
            raise serializers.ValidationError("Invalid email or password.")

        if not user.is_active:
            raise serializers.ValidationError("This account has been deactivated.")

        attrs["user"] = user
        return attrs


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    school_name = serializers.CharField(source="school.name", read_only=True, allow_null = True)
    onboarding_completed = serializers.BooleanField(source="school.onboarding_completed", read_only=True, allow_null = True)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "role",
            "school",
            "school_name",
            "onboarding_completed", 
            "is_active",
            "created_at",
        ]
        read_only_fields = ["id", "created_at", "school"]


class CreateUserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = [
            "email",
            "first_name",
            "last_name",
            "role",
            "password",
        ]

    def validate_role(self, value):
        # Admins can only be created by superusers — enforce at view level
        return value

    def create(self, validated_data):
        # school is injected by the view from request.user.school
        school = self.context.get("school")
        user = User.objects.create_user(**validated_data, school=school)
        return user