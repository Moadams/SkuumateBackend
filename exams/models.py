from core.models import TimestampedModel
from django.db import models

class AssessmentType(TimestampedModel):
    school = models.ForeignKey('schools.School', on_delete=models.CASCADE, help_text = "School for this assessment type")
    name  = models.CharField(max_length = 100, help_text = "name of assessment type")
    max_score = models.DecimalField(max_digits = 5, decimal_places = 2)
    is_active = models.BooleanField(default = True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields = ["school", "name"], name = "unique_school_assessment_name")
        ]

    def __str__(self):
        return f"{self.school.name} - {self.name}"
    
