from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache

from subscriptions.models import Plan, Subscription
from core.cache import CacheKeys


@receiver([post_save, post_delete], sender=Plan)
def invalidate_plan_cache(sender, instance, **kwargs):
    cache.delete_many([CacheKeys.PLAN_LIST, CacheKeys.PLAN_FEATURES])


@receiver([post_save, post_delete], sender=Subscription)
def invalidate_subscription_cache(sender, instance, **kwargs):
    from core.cache import invalidate_school_cache
    invalidate_school_cache(str(instance.school_id))
    cache.delete(CacheKeys.SUPERADMIN_DASHBOARD)
