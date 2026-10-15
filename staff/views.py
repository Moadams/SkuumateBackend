import logging

from django.db import IntegrityError, transaction
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics
from rest_framework.exceptions import PermissionDenied
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.views import APIView

from accounts.models import User
from core.mixins import AuditLogMixin, ExportMixin
from core.models import AuditLog
from core.permissions import IsTeacher, effective_keys
from core.responses import ApiResponse
from core.school_permissions import school_permission
from core.utils import log_action
from staff.enums.staff_status import StaffStatus
from subscriptions.permissions import HasExportAccess

from .filters import StaffProfileFilter
from .models import PERMISSION_CHOICES, PermissionKey, StaffPosition, StaffProfile
from .serializers import (
    StaffCreationSerializer,
    StaffListSerializer,
    StaffPositionSerializer,
    StaffPositionWriteSerializer,
    StaffProfileSerializer,
    UpdateStaffSerializer,
)
from .services import StaffService

logger = logging.getLogger(__name__)


def check_staff_management(user, profile):
    privileged = profile.role == "admin" or (profile.user and (profile.user.is_superuser or profile.user.role in ("admin", "superadmin")))
    if privileged and user.role != "admin" and "school.manage" not in effective_keys(user):
        raise PermissionDenied("Only school administrators can manage administrator accounts.")

# ─── Permission Keys ──────────────────────────────────────────────

class PermissionListView(APIView):
    """
    Returns all available permission keys grouped by module.
    Reads from the registry table (falling back to the bootstrap
    constants before the registry is seeded).
    Used by the frontend when building the position create/edit form.
    """
    permission_classes = (school_permission(read="school.manage", write="school.manage"),)

    def get(self, request):
        registry = PermissionKey.objects.all()
        if registry.exists():
            entries = registry.values("key", "label", "module")
        else:
            entries = [
                {"key": key, "label": label, "module": key.split(".")[0].capitalize()}
                for key, label in PERMISSION_CHOICES
            ]

        grouped = {}
        for entry in entries:
            grouped.setdefault(entry["module"], []).append(entry)

        return ApiResponse.success(
            data={
                "total": len(entries),
                "groups": [
                    {"module": module, "permissions": perms}
                    for module, perms in grouped.items()
                ],
            }
        )


# ─── Staff Positions ──────────────────────────────────────────────

