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
        "staff.StaffProfile",
        on_delete=models.CASCADE,
        related_name="class_teachers",
    )
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name="class_teachers",
        blank=True, 
        null=True
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["klass", "academic_year"]
        unique_together = ["school", "klass", "academic_year", "teacher"]

    def __str__(self):
        return f"{self.teacher.full_name} → {self.klass.name}"

class GradingSystem(TimestampedModel):
    """
        A named grading system for the school.
        A school can have multiple grading systems
        e.g one for primary one for jhs etc
    """
    school = models.ForeignKey("schools.School", on_delete = models.CASCADE,related_name="grading_systems")
    name = models.CharField(max_length = 100)
    description = models.TextField(blank=True)
    max_score = models.PositiveBigIntegerField(
        default = 100, help_text = "Maximum possible score for the grade system"
    )
    pass_mark = models.PositiveBigIntegerField(
        default = 50, help_text = "Minimum score considered a pass."
    )

    class Meta:
        ordering = ['name']
        unique_together = ["school","name"]

    def __str__(self):
        return f"{self.name} - {self.school.name}"
    

class GradeScale(TimestampedModel):
    grading_system = models.ForeignKey(GradingSystem, on_delete = models.CASCADE,related_name="grade_scales")
    school = models.ForeignKey("schools.School", on_delete = models.CASCADE,
        related_name="grade_scales")
    grade = models.CharField(max_length = 10, help_text = "Grade label e.g A1, B2")
    label = models.CharField(max_length = 50, help_text = "Descriptive label e.g Excellent, Very good")
    min_score = models.DecimalField(max_digits = 5, decimal_places = 2, help_text = "Minimum score for this grade (inclusive)")
    max_score = models.DecimalField(max_digits = 5, decimal_places = 2, help_text = "Maximum score for this grade (inclusive)")
    
    is_passing = models.BooleanField(default = True, help_text = "Whether is grade is considered as a passing grade")
    position = models.PositiveIntegerField(
        default=0,
        help_text="Display order — lower number appears first.",
    )

    class Meta:
        ordering = ["grading_system", "position", "-min_score"]
        unique_together = [
            ["grading_system", "grade"],
            ["grading_system", "position"]
        ] 

    def __str__(self):
        return (
            f"{self.grade} ({self.min_score}–{self.max_score}) "
            f"— {self.grading_system.name}"
        )
    
    def save(self, *args, **kwargs):
        position = self.position
        while GradeScale.objects.filter(grading_system = self.grading_system, position = position).exclude(pk=self.pk).exists():
            position += 1
        self.position = position
        return super().save(*args, **kwargs)

class SubjectTeacher(TimestampedModel):
    """
    Assigns a teacher to a specific subject in a specific class
    for a given academic year and term.
    A subject can have different teachers across different classes.
    """
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="subject_teachers",
    )
    klass = models.ForeignKey(
        Class,
        on_delete=models.CASCADE,
        related_name="subject_teachers",
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name="subject_teachers",
    )
    teacher = models.ForeignKey(
        "staff.StaffProfile",
        on_delete=models.CASCADE,
        related_name="subject_assignments",
    )
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name="subject_teachers",
        blank=True, 
        null=True
    )
    term = models.ForeignKey(
        Term,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="subject_teachers",
        help_text="Optional — if not set applies to the entire year.",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["klass", "subject"]
        unique_together = [
            "school", "klass", "subject",
            "academic_year", "term",
        ]

    def __str__(self):
        return (
            f"{self.teacher.user.full_name} → "
            f"{self.subject.name} in {self.klass.name} "
            
        )


class TimeTableSlot(TimestampedModel):
    class DaysOfWeek(models.TextChoices):
        MONDAY = "Monday","monday"
        TUESDAY = "Tuesday","tuesday"
        WEDNESDAY = "Wednesday","wednesday"
        THURSDAY = "Thursday","thursday"
        FRIDAY = "Friday","friday"

    day_of_week = models.CharField(choices = DaysOfWeek.choices, max_length = 150)
    start_time = models.TimeField()
    end_time = models.TimeField()
    school = models.ForeignKey("schools.School", on_delete = models.CASCADE, related_name = "timetable_slots")
    term = models.ForeignKey(Term, on_delete = models.CASCADE, related_name = "timetable_slots")
    klass = models.ForeignKey(Class, on_delete = models.CASCADE, related_name = "timetable_slots")
    subject = models.ForeignKey(Subject, on_delete = models.CASCADE, related_name = "timetable_slots")
    teacher = models.ForeignKey("staff.StaffProfile", on_delete = models.SET_NULL, null = True, related_name = "timetable_slots")
