"""Package & feature views — public catalog and superadmin management."""
from django.core.cache import cache
from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from core.cache import CacheKeys
from core.mixins import AuditLogMixin
from core.models import AuditLog
from core.responses import ApiResponse
from core.utils import log_action
from subscriptions.filters import FeatureFilter, PackageFilter
from subscriptions.models import Feature, Package
from subscriptions.permissions import IsPlatformSuperAdmin
from subscriptions.serializers import FeatureSerializer, PackageSerializer
from subscriptions.services.packages import (
    PackageService,
    package_feature_details,
    package_limit_details,
)

# ─────────────────────────────────────────────────────────────────────
# Public catalog (read-only, for signup pages)
# ─────────────────────────────────────────────────────────────────────

class PackageListView(APIView):
    """Public — list all active public packages. Filterable + cached."""

    permission_classes = (AllowAny,)

    def get(self, request):
        queryset = PackageFilter(
            request.query_params,
            queryset=Package.objects.filter(is_active=True, is_public=True),
        ).qs.order_by("display_order", "price")

        cache_key = self._cache_key(request)
        cached = cache.get(cache_key)
        if cached is not None:
            return ApiResponse.success(data=cached)

        data = PackageSerializer(queryset, many=True).data
        cache.set(cache_key, data, timeout=60 * 60)
        return ApiResponse.success(data=data)

    @staticmethod
    def _cache_key(request):
        params = request.query_params
        if not params:
            return CacheKeys.PLAN_LIST
        parts = sorted(
            f"{key}={','.join(request.query_params.getlist(key))}"
            for key in params
        )
        return f"{CacheKeys.PLAN_LIST}:{'&'.join(parts)}"


