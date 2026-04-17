from core.models import AuditLog
from core.responses import ApiResponse
from core.utils import log_action
from exams.filters import AssessmentTypeFilter
from exams.models import AssessmentType
from rest_framework import generics
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from core.permissions import IsAdmin
from exams.serializers import AssessmentTypeSerializer
from core.mixins import ExportMixin, AuditLogMixin

class AssessmentTypeListCreateView(AuditLogMixin, ExportMixin, generics.ListCreateAPIView):
    permission_classes = [IsAdmin]
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