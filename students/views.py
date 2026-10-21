from core.teacher_scope import (
    TeacherScopedQuerysetMixin,
    assigned_class_ids,
    needs_teacher_scope,
)
from core.school_permissions import school_permission
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, serializers
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from academics.models import AcademicYear, Term
from core.mixins import AuditLogMixin, ExportMixin
from core.models import AuditLog
from core.permissions import IsAdmin, IsAdminOrReadOnly, IsAdminOrTeacher
from core.responses import ApiResponse
from core.utils import log_action
from students.utils import parse_students_from_excel
from subscriptions.permissions import HasExportAccess, HasIdCardAccess
from subscriptions.utils import check_limit

from .filters import StudentFilter
from .models import Enrollment, Guardian, Promotion, PromotionBatch, Student
from .serializers import (
    BulkStudentUploadSerializer,
    EnrollmentSerializer,
    EnrollStudentSerializer,
    GuardianSerializer,
    IDCardRequestSerializer,
    PromotionBatchSerializer,
    PromotionRequestSerializer,
    StudentCreateSerializer,
    StudentListSerializer,
    StudentMinimalSerializer,
    StudentSerializer,
    StudentUpdateSerializer,
    StudentVerificationSerializer,
)
from .services import ClassBulkImportService, PromotionService
from .services.excel import build_class_bulk_template_workbook
from .services.id_cards import build_student_card_pdf, build_students_cards_pdf

# Cap on a single bulk card run. Larger sets must be narrowed by class or an
# explicit student selection so one request cannot build an unbounded PDF.
MAX_ID_CARD_BATCH = 300

# ─── Students ────────────────────────────────────────────────────

