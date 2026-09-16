from rest_framework import generics
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404

from core.models import AuditLog
from core.responses import ApiResponse
from core.mixins import AuditLogMixin
from core.utils import log_action

from subscriptions.models import Feature, Package, Subscription
from subscriptions.serializers import (
    FeatureSerializer,
    ManualActivationSerializer,
    PackageSerializer,
    SubscriptionSerializer,
)
from subscriptions.services.packages import PackageService
from subscriptions.permissions import IsPlatformSuperAdmin


class PackageListCreateView(AuditLogMixin, generics.ListCreateAPIView):
    """
    Super administrator — list / create packages.

    Query params: ``is_active``, ``billing_period``, ``is_public``.
    Ordering: ``ordering=display_order|price|name`` (optional ``-`` prefix).
    """
    permission_classes = [IsPlatformSuperAdmin]
    serializer_class = PackageSerializer

    audit_action = AuditLog.Action.CREATE
    audit_resource = "Package"

    ORDERING_FIELDS = {"display_order", "price", "name"}

    def get_queryset(self):
        queryset = Package.objects.all()

        is_active = self.request.query_params.get("is_active")
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() in ("1", "true"))

        billing_period = self.request.query_params.get("billing_period")
        if billing_period:
            queryset = queryset.filter(billing_period=billing_period.upper())

        is_public = self.request.query_params.get("is_public")
        if is_public is not None:
            queryset = queryset.filter(is_public=is_public.lower() in ("1", "true"))

        ordering = self.request.query_params.get("ordering")
        if ordering and (
            ordering in self.ORDERING_FIELDS
            or ordering.lstrip("-") in self.ORDERING_FIELDS
        ):
            queryset = queryset.order_by(ordering)

        return queryset

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
        return f"Package '{instance.name}' was created by {self.request.user.first_name} {self.request.user.last_name}."


class PackageRetrieveUpdateView(AuditLogMixin, generics.RetrieveUpdateAPIView):
    """Super administrator — retrieve / update a package."""
    queryset = Package.objects.all()
    serializer_class = PackageSerializer
    permission_classes = [IsPlatformSuperAdmin]

    audit_action = AuditLog.Action.UPDATE
    audit_resource = "Package"

    def get_audit_description(self, instance):
        return f"Package '{instance.name}' (ID: {instance.id}) was updated by {self.request.user.first_name} {self.request.user.last_name}."

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
            message=f"Package '{package.name}' {'activated' if is_active else 'deactivated'}.",
        )


class FeatureListCreateView(AuditLogMixin, generics.ListCreateAPIView):
    """Super administrator — list / create platform features."""
    queryset = Feature.objects.all().order_by("category", "name")
    serializer_class = FeatureSerializer
    permission_classes = [IsPlatformSuperAdmin]

    audit_action = AuditLog.Action.CREATE
    audit_resource = "Feature"

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
        return f"Feature '{instance.name}' was created by {self.request.user.first_name} {self.request.user.last_name}."


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
        return f"Feature '{instance.name}' was updated by {self.request.user.first_name} {self.request.user.last_name}."


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
            message=f"Feature '{feature.name}' {'activated' if is_active else 'deactivated'}.",
        )


class SchoolSubscriptionView(AuditLogMixin, generics.ListCreateAPIView):
    permission_classes = [IsPlatformSuperAdmin]
    serializer_class = ManualActivationSerializer
    queryset = Subscription.objects.all()

    audit_action = AuditLog.Action.CREATE
    audit_resource = "Subscription"

    def get_audit_description(self, instance):
        return f"Subscription for school '{instance.school.name}' was manually activated by {self.request.user.first_name} {self.request.user.last_name}."

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        subscription = self.perform_create(serializer)
        return ApiResponse.success(data=SubscriptionSerializer(subscription).data)