import uuid
from django.conf import settings
from django.db import models


class TimestampedModel(models.Model):
    """
    Abstract base model that provides:
    - UUID primary key
    - created_at / updated_at timestamps
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ["-created_at"]


class AuditLog(models.Model):

    class Action(models.TextChoices):
        CREATE = "create", "Create"
        UPDATE = "update", "Update"
        DELETE = "delete", "Delete"
        LOGIN = "login", "Login"
        LOGOUT = "logout", "Logout"
        OTHER = "other", "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=20, choices=Action.choices)
    resource = models.CharField(max_length=100)        # e.g. "Student", "Invoice"
    resource_id = models.CharField(max_length=100, blank=True)  # the PK of affected object
    description = models.TextField(blank=True)         # human-readable summary
    metadata = models.JSONField(default=dict, blank=True)  # optional extra data
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        return f"[{self.action}] {self.resource} by {self.actor} at {self.timestamp}"