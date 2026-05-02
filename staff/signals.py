from django.db.models.signals import post_save, post_delete, m2m_changed
from django.dispatch import receiver
from django.core.cache import cache

from core.cache import invalidate_school_cache, CacheKeys
from staff.models import StaffProfile, StaffPosition


@receiver([post_save, post_delete], sender=StaffProfile)
def invalidate_staff_cache(sender, instance, **kwargs):
    invalidate_school_cache(str(instance.school_id))


@receiver([post_save, post_delete], sender=StaffPosition)
def invalidate_position_cache(sender, instance, **kwargs):
    invalidate_school_cache(str(instance.school_id))


@receiver(m2m_changed, sender=StaffProfile.positions.through)
def invalidate_staff_position_m2m(sender, instance, **kwargs):
    invalidate_school_cache(str(instance.school_id))
