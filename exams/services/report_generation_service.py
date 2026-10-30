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


    @staticmethod
    @transaction.atomic
    def publish_reports(*, school, report_ids, allowed_class_ids=None):
        """Publish READY reports and queue guardian delivery in one transaction.

        ``allowed_class_ids`` limits teachers to their assigned classes; pass
        ``None`` for users who may publish across the school.
        """
        report_ids = list(report_ids)
        if not report_ids:
            raise ValueError("Select at least one report to publish.")

        # Reject duplicate IDs to avoid misleading counts.
        if len(report_ids) != len(set(report_ids)):
            raise ValueError("Duplicate report IDs were submitted.")

        queryset = StudentReport.objects.filter(
            school=school,
            id__in=report_ids,
            status=StudentReport.ReportStatus.READY,
        )
        if allowed_class_ids is not None:
            queryset = queryset.filter(student_class_id__in=allowed_class_ids)

        reports = list(
            queryset.select_related(
                "school", "student", "student_class", "term", "academic_year"
            ).prefetch_related("subject_scores__subject")
        )
        if len(reports) != len(report_ids):
            raise ValueError(
                "Some reports were not found for this school "
                "or are not ready for publishing."
            )

        StudentReport.objects.filter(school=school, id__in=report_ids).update(
            status=StudentReport.ReportStatus.PUBLISHED
        )

        # Same transaction as the status change: either reports are published
        # and queued, or the whole operation rolls back.
        from communications.services.report_distribution import (
            ReportDistributionService,
        )

        queued = ReportDistributionService.enqueue(reports)
        return {"published": len(reports), "queued": queued}

