from .models import AuditLog


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
        metadata=metadata or {},
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