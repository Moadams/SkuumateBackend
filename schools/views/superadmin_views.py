from django.db.models import Count, Q
from django.db import transaction

# filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from core.models import AuditLog
from core.utils import log_action
from schools.filters import SchoolFilter

from rest_framework.views import APIView
from rest_framework import generics

# Core funtions
from core.mixins import AuditLogMixin, ExportMixin
from core.permissions import IsSuperAdmin
from core.responses import ApiResponse

from schools.models import School
from schools.serializers.serializers import SchoolListSerializer, SchoolSerializer
from schools.serializers.superadmin_serializers import SchoolCreateSerializer, SchoolDetailSerializer, SchoolUpdateSerializer

class SchoolListCreateView(AuditLogMixin, ExportMixin, generics.ListCreateAPIView):
    """
    Superadmin only — paginated, filtered, searchable list of all schools.
    Matches the Schools management page on the frontend.
    """
    permission_classes = [IsSuperAdmin]
    serializer_class = SchoolListSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = SchoolFilter
    search_fields = ["name", "email", "city", "country"]
    ordering_fields = ["name", "created_at", "city"]
    ordering = ["-created_at"]

    # Auditing
    audit_action = AuditLog.Action.CREATE
    audit_resource = "School"

    def get_queryset(self):
        return School.objects.all().order_by("-created_at")

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        queryset = self.filter_queryset(self.get_queryset())
        school_ids = queryset.values_list("id", flat=True)

        from subscriptions.models import Subscription

        # SQLite-compatible: fetch all, deduplicate in Python
        subscriptions = (
            Subscription.objects
            .filter(school_id__in=school_ids)
            .select_related("plan")
            .order_by("school_id", "-start_date")
        )

        # Keep only the latest subscription per school
        seen = set()
        sub_map = {}
        for sub in subscriptions:
            sid = str(sub.school_id)
            if sid not in seen:
                seen.add(sid)
                sub_map[sid] = sub

        ctx["subscriptions"] = sub_map
        return ctx

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return ApiResponse.success(data=serializer.data)

    def get_audit_description(self, instance):
        return f"Created school {instance.name}"

    def create(self, request, *args, **kwargs):
        serializer = SchoolCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        
        return ApiResponse.created(
            data=serializer.data,
            message="School created successfully."
        )

class SuperSchoolDetailView(APIView):
    permission_classes = [IsSuperAdmin]

    def get(self, request, school_id=None):    
        # Fetch specific school details
        try:
            school = School.objects.annotate(
                total_users=Count('users', distinct=True),
                total_active_users=Count('users', filter=Q(users__is_active=True), distinct=True),
                total_students=Count('students', distinct=True),
                total_staff=Count('staff_profiles', distinct=True)
            ).get(id=school_id)
            serializer = SchoolDetailSerializer(school)
            return ApiResponse.success(data = serializer.data)
        except School.DoesNotExist:
            return ApiResponse.error(message="School not found", status_code=404)
    
    def patch(self, request, school_id=None):
        try:
            school = School.objects.get(id=school_id)
            serializer = SchoolUpdateSerializer(school, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            log_action(
                action=AuditLog.Action.UPDATE,
                resource="School",
                resource_id=str(school_id),
                description=f"Updated school {school.name}",
                actor=request.user,
                metadata=serializer.data,
                request=request,
            )
            return ApiResponse.success(data=serializer.data, message="School updated successfully.")
        except School.DoesNotExist:
            return ApiResponse.error(message="School not found", status_code=404)

    @transaction.atomic
    def delete(self, request, school_id=None):
        try:
            school = School.objects.get(id=school_id)
            metadata = SchoolSerializer(school).data
            school.delete()
            log_action(
                action=AuditLog.Action.DELETE,
                resource="School",
                resource_id=str(school_id),
                description=f"Deleted school {school.name}",
                actor=request.user,
                metadata=metadata,
                request=request,
            )
            
            return ApiResponse.success(message="School deleted successfully.")
        except School.DoesNotExist:
            return ApiResponse.error(message="School not found", status_code=404)