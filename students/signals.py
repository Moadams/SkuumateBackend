from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache

from core.cache import invalidate_school_cache
from students.models import Student


@receiver([post_save, post_delete], sender=Student)
def invalidate_student_cache(sender, instance, **kwargs):
    invalidate_school_cache(str(instance.school_id))