class StudentBulkCreateView(APIView):
    """
    Bulk create students from an uploaded Excel file.

    Payload: multipart/form-data
        file = .xlsx file (required)
        class_id = UUID (optional — applied to ALL students if provided)
        academic_year_id = UUID (optional — applied to ALL students if provided)

    Individual students in the Excel can override class_id
    and academic_year_id per row.
    """
    permission_classes = [school_permission(create="students.create")]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        school = request.user.school

        # ── Validate file ─────────────────────────────────────────
        file = request.FILES.get("file")
        if not file:
            return ApiResponse.error(
                message="No file uploaded. Please upload an .xlsx file.",
                status_code=400,
            )

        if not file.name.endswith(".xlsx"):
            return ApiResponse.error(
                message="Invalid file type. Only .xlsx files are supported.",
                status_code=400,
            )

        # ── Global fallback class/year ────────────────────────────
        # Applied to any student row that doesn't have its own
        global_class_id = request.data.get("class_id") or None
        if global_class_id:
            global_academic_year_id = AcademicYear.objects.filter(
                is_current=True, school=school
            ).first().id
        else:
            global_academic_year_id = None

        # ── Parse Excel ───────────────────────────────────────────
        try:
            students_data, parse_errors = parse_students_from_excel(file)
        except ValueError as e:
            return ApiResponse.error(message=str(e), status_code=400)

        if not students_data and parse_errors:
            return ApiResponse.error(
                message="All rows failed validation. No students were created.",
                data={
                    "summary": {
                        "total_submitted": len(parse_errors),
                        "created": 0,
                        "failed": len(parse_errors),
                        "parse_errors": parse_errors,
                    }
                },
                status_code=400,
            )

        # ── Plan limit check ──────────────────────────────────────
        # Reads PackageLimit first, matching check_limit() used by the
        # single-create path, and falls back to the display column.
        from subscriptions.services.packages import get_package_limit
        from subscriptions.utils import get_active_subscription
        subscription = get_active_subscription(school)
        plan = subscription.plan if subscription else None
        if plan is not None:
            max_students = get_package_limit(plan, "max_students")
            if max_students is None:
                max_students = plan.maximum_students
        else:
            max_students = None
        if max_students is not None:
            current_count = school.students.filter(
                status="active"
            ).count()
            remaining = max_students - current_count
            if len(students_data) > remaining:
                return ApiResponse.error(
                    message=(
                        f"This import would exceed your plan's student limit. "
                        f"You can add {remaining} more student(s). "
                        f"This file contains {len(students_data)} valid records."
                    ),
                    status_code=400,
                )

        # ── Create students ───────────────────────────────────────
        created = []
        failed = [*parse_errors]  # start with parse errors

        for student_data in students_data:
            row_num = student_data.pop("_row", None)

            # Apply global fallbacks if row doesn't have its own
            if not student_data.get("class_id"):
                student_data["class_id"] = global_class_id
            if not student_data.get("academic_year_id"):
                student_data["academic_year_id"] = global_academic_year_id

            try:
                with transaction.atomic():
                    student = self._create_student(
                        student_data=student_data,
                        school=school,
                    )
                    created.append({
                        "student_id": str(student.id),
                        "student_id_number": student.student_id,
                        "name": student.full_name,
                    })
            except Exception as e:
                failed.append({
                    "row": row_num,
                    "name": (
                        f"{student_data.get('first_name', '')} "
                        f"{student_data.get('last_name', '')}"
                    ).strip(),
                    "errors": [str(e)],
                })

        # ── Audit log ─────────────────────────────────────────────
        if created:
            log_action(
                action=AuditLog.Action.CREATE,
                resource="Student",
                description=(
                    f"Bulk Excel import: {len(created)} created, "
                    f"{len(failed)} failed"
                ),
                request=request,
                metadata={
                    "created_count": len(created),
                    "failed_count": len(failed),
                    "file_name": file.name,
                },
            )

        total_submitted = len(students_data) + len(parse_errors)

        return ApiResponse.success(
            data={
                "summary": {
                    "total_submitted": total_submitted,
                    "created": len(created),
                    "failed": len(failed),
                    "success_rate": (
                        f"{round((len(created) / total_submitted) * 100)}%"
                        if total_submitted > 0 else "0%"
                    ),
                },
                "created": created,
                "failed": failed,
            },
            message=(
                f"{len(created)} of {total_submitted} students "
                f"imported successfully."
                + (
                    f" {len(failed)} failed — check 'failed' for details."
                    if failed else ""
                )
            ),
        )

    @staticmethod
    def _create_student(student_data, school):
        from academics.models import AcademicYear, Class

        guardians_data = student_data.pop("guardians", [])
        class_id = student_data.pop("class_id", None)
        academic_year_id = student_data.pop("academic_year_id", None)

        student = Student.objects.create(
            school=school, **student_data
        )

        for guardian_data in guardians_data:
            Guardian.objects.create(
                student=student,
                school=school,
                **guardian_data,
            )

        if class_id and academic_year_id:
            try:
                klass = Class.objects.get(id=class_id, school=school)
                academic_year = AcademicYear.objects.get(
                    id=academic_year_id, school=school
                )
                Enrollment.objects.create(
                    school=school,
                    student=student,
                    klass=klass,
                    academic_year=academic_year,
                )
            except (Class.DoesNotExist, AcademicYear.DoesNotExist):
                pass

        return student

class ClassBulkStudentsView(APIView):
    """
    Bulk create students for a specific class from an Excel file.
    Each student is enrolled in the given class with one guardian.

    POST /api/v1/students/class-bulk/
        class_id (required) — UUID of the class to enroll in
        file (required) — .xlsx file
        photos (optional) — .zip file with student photos named by photo_filename column

    GET  /api/v1/students/class-bulk/ — downloads the template
    """
    permission_classes = [IsAdminOrTeacher]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        workbook = build_class_bulk_template_workbook()
        response = HttpResponse(
            content_type=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            )
        )
        response["Content-Disposition"] = (
            'attachment; filename="skuumate_class_bulk_template.xlsx"'
        )
        workbook.save(response)
        return response

    def post(self, request):
        school = request.user.school
        serializer = BulkStudentUploadSerializer(
            data=request.data, context={"school": school}
        )
        if not serializer.is_valid():
            return ApiResponse.error(
                message="Invalid data provided.",
                errors=serializer.errors,
                status_code=400,
            )

        try:
            result = ClassBulkImportService.run(
                school,
                class_id=serializer.validated_data["class_id"],
                file=request.FILES.get("file"),
                photos_file=request.FILES.get("photos"),
            )
        except serializers.ValidationError as exc:
            message = (
                exc.detail[0] if isinstance(exc.detail, list) else str(exc.detail)
            )
            return ApiResponse.error(message=message, status_code=400)

        if result.all_rows_failed_validation:
            return ApiResponse.error(
                message="All rows failed validation.",
                errors=result.all_failed_payload(),
                status_code=400,
            )

        if result.created:
            log_action(
                action=AuditLog.Action.CREATE,
                resource="Student",
                description=(
                    f"Class bulk import: {result.created_count} created in "
                    f"{result.class_name}, {result.failed_count} failed"
                ),
                request=request,
                metadata={
                    "created_count": result.created_count,
                    "failed_count": result.failed_count,
                    "class_id": result.class_id,
                    "class_name": result.class_name,
                    "academic_year": result.academic_year,
                    "file_name": result.file_name,
                    "photos_included": result.photos_included,
                },
            )

        return ApiResponse.success(
            data=result.success_payload(),
            message=result.status_message(),
        )


