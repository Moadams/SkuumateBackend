from core.models import TimestampedModel
from django.db import models
from django.core.exceptions import ValidationError

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
    
class ReportScheme(TimestampedModel):
    school = models.ForeignKey('schools.School', on_delete = models.CASCADE)
    name = models.CharField(max_length = 100, help_text = "E.g Primary Division report scheme")
    sba_components = models.ManyToManyField(AssessmentType, related_name="sba_report_schemes",help_text = "the assessments that contribute to the SBA components")
    main_exam = models.ForeignKey(AssessmentType, on_delete=models.PROTECT, related_name="exam_report_schemes", help_text = "the assessment that serve as the main exam")
    academic_year = models.ForeignKey("academics.AcademicYear", on_delete=models.PROTECT)
    term = models.ForeignKey("academics.Term", on_delete = models.PROTECT)
    sba_scaling = models.DecimalField(max_digits = 5, decimal_places = 2, default=50, help_text = "Weight for SBA (e.g 40 for 40%)")
    exam_scaling = models.DecimalField(max_digits = 5, decimal_places = 2, default=50, help_text = "Weight for Main exam (e.g 60 for 60%)")

    class Meta:
        # make sure that no two schemes in the same term has the same name
        constraints = [
            models.UniqueConstraint(fields = ['school','term','name'], name = "unique_scheme_name_per_term")
        ]

    def __str__(self):
        return f"{self.name} ({self.term.name})"
    
    def clean(self):
        if (self.sba_scaling + self.exam_scaling) != 100:
            raise ValidationError("SBA scaling and exam scaling should must sum to 100")
        
    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

class StudentMark(TimestampedModel):
    school = models.ForeignKey('schools.School', on_delete=models.CASCADE)
    student = models.ForeignKey("students.Student", on_delete = models.CASCADE)
    academic_year = models.ForeignKey("academics.AcademicYear", on_delete = models.PROTECT)
    term = models.ForeignKey("academics.Term", on_delete = models.PROTECT)
    subject = models.ForeignKey("academics.Subject", on_delete = models.PROTECT)
    assessment = models.ForeignKey(AssessmentType, on_delete = models.CASCADE)
    student_class = models.ForeignKey("academics.Class", on_delete = models.PROTECT)
    score = models.DecimalField(max_digits = 5, decimal_places = 2, null=True, blank=True)
    teacher_remarks = models.TextField(blank = True)
    teacher = models.ForeignKey("staff.StaffProfile", on_delete = models.SET_NULL, null = True, blank = True, related_name = "given_marks")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields = ["student", "assessment", "term", "subject", "student_class"], name = "unique_student_assessment_score")
        ]
        ordering = ["student", "assessment", "term", "subject"]

    def __str__(self):
        return f"{self.student.full_name} - {self.assessment.name} ({self.term.name})"
    
