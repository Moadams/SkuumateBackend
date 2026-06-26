import logging
from rest_framework import generics
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from accounts.utils.password_reset import generate_password_setup_link
from core.email import send_forgot_password_mail
from core.mixins import ExportMixin
from core.models import AuditLog
from core.responses import ApiResponse
from core.permissions import IsAdmin, IsSuperAdmin
from core.utils import log_action

from .models import User
from .serializers import LoginSerializer, ResetPasswordConfirmSerializer, ResetUserPasswordSerializer, UserLoginSerializer, UserSerializer, CreateUserSerializer

logger = logging.getLogger(__name__)

class LoginView(APIView):
    permission_classes = [AllowAny]
    
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
    permission_classes = [IsAuthenticated]

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
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user)
        return ApiResponse.success(data=serializer.data)

class UserExportView(ExportMixin, generics.ListAPIView):
    permission_classes = [IsAdmin]
    serializer_class = UserSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["role", "is_active"]
    search_fields = ["email", "first_name", "last_name"]
    ordering_fields = ["created_at", "first_name", "last_name", "email"]
    ordering = ["-created_at"]

    def get_queryset(self):
        return User.objects.filter(school=self.request.user.school)

    def get(self, request, *args, **kwargs):
        return self.export(request, *args, **kwargs)

class UserListCreateView(generics.ListCreateAPIView):
    """Admin only — list all users in their school / create a new user."""
    permission_classes = [IsSuperAdmin]
    serializer_class = UserSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["role", "is_active"]
    search_fields = ["email", "first_name", "last_name"]
    ordering_fields = ["created_at", "email", "first_name", "last_name"]
    ordering = ["-created_at"]

    def get_queryset(self):
        return User.objects.all()

    def get_serializer_class(self):
        if self.request.method == "POST":
            return CreateUserSerializer
        return UserSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["school"] = self.request.user.school
        return ctx

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return ApiResponse.created(
            data=UserSerializer(user).data,
            message="User created successfully.",
        )

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = UserSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = UserSerializer(queryset, many=True)
        return ApiResponse.success(data=serializer.data)


class UserDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Admin only — retrieve, update or deactivate a user."""
    permission_classes = [IsAdmin]
    serializer_class = UserSerializer

    def get_queryset(self):
        return User.objects.filter(school=self.request.user.school)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        return ApiResponse.success(data=UserSerializer(instance).data)

    def update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        instance = self.get_object()
        serializer = UserSerializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return ApiResponse.success(
            data=serializer.data,
            message="User updated successfully.",
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.is_active = False  # soft deactivate, never hard delete
        instance.save()
        return ApiResponse.success(message="User deactivated successfully.")

class ForgotPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get("email")
        if not email:
            return ApiResponse.error(message="Email is required.")
        
        try:
            user = User.objects.get(email=email)
    
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
    permission_classes = [IsAdmin]
    def put(self, request, user_id):
        school = request.user.school
        try:
            user = User.objects.get(school = school, id = user_id)
            data = request.data.copy()
            data['user_id'] = user.id
        except User.DoesNotExist:
            return ApiResponse.error(
                message="User not found", status_code=404
            )
        
        serializer = ResetUserPasswordSerializer(data = data)
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

        
