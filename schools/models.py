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
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, default="Ghana")
    onboarding_completed = models.BooleanField(default=False) 
    status = models.CharField(choices = SchoolStatus, default=SchoolStatus.ACTIVE) 
    joined = models.DateTimeField(auto_now_add=True)
    

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name