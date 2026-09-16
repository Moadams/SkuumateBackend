import uuid

from django.conf import settings
from django.db import models

from core.models import TimestampedModel


class PlatformPermission(TimestampedModel):
    """A single platform-level capability, identified by ``module.action``."""

    code = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    module = models.CharField(max_length=50, db_index=True)
    is_active = models.BooleanField(default=True)
    is_system = models.BooleanField(default=True)

    class Meta:
        ordering = ["module", "code"]

    def __str__(self):
        return self.code


class PlatformRole(TimestampedModel):
    """A named collection of platform permissions assigned to platform users."""

    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    is_system_role = models.BooleanField(default=False)

    permissions = models.ManyToManyField(
        PlatformPermission,
        through="PlatformRolePermission",
        related_name="roles",
        blank=True,
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.code


class PlatformRolePermission(TimestampedModel):
    """Join table linking a platform role to a platform permission."""

    role = models.ForeignKey(
        PlatformRole,
        on_delete=models.CASCADE,
        related_name="role_permissions",
    )
    permission = models.ForeignKey(
        PlatformPermission,
        on_delete=models.CASCADE,
        related_name="granted_in_roles",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["role", "permission"],
                name="uniq_platform_role_permission",
            ),
        ]

    def __str__(self):
        return f"{self.role.code}:{self.permission.code}"


class PlatformUserRole(TimestampedModel):
    """Join table linking a platform user to a platform role."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="platform_roles",
    )
    role = models.ForeignKey(
        PlatformRole,
        on_delete=models.CASCADE,
        related_name="user_roles",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "role"],
                name="uniq_platform_user_role",
            ),
        ]

    def __str__(self):
        return f"{self.user.email}:{self.role.code}"