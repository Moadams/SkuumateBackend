from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from core.permissions import IsAdmin, IsAdminOrTeacher
from core.responses import ApiResponse
from core.mixins import AuditLogMixin, ExportMixin
from core.models import AuditLog
from core.utils import log_action
from schools.utils import check_and_complete_onboarding

from .models import AcademicYear, GradeScale, GradingSystem, Term, Subject, Class, ClassSubject, ClassTeacher
from .serializers import (
    AcademicYearSerializer, BulkGradeScaleSerializer, GradeResolverSerializer, GradeScaleSerializer, GradingSystemSerializer, GradingSystemWriteSerializer, TermSerializer, SubjectSerializer,
    ClassSerializer, AssignSubjectsSerializer, AssignTeacherSerializer,
    ClassSubjectSerializer, ClassTeacherSerializer,
)
from .filters import AcademicYearFilter, TermFilter, SubjectFilter, ClassFilter

from django.db import transaction

# ─── Academic Year ───────────────────────────────────────────────

class AcademicYearListCreateView(AuditLogMixin, ExportMixin, generics.ListCreateAPIView):
    permission_classes = [IsAdmin]
    serializer_class = AcademicYearSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = AcademicYearFilter
    search_fields = ["name"]
    ordering_fields = ["start_date", "name", "created_at"]
    ordering = ["-start_date"]
    audit_resource = "AcademicYear"

    def get_queryset(self):
        return AcademicYear.objects.filter(school=self.request.user.school)

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


# ─── Term ────────────────────────────────────────────────────────
class AcademicYearTermsListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = TermSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = TermFilter
    search_fields = ["name", "academic_year__name"]
    ordering_fields = ["start_date", "name", "created_at"]
    ordering = ["start_date"]

    def get_queryset(self):
        academic_year_id = self.kwargs.get("academic_year_id")
        return Term.objects.filter(
            school=self.request.user.school,
            academic_year_id=academic_year_id,
        )
    
    
class TermListCreateView(AuditLogMixin, ExportMixin, generics.ListCreateAPIView):
    permission_classes = [IsAdmin]
    serializer_class = TermSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = TermFilter
    search_fields = ["name", "academic_year__name"]
    ordering_fields = ["start_date", "name", "created_at"]
    ordering = ["start_date"]
    audit_resource = "Term"

    def get_queryset(self):
        return Term.objects.filter(school=self.request.user.school)

    def perform_create(self, serializer):
        instance = serializer.save(school=self.request.user.school)
        log_action(
            action=AuditLog.Action.CREATE,
            resource="Term",
            resource_id=str(instance.pk),
            description=f"Term '{instance.get_name_display()}' created",
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
            message="Term created successfully.",
        )


