from django.db import transaction
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, status
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.views import APIView

from academics.models import Class, GradingSystem, Term
from core.mixins import AuditLogMixin, ExportMixin
from core.permissions import IsAdmin, IsAdminOrReadOnly, IsAdminOrTeacher, IsTeacher
from core.responses import ApiResponse
from exams.filters import AssessmentTypeFilter
from exams.models import (
    AssessmentType,
    ReportScheme,
    StudentMark,
    StudentReport,
    StudentReportSubjectScore,
)
from exams.serializers import (
    AssessmentTypeSerializer,
    GenerateReportResponseSerializer,
    HeadTeacherRemarksSerializer,
    ReportSchemeSerializer,
    ReportTeacherRemarksSerializer,
    StudentMarkCreationSerializer,
    StudentMarkSerializer,
    StudentReportDetailSerializer,
    StudentReportGeneratorSerializer,
    StudentReportSerializer,
    SubjectScoreSerializer,
)
from exams.services.report_generation_service import ReportGenerationService
from students.models import Enrollment


# from exams.services import generate_class_report
class AssessmentTypeListCreateView(AuditLogMixin, ExportMixin, generics.ListCreateAPIView):
    permission_classes = [IsAdminOrTeacher]
    serializer_class = AssessmentTypeSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = AssessmentTypeFilter
    search_fields = ["name"]
    ordering_fields = ["created_at"]
    ordering = ["name"]
    audit_resource = "AssessmentType"

    def get_queryset(self):
        return AssessmentType.objects.filter(school = self.request.user.school)

    def get_audit_description(self, instance):
        return f"Assessment type {instance.name} created."

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return ApiResponse.success(data = serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data = request.data)
        serializer.is_valid(raise_exception =  True)
        assessment_type = self.perform_create(serializer)
        return ApiResponse.created(
            message = "Assessment type created successfully",
            data = self.get_serializer(assessment_type).data
        )

class AssementTypeDetailView(AuditLogMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdmin]
    serializer_class = AssessmentTypeSerializer
    audit_resource = "AssessmentType"

    def get_queryset(self):
        return AssessmentType.objects.filter(school = self.request.user.school)

    def retrieve(self, reqeust, *args, **kwargs):
        instance = self.get_object()
        return ApiResponse.success(data = self.get_serializer(instance).data)


class ReportSchemeListCreateView(AuditLogMixin, ExportMixin, generics.ListCreateAPIView):
    permission_classes = [IsAdminOrReadOnly]
    serializer_class = ReportSchemeSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ["name"]
    ordering_fields = ["created_at"]
    ordering = ["name"]
    audit_resource = "ReportScheme"

    def get_queryset(self):
        return ReportScheme.objects.filter(school = self.request.user.school)

    def get_audit_description(self, instance):
        return f'Report scheme {instance.name} created'


    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return ApiResponse.success(data = serializer.data)

class ReportSchemeDetailView(AuditLogMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdmin]
    serializer_class = ReportSchemeSerializer
    audit_resource = "ReportScheme"

    def get_queryset(self):
        return ReportScheme.objects.filter(school = self.request.user.school)

class StudentMarksListView(generics.ListAPIView):
    serializer_class = StudentMarkSerializer
    pagination_class = None

    def get_queryset(self):
        school = self.request.user.school

        assessment_id = self.request.query_params.get("assessment_id")
        subject_id = self.request.query_params.get("subject_id")

        queryset = StudentMark.objects.filter(
            school=school,
            student_class_id=self.kwargs["class_id"],
            term__is_current=True,
        ).select_related("student")

        if assessment_id:
            queryset = queryset.filter(assessment_id=assessment_id)

        if subject_id:
            queryset = queryset.filter(subject_id=subject_id)

        return queryset

    def list(self, request, *args, **kwargs):
        school = request.user.school
        class_id = self.kwargs["class_id"]

        assessment_id = request.query_params.get("assessment_id")
        subject_id = request.query_params.get("subject_id")

        if not assessment_id:
            return ApiResponse.error(
                message="assessment_id is required."
            )

        if not subject_id:
            return ApiResponse.error(
                message="subject_id is required."
            )

        current_term = (
            Term.objects.select_related("academic_year")
            .filter(
                school=school,
                is_current=True,
            )
            .first()
        )

        if not current_term:
            return ApiResponse.error(
                message="No current academic term set for this school."
            )

        enrolled_students = (
            Enrollment.objects.filter(
                klass_id=class_id,
                academic_year=current_term.academic_year,
                is_active=True,
            )
            .select_related("student")
            .order_by("student__last_name", "student__first_name")
        )

        existing_marks = {
            mark.student_id: mark
            for mark in self.get_queryset()
        }

        registry_data = []

        for enrollment in enrolled_students:
            student = enrollment.student
            mark = existing_marks.get(student.id)

            registry_data.append(
                {
                    "id": student.id,
                    "name": student.full_name,
                    "student_id": student.student_id,
                    "score": mark.score if mark else "",
                    "teacher_remarks": (
                        mark.teacher_remarks if mark else ""
                    ),
                }
            )

        return ApiResponse.success(data=registry_data)

