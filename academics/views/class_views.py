
from django.db import transaction
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics
from rest_framework.filters import SearchFilter, OrderingFilter
from academics.filters import ClassFilter
from academics.models import Class, ClassSubject, ClassTeacher
from academics.serializers import ClassSerializer, ClassSubjectSerializer, ClassTeacherSerializer
from core.mixins import AuditLogMixin, ExportMixin
from core.permissions import IsAdmin, IsAdminOrTeacher
from core.responses import ApiResponse


class ClassListCreateView(AuditLogMixin, ExportMixin, generics.ListCreateAPIView):
    permission_classes = [IsAdminOrTeacher]
    serializer_class = ClassSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = ClassFilter
    search_fields = ["name"]
    ordering_fields = ["name", "capacity", "created_at"]
    ordering = ["name"]
    audit_resource = "Class"

    def get_queryset(self):
        return Class.objects.filter(school=self.request.user.school)

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAdmin()]
        return [IsAdminOrTeacher()]

    def get_audit_description(self, instance):
        return f"Class '{instance.name}' created by {self.request.user.full_name}"

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
            message="Class created successfully.",
        )


class ClassDetailView(AuditLogMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdmin]
    serializer_class = ClassSerializer
    audit_resource = "Class"

    def get_queryset(self):
        return Class.objects.filter(school=self.request.user.school)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        return ApiResponse.success(data=self.get_serializer(instance).data)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return ApiResponse.success(
            data=serializer.data,
            message="Class updated successfully.",
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return ApiResponse.success(message="Class deleted successfully.")


class ClassExportView(ExportMixin, generics.ListAPIView):
    permission_classes = [IsAdminOrTeacher]
    serializer_class = ClassSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = ClassFilter
    search_fields = ["name"]
    ordering = ["name"]

    def get_queryset(self):
        return Class.objects.filter(school=self.request.user.school)

    def get(self, request, *args, **kwargs):
        return self.export(request, *args, **kwargs)


# ─── Class Subjects ───────────────────────────────────────────────

class ClassSubjectsListCreateView(AuditLogMixin, generics.ListCreateAPIView):
    permission_classes = [IsAdmin]
    serializer_class = ClassSubjectSerializer
    audit_resource = "ClassSubject"
    
    def get_queryset(self):
        class_id = self.kwargs.get("class_id")
        return ClassSubject.objects.filter(klass_id=class_id, school=self.request.user.school)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return ApiResponse.success(data=serializer.data)

    def get_audit_description(self, instance):
        return f"Subject '{instance.subject.name}' assigned to class '{instance.klass.name}' by {self.request.user.full_name}"

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        class_id = self.kwargs.get("class_id")
        request.data['klass'] = str(class_id)
        serializer = self.get_serializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return ApiResponse.created(
            data=serializer.data,
            message="Subject assigned to class successfully.",
        )

class ClassSubjectDetailView(AuditLogMixin, generics.RetrieveDestroyAPIView):
    permission_classes = [IsAdmin]
    serializer_class = ClassSubjectSerializer
    audit_resource = "ClassSubject"

    def get_queryset(self):
        return ClassSubject.objects.filter(school=self.request.user.school)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        return ApiResponse.success(data=self.get_serializer(instance).data)

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return ApiResponse.success(message="Subject unassigned from class successfully.")



# CLASS TEACHER ASSIGNMENT
class ClassTeacherView(AuditLogMixin, generics.ListCreateAPIView):
    permission_classes = [IsAdmin]
    serializer_class = ClassTeacherSerializer
    audit_resource = "ClassTeacher"

    def get_queryset(self):
        class_id = self.kwargs.get("class_id")
        return ClassTeacher.objects.filter(klass_id=class_id, school=self.request.user.school)

    def get_audit_description(self, instance):
        teacher_name = instance.teacher.full_name if instance.teacher else "None"
        return f"Teacher '{teacher_name}' assigned to class '{instance.klass.name}' by {self.request.user.full_name}"
    
    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return ApiResponse.success(data=serializer.data)

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        class_id = self.kwargs.get("class_id")
        request.data['klass'] = str(class_id)
        serializer = self.get_serializer(data=request.data, context={"request": request, 'school': self.request.user.school})
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return ApiResponse.created(
            data=serializer.data,
            message="Teacher assigned to class successfully.",
        )
    
class UnassignClassTeacherView(AuditLogMixin, generics.DestroyAPIView):
    permission_classes = [IsAdmin]
    serializer_class = ClassTeacherSerializer
    audit_resource = "ClassTeacher"

    def get_queryset(self):
        return ClassTeacher.objects.filter(school=self.request.user.school)

    def get_audit_description(self, instance):
        return f"Teacher '{instance.teacher.full_name}' unassigned from class '{instance.klass.name}' by {self.request.user.full_name}"

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        teacher_name = instance.teacher.full_name if instance.teacher else "None"
        class_name = instance.klass.name if instance.klass else "None"
        self.perform_destroy(instance)
        return ApiResponse.success(message=f"Teacher '{teacher_name}' unassigned from class '{class_name}' successfully.")