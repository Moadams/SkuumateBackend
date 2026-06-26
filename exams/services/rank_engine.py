from collections import defaultdict
from exams.models import StudentReport, StudentReportSubjectScore


class RankEngine:

    @staticmethod
    def assign_subject_ranks(reports):
        report_ids = [r.id for r in reports.values()]
        if not report_ids:
            return

        scores = StudentReportSubjectScore.objects.filter(
            student_report_id__in=report_ids
        ).order_by("subject_id", "-total_score")

        grouped = defaultdict(list)

        for s in scores:
            grouped[s.subject_id].append(s)

        to_update = []

        for subject_id, rows in grouped.items():
            rank = 1

            for i, row in enumerate(rows):
                if i > 0 and row.total_score < rows[i - 1].total_score:
                    rank = i + 1

                to_update.append(
                    StudentReportSubjectScore(
                        id=row.id,
                        rank=rank
                    )
                )

        StudentReportSubjectScore.objects.bulk_update(to_update, ["rank"])

    @staticmethod
    def assign_overall_positions(reports):
        
        report_ids = [r.id for r in reports.values()]
        if not report_ids:
            return

        sorted_reports = list(
            StudentReport.objects.filter(id__in=report_ids)
            .order_by("-overall_score")
            .only("id", "overall_score")
        )

        to_update = []
        pos = 1

        for i, r in enumerate(sorted_reports):
            if i > 0 and r.overall_score < sorted_reports[i - 1].overall_score:
                pos = i + 1

            to_update.append(StudentReport(id=r.id, overall_position=pos))
        
        StudentReport.objects.bulk_update(to_update, ["overall_position"])