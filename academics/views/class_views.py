from django.db import transaction
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.views import APIView

from academics.filters import ClassFilter, ClassTeacherFilter
from academics.models import Class, ClassSubject, ClassTeacher
from academics.serializers import (
    BulkAssignClassSubjectsSerializer,
    ClassSerializer,
    ClassSubjectSerializer,
    ClassTeacherSerializer,
)
from academics.services import ClassSubjectService, ClassTeacherService
from core.mixins import AuditLogMixin, ExportMixin
from core.permissions import IsAdmin, IsAdminOrReadOnly
from core.responses import ApiResponse
from core.school_permissions import school_permission
from core.teacher_scope import TeacherScopedQuerysetMixin
from subscriptions.permissions import HasExportAccess


class ClassListCreateView(
    TeacherScopedQuerysetMixin, AuditLogMixin, ExportMixin, generics.ListCreateAPIView
):
    permission_classes = (
        school_permission(read="academics.view", write="academics.manage"),
    )
    serializer_class = ClassSerializer
    filter_backends = (DjangoFilterBackend, SearchFilter, OrderingFilter)
    filterset_class = ClassFilter
    search_fields = ("name",)
    ordering_fields = ("name", "capacity", "created_at")
    ordering = ("name",)
    audit_resource = "Class"

    def get_queryset(self):
        return Class.objects.filter(school=self.request.user.school)

    def get_permissions(self):
        if self.request.method == "POST":
            return (IsAdmin(),)
        return (IsAdminOrReadOnly(),)

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


class ClassDetailView(
    TeacherScopedQuerysetMixin, AuditLogMixin, generics.RetrieveUpdateDestroyAPIView
):
    permission_classes = (
        school_permission(read="academics.view", write="academics.manage"),
    )
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


class ClassExportView(TeacherScopedQuerysetMixin, ExportMixin, generics.ListAPIView):
    permission_classes = [
        school_permission(read="academics.view", write="academics.manage"),
        HasExportAccess,
    ]
    serializer_class = ClassSerializer
    filter_backends = (DjangoFilterBackend, SearchFilter, OrderingFilter)
    filterset_class = ClassFilter
    search_fields = ("name",)
    ordering = ("name",)

    def get_queryset(self):
        return Class.objects.filter(school=self.request.user.school)

    def get(self, request, *args, **kwargs):
        return self.export(request, *args, **kwargs)


# ─── Class Subjects ───────────────────────────────────────────────


class ClassSubjectsListCreateView(
    TeacherScopedQuerysetMixin, AuditLogMixin, generics.ListCreateAPIView
):
    permission_classes = (
        school_permission(read="academics.view", write="academics.manage"),
    )
    serializer_class = ClassSubjectSerializer
    audit_resource = "ClassSubject"

    def get_queryset(self):
        class_id = self.kwargs.get("class_id")
        return ClassSubject.objects.filter(
            klass_id=class_id, school=self.request.user.school
        )

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return ApiResponse.success(data=serializer.data)

    def get_audit_description(self, instance):
        return f"Subject '{instance.subject.name}' assigned to class '{instance.klass.name}' by {self.request.user.full_name}"

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        class_id = self.kwargs.get("class_id")
        request.data["klass"] = str(class_id)
        serializer = self.get_serializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return ApiResponse.created(
            data=serializer.data,
            message="Subject assigned to class successfully.",
        )


class ClassSubjectDetailView(
    TeacherScopedQuerysetMixin, AuditLogMixin, generics.RetrieveDestroyAPIView
):
    permission_classes = (
        school_permission(read="academics.view", write="academics.manage"),
    )
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
        ClassSubjectService.delete_class_subject(instance)
        return ApiResponse.success(
            message="Subject unassigned from class successfully."
        )


class BulkAssignClassSubjectsView(APIView):
    """
    Bulk assign subjects to a class.
    Payload: {"subjects": ["uuid1", "uuid2", ...]}
    Skips subjects already assigned to the class.
    """

    permission_classes = (
        school_permission(read="academics.view", write="academics.manage"),
    )

    @transaction.atomic
    def post(self, request, class_id):
        school = request.user.school

        try:
            klass = Class.objects.get(id=class_id, school=school, is_active=True)
        except Class.DoesNotExist:
            return ApiResponse.error(
                message="Class not found, inactive, or does not belong to this school.",
                status_code=404,
            )

        serializer = BulkAssignClassSubjectsSerializer(
            data=request.data,
            context={"school": school},
        )
        serializer.is_valid(raise_exception=True)
        try:
            data, message = ClassSubjectService.assign_subjects_to_class(
                klass,
                serializer.validated_data["subjects"],
                assign_teacher=serializer.validated_data.get("assign_teacher", False),
            )
        except ValueError as e:
            return ApiResponse.error(message=str(e), status_code=400)
        

        return ApiResponse.created(
            data=data,
            message=message,
        )


# CLASS TEACHER ASSIGNMENT
class ClassTeacherView(
    TeacherScopedQuerysetMixin, AuditLogMixin, generics.ListCreateAPIView
):
    permission_classes = (
        school_permission(read="academics.view", write="academics.manage"),
    )
    serializer_class = ClassTeacherSerializer
    audit_resource = "ClassTeacher"

    def get_queryset(self):
        class_id = self.kwargs.get("class_id")
        return ClassTeacher.objects.filter(
            klass_id=class_id, school=self.request.user.school
        )

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
        request.data["klass"] = str(class_id)
        serializer = self.get_serializer(
            data=request.data,
            context={"request": request, "school": self.request.user.school},
        )
        serializer.is_valid(raise_exception=True)
        try:
            class_teacher = ClassTeacherService.assign_teacher_to_class(
                serializer.validated_data["klass"],
                serializer.validated_data["teacher"],
                assign_subjects=serializer.validated_data["assign_subjects"],
            )

            return ApiResponse.created(
                data=ClassTeacherSerializer(class_teacher).data,
                message="Teacher assigned to class successfully.",
            )
        except ValueError as e:
            return ApiResponse.error(message=str(e), status_code=400)



class UnassignClassTeacherView(
    TeacherScopedQuerysetMixin, AuditLogMixin, generics.RetrieveDestroyAPIView
):
    permission_classes = (
        school_permission(read="academics.view", write="academics.manage"),
    )
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
        return ApiResponse.success(
            message=f"Teacher '{teacher_name}' unassigned from class '{class_name}' successfully."
        )


class TeacherClassesView(TeacherScopedQuerysetMixin, generics.ListAPIView):
    permission_classes = (school_permission(read="class.teach"),)
    serializer_class = ClassTeacherSerializer
    filter_backends = (DjangoFilterBackend, SearchFilter, OrderingFilter)
    filterset_class = ClassTeacherFilter
    search_fields = ("klass__name",)
    ordering_fields = ("klass__name", "created_at")
    ordering = ("klass__name",)

    def get_queryset(self):
        staff_account = self.request.user.staff_profile
        return ClassTeacher.objects.filter(
            teacher=staff_account, school=self.request.user.school
        )
