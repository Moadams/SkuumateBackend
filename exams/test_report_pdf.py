"""PDF rendering for report cards attached to guardian emails."""
from datetime import date
from io import BytesIO

from django.test import TestCase
from pypdf import PdfReader

from academics.models import AcademicYear, Class, Subject, Term
from exams.models import (
    AssessmentType,
    ReportScheme,
    StudentReport,
    StudentReportSubjectScore,
)
from exams.services.report_pdf import build_report_pdf
from schools.models import School
from students.models import Student


class ReportPdfTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Sunrise Academy",
            school_code="SUN",
            email="office@sunrise.example",
            phone="0302000000",
            address="12 Ring Road",
            city="Accra",
        )
        self.year = AcademicYear.objects.create(
            school=self.school,
            name="2026",
            is_current=True,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )
        self.term = Term.objects.create(
            school=self.school,
            academic_year=self.year,
            name=Term.TermName.TERM_1,
            start_date=date(2026, 1, 5),
            end_date=date(2026, 4, 10),
        )
        self.klass = Class.objects.create(school=self.school, name="Primary 3")
        assessment = AssessmentType.objects.create(
            school=self.school, name="End of term exam", max_score=100
        )
        self.scheme = ReportScheme.objects.create(
            school=self.school, name="Primary scheme", main_exam=assessment
        )
        self.student = Student.objects.create(
            school=self.school, first_name="Ama", last_name="Mensah", gender="female"
        )
        self.report = StudentReport.objects.create(
            school=self.school,
            student=self.student,
            academic_year=self.year,
            term=self.term,
            student_class=self.klass,
            report_scheme=self.scheme,
            overall_score="88.00",
            overall_position=1,
            overall_attendance=55,
            total_school_days=60,
            teacher_remarks="A diligent and respectful pupil.",
            headteacher_remarks="Promoted to Primary 4.",
            teacher="Ms. Adjei",
            headteacher="Mr. Owusu",
            promoted_to="Primary 4",
            status=StudentReport.ReportStatus.PUBLISHED,
        )
        subject = Subject.objects.create(
            school=self.school, name="Mathematics", code="MTH"
        )
        StudentReportSubjectScore.objects.create(
            student_report=self.report,
            student=self.student,
            subject=subject,
            exam_score=80,
            sba_score=40,
            total_score=88,
            grade="A",
            rank=1,
        )

    def _pdf_text(self, report):
        payload = build_report_pdf(report).getvalue()
        reader = PdfReader(BytesIO(payload))
        return payload, "\n".join(page.extract_text() or "" for page in reader.pages)

    def test_renders_a_valid_pdf_with_the_report_content(self):
        payload, text = self._pdf_text(self.report)

        self.assertTrue(payload.startswith(b"%PDF"))
        self.assertIn("Ama Mensah", text)
        self.assertIn("Mathematics", text)
        self.assertIn("88.00", text)
        self.assertIn("Term 1", text)

    def test_escapes_markup_characters_in_free_text(self):
        self.student.first_name = "Ama & Kofi"
        self.student.last_name = "Mensah <Jnr>"
        self.student.save()
        self.report.teacher_remarks = "Needs help with <algebra> & geometry."
        self.report.save()

        payload, _text = self._pdf_text(self.report)

        self.assertTrue(payload.startswith(b"%PDF"))

    def test_missing_logo_does_not_break_rendering(self):
        self.school.logo = "schools/logos/does-not-exist.png"
        self.school.save(update_fields=["logo"])

        payload, text = self._pdf_text(self.report)

        self.assertTrue(payload.startswith(b"%PDF"))
        self.assertIn("Sunrise Academy", text)
