from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache

from core.cache import CacheKeys, invalidate_school_cache
from schools.models import School


@receiver([post_save, post_delete], sender=School)
def invalidate_school_dashboard(sender, instance, **kwargs):
    invalidate_school_cache(str(instance.id))
    cache.delete(CacheKeys.SUPERADMIN_DASHBOARD)
