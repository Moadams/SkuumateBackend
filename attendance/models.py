from django.db import models
from core.models import TimestampedModel


class Attendance(TimestampedModel):

    class Status(models.TextChoices):
        PRESENT = "present", "Present"
        ABSENT = "absent", "Absent"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="attendance_records",
    )
    student = models.ForeignKey(
        "students.Student",
        on_delete=models.CASCADE,
        related_name="attendance_records",
    )
    klass = models.ForeignKey(
        "academics.Class",
        on_delete=models.CASCADE,
        related_name="attendance_records",
    )
    term = models.ForeignKey(
        "academics.Term",
        on_delete=models.CASCADE,
        related_name="attendance_records",
    )
    date = models.DateField()
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PRESENT,
    )
    remarks = models.CharField(max_length=255, blank=True)
    recorded_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="recorded_attendance",
    )

    class Meta:
        ordering = ["-date"]
        unique_together = ["school", "student", "date"]

    def __str__(self):
        return (
            f"{self.student.full_name} — "
            f"{self.status} on {self.date}"
        )


class AttendanceSummary(TimestampedModel):
    """
    Daily summary per class — precomputed to avoid
    heavy aggregations on every dashboard load.
    Updated whenever attendance is marked for that class/date.
    """
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="attendance_summaries",
    )
    klass = models.ForeignKey(
        "academics.Class",
        on_delete=models.CASCADE,
        related_name="attendance_summaries",
    )
    term = models.ForeignKey(
        "academics.Term",
        on_delete=models.CASCADE,
        related_name="attendance_summaries",
    )
    date = models.DateField()
    total_students = models.PositiveIntegerField(default=0)
    present_count = models.PositiveIntegerField(default=0)
    absent_count = models.PositiveIntegerField(default=0)
    late_count = models.PositiveIntegerField(default=0)
    attendance_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=0
    )

    class Meta:
        ordering = ["-date"]
        unique_together = ["school", "klass", "date"]

    def __str__(self):
        return (
            f"{self.klass.name} — {self.date} "
            f"({self.attendance_percentage}%)"
        )

    def recompute(self):
        """Recomputes and saves summary from raw attendance records."""
        records = Attendance.objects.filter(
            school=self.school,
            klass=self.klass,
            date=self.date,
        )
        self.total_students = records.count()
        self.present_count = records.filter(
            status=Attendance.Status.PRESENT
        ).count()
        self.absent_count = records.filter(
            status=Attendance.Status.ABSENT
        ).count()
        self.late_count = records.filter(
            status=Attendance.Status.LATE
        ).count()
        self.attendance_percentage = (
            round(
                (self.present_count / self.total_students) * 100, 2
            )
            if self.total_students > 0 else 0
        )
        self.save()