class StudentMarkBulkView(AuditLogMixin, generics.CreateAPIView):
    serializer_class = StudentMarkCreationSerializer
    audit_resource = "StudentMark"

    def get_queryset(self):
        return StudentMark.objects.filter(
            school=self.request.user.school
        ).select_related('student')

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        school = request.user.school
        current_term = Term.objects.select_related("academic_year").filter(school=school, is_current=True).first()

        if not current_term:
            return ApiResponse.error(message="Cannot save marks: No active term found.")

        marks_data = request.data['marks']
        results = []

        for item in marks_data:

            instance = StudentMark.objects.filter(
                student_id=item.get('student'),
                assessment_id=request.data['assessment'],
                subject_id=request.data['subject'],
                term=current_term
            ).first()
            print(instance)

            # Prepare data for the serializer
            data = {
                "student": item.get('student'),
                "score": item.get('score') if item.get('score') != "" else None,
                "assessment": request.data['assessment'],
                "subject": request.data['subject'],
                "student_class": request.data['student_class'],
                "term": current_term.id,
                "academic_year": current_term.academic_year.id,
                "teacher_remarks": item.get('teacher_remarks', ""),
                "teacher": getattr(request.user, 'staff_profile', None).id if hasattr(request.user, 'staff_profile') else None
            }

            serializer = self.get_serializer(instance, data=data, partial=True, context = {"request":request}) if instance else self.get_serializer(data=data, context = {"request":request})

            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)
            results.append(serializer.data)

        return ApiResponse.success(message="Marks updated successfully", data=results)

class ClassReportGenerationValidityView(APIView):
    permission_classes = [IsAdminOrTeacher]
    def get(self, request, class_id):
        school = request.user.school
        current_term = Term.objects.filter(school=school, is_current=True).first()

        try:
            school_class = Class.objects.get(id=class_id, school=school)
        except Class.DoesNotExist:
            return ApiResponse.error(message="Class not found.", status=404)

        # check if the class is assigned a report scheme for the current term
        scheme = school_class.report_schemes.filter(term = current_term).first()

        grading_scheme = GradingSystem.objects.filter(school=school, is_default=True).first()


        context = {
            "scheme": scheme.id,
            "grading_scheme_name": grading_scheme.name if grading_scheme else None,
            "sba_scaling": scheme.sba_scaling if scheme else None,
            "exam_scaling": scheme.exam_scaling if scheme else None,
            "subjects_count": school_class.class_subjects.count(),
            "grading_scheme": grading_scheme.id if grading_scheme else None,
            "term": current_term.get_name_display(),
            "academic_year": current_term.academic_year.name
        }

        if not current_term:
            return ApiResponse.error(message="No active term found for this school.", status_code=status.HTTP_400_BAD_REQUEST)
        return ApiResponse.success(data=context)