class StudentExcelTemplateView(APIView):
    """
    Returns a downloadable Excel template for bulk student import.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        import openpyxl
        from django.http import HttpResponse

        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = "Students"

        headers = [
            "first_name",
            "last_name",
            "other_names",
            "date_of_birth",
            "gender",
            "admission_date",
            "address",
            "previous_school",
            "class_id",
            "academic_year_id",
            "guardian_1_first_name",
            "guardian_1_last_name",
            "guardian_1_relationship",
            "guardian_1_phone",
            "guardian_1_email",
            "guardian_1_is_primary",
            "guardian_2_first_name",
            "guardian_2_last_name",
            "guardian_2_relationship",
            "guardian_2_phone",
            "guardian_2_email",
            "guardian_2_is_primary",
        ]

        # ── Style the header row ──────────────────────────────────
        from openpyxl.styles import Alignment, Font, PatternFill
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(
            start_color="2563EB",
            end_color="2563EB",
            fill_type="solid",
        )

        for col_num, header in enumerate(headers, start=1):
            cell = sheet.cell(row=1, column=col_num, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center")
            sheet.column_dimensions[
                cell.column_letter
            ].width = max(len(header) + 4, 16)

        # ── Add a sample row ──────────────────────────────────────
        sample = [
            "Ekow", "Mensah", "Kofi",
            "2010-05-14", "male", "2025-09-01",
            "123 Adum Street, Kumasi", "Good Shepherd Academy",
            "", "",   # class_id and academic_year_id left blank
            "Kwame", "Mensah", "father",
            "0244000001", "kwame@email.com", "true",
            "Akua", "Mensah", "mother",
            "0244000002", "", "false",
        ]

        for col_num, value in enumerate(sample, start=1):
            cell = sheet.cell(row=2, column=col_num, value=value)
            cell.alignment = Alignment(horizontal="left")

        # ── Add a notes sheet ─────────────────────────────────────
        notes_sheet = workbook.create_sheet(title="Notes")
        notes = [
            ["Field", "Required", "Format / Allowed Values"],
            ["first_name", "Yes", "Text"],
            ["last_name", "Yes", "Text"],
            ["other_names", "No", "Text"],
            ["date_of_birth", "Yes", "YYYY-MM-DD or DD/MM/YYYY"],
            ["gender", "Yes", "male / female / other"],
            ["admission_date", "Yes", "YYYY-MM-DD or DD/MM/YYYY"],
            ["address", "No", "Text"],
            ["previous_school", "No", "Text"],
            ["class_id", "No", "UUID from the system"],
            ["academic_year_id", "No", "UUID from the system"],
            ["guardian_X_first_name", "No", "Text"],
            ["guardian_X_last_name", "No", "Text"],
            ["guardian_X_relationship", "No", "father/mother/guardian/sibling/other"],
            ["guardian_X_phone", "No", "Phone number"],
            ["guardian_X_email", "No", "Email address"],
            ["guardian_X_is_primary", "No", "true / false"],
        ]

        notes_header_font = Font(bold=True)
        for row_index, row_data in enumerate(notes, start=1):
            for col_index, value in enumerate(row_data, start=1):
                cell = notes_sheet.cell(
                    row=row_index, column=col_index, value=value
                )
                if row_index == 1:
                    cell.font = notes_header_font
                notes_sheet.column_dimensions[
                    cell.column_letter
                ].width = 35

        # ── Return as downloadable file ───────────────────────────
        response = HttpResponse(
            content_type=(
                "application/vnd.openxmlformats-officedocument"
                ".spreadsheetml.sheet"
            )
        )
        response["Content-Disposition"] = (
            'attachment; filename="skuumate_students_template.xlsx"'
        )
        workbook.save(response)
        return response

class StudentListCreateView(TeacherScopedQuerysetMixin, AuditLogMixin, ExportMixin, generics.ListCreateAPIView):
    permission_classes = (school_permission(read="students.view", create="students.create"),)
    filter_backends = (DjangoFilterBackend, SearchFilter, OrderingFilter,)
    filterset_class = StudentFilter
    search_fields = (
        "first_name", "last_name",
        "other_names", "student_id",
    )
    ordering_fields = (
        "first_name", "last_name",
        "admission_date", "created_at",
    )
    ordering = ("last_name", "first_name")
    parser_classes = (MultiPartParser, FormParser, JSONParser)
    audit_resource = "Student"


    def get_serializer_class(self):
        if self.request.method == "POST":
            return StudentCreateSerializer
        return StudentListSerializer

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
            serializer = StudentListSerializer(page, many=True, context={"request": request})
            return self.get_paginated_response(serializer.data)
        serializer = StudentListSerializer(queryset, many=True, context={"request": request})
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
            data=StudentListSerializer(student).data,
            message="Student registered successfully.",
        )


class StudentDetailView(TeacherScopedQuerysetMixin, AuditLogMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [school_permission(read="students.view", edit="students.edit", delete="students.delete")]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    audit_resource = "Student"


    def get_serializer_class(self):
        if self.request.method in ["PATCH","PUT"]:
            return StudentUpdateSerializer
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
        serializer = StudentUpdateSerializer(
            instance, data=request.data, partial=True,
            context={"school": request.user.school, "request":request}
        )
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return ApiResponse.success(
            data=StudentListSerializer(serializer.instance, context = {"request":request}).data,
            message="Student updated successfully.",
        )


class StudentExportView(TeacherScopedQuerysetMixin, ExportMixin, generics.ListAPIView):
    permission_classes = [
        school_permission(read="students.export"),
        HasExportAccess,
    ]
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

class GuardianListCreateView(TeacherScopedQuerysetMixin, generics.ListCreateAPIView):
    permission_classes = [school_permission(read="students.view", write="students.edit")]
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


class GuardianDetailView(TeacherScopedQuerysetMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [school_permission(read="students.view", write="students.edit")]
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
    permission_classes = [school_permission(create="students.create", delete="students.edit")]

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


class StudentEnrollmentHistoryView(TeacherScopedQuerysetMixin, generics.ListAPIView):
    """Full enrollment history for a student."""
    permission_classes = [school_permission(read="students.view")]
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


class ClassStudentsListView(TeacherScopedQuerysetMixin, generics.ListAPIView):
    '''List of students currently enrolled in a specific class.'''
    permission_classes = (school_permission(read="students.view"),)
    serializer_class = StudentMinimalSerializer

    def get_queryset(self):
        return Student.objects.filter(
            school=self.request.user.school,
            enrollments__klass_id=self.kwargs["class_id"],
            enrollments__is_active=True,
        ).distinct().prefetch_related("guardians","enrollments__klass", "enrollments__academic_year")

    
    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()

        # Skip pagination when no_pagination=true
        if request.query_params.get("no_pagination", "").lower() == "true":
            serializer = self.get_serializer(queryset, many=True)
            return ApiResponse.success(data=serializer.data)

        page = self.paginate_queryset(queryset)

        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return ApiResponse.success(data=serializer.data)


# ─── Student ID cards ─────────────────────────────────────────────

def _resolve_term(school, term_id):
    if not term_id:
        return None
    return Term.objects.filter(pk=term_id, school=school).first()


def _scoped_students(request):
    """Base queryset for card generation, honouring the teacher class scope."""
    qs = (
        Student.objects.filter(school=request.user.school)
        .select_related("school")
        .prefetch_related(
            "guardians", "enrollments__klass", "enrollments__academic_year"
        )
    )
    if needs_teacher_scope(request.user):
        qs = qs.filter(
            enrollments__klass_id__in=assigned_class_ids(request.user),
            enrollments__is_active=True,
        )
    return qs.distinct()


def _pdf_response(buffer, filename):
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


class StudentIDCardView(APIView):
    """GET — one student's ID card as a print-ready PDF (front + back pages)."""

    permission_classes = (school_permission(read="students.view"), HasIdCardAccess)

    def get(self, request, pk):
        school = request.user.school
        student = get_object_or_404(Student, pk=pk, school=school)

        term_id = request.query_params.get("term_id")
        term = _resolve_term(school, term_id) if term_id else None
        if term_id and term is None:
            return ApiResponse.error(message="Term not found.", status_code=404)

        if needs_teacher_scope(request.user) and not student.enrollments.filter(
            klass_id__in=assigned_class_ids(request.user, term), is_active=True
        ).exists():
            from rest_framework.exceptions import NotFound

            raise NotFound()

        buffer = build_student_card_pdf(student, school, term)
        log_action(
            action=AuditLog.Action.OTHER,
            resource="StudentIDCard",
            resource_id=str(student.pk),
            description=(
                f"Generated ID card for {student.full_name} ({student.student_id})"
            ),
            request=request,
        )
        return _pdf_response(buffer, f"id_card_{student.student_id}.pdf")


