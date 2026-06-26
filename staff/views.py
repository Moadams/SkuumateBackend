from rest_framework import generics
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework import status

from core.permissions import IsAdmin, IsTeacher
from core.responses import ApiResponse
from core.mixins import AuditLogMixin, ExportMixin
from core.models import AuditLog
from core.utils import log_action

from .models import (
    StaffPosition,
    StaffProfile,
    PERMISSION_CHOICES
)
from .serializers import (
    StaffCreationSerializer,
    StaffListSerializer,
    StaffPositionSerializer,
    StaffPositionWriteSerializer,
    StaffProfileSerializer,
    UpdateStaffSerializer,
)
from .filters import StaffProfileFilter


# ─── Permission Keys ──────────────────────────────────────────────

class PermissionListView(APIView):
    """
    Returns all available permission keys grouped by module.
    Used by the frontend when building the position create/edit form.
    """
    permission_classes = [IsAdmin]

    def get(self, request):
        grouped = {}
        for key, label in PERMISSION_CHOICES:
            module = key.split(".")[0].capitalize()
            if module not in grouped:
                grouped[module] = []
            grouped[module].append({"key": key, "label": label})

        return ApiResponse.success(
            data={
                "total": len(PERMISSION_CHOICES),
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
    permission_classes = [IsAdmin]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["name", "description"]
    ordering_fields = ["name", "created_at", "is_system"]
    ordering = ["-is_system", "name"]
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
    permission_classes = [IsAdmin]
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
            status=StaffProfile.Status.ACTIVE
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
    permission_classes = [IsAdmin]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = StaffProfileFilter
    search_fields = [
        "user__first_name",
        "user__last_name",
        "user__email",
        "employee_id",
    ]
    ordering_fields = [
        "user__last_name", "date_joined",
        "status", "employment_type",
    ]
    ordering = ["user__last_name"]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
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
            .prefetch_related("positions")
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

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        return ApiResponse.created(
            message = f"Staff profile for {serializer.instance.user.full_name} created successfully. "
        )


class StaffDetailView(
    AuditLogMixin, generics.RetrieveUpdateDestroyAPIView
):
    permission_classes = [IsAdmin]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    audit_resource = "StaffProfile"

    def get_queryset(self):
        return (
            StaffProfile.objects
            .filter(school=self.request.user.school)
            .select_related("user")
            .prefetch_related("positions")
        )

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["school"] = self.request.user.school
        return ctx

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        return ApiResponse.success(
            data=StaffProfileSerializer(
                instance, context={"request": request}
            ).data
        )

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = UpdateStaffSerializer(
            instance,
            data=request.data,
            partial=True,
            context={"school": request.user.school},
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

        # Soft deactivate rather than hard delete
        instance.status = StaffProfile.Status.TERMINATED
        instance.save()
        instance.user.is_active = False
        instance.user.save(update_fields=["is_active"])

        log_action(
            action=AuditLog.Action.UPDATE,
            resource="StaffProfile",
            resource_id=str(instance.pk),
            description=(
                f"Staff member {instance.user.full_name} terminated"
            ),
            request=request,
        )

        return ApiResponse.success(
            message=(
                f"{instance.user.full_name} has been "
                f"terminated and deactivated."
            )
        )


class StaffExportView(ExportMixin, generics.ListAPIView):
    permission_classes = [IsAdmin]
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