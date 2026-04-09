from django.db import models
from core.models import TimestampedModel


class School(TimestampedModel):
    name = models.CharField(max_length=255)
    logo = models.ImageField(upload_to="schools/logos/", null=True, blank=True)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, default="Ghana")
    is_active = models.BooleanField(default=True)
    onboarding_completed = models.BooleanField(default=False) 

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name