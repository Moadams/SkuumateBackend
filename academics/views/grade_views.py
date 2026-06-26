from django.db import transaction
from academics.models import GradeScale, GradingSystem
from academics.serializers import GradeScaleSerializer, GradingSystemListSerializer, GradingSystemSerializer, GradingSystemUpdateSerializer
from core.mixins import AuditLogMixin
from rest_framework import generics

from core.permissions import IsAdmin
from core.responses import ApiResponse
from rest_framework.filters import SearchFilter, OrderingFilter

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
    ordering_fields = ["name", "created_at"]
    audit_resource = "GradingSystem"

    def get_serializer_class(self):
        if self.request.method == "POST":
            return GradingSystemSerializer
        return GradingSystemListSerializer

    def get_queryset(self):
        return (
            GradingSystem.objects
            .filter(school=self.request.user.school)
            .prefetch_related("grade_scales")
        )

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return ApiResponse.success(data=serializer.data)

    def get_audit_description(self, instance):
        return f"Grading system '{instance.name}' was created by {self.request.user.full_name}."

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(
            data=request.data,
            context={"request":request,"school": request.user.school},
        )
        serializer.is_valid(raise_exception=True)
        system = self.perform_create(serializer)

        return ApiResponse.created(
            data=GradingSystemSerializer(system).data,
            message=f"Grading system '{system.name}' created successfully.",
        )

class GradingSystemDetailView(AuditLogMixin, generics.RetrieveUpdateDestroyAPIView):
    """
    Retrieve, update or delete a grading system.
    """
    permission_classes = [IsAdmin]
    audit_resource = "GradingSystem"

    def get_serializer_class(self):
        if self.request.method in ["PUT", "PATCH"]:
            return GradingSystemUpdateSerializer
        return GradingSystemSerializer

    def get_audit_description(self, instance):
        if self.request.method in ["PUT", "PATCH"]:
            return f"Grading system '{instance.name}' was updated by {self.request.user.full_name}."
        elif self.request.method == "DELETE":
            return f"Grading system '{instance.name}' was deleted by {self.request.user.full_name}."
        
        return super().get_audit_description(instance)

    def get_queryset(self):
        return GradingSystem.objects.filter(school=self.request.user.school).prefetch_related("grade_scales")
    
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial, context={"request":request,"school": request.user.school})
        serializer.is_valid(raise_exception=True)
        system = self.perform_update(serializer)

        return ApiResponse.success(
            data=GradingSystemSerializer(system).data,
            message=f"Grading system '{system.name}' updated successfully.",
        )
    
class GradingScaleCreateListView(AuditLogMixin, generics.ListCreateAPIView):
    permission_classes = [IsAdmin]
    serializer_class = GradeScaleSerializer
    audit_resource = "GradeScale"

    def get_queryset(self):
        grading_system_id = self.kwargs.get("grading_system_id")
        return GradeScale.objects.filter(grading_system_id=grading_system_id, school=self.request.user.school)
    
    def get_audit_description(self, instance):
        return f"Grade scale '{instance.grade}' for grading system '{instance.grading_system.name}' was created by {self.request.user.full_name}."

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        grading_system_id = self.kwargs.get("grading_system_id")
        grading_system = generics.get_object_or_404(GradingSystem, id=grading_system_id, school=request.user.school)
        data = request.data.copy()
        data["grading_system"] = grading_system.id
        serializer = self.get_serializer(data=data, context={"request": request, "school": request.user.school})
        serializer.is_valid(raise_exception=True)
        grade_scale = self.perform_create(serializer)

        return ApiResponse.created(
            data=GradeScaleSerializer(grade_scale).data,
            message=f"Grade scale '{grade_scale.grade}' created successfully for grading system '{grading_system.name}'."
        )
    

class GradeScaleUpdateDestroyView(AuditLogMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdmin]
    serializer_class = GradeScaleSerializer
    audit_resource = "GradeScale"

    def get_queryset(self):
        return GradeScale.objects.filter(school = self.request.user.school)

    def get_audit_description(self, instance):
        if self.request.method in ["PUT", "PATCH"]:
            return f"Grade scale '{instance.grade} has been updated by {self.request.user.full_name}"
        return f"Grade scale '{instance.grade}' has been deleted by {self.request.user.full_name}"
    