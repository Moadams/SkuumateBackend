from django.db import models
from core.models import TimestampedModel


class AcademicYear(TimestampedModel):
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="academic_years",
    )
    name = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField()
    is_current = models.BooleanField(default=False)

    class Meta:
        ordering = ["-start_date"]
        unique_together = ["school", "name"]

    def __str__(self):
        return f"{self.name} — {self.school.name}"

    def save(self, *args, **kwargs):
        # Ensure only one current academic year per school
        if self.is_current and self.school_id:
            AcademicYear.objects.filter(
                school_id=self.school_id,
                is_current=True
            ).exclude(pk=self.pk).update(is_current=False)
        super().save(*args, **kwargs)


class Term(TimestampedModel):

    class TermName(models.TextChoices):
        TERM_1 = "term_1", "Term 1"
        TERM_2 = "term_2", "Term 2"
        TERM_3 = "term_3", "Term 3"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="terms",
    )
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name="terms",
    )
    name = models.CharField(max_length=20, choices=TermName.choices)
    start_date = models.DateField()
    end_date = models.DateField()
    next_reopening_date = models.DateField(null=True, blank=True)
    is_current = models.BooleanField(default=False)

    class Meta:
        ordering = ["academic_year", "name"]
        unique_together = ["school", "academic_year", "name"]

    def __str__(self):
        return f"{self.get_name_display()} — {self.academic_year.name}"

    def save(self, *args, **kwargs):
        # Ensure only one current term per school
        if self.is_current:
            Term.objects.filter(
                school=self.school,
                is_current=True
            ).exclude(pk=self.pk).update(is_current=False)
        super().save(*args, **kwargs)


class Subject(TimestampedModel):
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="subjects",
    )
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        unique_together = ["school", "name"]

    def __str__(self):
        return f"{self.name} ({self.school.name})"


class Class(TimestampedModel):
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="classes",
    )
    name = models.CharField(max_length=100) 
    description = models.TextField(blank=True)
    capacity = models.PositiveIntegerField(default=30)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        unique_together = ["school", "name"]
        verbose_name = "Class"
        verbose_name_plural = "Classes"

    def __str__(self):
        return f"{self.name} — {self.school.name}"

    @property
    def current_student_count(self):
        return self.enrollments.filter(
            is_active=True,
            academic_year__is_current=True,
        ).count()


class ClassSubject(TimestampedModel):
    """Links subjects to classes — a class can have many subjects."""
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="class_subjects",
    )
    klass = models.ForeignKey(
        Class,
        on_delete=models.CASCADE,
        related_name="class_subjects",
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name="class_subjects",
    )

    class Meta:
        ordering = ["klass", "subject"]
        unique_together = ["school", "klass", "subject"]

    def __str__(self):
        return f"{self.subject.name} in {self.klass.name}"


class ClassTeacher(TimestampedModel):
    """Assigns a teacher to a class for a given academic year."""
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="class_teachers",
    )
    klass = models.ForeignKey(
        Class,
        on_delete=models.CASCADE,
        related_name="class_teachers",
    )
    teacher = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="class_teachers",
    )
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name="class_teachers",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["klass", "academic_year"]
        unique_together = ["school", "klass", "academic_year", "teacher"]

    def __str__(self):
        return f"{self.teacher.full_name} → {self.klass.name} ({self.academic_year.name})"