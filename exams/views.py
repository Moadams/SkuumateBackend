from academics.models import Term
from core.models import AuditLog
from core.responses import ApiResponse
from core.utils import log_action
from exams.filters import AssessmentTypeFilter
from exams.models import AssessmentType, ReportScheme, StudentMark
from rest_framework import generics, viewsets, filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from core.permissions import IsAdmin, IsAdminOrTeacher
from exams.serializers import AssessmentTypeSerializer, ReportSchemeSerializer, StudentMarkSerializer
from core.mixins import ExportMixin, AuditLogMixin
from django.db import transaction

from students.models import Enrollment

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
    
    def perform_create(self, serializer):
        super().perform_create(serializer, school = self.request.user.school)
    
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
        self.perform_create(serializer)
        return ApiResponse.created(
            message = "Assessment type created successfully"
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
    
    def update(self, request, *args, **kwargs):
        kwargs['partial'] = True
        instance = self.get_object()
        serializer = self.get_serializer(instance, data = request.data, partial = True)
        serializer.is_valid(raise_exception = True)
        self.perform_update(serializer)
        return ApiResponse.success(
            message = "Assessment type updated successfully"
        )
    
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return ApiResponse.success(message = "Assessment type deleted successfully")
    
class ReportSchemeListCreateView(AuditLogMixin, ExportMixin, generics.ListCreateAPIView):
    permission_classes = [IsAdmin]
    serializer_class = ReportSchemeSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ["name"]
    ordering_fields = ["created_at"]
    ordering = ["name"]
    audit_resource = "ReportScheme"

    def get_queryset(self):
        try:
            current_term = Term.objects.get(school = self.request.user.school, is_current = True)
            return ReportScheme.objects.filter(term = current_term, school = self.request.user.school)
        except Term.DoesNotExist:
            return ReportScheme.objects.none()
        
    def perform_create(self, serializer):
        super().perform_create(serializer, school = self.request.user.school)

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

            
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data = request.data)
        serializer.is_valid(raise_exception = True)
        self.perform_create(serializer)
        return ApiResponse.created(
            message = "Report scheme created"
        )

class ReportSchemeDetailView(AuditLogMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdmin]
    serializer_class = ReportSchemeSerializer
    audit_resource = "ReportScheme"

    def get_queryset(self):
        return ReportScheme.objects.filter(school = self.request.user.school)
    
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        return ApiResponse.success(data = self.get_serializer(instance).data)
    
    def update(self, request, *args, **kwargs):
        kwargs['partial'] = True
        instance = self.get_object()
        serializer = self.get_serializer(instance, data = request.data, partial = True)
        serializer.is_valid(raise_exception = True)
        self.perform_update(serializer)
        return ApiResponse.success(
            message = "Report scheme updated successfully"
        )
    
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return ApiResponse.success(
            message = "Report Scheme deleted"
        )
    

class StudentMarkBulkView(generics.ListCreateAPIView):
    serializer_class = StudentMarkSerializer
    pagination_class = None 

    def get_queryset(self):
        return StudentMark.objects.filter(
            school=self.request.user.school,
            student_class_id=self.kwargs['class_id'],
            assessment_id=self.kwargs['assessment_id'],
            subject_id=self.kwargs['subject_id'],
            term__is_current=True
        ).select_related('student')

    def list(self, request, *args, **kwargs):
        school = request.user.school
        class_id = self.kwargs['class_id']
        
        # 1. Identify the current Academic Year and Term
        current_term = Term.objects.filter(school=school, is_current=True).first()
        if not current_term:
            return ApiResponse.error(message="No current academic term set for this school.", status=400)

        # 2. Get all students ENROLLED in this class for the current academic year
        enrolled_students = Enrollment.objects.filter(
            klass_id=class_id,
            academic_year=current_term.academic_year,
            is_active=True
        ).select_related('student')

        # 3. Get existing marks for these students
        existing_marks = {
            mark.student_id: mark 
            for mark in self.get_queryset()
        }

        # 4. Build the registry for the React table
        registry_data = []
        for enrollment in enrolled_students:
            student = enrollment.student
            mark = existing_marks.get(student.id)
            
            registry_data.append({
                "id": student.id, 
                "name": student.full_name,
                "student_id": student.student_id,
                "score": mark.score if mark else "",
                "teacher_remarks": mark.teacher_remarks if mark else ""
            })

        return ApiResponse.success(data=registry_data)

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        school = request.user.school
        current_term = Term.objects.filter(school=school, is_current=True).first()
        
        if not current_term:
            return ApiResponse.error(message="Cannot save marks: No active term found.")

        marks_data = request.data['marks']
        results = []

        for item in marks_data:
            
            instance = StudentMark.objects.filter(
                student_id=item.get('id'),
                assessment_id=self.kwargs['assessment_id'],
                subject_id=self.kwargs['subject_id'],
                term=current_term
            ).first()

            # Prepare data for the serializer
            data = {
                "student": item.get('id'),
                "score": item.get('score') if item.get('score') != "" else None,
                "assessment": self.kwargs['assessment_id'],
                "subject": self.kwargs['subject_id'],
                "student_class": self.kwargs['class_id'],
                "term": current_term.id,
                "academic_year": current_term.academic_year.id,
                "teacher_remarks": item.get('teacher_remarks', ""),
                "teacher": getattr(request.user, 'staff_profile', None).id if hasattr(request.user, 'staff_profile') else None
            }

            serializer = self.get_serializer(instance, data=data, partial=True) if instance else self.get_serializer(data=data)
            
            serializer.is_valid(raise_exception=True)
            serializer.save(school=school, teacher=getattr(request.user, 'staff_profile', None))
            results.append(serializer.data)

        return ApiResponse.success(message="Marks updated successfully")