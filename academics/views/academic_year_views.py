from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, status
from rest_framework.filters import OrderingFilter, SearchFilter

from academics.filters import AcademicYearFilter
from academics.models import AcademicYear
from academics.serializers import AcademicYearSerializer
from core.mixins import AuditLogMixin, ExportMixin
from core.models import AuditLog
from core.permissions import IsAdmin, IsAdminOrReadOnly
from core.responses import ApiResponse
from core.utils import log_action
from schools.utils import check_and_complete_onboarding


class AcademicYearListCreateView(AuditLogMixin, ExportMixin, generics.ListCreateAPIView):
    permission_classes = [IsAdminOrReadOnly]
    serializer_class = AcademicYearSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = AcademicYearFilter
    search_fields = ["name"]
    ordering_fields = ["start_date", "name", "created_at"]
    ordering = ["-start_date"]
    audit_resource = "AcademicYear"

    def get_queryset(self):
        return AcademicYear.objects.filter(school=self.request.user.school).prefetch_related("terms")

    def perform_create(self, serializer):
        instance = serializer.save(school=self.request.user.school)
        log_action(
            action=AuditLog.Action.CREATE,
            resource="AcademicYear",
            resource_id=str(instance.pk),
            description=f"Academic year '{instance.name}' created",
            request=self.request,
        )
        check_and_complete_onboarding(self.request.user.school)
        return instance

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return ApiResponse.success(data=serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return ApiResponse.created(
            data=serializer.data,
            message="Academic year created successfully.",
        )


class AcademicYearDetailView(AuditLogMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdmin]
    serializer_class = AcademicYearSerializer
    audit_resource = "AcademicYear"

    def get_queryset(self):
        return AcademicYear.objects.filter(school=self.request.user.school)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        return ApiResponse.success(data=self.get_serializer(instance).data)

    def update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return ApiResponse.success(
            data=serializer.data,
            message="Academic year updated successfully.",
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.terms.exists():
            return ApiResponse.error(
                message="Cannot delete academic year with associated terms.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        if instance.is_current:
            return ApiResponse.error(
                message="Cannot delete the current academic year.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        self.perform_destroy(instance)
        return ApiResponse.success(message="Academic year deleted successfully.")


class AcademicYearExportView(ExportMixin, generics.ListAPIView):
    permission_classes = [IsAdmin]
    serializer_class = AcademicYearSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = AcademicYearFilter
    search_fields = ["name"]
    ordering_fields = ["start_date", "name", "created_at"]
    ordering = ["-start_date"]

    def get_queryset(self):
        return AcademicYear.objects.filter(school=self.request.user.school)

    def get(self, request, *args, **kwargs):
        return self.export(request, *args, **kwargs)
