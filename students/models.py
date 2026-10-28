from django.db import models

from core.models import TimestampedModel


class Student(TimestampedModel):

    class Gender(models.TextChoices):
        MALE = "male", "Male"
        FEMALE = "female", "Female"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        WITHDRAWN = "withdrawn", "Withdrawn"
        INACTIVE = "inactive", "Inactive"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="students",
    )
    user_account = models.OneToOneField(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="student_profile",
    )
    student_id = models.CharField(max_length=20, unique=True, editable=False)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    other_names = models.CharField(max_length=100, blank=True)
    date_of_birth = models.DateField(blank=True, null=True)
    gender = models.CharField(max_length=10, choices=Gender.choices)
    email = models.EmailField(blank=True)
    phone_number = models.CharField(max_length=20, blank=True)
    profile_photo = models.ImageField(
        upload_to="students/photos/", null=True, blank=True
    )
    address = models.TextField(blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE
    )
    admission_date = models.DateField(blank=True, null=True)
    previous_school = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["last_name", "first_name"]

    def __str__(self):
        return f"{self.full_name} ({self.student_id})"

    @property
    def full_name(self):
        names = [self.first_name, self.other_names, self.last_name]
        return " ".join(n for n in names if n).strip()

    def save(self, *args, **kwargs):
        if not self.student_id:
            self.student_id = self._generate_student_id()
        super().save(*args, **kwargs)

    def _generate_student_id(self):
        import datetime
        year = datetime.date.today().year
        school_prefix = self.school.school_code.upper() if self.school.school_code else "SCH"
        count = Student.objects.filter(school=self.school).count() + 1

        if self.admission_date:
            year = self.admission_date.year
            count = Student.objects.filter(
                school=self.school,
                admission_date__year=year
            ).count() + 1

        return f"{school_prefix}-{year}-{count:04d}"


class Enrollment(TimestampedModel):
    """Tracks which class a student is in for a given academic year."""

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="enrollments",
    )
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="enrollments",
    )
    klass = models.ForeignKey(
        "academics.Class",
        on_delete=models.CASCADE,
        related_name="enrollments",
    )
    academic_year = models.ForeignKey(
        "academics.AcademicYear",
        on_delete=models.CASCADE,
        related_name="enrollments",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-academic_year__start_date"]
        unique_together = ["school", "student", "academic_year"]

    def __str__(self):
        return (
            f"{self.student.full_name} → "
            f"{self.klass.name} ({self.academic_year.name})"
        )


class PromotionBatch(TimestampedModel):
    """A single promotion run — one target class/year for one or many students.

    Enrollments are per academic year (see :class:`Enrollment`), so a promotion
    simply creates a new enrollment in the target year. The term is recorded
    for reporting only; it does not affect the duplicate check.
    """

    class Status(models.TextChoices):
        COMPLETED = "completed", "Completed"
        REVERSED = "reversed", "Reversed"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="promotion_batches",
    )
    from_academic_year = models.ForeignKey(
        "academics.AcademicYear",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="promotion_batches_from",
    )
    from_class = models.ForeignKey(
        "academics.Class",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="promotion_batches_from",
    )
    to_academic_year = models.ForeignKey(
        "academics.AcademicYear",
        on_delete=models.CASCADE,
        related_name="promotion_batches_to",
    )
    to_class = models.ForeignKey(
        "academics.Class",
        on_delete=models.CASCADE,
        related_name="promotion_batches_to",
    )
    to_term = models.ForeignKey(
        "academics.Term",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="promotion_batches",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.COMPLETED
    )
    notes = models.TextField(blank=True)
    promoted_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="promotion_batches",
    )
    reversed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Promotion Batch"
        verbose_name_plural = "Promotion Batches"

    def __str__(self):
        return f"Promotion → {self.to_class.name} ({self.to_academic_year.name})"

    def outcome_counts(self):
        counts = {"promoted": 0, "skipped": 0, "failed": 0}
        for outcome in self.items.values_list("outcome", flat=True):
            counts[outcome] = counts.get(outcome, 0) + 1
        counts["total"] = sum(
            counts[k] for k in ("promoted", "skipped", "failed")
        )
        return counts


class Promotion(TimestampedModel):
    """Per-student outcome within a :class:`PromotionBatch`."""

    class Outcome(models.TextChoices):
        PROMOTED = "promoted", "Promoted"
        SKIPPED = "skipped", "Skipped"
        FAILED = "failed", "Failed"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="promotion_items",
    )
    batch = models.ForeignKey(
        PromotionBatch,
        on_delete=models.CASCADE,
        related_name="items",
    )
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="promotions",
    )
    from_enrollment = models.ForeignKey(
        Enrollment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="promotions_from",
    )
    resulting_enrollment = models.ForeignKey(
        Enrollment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="promotion_results",
    )
    outcome = models.CharField(
        max_length=20, choices=Outcome.choices, default=Outcome.PROMOTED
    )
    message = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["student__last_name", "student__first_name"]
        unique_together = ["batch", "student"]

    def __str__(self):
        return f"{self.student.full_name} → {self.batch.to_class.name}"