class GenerateClassReportView(APIView):
    permission_classes = [IsAdminOrTeacher]
    def post(self, request):
        serializer = StudentReportGeneratorSerializer(data = request.data)
        serializer.is_valid(raise_exception = True)
        data = serializer.validated_data

        school = request.user.school

        klass = get_object_or_404(
            Class, id=data["class_id"], school=school, is_active=True
        )

        report_scheme = get_object_or_404(
            ReportScheme.objects.prefetch_related("sba_components"),
            id=data["report_scheme_id"],
            school=school,
        )

        grading_system = get_object_or_404(
            GradingSystem,
            id=data["grading_system_id"],
            school=school,
        )

        term = (
            Term.objects.select_related("academic_year")
            .filter(school=school, is_current=True)
            .first()
        )

        if not term:
            return ApiResponse.error(
                message = "There is no current active term."
            )

        result = ReportGenerationService.generate(
            school=school,
            klass=klass,
            report_scheme=report_scheme,
            grading_system=grading_system,
            term=term,
        )
        return ApiResponse.success(message = "Reports generated", data=result)

class StudentReportListView(generics.ListAPIView):
    serializer_class = StudentReportSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ["student__full_name", "student__student_id"]
    ordering_fields = ["created_at"]
    ordering = ["-created_at"]

    def get_queryset(self):
        return StudentReport.objects.filter(
            school=self.request.user.school,
            term = self.kwargs['term_id'],
            student_class_id = self.kwargs['class_id']
        ).select_related('student', 'term', 'academic_year')

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return ApiResponse.success(data = serializer.data)

class StudentReportDetailView(AuditLogMixin, generics.RetrieveAPIView):
    serializer_class = StudentReportDetailSerializer

    def get_queryset(self):
        return StudentReport.objects.filter(
            school=self.request.user.school
        ).select_related('student', 'term', 'academic_year', 'school'
        ).prefetch_related('subject_scores__student_report')


class StudentReportSubjectScoreListView(generics.ListAPIView):
    permission_classes = [IsAdminOrTeacher]
    serializer_class = SubjectScoreSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ["student__first_name", "student__last_name"]
    ordering_fields = ["student__first_name"]
    ordering = ["-student__first_name"]

    def get_queryset(self):
        return StudentReportSubjectScore.objects.filter(
            subject_id = self.kwargs['subject_id'],
            student_report__term_id = self.kwargs['term_id'],
            student_report__student_class_id = self.kwargs['class_id']
        ).select_related("student")

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return ApiResponse.success(data = serializer.data)


class StudentReportTeacherRemarksView(AuditLogMixin, generics.UpdateAPIView):
    permission_classes = [IsAdminOrTeacher]
    serializer_class = ReportTeacherRemarksSerializer
    audit_resource = "StudentReport"

    def get_queryset(self):
        return StudentReport.objects.filter(school = self.request.user.school)

    def get_audit_description(self, instance):
        return "Student report's teacher remarks has been updated"

    def update(self, request, *args, **kwargs):
        instance = self.get_object()

        data = request.data.copy()
        data["teacher"] = request.user.full_name

        serializer = self.get_serializer(data = data, instance = instance, partial=True)
        serializer.is_valid(raise_exception = True)
        self.perform_update(serializer)
        return ApiResponse.success("Teacher remarks updated")


class StudentReportHeadteacherRemarksView(AuditLogMixin, generics.UpdateAPIView):
    permission_classes = [IsAdminOrTeacher]
    serializer_class = HeadTeacherRemarksSerializer
    audit_resource = "StudentReport"

    def get_queryset(self):
        return StudentReport.objects.filter(school = self.request.user.school)

    def get_audit_description(self, instance):
        return "Student report's headteacher remarks has been updated"

    def update(self, request, *args, **kwargs):
        instance = self.get_object()

        data = request.data.copy()
        data["headteacher"] = request.user.full_name

        serializer = self.get_serializer(data = data, instance = instance, partial=True)
        serializer.is_valid(raise_exception = True)
        self.perform_update(serializer)
        return ApiResponse.success("Head Teacher remarks updated")

class PublishStudentReportsView(APIView):
    permission_classes = [IsAdmin]
    def post(self, request):
        reports = request.data.get("reports",[])

        StudentReport.objects.filter(
            id__in=reports, school=request.user.school, status=StudentReport.ReportStatus.READY
        ).update(
            status=StudentReport.ReportStatus.PUBLISHED
        )

        return ApiResponse.success("Reports published")