class PackageFeaturesView(APIView):
    """
    Public endpoint — returns all active packages with entitlements
    grouped by feature category for easy frontend rendering.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        cached = cache.get(CacheKeys.PLAN_FEATURES)
        if cached is not None:
            return ApiResponse.success(data=cached)

        packages = Package.objects.filter(
            is_active=True, is_public=True
        ).order_by("display_order", "price")

        data = {
            "packages": [self._format_package(package) for package in packages],
            "feature_categories": self._get_feature_categories(),
        }
        cache.set(CacheKeys.PLAN_FEATURES, data, timeout=60 * 60)
        return ApiResponse.success(data=data)

    def _format_package(self, package):
        features = package_feature_details(package)
        return {
            "id": str(package.id),
            "name": package.name,
            "code": package.code,
            "plan_type": package.plan_type,
            "tagline": package.tagline,
            "description": package.description,
            "pricing": {
                "price": float(package.price),
                "setup_fee": float(package.setup_fee),
                "currency": package.currency,
                "billing_period": package.billing_period,
            },
            "limits": {
                "minimum_students": package.minimum_students,
                "maximum_students": package.maximum_students,
                "student_range": self._student_range(package),
                "package_limits": package_limit_details(package),
            },
            "features": features,
            "is_popular": package.code == "advantage",
        }

    def _get_feature_categories(self):
        categories = (
            Feature.objects
            .filter(is_active=True)
            .exclude(category="")
            .order_by("category")
            .values_list("category", flat=True)
            .distinct()
        )
        return [
            {
                "key": category,
                "label": category.replace("_", " ").title(),
            }
            for category in categories
        ]

    @staticmethod
    def _student_range(package):
        if package.maximum_students is None:
            return f"{package.minimum_students}+ Students"
        return f"{package.minimum_students}–{package.maximum_students} Students"


# ─────────────────────────────────────────────────────────────────────
# Superadmin — package management
# ─────────────────────────────────────────────────────────────────────

class PackageListCreateView(AuditLogMixin, generics.ListCreateAPIView):
    """
    Super administrator — list / create packages.

    Filters: ``plan_type``, ``billing_period``, ``currency``, ``is_active``,
    ``is_public``, ``min_price``, ``max_price``, ``more_students_than``.
    Ordering: ``ordering=display_order|price|name`` (optional ``-`` prefix).
    """

    permission_classes = [IsPlatformSuperAdmin]
    serializer_class = PackageSerializer
    filterset_class = PackageFilter
    search_fields = ["name", "code", "description"]
    ordering_fields = ["display_order", "price", "name", "created_at"]

    audit_action = AuditLog.Action.CREATE
    audit_resource = "Package"

    def get_queryset(self):
        return Package.objects.all()

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        return ApiResponse.success(data=serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = self.perform_create(serializer)
        return ApiResponse.created(data=PackageSerializer(instance).data)

    def get_audit_description(self, instance):
        return (
            f"Package '{instance.name}' was created by "
            f"{self.request.user.first_name} {self.request.user.last_name}."
        )


class PackageRetrieveUpdateView(AuditLogMixin, generics.RetrieveUpdateAPIView):
    """Super administrator — retrieve / update a package."""

    queryset = Package.objects.all()
    serializer_class = PackageSerializer
    permission_classes = [IsPlatformSuperAdmin]

    audit_action = AuditLog.Action.UPDATE
    audit_resource = "Package"

    def get_audit_description(self, instance):
        return (
            f"Package '{instance.name}' (ID: {instance.id}) was updated by "
            f"{self.request.user.first_name} {self.request.user.last_name}."
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        instance = self.perform_update(serializer)
        return ApiResponse.success(data=PackageSerializer(instance).data)


class PackageActivateDeactivateView(AuditLogMixin, APIView):
    """Super administrator — activate / deactivate a package (is_active)."""

    permission_classes = [IsPlatformSuperAdmin]
    audit_resource = "Package"

    def post(self, request, pk):
        package = get_object_or_404(Package, pk=pk)
        path = request.path.rstrip("/")
        is_active = path.endswith("activate") and not path.endswith("deactivate")
        PackageService.set_active(package, is_active)
        log_action(
            action=AuditLog.Action.UPDATE,
            resource=self.audit_resource,
            resource_id=str(package.pk),
            description=(
                f"Package '{package.name}' was "
                f"{'activated' if is_active else 'deactivated'} by "
                f"{request.user.first_name} {request.user.last_name}."
            ),
            request=request,
        )
        return ApiResponse.success(
            data=PackageSerializer(package).data,
            message=f"Package '{package.name}' "
            f"{'activated' if is_active else 'deactivated'}.",
        )


# ─────────────────────────────────────────────────────────────────────
# Superadmin — feature management
# ─────────────────────────────────────────────────────────────────────

class FeatureListCreateView(AuditLogMixin, generics.ListCreateAPIView):
    """Super administrator — list / create platform features."""

    permission_classes = [IsPlatformSuperAdmin]
    serializer_class = FeatureSerializer
    filterset_class = FeatureFilter
    search_fields = ["name", "code", "category"]

    audit_action = AuditLog.Action.CREATE
    audit_resource = "Feature"

    def get_queryset(self):
        return Feature.objects.all().order_by("category", "name")

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        return ApiResponse.success(data=serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = self.perform_create(serializer)
        return ApiResponse.created(data=FeatureSerializer(instance).data)

    def get_audit_description(self, instance):
        return (
            f"Feature '{instance.name}' was created by "
            f"{self.request.user.first_name} {self.request.user.last_name}."
        )


class FeatureRetrieveUpdateView(AuditLogMixin, generics.RetrieveUpdateAPIView):
    """Super administrator — retrieve / update a feature."""

    queryset = Feature.objects.all()
    serializer_class = FeatureSerializer
    permission_classes = [IsPlatformSuperAdmin]

    audit_action = AuditLog.Action.UPDATE
    audit_resource = "Feature"

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        instance = self.perform_update(serializer)
        return ApiResponse.success(data=FeatureSerializer(instance).data)

    def get_audit_description(self, instance):
        return (
            f"Feature '{instance.name}' was updated by "
            f"{self.request.user.first_name} {self.request.user.last_name}."
        )


class FeatureActivateDeactivateView(AuditLogMixin, APIView):
    """Super administrator — activate / deactivate a feature."""

    permission_classes = [IsPlatformSuperAdmin]
    audit_resource = "Feature"

    def post(self, request, pk):
        feature = get_object_or_404(Feature, pk=pk)
        path = request.path.rstrip("/")
        is_active = path.endswith("activate") and not path.endswith("deactivate")
        feature.is_active = is_active
        feature.save(update_fields=["is_active", "updated_at"])
        log_action(
            action=AuditLog.Action.UPDATE,
            resource=self.audit_resource,
            resource_id=str(feature.pk),
            description=(
                f"Feature '{feature.name}' was "
                f"{'activated' if is_active else 'deactivated'} by "
                f"{request.user.first_name} {request.user.last_name}."
            ),
            request=request,
        )
        return ApiResponse.success(
            data=FeatureSerializer(feature).data,
            message=f"Feature '{feature.name}' "
            f"{'activated' if is_active else 'deactivated'}.",
        )