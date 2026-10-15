from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.views import APIView

from core.cache import CacheKeys, cache_response, invalidate_school_cache
from core.mixins import AuditLogMixin, ExportMixin
from core.models import AuditLog
from core.responses import ApiResponse
from core.school_permissions import school_permission
from schools.serializers.presenters import SchoolDetailsPresenter
from schools.services import SchoolDetailsService
from schools.services.onboarding import OnboardingService
from schools.services.prospective_school import ProspectiveSchoolService
from subscriptions.permissions import IsPlatformSuperAdmin

from ..filters import SchoolFilter
from ..models import ProspectiveSchool, School
from ..serializers.serializers import (
    MySchoolUpdateSerializer,
    PublicSchoolRegistrationSerializer,
    SchoolListSerializer,
    SchoolProfileSerializer,
    SchoolSerializer,
)


class PublicSchoolRegistrationView(generics.CreateAPIView):
    serializer_class = PublicSchoolRegistrationSerializer
    permission_classes = []  # Allow public access

class ProspectiveSchoolListView(generics.ListAPIView):
    serializer_class = PublicSchoolRegistrationSerializer
    permission_classes = (IsPlatformSuperAdmin,)
    filter_backends = (DjangoFilterBackend, SearchFilter, OrderingFilter)   
    filterset_fields = ("status", "created_at")
    search_fields = ("name", "email", "admin_first_name", "admin_last_name", "admin_email","admin_phone")

    def get_queryset(self):
        return ProspectiveSchool.objects.all().order_by("-created_at")


class ProspectiveSchoolApprovalView(APIView):
    permission_classes = (IsPlatformSuperAdmin,)

    def post(self, request, pk):
        try:
            prospective_school = ProspectiveSchool.objects.get(pk=pk)
        except ProspectiveSchool.DoesNotExist:
            return ApiResponse.error(
                message="Prospective school not found.",
                status_code=404,
            )

        action = request.data.get("action", None)
        if action not in ProspectiveSchool.ProspectiveSchoolStatus.values:
            return ApiResponse.error(
                message="Invalid action.",
                status_code=400,
            )
        try:
            if action == ProspectiveSchool.ProspectiveSchoolStatus.APPROVED:
                # Activate the school and create the admin user
                ProspectiveSchoolService().approve_prospective_school(prospective_school)
            elif action == ProspectiveSchool.ProspectiveSchoolStatus.REJECTED:
                ProspectiveSchoolService().reject_prospective_school(prospective_school)
        except ValueError as e:
            return ApiResponse.error(
                message=str(e),
                status_code=400,
            )

        return ApiResponse.success(
            message=f"Prospective school has been {prospective_school.status}.",
            data={"id": prospective_school.id, "status": prospective_school.status},
        )

class SchoolListExportView(ExportMixin, generics.ListAPIView):
    """Export all schools — full unpaginated list. Superadmin only."""
    serializer_class = SchoolListSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = SchoolFilter
    search_fields = ["name", "email", "city", "country"]
    ordering = ["-created_at"]

    def get_queryset(self):
        if not self.request.user.is_superuser:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied(
                "Only superadmins can export the school list."
            )
        return School.objects.all().order_by("-created_at")

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        queryset = self.filter_queryset(self.get_queryset())
        school_ids = queryset.values_list("id", flat=True)

        from subscriptions.models import Subscription
        subscriptions = (
            Subscription.objects
            .filter(school_id__in=school_ids)
            .select_related("plan")
            .order_by("school_id", "-start_date")
            .distinct("school_id")
        )
        ctx["subscriptions"] = {
            str(sub.school_id): sub for sub in subscriptions
        }
        return ctx

    def get(self, request, *args, **kwargs):
        return self.export(request, *args, **kwargs)


class MySchoolRetrieveUpdateView(AuditLogMixin, generics.RetrieveUpdateAPIView):
    """Retrieve or update the current user's school."""
    permission_classes = [school_permission(read="settings.view", write="settings.manage")]
    serializer_class = SchoolSerializer

    audit_action = AuditLog.Action.UPDATE
    audit_resource = "School"

    def get_object(self):
        return self.request.user.school

    def get_audit_description(self, instance):
        return f"{self.request.user.full_name} updated school details for {instance.name}"

    def update(self, request, *args, **kwargs):
        serializer = MySchoolUpdateSerializer(
            self.get_object(), data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        invalidate_school_cache(str(request.user.school.id))
        return ApiResponse.success(data=serializer.data)


class SchoolProfileView(APIView):
    """
    Admin school profile — view and edit school details.
    """
    permission_classes = [school_permission(read="settings.view", write="settings.manage")]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request):
        school = request.user.school
        if not school:
            return ApiResponse.error(
                message="No school associated with this account.",
                status_code=404,
            )
        serializer = SchoolProfileSerializer(school, context={"request": request})
        return ApiResponse.success(data=serializer.data)

    def patch(self, request):
        school = request.user.school
        if not school:
            return ApiResponse.error(
                message="No school associated with this account.",
                status_code=404,
            )
        serializer = MySchoolUpdateSerializer(
            school, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        invalidate_school_cache(str(school.id))
        return ApiResponse.success(data=serializer.data)


class SchoolDetailsView(APIView):
    """
    Comprehensive school details — profile, subscription, academics,
    staff, students, finance, attendance, communications, exams and
    onboarding status in one cached request.
    """
    permission_classes = [school_permission(read="school.manage")]

    @cache_response(
        lambda self, request: CacheKeys.school_details(
            str(request.user.school_id or request.user.id)
        ),
        timeout=60 * 3,
    )
    def get(self, request, *args, **kwargs):
        school = request.user.school
        if not school:
            return ApiResponse.error(
                message="No school associated with this account.",
                status_code=404,
            )

        dto = SchoolDetailsService().get_details(school)
        return ApiResponse.success(
            data=SchoolDetailsPresenter(request).present(dto)
        )


class SchoolOnboardingStatusView(APIView):
    """
    Returns the current school's onboarding status, per-step completion,
    the next incomplete step, and the already-saved data needed to resume
    a partially completed onboarding flow.
    """
    permission_classes = [school_permission(read="school.manage")]  # noqa: RUF012

    @cache_response(
        lambda self, request: CacheKeys.school_onboarding(
            str(request.user.school_id or request.user.id)
        ),
        timeout=60 * 2,
    )
    def get(self, request, *args, **kwargs):
        school = request.user.school
        if not school:
            return ApiResponse.error(
                message="No school associated with this account.",
                status_code=404,
            )

        dto = OnboardingService.build(school, include_data=True, request=request)
        return ApiResponse.success(
            data=SchoolDetailsPresenter(request).present(dto)
        )