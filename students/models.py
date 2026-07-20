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


class Guardian(TimestampedModel):

    class Relationship(models.TextChoices):
        FATHER = "father", "Father"
        MOTHER = "mother", "Mother"
        GUARDIAN = "guardian", "Guardian"
        SIBLING = "sibling", "Sibling"
        OTHER = "other", "Other"

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="guardians",
    )
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="guardians",
    )
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    relationship = models.CharField(max_length=20, choices=Relationship.choices)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    is_primary = models.BooleanField(default=False)

    class Meta:
        ordering = ["-is_primary", "last_name"]

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.get_relationship_display()})"

    def save(self, *args, **kwargs):
        # Ensure only one primary guardian per student
        if self.is_primary:
            Guardian.objects.filter(
                student=self.student,
                is_primary=True,
            ).exclude(pk=self.pk).update(is_primary=False)
        super().save(*args, **kwargs)


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