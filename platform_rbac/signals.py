"""Cache invalidation: any mutation that can change an effective platform
permission set bumps the global version key, making every cached set stale."""
from django.db.models.signals import post_delete, post_save

from .models import (
    PlatformPermission,
    PlatformRole,
    PlatformRolePermission,
    PlatformUserRole,
)
from .services import bump_platform_permissions_version

_SENDERS = (
    PlatformRolePermission,
    PlatformUserRole,
    PlatformRole,
    PlatformPermission,
)


def _invalidate(sender, **kwargs):
    bump_platform_permissions_version()


for _model in _SENDERS:
    post_save.connect(_invalidate, sender=_model, dispatch_uid=f"platform_inv_{_model.__name__}_save", weak=False)
    post_delete.connect(_invalidate, sender=_model, dispatch_uid=f"platform_inv_{_model.__name__}_del", weak=False)