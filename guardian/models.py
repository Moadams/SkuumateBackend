from django.db import models

from core.models import TimestampedModel
from guardian.enums import GuardianGender, GuardianStudentRelationship


class Guardian(TimestampedModel):
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE)
    user_account = models.OneToOneField("accounts.User", on_delete=models.CASCADE)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(null=True, blank=True)
    phone = models.CharField(max_length=15)
    address = models.CharField(max_length=255, blank=True, null=True)
    gender = models.CharField(max_length=10, choices=GuardianGender.choices)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


class GuardianStudent(TimestampedModel):
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE)
    guardian = models.ForeignKey(Guardian, on_delete=models.CASCADE, related_name="guardian_students")
    student = models.ForeignKey("students.Student", on_delete=models.CASCADE, related_name="guardian_links")
    relationship = models.CharField(max_length=100, choices=GuardianStudentRelationship.choices)
