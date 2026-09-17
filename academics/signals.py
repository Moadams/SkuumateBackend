from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from core.cache import invalidate_school_cache


@receiver(post_save, sender="academics.AcademicYear")
@receiver(post_delete, sender="academics.AcademicYear")
@receiver(post_save, sender="academics.Term")
@receiver(post_delete, sender="academics.Term")
@receiver(post_save, sender="academics.Class")
@receiver(post_delete, sender="academics.Class")
@receiver(post_save, sender="academics.Subject")
@receiver(post_delete, sender="academics.Subject")
def invalidate_academics_cache(sender, instance, **kwargs):
    """Onboarding/dashboard read models depend on years, terms, classes
    and subjects — drop the school caches when they change so the
    onboarding status never goes stale mid-flow."""
    invalidate_school_cache(str(instance.school_id))