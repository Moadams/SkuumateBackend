from attendance.models import Attendance
from exams.models import StudentReport, StudentReportSubjectScore


class ReportWriter:

    @staticmethod
    def save_reports(*, school, klass, term, academic_year, report_scheme, students, computed):
        student_ids = [s.id for s in students]

        existing = {
            r.student_id: r
            for r in StudentReport.objects.filter(
                school=school,
                student_id__in=student_ids,
                term=term,
                student_class=klass,
            )
        }

        to_create, to_update = [], []

        reports = {}

        for student in students:
            data = computed.get(student.id)
            if data is None:
                continue

            report = existing.get(student.id)

            attendance_qs = Attendance.objects.filter(
                student=student,
                klass=klass,
                term=term,
            )

            present = attendance_qs.filter(status=Attendance.Status.PRESENT).count()

            if report:
                report.overall_score = data["overall"]
                report.total_school_days = attendance_qs.count()
                report.overall_attendance = present
                report.report_scheme = report_scheme
                to_update.append(report)
            else:
                report = StudentReport(
                    school=school,
                    student=student,
                    academic_year=academic_year,
                    term=term,
                    student_class=klass,
                    report_scheme=report_scheme,
                    overall_score=data["overall"],
                    overall_attendance=present,
                    total_school_days=attendance_qs.count(),
                )
                to_create.append(report)

        if to_create:
            StudentReport.objects.bulk_create(to_create)

        if to_update:
            StudentReport.objects.bulk_update(
                to_update,
                ["overall_score", "report_scheme", "total_school_days", "overall_attendance"],
            )

        computed_student_ids = [sid for sid in student_ids if sid in computed]

        return {
            "created": len(to_create),
            "updated":len(to_update),
            "reports":{
                r.student_id: r
                for r in StudentReport.objects.filter(
                    school=school,
                    student_id__in=computed_student_ids,
                    term=term,
                    student_class=klass,
                )
            }
        }

    @staticmethod
    def save_subject_scores(reports, computed):
        StudentReportSubjectScore.objects.filter(
            student_report_id__in=[r.id for r in reports.values()]
        ).delete()

        rows = []

        for student_id, report in reports.items():
            student_computed = computed.get(student_id)
            if student_computed is None:
                continue
            for row in student_computed["rows"]:
                rows.append(
                    StudentReportSubjectScore(
                        student_report=report,
                        student_id=student_id,
                        **row,
                    )
                )

        StudentReportSubjectScore.objects.bulk_create(rows)