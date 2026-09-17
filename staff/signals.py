from django.db.models.signals import post_save, post_delete, m2m_changed
from django.dispatch import receiver
from django.core.cache import cache

from core.cache import invalidate_school_cache, CacheKeys
from staff.models import StaffProfile, StaffPosition


@receiver([post_save, post_delete], sender=StaffProfile)
def invalidate_staff_cache(sender, instance, **kwargs):
    invalidate_school_cache(str(instance.school_id))
    cache.delete(CacheKeys.user_permissions(instance.user_id or instance.id))


@receiver(m2m_changed, sender=StaffProfile.positions.through)
@receiver(m2m_changed, sender=StaffProfile.permission_grants.through)
@receiver(m2m_changed, sender=StaffProfile.permission_revokes.through)
def invalidate_profile_permissions_cache(sender, instance, action, **kwargs):
    if kwargs.get("reverse"):
        return  # Effective permissions are resolved live.
    if action not in ("post_add", "post_remove", "post_clear"):
        return
    cache.delete(CacheKeys.user_permissions(instance.user_id or instance.id))


@receiver(m2m_changed, sender=StaffPosition.permissions.through)
def invalidate_position_permissions_cache(sender, instance, action, **kwargs):
    if kwargs.get("reverse"):
        return
    if action not in ("post_add", "post_remove", "post_clear"):
        return
    affected = StaffProfile.objects.filter(positions=instance).values_list(
        "user_id", "id"
    )
    for user_id, profile_id in affected:
        cache.delete(CacheKeys.user_permissions(user_id or profile_id))
