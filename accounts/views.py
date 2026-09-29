import logging

from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.utils.password_reset import generate_password_setup_link
from core.email import send_forgot_password_mail
from core.mixins import ExportMixin
from core.models import AuditLog
from core.permissions import (
    IsAdmin,
    IsAdminOrSuperAdmin,
    IsSuperAdmin,
    is_platform_superadmin,
)
from core.responses import ApiResponse
from core.utils import log_action

from .models import User
from .serializers import (
    CreateUserSerializer,
    LoginSerializer,
    ResetPasswordConfirmSerializer,
    ResetUserPasswordSerializer,
    SchoolUserUpdateSerializer,
    UserLoginSerializer,
    UserSerializer,
    UserUpdateSerializer,
)

logger = logging.getLogger(__name__)

class LoginView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})

        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data["user"]
        refresh = RefreshToken.for_user(user)


        return ApiResponse.success(
            data={
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": UserLoginSerializer(user).data,
            },
            message="Login successful",
        )


class LogoutView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return ApiResponse.error(message="Refresh token is required.")
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except TokenError:
            # Already expired or invalid — still return success
            pass

        log_action(
            action=AuditLog.Action.LOGOUT,
            resource="User",
            resource_id=str(request.user.id),
            description=f"{request.user.full_name} logged out",
            request=request,
        )

        return ApiResponse.success(message="Logged out successfully.")


class MeView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        serializer = UserSerializer(request.user)
        return ApiResponse.success(data=serializer.data)

    def patch(self, request):
        serializer = UserUpdateSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return ApiResponse.success(
            data=serializer.data,
            message="User profile updated successfully.",
        )

class UserExportView(ExportMixin, generics.ListAPIView):
    permission_classes = (IsAdminOrSuperAdmin,)
    serializer_class = UserSerializer
    filter_backends = (DjangoFilterBackend, SearchFilter, OrderingFilter,)
    filterset_fields = ("role", "is_active",)
    search_fields = ("email", "first_name", "last_name",)
    ordering_fields = ("created_at", "first_name", "last_name", "email",)
    ordering = ("-created_at",)

    def get_queryset(self):
        return User.objects.filter(school=self.request.user.school)

    def get(self, request, *args, **kwargs):
        return self.export(request, *args, **kwargs)

class UserListView(generics.ListAPIView):
    """Admin only — list all users in their school / create a new user."""
    permission_classes = (IsAdminOrSuperAdmin,)
    serializer_class = UserSerializer
    filter_backends = (DjangoFilterBackend, SearchFilter, OrderingFilter,)
    filterset_fields = ("role", "is_active", "school",)
    search_fields = ("email", "first_name", "last_name")
    ordering_fields = ("created_at", "email", "first_name", "last_name")
    ordering = ("-created_at")

    def get_queryset(self):
        if is_platform_superadmin(self.request.user):
            return User.objects.all().exclude(deleted_at__isnull=False)
        return User.objects.filter(school=self.request.user.school).exclude(deleted_at__isnull=False)


class UserDetailView(generics.RetrieveUpdateDestroyAPIView):
    """School admins and super admins — retrieve, update or deactivate a user.

    School admins only reach users registered to their own school; super
    admins reach every user.
    """
    permission_classes = (IsAdminOrSuperAdmin,)
    serializer_class = UserSerializer

    def get_queryset(self):
        if is_platform_superadmin(self.request.user):
            return User.objects.all().exclude(deleted_at__isnull=False)
        return User.objects.filter(
            school=self.request.user.school,
            is_superuser=False,
        ).exclude(role=User.Role.SUPERADMIN).exclude(deleted_at__isnull=False)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        return ApiResponse.success(data=UserSerializer(instance).data)

    def update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        instance = self.get_object()
        serializer = SchoolUserUpdateSerializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return ApiResponse.success(
            data=serializer.data,
            message="User updated successfully.",
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.is_active = False
        instance.deleted_at = timezone.now()
        instance.deleted_by = request.user
        instance.save()
        return ApiResponse.success(message="User deleted successfully.")

class ForgotPasswordView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        email = request.data.get("email")
        if not email:
            return ApiResponse.error(message="Email is required.")

        try:
            user = User.objects.get(email=email, deleted_at__isnull=True)

            reset_link = generate_password_setup_link(user)
            send_forgot_password_mail(
                name=user.full_name,
                email=email,
                reset_link=reset_link
            )

        except User.DoesNotExist as e:
            logger.error(f"Forgot password request for {email}: {e}")

        return ApiResponse.success(message="If an account with that email exists, a password reset link has been sent.")

class ResetPasswordConfirmView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ResetPasswordConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return ApiResponse.success(message="Password reset successful.")


class ResetUserPassword(APIView):
    permission_classes = [IsAdminOrSuperAdmin]
    def put(self, request, user_id):
        school = request.user.school
        try:
            if is_platform_superadmin(request.user):
                user = User.objects.get(id=user_id, deleted_at__isnull=True)
            else:
                user = User.objects.filter(is_superuser=False).exclude(role="superadmin", deleted_at__isnull=True).get(school=school, id=user_id)
            data = request.data.copy()
            data['user_id'] = user.id
        except User.DoesNotExist:
            return ApiResponse.error(
                message="User not found", status_code=404
            )

        serializer = ResetUserPasswordSerializer(data=data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        log_action(
            action=AuditLog.Action.UPDATE,
            resource="User",
            resource_id=str(user.pk),
            description=f"User {user.full_name} password updated",
            request=self.request,
        )
        return ApiResponse.success(message="User's password reset successfully.")


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request):
        user = request.user
        data = request.data.copy()
        data['user_id'] = user.id
        serializer = ResetUserPasswordSerializer(data=data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        log_action(
            action=AuditLog.Action.UPDATE,
            resource="User",
            resource_id=str(user.pk),
            description=f"User {user.full_name} changed their password",
            request=self.request,
        )
        return ApiResponse.success(message="Password changed successfully.")


class ChangeUserPasswordView(APIView):
    permission_classes = [IsAdmin]

    def put(self, request):

        serializer = ResetUserPasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        log_action(
            action=AuditLog.Action.UPDATE,
            resource="User",
            resource_id=str(request.data['user_id']),
            description=f"User {request.user.full_name} changed the password of user {request.data['user_id']}",
            request=self.request,
        )
        return ApiResponse.success(message="Password changed successfully.")
