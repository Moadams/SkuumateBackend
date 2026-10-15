from django.db import models

from core.models import TimestampedModel


class School(TimestampedModel):
    class SchoolStatus(models.TextChoices):
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"
        PENDING = "pending", "Pending"

    name = models.CharField(max_length=255)
    school_code = models.CharField(max_length = 10, blank=True, null=True)
    logo = models.ImageField(upload_to="schools/logos/", null=True, blank=True)
    email = models.EmailField(unique=True, blank=True, null=True)
    school_email_domain = models.CharField(max_length=255, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, default="Ghana")
    onboarding_completed = models.BooleanField(default=False)
    status = models.CharField(
        max_length=20,
        choices=SchoolStatus.choices,
        default=SchoolStatus.ACTIVE,
    )
    joined = models.DateTimeField(auto_now_add=True)
    

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name

    def force_delete(self, *args, **kwargs):
        """
        Force delete the school and all related objects.
        """
        # Delete related objects first
        self.users.all().delete()
        self.subscriptions.all().delete()
        self.students.all().delete()
        self.staff_profiles.all().delete()
        self.classes.all().delete()
        from exams.models import ReportScheme

        ReportScheme.objects.filter(school=self).delete()
        self.assessment_types.all().delete()

        # Now delete the school itself
        super().delete(*args, **kwargs)



class ProspectiveSchool(TimestampedModel):
    class ProspectiveSchoolStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20)
    admin_first_name = models.CharField(max_length=100)
    admin_last_name = models.CharField(max_length=100)
    admin_email = models.EmailField()
    admin_phone = models.CharField(max_length=20)
    status = models.CharField(
        max_length=20,
        choices=ProspectiveSchoolStatus.choices,
        default=ProspectiveSchoolStatus.PENDING,
    )

    def __str__(self):
        return f"{self.name} ({self.email})"