class StudentIDCardsBulkView(APIView):
    """POST — bulk ID cards (class / explicit selection / all active) as one PDF.

    Body (all optional):
        student_ids: [uuid, ...]   explicit selection
        class_id: uuid             every active student in a class
        term_id: uuid              term whose year/class the cards should show
    A student cap keeps a single request from building an unbounded document.
    """

    permission_classes = (school_permission(create="students.view"), HasIdCardAccess)

    def post(self, request):
        school = request.user.school
        serializer = IDCardRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        term_id = data.get("term_id")
        term = _resolve_term(school, str(term_id)) if term_id else None
        if term_id and term is None:
            return ApiResponse.error(message="Term not found.", status_code=404)

        students = _scoped_students(request)

        student_ids = data.get("student_ids") or []
        class_id = data.get("class_id")

        if student_ids:
            students = students.filter(pk__in=student_ids)
        if class_id:
            students = students.filter(
                enrollments__klass_id=class_id, enrollments__is_active=True
            )
            if term is not None:
                students = students.filter(
                    enrollments__academic_year_id=term.academic_year_id
                )
            else:
                students = students.filter(enrollments__academic_year__is_current=True)

        students = students.order_by("last_name", "first_name").distinct()
        count = students.count()

        if count == 0:
            return ApiResponse.error(
                message="No students matched the request.", status_code=400
            )
        if count > MAX_ID_CARD_BATCH:
            return ApiResponse.error(
                message=(
                    f"{count} students matched; the maximum per request is "
                    f"{MAX_ID_CARD_BATCH}. Filter by class or select students."
                ),
                status_code=400,
            )

        buffer = build_students_cards_pdf(list(students), school, term)
        log_action(
            action=AuditLog.Action.OTHER,
            resource="StudentIDCard",
            resource_id=str(school.pk),
            description=f"Generated {count} ID card(s) for {school.name}",
            metadata={
                "student_count": count,
                "class_id": str(class_id) if class_id else None,
            },
            request=request,
        )
        return _pdf_response(buffer, "student_id_cards.pdf")


