from django.db import transaction


@transaction.atomic
def mark_bulk_attendance(school, klass, term, date, records, recorded_by):
    """
    Creates or updates attendance records for a list of students.
    Also refreshes the AttendanceSummary for the class/date.

    Returns:
        created_count, updated_count
    """
    from .models import Attendance, AttendanceSummary

    created_count = 0
    updated_count = 0

    for record in records:
        obj, created = Attendance.objects.update_or_create(
            school=school,
            student_id=record["student_id"],
            date=date,
            defaults={
                "klass": klass,
                "term": term,
                "status": record["status"],
                "remarks": record.get("remarks", ""),
                "recorded_by": recorded_by,
            },
        )
        if created:
            created_count += 1
        else:
            updated_count += 1

    # Refresh daily summary for this class
    summary, _ = AttendanceSummary.objects.get_or_create(
        school=school,
        klass=klass,
        date=date,
        defaults={"term": term},
    )
    summary.recompute()

    return created_count, updated_count