class TermDetailView(AuditLogMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdmin]
    serializer_class = TermSerializer
    audit_resource = "Term"

    def get_queryset(self):
        return Term.objects.filter(school=self.request.user.school)

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
            message="Term updated successfully.",
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.is_current:
            return ApiResponse.error(
                message="Cannot delete the current active term.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        self.perform_destroy(instance)
        return ApiResponse.success(message="Term deleted successfully.")

class ActivateTermView(APIView):
    def post(self, request, term_id):
        try:
            term = Term.objects.get(pk=term_id, school=request.user.school)
        except Term.DoesNotExist:
            return ApiResponse.error(message="Term not found.", status_code=404)

        # Deactivate any currently active term in the same academic year
        Term.objects.filter(
            school=request.user.school,
            is_current=True,
        ).exclude(pk=term.pk).update(is_current=False)

        AcademicYear.objects.filter(
            school=request.user.school,
            is_current=True,
        ).exclude(pk=term.academic_year.pk).update(is_current=False)


        term.is_current = True
        term.academic_year.is_current = True
        term.academic_year.save()
        term.save()

        return ApiResponse.success(
            data=None,
            message=f"{term.name} is now the active term.",
        )

class TermExportView(ExportMixin, generics.ListAPIView):
    permission_classes = [IsAdmin]
    serializer_class = TermSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = TermFilter
    search_fields = ["name", "academic_year__name"]
    ordering = ["start_date"]

    def get_queryset(self):
        return Term.objects.filter(school=self.request.user.school)

    def get(self, request, *args, **kwargs):
        return self.export(request, *args, **kwargs)


# ─── Subject ─────────────────────────────────────────────────────

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

    def perform_create(self, serializer):
        instance = serializer.save(school=self.request.user.school)
        log_action(
            action=AuditLog.Action.CREATE,
            resource="Subject",
            resource_id=str(instance.pk),
            description=f"Subject '{instance.name}' created",
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

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return ApiResponse.success(
            data=serializer.data,
            message="Subject updated successfully.",
        )

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


# ─── Class ───────────────────────────────────────────────────────

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

    def perform_create(self, serializer):
        instance = serializer.save(school=self.request.user.school)
        log_action(
            action=AuditLog.Action.CREATE,
            resource="Class",
            resource_id=str(instance.pk),
            description=f"Class '{instance.name}' created",
            request=self.request,
        )
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

class ClassSubjectAssignView(APIView):
    """Bulk assign or remove subjects from a class."""
    permission_classes = [IsAdmin]

    def get_class(self, request, pk):
        try:
            return Class.objects.get(pk=pk, school=request.user.school)
        except Class.DoesNotExist:
            return None

    def post(self, request, pk):
        klass = self.get_class(request, pk)
        if not klass:
            return ApiResponse.error(message="Class not found.", status_code=404)

        serializer = AssignSubjectsSerializer(
            data=request.data,
            context={"school": request.user.school},
        )
        serializer.is_valid(raise_exception=True)
        subject_ids = serializer.validated_data["subject_ids"]

        created_count = 0
        for subject_id in subject_ids:
            _, created = ClassSubject.objects.get_or_create(
                school=request.user.school,
                klass=klass,
                subject_id=subject_id,
            )
            if created:
                created_count += 1

        log_action(
            action=AuditLog.Action.UPDATE,
            resource="ClassSubject",
            resource_id=str(klass.pk),
            description=f"{created_count} subject(s) assigned to {klass.name}",
            request=request,
        )

        return ApiResponse.success(
            data=ClassSerializer(klass).data,
            message=f"{created_count} subject(s) assigned successfully.",
        )

    def delete(self, request, pk):
        klass = self.get_class(request, pk)
        if not klass:
            return ApiResponse.error(message="Class not found.", status_code=404)

        serializer = AssignSubjectsSerializer(
            data=request.data,
            context={"school": request.user.school},
        )
        serializer.is_valid(raise_exception=True)
        subject_ids = serializer.validated_data["subject_ids"]

        deleted_count, _ = ClassSubject.objects.filter(
            school=request.user.school,
            klass=klass,
            subject_id__in=subject_ids,
        ).delete()

        log_action(
            action=AuditLog.Action.DELETE,
            resource="ClassSubject",
            resource_id=str(klass.pk),
            description=f"{deleted_count} subject(s) removed from {klass.name}",
            request=request,
        )

        return ApiResponse.success(
            message=f"{deleted_count} subject(s) removed successfully.",
        )


# ─── Class Teacher ────────────────────────────────────────────────

class ClassTeacherAssignView(APIView):
    """Assign or remove a teacher from a class."""
    permission_classes = [IsAdmin]

    def get_class(self, request, pk):
        try:
            return Class.objects.get(pk=pk, school=request.user.school)
        except Class.DoesNotExist:
            return None

    def post(self, request, pk):
        klass = self.get_class(request, pk)
        if not klass:
            return ApiResponse.error(message="Class not found.", status_code=404)

        serializer = AssignTeacherSerializer(
            data=request.data,
            context={"school": request.user.school},
        )
        serializer.is_valid(raise_exception=True)

        teacher = serializer.validated_data["teacher"]
        academic_year = AcademicYear.objects.filter(school=request.user.school, is_current=True).first()
        if not academic_year:
            return ApiResponse.error(message="No active academic year found.", status_code=400)

        class_teacher = ClassTeacher.objects.create(
            school=request.user.school,
            klass=klass,
            academic_year=academic_year,
            teacher=teacher,
            is_active=True,
        )

        log_action(
            action=AuditLog.Action.UPDATE,
            resource="ClassTeacher",
            resource_id=str(klass.pk),
            description=f"{teacher.full_name} assigned to {klass.name}",
            request=request,
        )

        return ApiResponse.success(
            data=ClassTeacherSerializer(class_teacher).data,
            message="Teacher assigned successfully.",
        )

    def delete(self, request, pk):
        klass = self.get_class(request, pk)
        if not klass:
            return ApiResponse.error(message="Class not found.", status_code=404)

        academic_year_id = request.data.get("academic_year_id")
        if not academic_year_id:
            return ApiResponse.error(message="academic_year_id is required.")

        deleted_count, _ = ClassTeacher.objects.filter(
            school=request.user.school,
            klass=klass,
            academic_year_id=academic_year_id,
        ).delete()

        if not deleted_count:
            return ApiResponse.error(
                message="No teacher assignment found for this class and academic year.",
                status_code=404,
            )

        log_action(
            action=AuditLog.Action.DELETE,
            resource="ClassTeacher",
            resource_id=str(klass.pk),
            description=f"Teacher removed from {klass.name}",
            request=request,
        )

        return ApiResponse.success(message="Teacher removed successfully.")
    

# ─── Grading System ───────────────────────────────────────────────

class GradingSystemListCreateView(
    AuditLogMixin, generics.ListCreateAPIView
):
    """
    List all grading systems for the school
    or create a new one.
    """
    permission_classes = [IsAdmin]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["name", "description"]
    ordering_fields = ["name", "is_default", "created_at"]
    ordering = ["-is_default", "name"]
    audit_resource = "GradingSystem"

    def get_serializer_class(self):
        if self.request.method == "POST":
            return GradingSystemWriteSerializer
        return GradingSystemSerializer

    def get_queryset(self):
        return (
            GradingSystem.objects
            .filter(school=self.request.user.school)
            .prefetch_related("grade_scales")
        )

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["school"] = self.request.user.school
        return ctx

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = GradingSystemSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = GradingSystemSerializer(queryset, many=True)
        return ApiResponse.success(data=serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = GradingSystemWriteSerializer(
            data=request.data,
            context={"school": request.user.school},
        )
        serializer.is_valid(raise_exception=True)
        system = serializer.save(school=request.user.school)

        log_action(
            action=AuditLog.Action.CREATE,
            resource="GradingSystem",
            resource_id=str(system.pk),
            description=f"Grading system '{system.name}' created",
            request=request,
        )

        return ApiResponse.created(
            data=GradingSystemSerializer(system).data,
            message=f"Grading system '{system.name}' created successfully.",
        )


class GradingSystemDetailView(
    AuditLogMixin, generics.RetrieveUpdateDestroyAPIView
):
    permission_classes = [IsAdmin]
    audit_resource = "GradingSystem"

    def get_serializer_class(self):
        if self.request.method in ["PUT", "PATCH"]:
            return GradingSystemWriteSerializer
        return GradingSystemSerializer

    def get_queryset(self):
        return (
            GradingSystem.objects
            .filter(school=self.request.user.school)
            .prefetch_related("grade_scales")
        )

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["school"] = self.request.user.school
        return ctx

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        return ApiResponse.success(
            data=GradingSystemSerializer(instance).data
        )

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = GradingSystemWriteSerializer(
            instance,
            data=request.data,
            partial=True,
            context={"school": request.user.school},
        )
        serializer.is_valid(raise_exception=True)
        system = serializer.save()

        log_action(
            action=AuditLog.Action.UPDATE,
            resource="GradingSystem",
            resource_id=str(system.pk),
            description=f"Grading system '{system.name}' updated",
            request=request,
        )

        return ApiResponse.success(
            data=GradingSystemSerializer(system).data,
            message="Grading system updated successfully.",
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()

        # Block deletion of the only grading system
        total = GradingSystem.objects.filter(
            school=request.user.school
        ).count()
        if total == 1:
            return ApiResponse.error(
                message=(
                    "Cannot delete the only grading system. "
                    "Create another one first."
                ),
                status_code=400,
            )

        # Block deletion of the default grading system
        if instance.is_default:
            return ApiResponse.error(
                message=(
                    "Cannot delete the default grading system. "
                    "Set another system as default first."
                ),
                status_code=400,
            )

        log_action(
            action=AuditLog.Action.DELETE,
            resource="GradingSystem",
            resource_id=str(instance.pk),
            description=f"Grading system '{instance.name}' deleted",
            request=request,
        )

        instance.delete()
        return ApiResponse.success(
            message="Grading system deleted successfully."
        )


class GradingSystemSetDefaultView(APIView):
    """Set a grading system as the school default."""
    permission_classes = [IsAdmin]

    def patch(self, request, pk):
        try:
            system = GradingSystem.objects.get(
                pk=pk, school=request.user.school
            )
        except GradingSystem.DoesNotExist:
            return ApiResponse.error(
                message="Grading system not found.",
                status_code=404,
            )

        system.is_default = True
        system.save()

        log_action(
            action=AuditLog.Action.UPDATE,
            resource="GradingSystem",
            resource_id=str(system.pk),
            description=(
                f"Grading system '{system.name}' set as default"
            ),
            request=request,
        )

        return ApiResponse.success(
            data=GradingSystemSerializer(system).data,
            message=f"'{system.name}' is now the default grading system.",
        )


# ─── Grade Scales ─────────────────────────────────────────────────

class GradeScaleBulkSetView(APIView):
    """
    Replaces all grade scales for a grading system at once.

    This is the primary way to define grades —
    submit the complete set and we validate the entire
    range for gaps, overlaps and coverage.
    """
    permission_classes = [IsAdmin]

    def get_grading_system(self, pk, school):
        try:
            return GradingSystem.objects.prefetch_related(
                "grade_scales"
            ).get(pk=pk, school=school)
        except GradingSystem.DoesNotExist:
            return None

    def get(self, request, pk):
        """Returns all grade scales for a grading system."""
        system = self.get_grading_system(pk, request.user.school)
        if not system:
            return ApiResponse.error(
                message="Grading system not found.",
                status_code=404,
            )

        scales = system.grade_scales.all().order_by(
            "position", "-min_score"
        )
        return ApiResponse.success(
            data={
                "grading_system": GradingSystemSerializer(system).data,
                "grade_scales": GradeScaleSerializer(
                    scales, many=True
                ).data,
            }
        )

    def post(self, request, pk):
        """
        Bulk set grade scales — replaces all existing ones.
        Validates the entire range before saving anything.
        """
        system = self.get_grading_system(pk, request.user.school)
        if not system:
            return ApiResponse.error(
                message="Grading system not found.",
                status_code=404,
            )

        serializer = BulkGradeScaleSerializer(
            data=request.data,
            context={"grading_system": system},
        )
        serializer.is_valid(raise_exception=True)

        grades = serializer.validated_data["grades"]

        # All validations passed — replace existing scales
        with transaction.atomic():
            system.grade_scales.all().delete()

            created_scales = []
            for position, grade_data in enumerate(
                sorted(
                    grades,
                    key=lambda x: float(x["min_score"]),
                    reverse=True,
                )
            ):
                grade_data_copy = grade_data.copy()
                grade_data_copy.pop("position", None)  # Remove position if present in request data
                scale = GradeScale.objects.create(
                    grading_system=system,
                    school=request.user.school,
                    position=position,
                    **grade_data_copy,
                )
                created_scales.append(scale)

        log_action(
            action=AuditLog.Action.UPDATE,
            resource="GradingSystem",
            resource_id=str(system.pk),
            description=(
                f"Grade scales updated for '{system.name}' — "
                f"{len(created_scales)} grades defined"
            ),
            request=request,
        )

        return ApiResponse.success(
            data={
                "grading_system": GradingSystemSerializer(
                    system
                ).data,
                "grade_scales": GradeScaleSerializer(
                    created_scales, many=True
                ).data,
            },
            message=(
                f"{len(created_scales)} grade scales saved successfully."
            ),
        )


class GradeScaleUpdateView(APIView):
    """Update or delete a single grade scale."""
    permission_classes = [IsAdmin]

    def get_scale(self, pk, school):
        try:
            return GradeScale.objects.select_related(
                "grading_system"
            ).get(pk=pk, school=school)
        except GradeScale.DoesNotExist:
            return None

    def patch(self, request, pk):
        scale = self.get_scale(pk, request.user.school)
        if not scale:
            return ApiResponse.error(
                message="Grade scale not found.", status_code=404
            )

        serializer = GradeScaleSerializer(
            scale, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)

        # After updating this scale, verify the whole system
        # still has no gaps or overlaps
        updated_data = serializer.validated_data
        other_scales = scale.grading_system.grade_scales.exclude(
            pk=scale.pk
        ).values(
            "grade", "min_score", "max_score",
        )

        # Build a temporary full list to validate against
        temp_grades = list(other_scales) + [{
            "grade": updated_data.get("grade", scale.grade),
            "min_score": updated_data.get("min_score", scale.min_score),
            "max_score": updated_data.get("max_score", scale.max_score),
        }]

        bulk_serializer = BulkGradeScaleSerializer(
            data={"grades": temp_grades},
            context={"grading_system": scale.grading_system},
        )
        if not bulk_serializer.is_valid():
            return ApiResponse.error(
                message="This update would create gaps or overlaps.",
                errors=bulk_serializer.errors,
                status_code=400,
            )

        serializer.save()

        log_action(
            action=AuditLog.Action.UPDATE,
            resource="GradeScale",
            resource_id=str(scale.pk),
            description=(
                f"Grade '{scale.grade}' updated in "
                f"'{scale.grading_system.name}'"
            ),
            request=request,
        )

        return ApiResponse.success(
            data=GradeScaleSerializer(scale).data,
            message="Grade scale updated successfully.",
        )

    def delete(self, request, pk):
        scale = self.get_scale(pk, request.user.school)
        if not scale:
            return ApiResponse.error(
                message="Grade scale not found.", status_code=404
            )

        # Must have at least 2 grades
        total = scale.grading_system.grade_scales.count()
        if total <= 2:
            return ApiResponse.error(
                message=(
                    "Cannot delete — a grading system must have "
                    "at least 2 grade bands."
                ),
                status_code=400,
            )

        scale.delete()
        return ApiResponse.success(
            message=f"Grade '{scale.grade}' removed successfully."
        )


class GradeResolverView(APIView):
    """
    Test endpoint — given a score, returns the matching grade.
    Useful for the frontend to preview grading before saving.
    """
    permission_classes = [IsAdminOrTeacher]

    def post(self, request, pk):
        from .utils import resolve_grade

        try:
            system = GradingSystem.objects.get(
                pk=pk, school=request.user.school
            )
        except GradingSystem.DoesNotExist:
            return ApiResponse.error(
                message="Grading system not found.",
                status_code=404,
            )

        serializer = GradeResolverSerializer(
            data=request.data,
            context={"grading_system": system},
        )
        serializer.is_valid(raise_exception=True)

        score = serializer.validated_data["score"]
        grade = resolve_grade(system, score)

        if not grade:
            return ApiResponse.error(
                message=(
                    f"No grade found for score {score} in "
                    f"'{system.name}'. Check your grade ranges."
                ),
                status_code=404,
            )

        return ApiResponse.success(
            data={
                "score": float(score),
                "grade": grade.grade,
                "label": grade.label,
                "remark": grade.remark,
                "is_passing": grade.is_passing,
                "range": {
                    "min": float(grade.min_score),
                    "max": float(grade.max_score),
                },
            }
        )