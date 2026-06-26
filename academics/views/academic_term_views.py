# ─── Term ────────────────────────────────────────────────────────
from django.db import transaction
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework import status

from academics.filters import TermFilter
from academics.models import AcademicYear, Term



from academics.serializers import TermSerializer,TermUpdateSerializer
from core.mixins import AuditLogMixin, ExportMixin
from core.models import AuditLog
from core.permissions import IsAdmin
from core.responses import ApiResponse
from core.utils import log_action
from schools.utils import check_and_complete_onboarding


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

    @transaction.atomic
    def perform_create(self, serializer):
        instance = serializer.save(school=self.request.user.school)
        log_action(
            action=AuditLog.Action.CREATE,
            resource="Term",
            resource_id=str(instance.pk),
            description=f"Term '{instance.get_name_display()}' created by {self.request.user.full_name()}",
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
        serializer = TermUpdateSerializer(instance, data=request.data, partial=True)
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
