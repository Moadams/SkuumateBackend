from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from core.permissions import IsAdmin, IsAdminOrTeacher
from core.responses import ApiResponse
from core.mixins import AuditLogMixin, ExportMixin
from core.models import AuditLog
from core.utils import log_action
from subscriptions.utils import check_limit

from .models import Student, Guardian, Enrollment
from .serializers import (
    StudentSerializer, StudentCreateSerializer,
    GuardianSerializer, EnrollStudentSerializer,
    EnrollmentSerializer,
)
from .filters import StudentFilter


# ─── Students ────────────────────────────────────────────────────

class StudentListCreateView(AuditLogMixin, ExportMixin, generics.ListCreateAPIView):
    permission_classes = [IsAdminOrTeacher]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = StudentFilter
    search_fields = [
        "first_name", "last_name",
        "other_names", "student_id",
    ]
    ordering_fields = [
        "first_name", "last_name",
        "admission_date", "created_at",
    ]
    ordering = ["last_name", "first_name"]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    audit_resource = "Student"

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAdmin()]
        return [IsAdminOrTeacher()]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return StudentCreateSerializer
        return StudentSerializer

    def get_queryset(self):
        return Student.objects.filter(
            school=self.request.user.school
        ).prefetch_related("guardians", "enrollments__klass", "enrollments__academic_year")

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["school"] = self.request.user.school
        return ctx

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = StudentSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = StudentSerializer(queryset, many=True)
        return ApiResponse.success(data=serializer.data)

    def create(self, request, *args, **kwargs):
        check_limit(request.user.school, "students") 
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        student = serializer.save()
        log_action(
            action=AuditLog.Action.CREATE,
            resource="Student",
            resource_id=str(student.pk),
            description=f"Student {student.full_name} registered",
            request=request,
        )
        return ApiResponse.created(
            data=StudentSerializer(student).data,
            message="Student registered successfully.",
        )


class StudentDetailView(AuditLogMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminOrTeacher]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    audit_resource = "Student"

    def get_permissions(self):
        if self.request.method in ["PATCH", "DELETE"]:
            return [IsAdmin()]
        return [IsAdminOrTeacher()]

    def get_serializer_class(self):
        if self.request.method == "PATCH":
            return StudentCreateSerializer
        return StudentSerializer

    def get_queryset(self):
        return Student.objects.filter(
            school=self.request.user.school
        ).prefetch_related("guardians", "enrollments__klass", "enrollments__academic_year")

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["school"] = self.request.user.school
        return ctx

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        return ApiResponse.success(data=StudentSerializer(instance).data)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = StudentCreateSerializer(
            instance, data=request.data, partial=True,
            context={"school": request.user.school}
        )
        serializer.is_valid(raise_exception=True)
        student = serializer.save()
        log_action(
            action=AuditLog.Action.UPDATE,
            resource="Student",
            resource_id=str(student.pk),
            description=f"Student {student.full_name} updated",
            request=request,
        )
        return ApiResponse.success(
            data=StudentSerializer(student).data,
            message="Student updated successfully.",
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.status = Student.Status.WITHDRAWN
        instance.save()
        log_action(
            action=AuditLog.Action.UPDATE,
            resource="Student",
            resource_id=str(instance.pk),
            description=f"Student {instance.full_name} withdrawn",
            request=request,
        )
        return ApiResponse.success(message="Student withdrawn successfully.")


class StudentExportView(ExportMixin, generics.ListAPIView):
    permission_classes = [IsAdminOrTeacher]
    serializer_class = StudentSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = StudentFilter
    search_fields = ["first_name", "last_name", "other_names", "student_id"]
    ordering = ["last_name", "first_name"]

    def get_queryset(self):
        return Student.objects.filter(
            school=self.request.user.school
        ).prefetch_related("guardians", "enrollments__klass", "enrollments__academic_year")

    def get(self, request, *args, **kwargs):
        return self.export(request, *args, **kwargs)


# ─── Guardians ────────────────────────────────────────────────────

class GuardianListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAdmin]
    serializer_class = GuardianSerializer

    def get_student(self, request, pk):
        try:
            return Student.objects.get(pk=pk, school=request.user.school)
        except Student.DoesNotExist:
            return None

    def get_queryset(self):
        student = self.get_student(self.request, self.kwargs["pk"])
        if not student:
            return Guardian.objects.none()
        return Guardian.objects.filter(student=student)

    def list(self, request, *args, **kwargs):
        student = self.get_student(request, kwargs["pk"])
        if not student:
            return ApiResponse.error(message="Student not found.", status_code=404)
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return ApiResponse.success(data=serializer.data)

    def create(self, request, *args, **kwargs):
        student = self.get_student(request, kwargs["pk"])
        if not student:
            return ApiResponse.error(message="Student not found.", status_code=404)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        guardian = serializer.save(student=student, school=request.user.school)
        log_action(
            action=AuditLog.Action.CREATE,
            resource="Guardian",
            resource_id=str(guardian.pk),
            description=f"Guardian {guardian} added to {student.full_name}",
            request=request,
        )
        return ApiResponse.created(
            data=serializer.data,
            message="Guardian added successfully.",
        )


class GuardianDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdmin]
    serializer_class = GuardianSerializer

    def get_queryset(self):
        return Guardian.objects.filter(school=self.request.user.school)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        return ApiResponse.success(data=self.get_serializer(instance).data)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return ApiResponse.success(
            data=serializer.data,
            message="Guardian updated successfully.",
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()
        return ApiResponse.success(message="Guardian removed successfully.")


# ─── Enrollment ───────────────────────────────────────────────────

class StudentEnrollView(APIView):
    """Enroll a student into a class for a given academic year."""
    permission_classes = [IsAdmin]

    def get_student(self, request, pk):
        try:
            return Student.objects.get(pk=pk, school=request.user.school)
        except Student.DoesNotExist:
            return None

    def post(self, request, pk):
        student = self.get_student(request, pk)
        if not student:
            return ApiResponse.error(message="Student not found.", status_code=404)

        serializer = EnrollStudentSerializer(
            data=request.data,
            context={
                "school": request.user.school,
                "student": student,
            },
        )
        serializer.is_valid(raise_exception=True)

        enrollment = Enrollment.objects.create(
            school=request.user.school,
            student=student,
            klass=serializer.validated_data["klass"],
            academic_year=serializer.validated_data["academic_year"],
        )

        log_action(
            action=AuditLog.Action.CREATE,
            resource="Enrollment",
            resource_id=str(enrollment.pk),
            description=(
                f"{student.full_name} enrolled in "
                f"{enrollment.klass.name} for {enrollment.academic_year.name}"
            ),
            request=request,
        )

        return ApiResponse.created(
            data=EnrollmentSerializer(enrollment).data,
            message="Student enrolled successfully.",
        )

    def delete(self, request, pk):
        """Withdraw a student from their current enrollment."""
        student = self.get_student(request, pk)
        if not student:
            return ApiResponse.error(message="Student not found.", status_code=404)

        academic_year_id = request.data.get("academic_year_id")
        if not academic_year_id:
            return ApiResponse.error(message="academic_year_id is required.")

        try:
            enrollment = Enrollment.objects.get(
                student=student,
                academic_year_id=academic_year_id,
                school=request.user.school,
                is_active=True,
            )
        except Enrollment.DoesNotExist:
            return ApiResponse.error(
                message="Active enrollment not found.", status_code=404
            )

        enrollment.is_active = False
        enrollment.save()

        log_action(
            action=AuditLog.Action.UPDATE,
            resource="Enrollment",
            resource_id=str(enrollment.pk),
            description=f"{student.full_name} withdrawn from {enrollment.klass.name}",
            request=request,
        )

        return ApiResponse.success(message="Student withdrawn from class successfully.")


class StudentEnrollmentHistoryView(generics.ListAPIView):
    """Full enrollment history for a student."""
    permission_classes = [IsAdminOrTeacher]
    serializer_class = EnrollmentSerializer

    def get_queryset(self):
        return Enrollment.objects.filter(
            student_id=self.kwargs["pk"],
            school=self.request.user.school,
        ).select_related("klass", "academic_year")

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return ApiResponse.success(data=serializer.data)