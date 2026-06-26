from core.models import TimestampedModel
from django.db import models
from django.core.exceptions import ValidationError

class AssessmentType(TimestampedModel):
    school = models.ForeignKey('schools.School', on_delete=models.CASCADE, help_text = "School for this assessment type")
    name  = models.CharField(max_length = 100, help_text = "name of assessment type")
    max_score = models.DecimalField(max_digits = 5, decimal_places = 2)
    is_active = models.BooleanField(default = True)

    class Meta:
        unique_together = [
            ["school", "name"]
        ] 


    def __str__(self):
        return f"{self.school.name} - {self.name}"
    
class ReportScheme(TimestampedModel):
    school = models.ForeignKey('schools.School', on_delete = models.CASCADE)
    name = models.CharField(max_length = 100, help_text = "E.g Primary Division report scheme")
    sba_components = models.ManyToManyField(AssessmentType, related_name="sba_report_schemes",help_text = "the assessments that contribute to the SBA components")
    main_exam = models.ForeignKey(AssessmentType, on_delete=models.PROTECT, related_name="exam_report_schemes", help_text = "the assessment that serve as the main exam")
    sba_scaling = models.DecimalField(max_digits = 5, decimal_places = 2, default=50, help_text = "Weight for SBA (e.g 40 for 40%)")
    exam_scaling = models.DecimalField(max_digits = 5, decimal_places = 2, default=50, help_text = "Weight for Main exam (e.g 60 for 60%)")

    def __str__(self):
        return f"{self.name}"
    
    def clean(self):
        if (self.sba_scaling + self.exam_scaling) != 100:
            raise ValidationError("SBA scaling and exam scaling should must sum to 100")
        
    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["name", "school"],
                name="unique_reportscheme_per_school"
            )
        ]

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
    
class StudentReport(TimestampedModel):
    class ReportStatus(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        READY = "READY", "Ready"
        PUBLISHED = "PUBLISHED", "Published"
        PENDING_REMARKS = "PENDING_REMARKS", "Pending Remarks"

    school = models.ForeignKey('schools.School', on_delete=models.CASCADE)
    student = models.ForeignKey("students.Student", on_delete = models.CASCADE)
    academic_year = models.ForeignKey("academics.AcademicYear", on_delete = models.PROTECT)
    term = models.ForeignKey("academics.Term", on_delete = models.PROTECT)
    student_class = models.ForeignKey("academics.Class", on_delete = models.PROTECT)
    report_scheme = models.ForeignKey(ReportScheme, on_delete = models.PROTECT)
    overall_score = models.DecimalField(max_digits = 5, decimal_places = 2, default = 0.00)
    overall_attendance = models.PositiveSmallIntegerField(default = 0, help_text = "Number of days attended")
    overall_position = models.PositiveIntegerField(default = 0, null=True, blank=True)
    total_school_days = models.PositiveSmallIntegerField(default = 0, help_text = "Total number of school days in the term")
    teacher_remarks = models.TextField(blank = True)
    headteacher_remarks = models.TextField(blank=True)
    headteacher = models.CharField(max_length = 100,blank=True, null=True)
    teacher = models.CharField(max_length = 100, blank=True, null=True)
    status = models.CharField(max_length = 20, choices = ReportStatus.choices, default = ReportStatus.DRAFT)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields = ["student", "term", "student_class"], name = "unique_student_report_per_term_year")
        ]
        ordering = ["student", "term", "academic_year"]

    def __str__(self):
        return f"{self.student.full_name} - {self.term.name} Report"

    def save(self, *args, **kwargs):
        if self.teacher_remarks and self.headteacher_remarks:
            self.status = self.ReportStatus.READY
        if self.teacher_remarks is None or self.headteacher_remarks is None:
            self.status = self.ReportStatus.PENDING_REMARKS
        super().save(*args, **kwargs)

class StudentReportSubjectScore(TimestampedModel):
    student_report = models.ForeignKey(StudentReport, on_delete = models.CASCADE, related_name = "subject_scores")
    student = models.ForeignKey("students.Student", on_delete = models.CASCADE,blank = True, null=True, related_name = "report_subject_scores")
    rank = models.PositiveIntegerField(null = True, blank = True)
    subject = models.ForeignKey("academics.Subject", on_delete = models.PROTECT)
    exam_score = models.DecimalField(max_digits = 5, decimal_places = 2, default = 0.00)
    sba_score = models.DecimalField(max_digits = 5, decimal_places = 2, default = 0.00)
    total_score = models.DecimalField(max_digits = 5, decimal_places = 2, default = 0.00)
    grade = models.CharField(max_length = 10, blank = True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields = ["student_report", "subject"], name = "unique_subject_score_per_report")
        ]
        ordering = ["student_report", "subject"]

    def __str__(self):
        return f"{self.student_report.student.full_name} - {self.subject.name} Score"