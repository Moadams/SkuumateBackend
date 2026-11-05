from django.core.files.uploadedfile import UploadedFile

from .models import AuditLog

REDACTED = "[REDACTED]"

# Metadata keys whose values must never reach the audit log.
SENSITIVE_KEY_PARTS = (
    "password",
    "token",
    "secret",
    "api_key",
    "api-key",
    "apikey",
    "authorization",
    "credential",
)


def is_sensitive_key(key):
    lowered = str(key).lower()
    return any(part in lowered for part in SENSITIVE_KEY_PARTS)


def sanitize_audit_payload(data):
    """Return ``data`` as JSON-safe audit metadata, redacting secret-like keys.

    Uploaded files are replaced with metadata. Used by both
    ``AuditLogMixin`` and the free-standing ``log_action`` helper so every
    audit path redacts alike.
    """
    if isinstance(data, dict):
        return {
            key: (REDACTED if is_sensitive_key(key) else sanitize_audit_payload(value))
            for key, value in data.items()
            if not isinstance(value, UploadedFile)
        }
    if isinstance(data, (list, tuple)):
        return [
            sanitize_audit_payload(item)
            for item in data
            if not isinstance(item, UploadedFile)
        ]
    if isinstance(data, UploadedFile):
        return {
            "filename": getattr(data, "name", None),
            "size": getattr(data, "size", None),
            "content_type": getattr(data, "content_type", None),
        }
    return data


def log_action(
    action,
    resource,
    resource_id="",
    description="",
    actor=None,
    school=None,
    metadata=None,
    request=None,
):
    """
    Helper to create an audit log entry from anywhere in the codebase.

    Usage:
        log_action(
            action=AuditLog.Action.CREATE,
            resource="Student",
            resource_id=str(student.id),
            description=f"Student {student.full_name} enrolled",
            actor=request.user,
            school=request.user.school,
            request=request,
        )
    """
    ip = None
    if request:
        ip = get_client_ip(request)
        if actor is None:
            actor = resolve_actor(request, actor)
        if school is None and hasattr(request.user, "school"):
            school = request.user.school

    AuditLog.objects.create(
        action=action,
        resource=resource,
        resource_id=str(resource_id),
        description=description,
        actor=actor,
        school=school,
        metadata=sanitize_audit_payload(metadata) if metadata else {},
        ip_address=ip,
    )

def resolve_actor(request, actor):
    if actor is not None:
        return actor
    
    if request and hasattr(request, "user"):
        return request.user if request.user.is_authenticated else None
    
    return None

def get_client_ip(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")