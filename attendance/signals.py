from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache

from core.cache import invalidate_school_cache
from attendance.models import Attendance, AttendanceSummary


@receiver([post_save, post_delete], sender=Attendance)
def invalidate_attendance_cache(sender, instance, **kwargs):
    invalidate_school_cache(str(instance.school_id))


@receiver([post_save, post_delete], sender=AttendanceSummary)
def invalidate_attendance_summary_cache(sender, instance, **kwargs):
    invalidate_school_cache(str(instance.school_id))
