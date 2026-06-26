from django.db import transaction
from rest_framework import generics
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend

from academics.models import Subject, SubjectTeacher
from academics.serializers import SubjectSerializer, SubjectTeacherCreationSerializer, SubjectTeacherListSerializer
from academics.filters import SubjectFilter, SubjectTeacherFilter
from schools.utils import check_and_complete_onboarding
from core.mixins import AuditLogMixin, ExportMixin
from core.permissions import IsAdmin, IsAdminOrTeacher
from core.responses import ApiResponse

class SubjectListCreateView(AuditLogMixin, ExportMixin, generics.ListCreateAPIView):
    permission_classes = [IsAdminOrTeacher]
    serializer_class = SubjectSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = SubjectFilter
    search_fields = ["name", "code"]
    ordering_fields = ["name", "code", "created_at"]
    ordering = ["name"]
    audit_resource = "Subject"

    def get_queryset(self):
        return Subject.objects.filter(school=self.request.user.school)

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAdmin()]
        return [IsAdminOrTeacher()]

    def get_audit_description(self, instance):
        return f"Subject '{instance.name}' created by {self.request.user.full_name}"

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return ApiResponse.success(data=serializer.data)

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        check_and_complete_onboarding(self.request.user.school)
        return ApiResponse.created(
            data=serializer.data,
            message="Subject created successfully.",
        )


class SubjectDetailView(AuditLogMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdmin]
    serializer_class = SubjectSerializer
    audit_resource = "Subject"

    def get_queryset(self):
        return Subject.objects.filter(school=self.request.user.school)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        return ApiResponse.success(data=self.get_serializer(instance).data)

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return ApiResponse.success(
            data=serializer.data,
            message="Subject updated successfully.",
        )
    
    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return ApiResponse.success(message="Subject deleted successfully.")


class SubjectExportView(ExportMixin, generics.ListAPIView):
    permission_classes = [IsAdminOrTeacher]
    serializer_class = SubjectSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = SubjectFilter
    search_fields = ["name", "code"]
    ordering = ["name"]

    def get_queryset(self):
        return Subject.objects.filter(school=self.request.user.school)

    def get(self, request, *args, **kwargs):
        return self.export(request, *args, **kwargs)

class SubjectTeacherListCreateView(AuditLogMixin, generics.ListCreateAPIView):
    permission_classes = [IsAdmin]
    
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = SubjectTeacherFilter
    search_fields = ["teacher__first_name", "teacher__last_name", "teacher__email", "subject__name", "subject__code"]
    ordering_fields = ["teacher__first_name", "teacher__last_name", "teacher__email", "subject__name", "subject__code"]
    ordering = ["teacher__last_name", "teacher__first_name"]

    
    audit_resource = "SubjectTeacher"

    def get_queryset(self):
        return SubjectTeacher.objects.filter(school=self.request.user.school)
    
    def get_audit_description(self, instance):
        return f"Subject teacher assignment of {instance.teacher.user.full_name} to {instance.subject.name} created by {self.request.user.full_name}"

    def get_serializer(self, *args, **kwargs):
        if self.request.method == "POST":
            return SubjectTeacherCreationSerializer(*args, **kwargs)
        return SubjectTeacherListSerializer(*args, **kwargs)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return ApiResponse.success(data=serializer.data)
    
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={"request": request, "school": request.user.school})
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return ApiResponse.created(
            data=serializer.data,
            message="Subject teacher assignment created successfully.",
        )
    
class UnassignSubjectTeacherView(AuditLogMixin, generics.DestroyAPIView):
    permission_classes = [IsAdmin]
    serializer_class = SubjectTeacherListSerializer
    audit_resource = "SubjectTeacher"

    def get_queryset(self):
        return SubjectTeacher.objects.filter(school=self.request.user.school)

    def get_audit_description(self, instance):
        return f"Unassigned {instance.teacher.user.full_name} from teaching {instance.subject.name}"

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return ApiResponse.success(message="Subject teacher assignment removed successfully.")