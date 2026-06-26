from django.core.files.uploadedfile import UploadedFile
from core.responses import ApiResponse
from django.db import transaction
from .utils import log_action
from .models import AuditLog


def _make_json_serializable(data):
    """
    Recursively filter out non-JSON-serializable objects like uploaded files.
    Converts dict-like and list-like objects, excluding file upload objects.
    """
    if isinstance(data, dict):
        return {
            k: _make_json_serializable(v)
            for k, v in data.items()
            if not isinstance(v, UploadedFile)
        }
    elif isinstance(data, (list, tuple)):
        return [
            _make_json_serializable(item)
            for item in data
            if not isinstance(item, UploadedFile)
        ]
    elif isinstance(data, UploadedFile):
        # Return file metadata instead of the file object
        return {
            "filename": getattr(data, "name", None),
            "size": getattr(data, "size", None),
            "content_type": getattr(data, "content_type", None),
        }
    else:
        return data


class AuditLogMixin:
    """
    Mixin for APIView and GenericAPIView subclasses.
    Override audit_* properties per view to control log content.
    """
    audit_action = AuditLog.Action.OTHER
    audit_resource = ""

    def get_audit_metadata(self, instance=None):
        return {
            "instance": str(instance) if instance else None,
            "user": f"{self.request.user.first_name} {self.request.user.last_name}" if self.request.user.is_authenticated else None,
            "data": _make_json_serializable(self.request.data),
        }

    def get_audit_description(self, instance):
        return f"{self.audit_action.capitalize()} {self.audit_resource}"

    @transaction.atomic
    def perform_create(self, serializer, **kwargs):
        school = self.request.user.school
        if school:
            kwargs["school"] = school
        instance = serializer.save(**kwargs)
        log_action(
            action=AuditLog.Action.CREATE,
            resource=self.audit_resource,
            resource_id=str(instance.pk),
            description=self.get_audit_description(instance),
            request=self.request,
            metadata=self.get_audit_metadata(instance),
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
            metadata=self.get_audit_metadata(instance),
        )
        return instance

    def perform_destroy(self, instance):
        log_action(
            action=AuditLog.Action.DELETE,
            resource=self.audit_resource,
            resource_id=str(instance.pk),
            description=self.get_audit_description(instance),
            request=self.request,
            metadata=self.get_audit_metadata(instance),
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