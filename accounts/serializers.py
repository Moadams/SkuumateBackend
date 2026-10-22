from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from .models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        email = attrs.get("email")
        password = attrs.get("password")

        try:
            user = User.objects.select_related("staff_profile").get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError("Invalid email or password.")

        if not user.is_active:
            raise serializers.ValidationError("This account has been deactivated.")
        
        if not user.check_password(password):
            raise serializers.ValidationError("Invalid email or password.")

        from .authentication import validate_account_access
        validate_account_access(user)
        attrs["user"] = user
        return attrs

class SchoolAccessSerializerMixin:
    def get_effective_permissions(self, obj):
        from core.permissions import effective_keys
        from staff.permission_registry import PERMISSION_KEYS
        return sorted(PERMISSION_KEYS if obj.role == "admin" else effective_keys(obj))


class UserLoginSerializer(SchoolAccessSerializerMixin, serializers.ModelSerializer):
    effective_permissions = serializers.SerializerMethodField()
    full_name = serializers.CharField(read_only=True)
    school_name = serializers.CharField(source="school.name", read_only=True, allow_null = True)
    onboarding_completed = serializers.BooleanField(source="school.onboarding_completed", read_only=True, allow_null = True)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "full_name",
            "role",
            "school",
            "school_name",
            "is_superuser",
            "onboarding_completed", 
            "must_change_password", "effective_permissions"
        ]
        read_only_fields = ["id", "created_at", "school"]

class UserSerializer(SchoolAccessSerializerMixin, serializers.ModelSerializer):
    effective_permissions = serializers.SerializerMethodField()
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
            "phone",
            "role",
            "school",
            "school_name",
            "onboarding_completed", 
            "is_active",
            "is_superuser",
            "effective_permissions",
            "created_at",
        ]
        read_only_fields = ["id", "created_at", "school"]

class UserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "first_name",
            "last_name",
            "phone",
            "email"
        ]


class SchoolUserUpdateSerializer(UserSerializer):
    def validate_role(self, value):
        if value == User.Role.SUPERADMIN:
            raise serializers.ValidationError("Platform roles cannot be assigned by a school.")
        return value

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
    

class ResetPasswordConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        uid = attrs.get("uid")
        token = attrs.get("token")
        password = attrs.get("password")
        confirm_password = attrs.get("confirm_password")

        if password != confirm_password:
            raise serializers.ValidationError(
                {"confirm_password": "Passwords do not match."}
            )

        try:
            user_id = force_str(urlsafe_base64_decode(uid))
            user = User.objects.get(pk=user_id)

        except (User.DoesNotExist, ValueError, TypeError, UnicodeDecodeError, DjangoValidationError):
            raise serializers.ValidationError(
                {"uid": "Invalid reset link."}
            )

        if not default_token_generator.check_token(user, token):
            raise serializers.ValidationError(
                {"token": "Invalid or expired token."}
            )

        validate_password(password, user)

        attrs["user"] = user

        return attrs

    def save(self):
        user = self.validated_data["user"]
        password = self.validated_data["password"]

        user.set_password(password)

        # Optional: mark first login complete
        if hasattr(user, "must_change_password"):
            user.must_change_password = False

        user.save()

        return user
    
class ResetUserPasswordSerializer(serializers.Serializer):
    user_id = serializers.UUIDField(write_only = True)
    password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        user_id = attrs.get("user_id")
        password = attrs.get("password")
        confirm_password = attrs.get("confirm_password")

        if password != confirm_password:
            raise serializers.ValidationError(
                {"confirm_password": "Passwords do not match."}
            )

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            raise serializers.ValidationError(
                {"user_id": "User not found."}
            )

        validate_password(password, user)

        attrs["user"] = user

        return attrs

    def save(self):
        user = self.validated_data["user"]
        password = self.validated_data["password"]

        user.set_password(password)

        # Optional: mark first login complete
        if hasattr(user, "must_change_password"):
            user.must_change_password = False

        user.save()

        return user


class SchoolTokenRefreshSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        from .authentication import SchoolJWTAuthentication
        token = self.token_class(attrs["refresh"])
        SchoolJWTAuthentication().get_user(token)
        return super().validate(attrs)