class StaffPositionListCreateView(
    AuditLogMixin, ExportMixin, generics.ListCreateAPIView
):
    permission_classes = (school_permission(read="school.manage", write="school.manage"),)
    filter_backends = (SearchFilter, OrderingFilter)
    search_fields = ("name", "description")
    ordering_fields = ("name", "created_at", "is_system")
    ordering = ("-is_system", "name")
    audit_resource = "StaffPosition"

    def get_serializer_class(self):
        if self.request.method == "POST":
            return StaffPositionWriteSerializer
        return StaffPositionSerializer

    def get_queryset(self):
        return StaffPosition.objects.filter(
            school=self.request.user.school
        )

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["school"] = self.request.user.school
        return ctx

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = StaffPositionSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = StaffPositionSerializer(
            queryset, many=True
        )
        return ApiResponse.success(data=serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        position = serializer.save(school=request.user.school)
        log_action(
            action=AuditLog.Action.CREATE,
            resource="StaffPosition",
            resource_id=str(position.pk),
            description=f"Position '{position.name}' created",
            request=request,
        )
        return ApiResponse.created(
            data=StaffPositionSerializer(position).data,
            message=f"Position '{position.name}' created successfully.",
        )


class StaffPositionDetailView(
    AuditLogMixin, generics.RetrieveUpdateDestroyAPIView
):
    permission_classes = (school_permission(read="school.manage", write="school.manage"),)
    audit_resource = "StaffPosition"

    def get_serializer_class(self):
        if self.request.method in ["PUT", "PATCH"]:
            return StaffPositionWriteSerializer
        return StaffPositionSerializer

    def get_queryset(self):
        return StaffPosition.objects.filter(
            school=self.request.user.school
        )

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["school"] = self.request.user.school
        return ctx

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        return ApiResponse.success(
            data=StaffPositionSerializer(instance).data
        )

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = StaffPositionWriteSerializer(
            instance,
            data=request.data,
            partial=True,
            context={"school": request.user.school},
        )
        serializer.is_valid(raise_exception=True)
        position = serializer.save()
        log_action(
            action=AuditLog.Action.UPDATE,
            resource="StaffPosition",
            resource_id=str(position.pk),
            description=f"Position '{position.name}' updated",
            request=request,
        )
        return ApiResponse.success(
            data=StaffPositionSerializer(position).data,
            message="Position updated successfully.",
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()

        # Block deletion of system positions
        if instance.is_system:
            return ApiResponse.error(
                message=(
                    f"'{instance.name}' is a system position "
                    f"and cannot be deleted."
                ),
                status_code=400,
            )

        # Block if staff are assigned to this position
        active_staff = instance.staff_members.filter(
            status=StaffStatus.ACTIVE
        ).count()
        if active_staff > 0:
            return ApiResponse.error(
                message=(
                    f"Cannot delete '{instance.name}' — "
                    f"{active_staff} active staff member(s) are "
                    f"assigned to this position. "
                    f"Reassign them first."
                ),
                status_code=400,
            )

        log_action(
            action=AuditLog.Action.DELETE,
            resource="StaffPosition",
            resource_id=str(instance.pk),
            description=f"Position '{instance.name}' deleted",
            request=request,
        )
        instance.delete()
        return ApiResponse.success(
            message="Position deleted successfully."
        )


# ─── Staff Profiles ───────────────────────────────────────────────

class StaffListCreateView(
    AuditLogMixin, ExportMixin, generics.ListCreateAPIView
):
    permission_classes = (school_permission(read="staff.view", write="staff.manage"),)
    filter_backends = (DjangoFilterBackend, SearchFilter, OrderingFilter)
    filterset_class = StaffProfileFilter
    search_fields = (
        "user__first_name",
        "user__last_name",
        "user__email",
        "employee_id",
    )
    ordering_fields = (
        "user__last_name", "date_joined",
        "status", "employment_type",
    )
    ordering = ("user__last_name",)
    parser_classes = (MultiPartParser, FormParser, JSONParser)
    audit_resource = "StaffProfile"

    def get_serializer_class(self):
        if self.request.method == "POST":
            return StaffCreationSerializer
        return StaffListSerializer

    def get_queryset(self):
        return (
            StaffProfile.objects
            .filter(school=self.request.user.school)
            .select_related("user")
        )

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["school"] = self.request.user.school
        return ctx

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = StaffListSerializer(
                page, many=True, context={"request": request}
            )
            return self.get_paginated_response(serializer.data)
        serializer = StaffListSerializer(
            queryset, many=True, context={"request": request}
        )
        return ApiResponse.success(data=serializer.data)

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            StaffService.create_staff(
                school=request.user.school,
                user_data=serializer.validated_data,
                position_name=request.data.get("position_name")
            )
        except ValueError as e:
            return ApiResponse.error(message=str(e))

        return ApiResponse.created(
            message = "Staff profile created successfully. "
        )


class StaffDetailView(
    AuditLogMixin, generics.RetrieveUpdateDestroyAPIView
):
    permission_classes = (school_permission(read="staff.view", write="staff.manage"),)
    filter_backends = (DjangoFilterBackend, SearchFilter, OrderingFilter)
    parser_classes = (MultiPartParser, FormParser, JSONParser)
    audit_resource = "StaffProfile"
    serializer_class = StaffProfileSerializer

    def get_queryset(self):
        return (
            StaffProfile.objects
            .filter(school=self.request.user.school)
            .select_related("user")
        )

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["school"] = self.request.user.school
        return ctx


    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        check_staff_management(request.user, instance)
        serializer = UpdateStaffSerializer(
            instance,
            data=request.data,
            partial=True,
            context={"school": request.user.school, "request": request},
        )
        serializer.is_valid(raise_exception=True)
        profile = self.perform_update(serializer)
        
        return ApiResponse.success(
            data=StaffProfileSerializer(
                profile, context={"request": request}
            ).data,
            message="Staff profile updated successfully.",
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        check_staff_management(request.user, instance)
        try:
            StaffService.delete_staff(instance)
        except ValueError as e:
            return ApiResponse.error(message=str(e))
        return ApiResponse.success(
            message="Staff profile deleted successfully."
        )

class UpdateStaffStatusView(APIView):
    permission_classes = [school_permission(read="staff.view", write="staff.manage")]
    audit_resource = "StaffProfile"

    @transaction.atomic
    def post(self, request, pk):
        try:
            staff_profile = StaffProfile.objects.get(pk=pk, school=request.user.school)
        except StaffProfile.DoesNotExist:
            return ApiResponse.error(
                message="Staff profile not found.",
                status_code=404,
            )
        
        status = request.data.get("status")
        check_staff_management(request.user, staff_profile)
        if status not in StaffStatus.values:
            return ApiResponse.error(
                message=f"Invalid status '{status}'.",
                status_code=400,
            )

        if staff_profile.status == status:
            return ApiResponse.error(
                message=f"Staff profile is already '{status}'.",
                status_code=400,
            )
        
        if status == StaffStatus.ACTIVE:
            return self._activate_staff_profile(request, staff_profile)
        
        else:
            return self._deactivate_staff_profile(request, staff_profile)
        
    def _activate_staff_profile(self, request, staff_profile):
        staff_profile.status = StaffStatus.ACTIVE
        staff_profile.save()
        if staff_profile.user:
            staff_profile.user.is_active = True
            staff_profile.user.save()
        log_action(
            action=AuditLog.Action.UPDATE,
            resource="StaffProfile",
            resource_id=str(staff_profile.pk),
            description=f"Staff profile '{staff_profile.full_name}' activated",
            request=request,
        )
        return ApiResponse.success(
            message=f"Staff profile '{staff_profile.full_name}' activated successfully."
        )
    
    def _deactivate_staff_profile(self, request, staff_profile):
        staff_profile.status = StaffStatus.INACTIVE
        staff_profile.save()
        if staff_profile.user:
            staff_profile.user.is_active = False
            staff_profile.user.save()
        log_action(
            action=AuditLog.Action.UPDATE,
            resource="StaffProfile",
            resource_id=str(staff_profile.pk),
            description=f"Staff profile '{staff_profile.full_name}' deactivated",
            request=request,
        )
        return ApiResponse.success(
            message=f"Staff profile '{staff_profile.full_name}' deactivated successfully."
        )

class StaffExportView(ExportMixin, generics.ListAPIView):
    permission_classes = [school_permission(read="staff.manage"), HasExportAccess]
    serializer_class = StaffProfileSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = StaffProfileFilter
    search_fields = [
        "user__first_name", "user__last_name",
        "user__email", "employee_id",
    ]
    ordering = ["user__last_name"]

    def get_queryset(self):
        return (
            StaffProfile.objects
            .filter(school=self.request.user.school)
            .select_related("user")
            .prefetch_related("positions")
        )

    def get(self, request, *args, **kwargs):
        return self.export(request, *args, **kwargs)


class MyStaffProfileView(APIView):
    """
    Returns the logged-in user's own staff profile and permissions.
    Used by the frontend after login to determine dashboard
    redirect and available navigation items.
    """
    permission_classes = [IsTeacher]

    def get(self, request):
        try:
            profile = StaffProfile.objects.select_related(
                "user"
            ).prefetch_related("positions").get(
                user=request.user
            )
        except StaffProfile.DoesNotExist:
            return ApiResponse.error(
                message="No staff profile found for this account.",
                status_code=404,
            )

        return ApiResponse.success(
            data=StaffProfileSerializer(
                    profile, context={"request": request}
                ).data
        )
    
class ActivateStaffUserAccountView(APIView):
    """
    Activates the user account associated with a staff profile.
    """
    permission_classes = [school_permission(read="staff.view", write="staff.manage")]

    def post(self, request, pk):
        try:
            staff_profile = StaffProfile.objects.get(pk=pk, school=request.user.school)
        except StaffProfile.DoesNotExist:
            return ApiResponse.error(
                message="Staff profile not found.",
                status_code=404,
            )

        check_staff_management(request.user, staff_profile)
        if staff_profile.user:
            return ApiResponse.error(
                message="Staff profile already has an associated user account.",
                status_code=400,
            )

        if staff_profile.role not in ("admin", "teacher", "finance_manager"):
            return ApiResponse.error(message="Only school staff roles can be activated.", status_code=400)

        try:
            with transaction.atomic():
                staff_profile = StaffProfile.objects.select_for_update().get(pk=pk, school=request.user.school)
                if staff_profile.user_id:
                    return ApiResponse.error(message="Staff profile already has an associated user account.", status_code=400)
                user = User.objects.create_user(
                    email=staff_profile.email,
                    first_name=staff_profile.first_name,
                    last_name=staff_profile.last_name,
                    role=staff_profile.role,
                    school=request.user.school,
                    must_change_password=True,
                )
                staff_profile.user = user
                staff_profile.save()
       
        except IntegrityError as exc:
            logger.error(
                "Failed to create user account for staff profile %s: %s",
                staff_profile.pk,
                str(exc),
            )
            if "accounts_user.email" in str(exc) or "email" in str(exc).lower():
                return ApiResponse.error(
                    message="A user account with this email already exists. Please update the staff profile's email or use a different email.",
                    status_code=400,
                )
            return ApiResponse.error(
                message="Failed to create user account due to a data conflict.",
                status_code=400,
            )
        
        except Exception as e:
            logger.error(f"Failed to create user account for staff profile {staff_profile.pk}: {str(e)}")
            return ApiResponse.error(
                message="Failed to create user account. Please try again.",
                status_code=500,
            )
        log_action(
            action=AuditLog.Action.UPDATE,
            resource="StaffProfile",
            resource_id=str(staff_profile.pk),
            description=f"Activated user account for '{staff_profile.full_name}'",
            request=request,
        )

        return ApiResponse.success(
            message=f"User account for '{staff_profile.full_name}' activated successfully."
        )
