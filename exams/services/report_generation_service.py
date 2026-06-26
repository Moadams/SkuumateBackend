from django.db import transaction

from exams.models import StudentReport
from exams.repositories.grade_scale_repository import GradeScaleRepository
from exams.repositories.mark_repository import MarkRepository
from exams.services.rank_engine import RankEngine
from exams.services.score_engine import ScoreEngine
from exams.writers.report_writer import ReportWriter
from students.models import Enrollment


class ReportGenerationService:

    @staticmethod
    @transaction.atomic
    def generate(*, school, klass, report_scheme, grading_system, term):
        academic_year = term.academic_year

        enrollments = Enrollment.objects.filter(
            klass=klass,
            academic_year=academic_year,
            is_active=True,
            school=school,
        ).select_related("student")

        students = [e.student for e in enrollments]

        if not students:
            return {
                "generated": 0,
                "updated": 0,
                "reports": StudentReport.objects.none(),
            }

        marks = MarkRepository.get_marks(
            school=school,
            klass=klass,
            term=term,
            students=students,
            report_scheme=report_scheme,
        )

        grade_scales = GradeScaleRepository.get(grading_system, school=school)

        computed = ScoreEngine.compute(
            students=students,
            marks=marks,
            report_scheme=report_scheme,
            grade_scales=grade_scales,
        )

        reports = ReportWriter.save_reports(
            school=school,
            klass=klass,
            term=term,
            academic_year=academic_year,
            report_scheme=report_scheme,
            students=students,
            computed=computed,
        )

        ReportWriter.save_subject_scores(reports["reports"], computed)
        RankEngine.assign_subject_ranks(reports["reports"])
        RankEngine.assign_overall_positions(reports["reports"])

        return {
            "generated": reports['created'],
            "updated": reports['updated']
        }