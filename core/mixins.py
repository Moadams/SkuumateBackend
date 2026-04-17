from core.responses import ApiResponse

from .utils import log_action
from .models import AuditLog


class AuditLogMixin:
    """
    Mixin for APIView and GenericAPIView subclasses.
    Override audit_* properties per view to control log content.
    """
    audit_action = AuditLog.Action.OTHER
    audit_resource = ""

    def get_audit_description(self, instance):
        return f"{self.audit_action.capitalize()} {self.audit_resource}"

    def perform_create(self, serializer, **kwargs):
        instance = serializer.save(**kwargs)
        log_action(
            action=AuditLog.Action.CREATE,
            resource=self.audit_resource,
            resource_id=str(instance.pk),
            description=self.get_audit_description(instance),
            request=self.request,
        )
        return instance

    def perform_update(self, serializer):
        instance = serializer.save()
        log_action(
            action=AuditLog.Action.UPDATE,
            resource=self.audit_resource,
            resource_id=str(instance.pk),
            description=self.get_audit_description(instance),
            request=self.request,
        )
        return instance

    def perform_destroy(self, instance):
        log_action(
            action=AuditLog.Action.DELETE,
            resource=self.audit_resource,
            resource_id=str(instance.pk),
            description=self.get_audit_description(instance),
            request=self.request,
        )
        instance.delete()


class ExportMixin:
    """
    Adds an /export/ action to any ListAPIView or ViewSet.
    Returns the full unpaginated queryset using the same
    filters and serializer as the list endpoint.
    """
    export_serializer_class = None  # override if export needs a different serializer

    def get_export_serializer_class(self):
        return self.export_serializer_class or self.serializer_class

    def export(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer_class = self.get_export_serializer_class()
        serializer = serializer_class(queryset, many=True)
        return ApiResponse.success(
            data={
                "count": queryset.count(),
                "results": serializer.data,
            },
            message="Export data retrieved successfully.",
        )