class StudentVerifyView(APIView):
    """Public — verify a ``student_id`` (the payload encoded in a card QR code).

    No authentication: anyone scanning a card can confirm the holder. The
    response is a minimal, non-sensitive projection of the student.
    """

    permission_classes = (AllowAny,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "student_verify"

    def get(self, request, student_id):
        student = (
            Student.objects.select_related("school")
            .filter(student_id__iexact=str(student_id).strip())
            .first()
        )
        if student is None:
            return ApiResponse.error(
                message="No student found for this ID.", status_code=404
            )
        serializer = StudentVerificationSerializer(
            student, context={"request": request}
        )
        return ApiResponse.success(
            data=serializer.data, message="Student ID verified."
        )


# ─── Promotion ────────────────────────────────────────────────────

def _promotion_students(request, data):
    """Scoped student set for a promotion (teacher scope + source filters)."""
    school = request.user.school
    students = Student.objects.filter(school=school)

    if needs_teacher_scope(request.user):
        allowed = assigned_class_ids(request.user)
        source_class = data.get("from_class")
        if source_class is not None and source_class.pk not in allowed:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("You are not assigned to this class.")
        students = students.filter(
            enrollments__klass_id__in=allowed,
            enrollments__is_active=True,
        )

    source_class = data.get("from_class")
    if source_class is not None:
        students = students.filter(
            enrollments__klass=source_class, enrollments__is_active=True
        )
        source_year = data.get("from_academic_year")
        if source_year is not None:
            students = students.filter(enrollments__academic_year=source_year)
        else:
            students = students.filter(enrollments__academic_year__is_current=True)

    student_ids = data.get("student_ids") or []
    if student_ids:
        students = students.filter(pk__in=student_ids)

    return list(students.distinct())


class PromotionBatchListCreateView(
    TeacherScopedQuerysetMixin, generics.ListCreateAPIView
):
    """List promotion history and create a single/bulk promotion run."""

    permission_classes = (
        school_permission(read="students.view", create="students.edit"),
    )
    serializer_class = PromotionBatchSerializer

    def get_queryset(self):
        return (
            PromotionBatch.objects.filter(school=self.request.user.school)
            .select_related(
                "from_class",
                "from_academic_year",
                "to_class",
                "to_academic_year",
                "to_term",
                "promoted_by",
            )
            .prefetch_related("items__student")
        )

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page or queryset, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return ApiResponse.success(data=serializer.data)

    def create(self, request, *args, **kwargs):
        school = request.user.school
        serializer = PromotionRequestSerializer(
            data=request.data, context={"school": school, "request": request}
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        students = _promotion_students(request, data)
        if not students:
            return ApiResponse.error(
                message="No students matched the request.", status_code=400
            )

        batch = PromotionService.promote(
            school=school,
            students=students,
            to_class=data["to_class"],
            to_academic_year=data["to_academic_year"],
            to_term=data["to_term"],
            from_class=data["from_class"],
            from_academic_year=data["from_academic_year"],
            promoted_by=request.user,
            notes=data.get("notes", ""),
        )

        counts = batch.outcome_counts()
        log_action(
            action=AuditLog.Action.CREATE,
            resource="PromotionBatch",
            resource_id=str(batch.pk),
            description=(
                f"Promoted {counts['promoted']} student(s) to "
                f"{batch.to_class.name} ({batch.to_academic_year.name}); "
                f"{counts['skipped']} skipped."
            ),
            metadata={
                "to_class_id": str(batch.to_class_id),
                "to_academic_year_id": str(batch.to_academic_year_id),
                "promoted": counts["promoted"],
                "skipped": counts["skipped"],
            },
            request=request,
        )

        return ApiResponse.created(
            data=PromotionBatchSerializer(batch, context={"request": request}).data,
            message=(
                f"{counts['promoted']} student(s) promoted; "
                f"{counts['skipped']} skipped."
            ),
        )


class PromotionBatchDetailView(
    TeacherScopedQuerysetMixin, generics.RetrieveAPIView
):
    """Retrieve a single promotion batch with its per-student outcomes."""

    permission_classes = (school_permission(read="students.view"),)
    serializer_class = PromotionBatchSerializer

    def get_queryset(self):
        return (
            PromotionBatch.objects.filter(school=self.request.user.school)
            .select_related(
                "from_class",
                "from_academic_year",
                "to_class",
                "to_academic_year",
                "to_term",
                "promoted_by",
            )
            .prefetch_related("items__student")
        )

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return ApiResponse.success(data=serializer.data)


class PromotionBatchReverseView(APIView):
    """Undo a promotion batch by removing the enrollments it created."""

    permission_classes = (school_permission(create="students.edit"),)

    def post(self, request, pk):
        batch = get_object_or_404(
            PromotionBatch, pk=pk, school=request.user.school
        )

        if needs_teacher_scope(request.user) and batch.promoted_by_id != request.user.id:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("You can only reverse promotions you created.")

        if batch.status == PromotionBatch.Status.REVERSED:
            return ApiResponse.error(
                message="This promotion has already been reversed.",
                status_code=400,
            )

        PromotionService.reverse(batch)

        log_action(
            action=AuditLog.Action.UPDATE,
            resource="PromotionBatch",
            resource_id=str(batch.pk),
            description=(
                f"Reversed promotion to {batch.to_class.name} "
                f"({batch.to_academic_year.name})."
            ),
            request=request,
        )

        return ApiResponse.success(
            data=PromotionBatchSerializer(batch, context={"request": request}).data,
            message="Promotion reversed; the enrollments it created were removed.",
        )

