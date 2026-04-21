from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal
import uuid
from django.db import transaction

from academics.models import AcademicYear, Class, GradeScale, GradingSystem, Term
from attendance.models import Attendance
from exams.models import ReportScheme, StudentMark, StudentReport, StudentReportSubjectScore
from schools.models import School
from students.models import Enrollment


def _get_grade(score: Decimal, grade_scales: list[GradeScale]) -> str:
    """Return the grade label for a score given an ordered list of GradeScale objects."""
    for scale in grade_scales:
        if scale.min_score <= score <= scale.max_score:
            return scale.grade
    return ""


def generate_class_report(
        *, 
        klass:Class, 
        report_scheme:ReportScheme, 
        grading_system:GradingSystem, 
        term:Term, 
        academic_year:AcademicYear, 
        school:School
) -> dict:
    """
    Generate (or regenerate) StudentReport + StudentReportSubjectScore records
    for every active student enrolled in `klass` for `academic_year`.

    Returns a summary dict with counts and the report queryset.
    """

    # ------------------------------------------------------------------ #
    # 1. Fetch all active enrollments for this class / year in one query  #
    # ------------------------------------------------------------------ #
    enrollments = (
        Enrollment.objects.filter(
            klass = klass,
            academic_year = academic_year,
            is_active = True,
            school =school
        ).select_related('student')
    )

    students = [enrollment.student for enrollment in enrollments]
    student_ids = [student.id for student in students]

    if not students:
        return {
            "generated":0,
            "updated":0,
            "reports":StudentReport.objects.none()
        }
    
    # ------------------------------------------------------------------ #
    # 2. Get the ids of SBA assessment types and the main exam type              #
    # ------------------------------------------------------------------ #
    sba_assessments_ids = set(
        report_scheme.sba_components.values_list("id", flat = True)
    )
    main_exam_id = report_scheme.main_exam.id

    # ------------------------------------------------------------------ #
    # 3. Fetch ALL marks for these students in this term/class at once    #
    # ------------------------------------------------------------------ #
    marks_qs = (
        StudentMark.objects.filter(
            school = school,
            student_id__in = student_ids,
            term = term,
            student_class = klass
        ).select_related("assessment","student")
    )

    mark_map: dict[uuid, dict[uuid, dict ]] = defaultdict(
        lambda: defaultdict(lambda: {"sba":[], "exam": None})
    )

    for mark in marks_qs:
        bucket = mark_map[mark.student_id][mark.subject_id]
        if mark.assessment_id == main_exam_id:
            bucket['exam'] = mark.score
        elif mark.assessment_id in sba_assessments_ids:
            bucket['sba'].append(mark.score)

    # ------------------------------------------------------------------ #
    # 4. Fetch grade scales once, ordered for fast lookup                 #
    # ------------------------------------------------------------------ #
    grade_scales = (
        GradeScale.objects.filter(grading_system = grading_system).order_by('-min_score')
    )

    # ------------------------------------------------------------------ #
    # 5. Compute scores per student per subject                           #
    # ------------------------------------------------------------------ #
    sba_weight = report_scheme.sba_scaling / Decimal(100)
    exam_weight = report_scheme.exam_scaling / Decimal(100)

    all_subject_ids = set()
    for subj_map in mark_map.values():
        all_subject_ids.update(subj_map.keys())

    TWO_PLACES = Decimal("0.01")

    student_subject_scores: dict[uuid, list[dict]] = {}

    for student in students:
        rows = []
        subj_map = mark_map.get(student.id, {})
        overall_total = Decimal("0.00")

        for subject_id, scores in subj_map.items():
            
            raw_sba_scores = [sba_score for sba_score in scores["sba"] if sba_score is not None]
            if raw_sba_scores:
                raw_sba_avg = sum(raw_sba_scores) / len(raw_sba_scores)
            else:
                raw_sba_avg = Decimal("0.00")

            raw_exam = scores["exam"] if scores["exam"] is not None else Decimal("0.00")

            # Scale to report weights
            sba_scaled = (raw_sba_avg * sba_weight).quantize(TWO_PLACES, ROUND_HALF_UP)
            exam_scaled = (raw_exam * exam_weight).quantize(TWO_PLACES, ROUND_HALF_UP)
            total = (sba_scaled + exam_scaled).quantize(TWO_PLACES, ROUND_HALF_UP)
            grade = _get_grade(total, grade_scales)
            overall_total += total

            rows.append(
                {
                    "subject_id": subject_id,
                    "sba_score": sba_scaled,
                    "exam_score": exam_scaled,
                    "total_score": total,
                    "grade": grade,
                }
            )

        overall_avg = (
            (overall_total / len(rows)).quantize(TWO_PLACES, ROUND_HALF_UP)
            if rows
            else Decimal("0.00")
        )
        student_subject_scores[student.id] = {
            "rows": rows,
            "overall": overall_avg,
        }

    # ------------------------------------------------------------------ #
    # 6. Upsert StudentReport rows                                        #
    # ------------------------------------------------------------------ #
    with transaction.atomic():
        existing_reports = {
            r.student_id: r
            for r in StudentReport.objects.filter(
                school=school,
                student_id__in=student_ids,
                term=term,
                student_class=klass,
            )
        }

        to_create: list[StudentReport] = []
        to_update: list[StudentReport] = []

        for student in students:
            data = student_subject_scores.get(student.id, {"rows": [], "overall": Decimal("0.00")})
            overall = data["overall"]

            # GET ATTENDANCE DATA 
            attendance = Attendance.objects.filter(
                student = student,
                klass = klass,
                term = term
            )
            days_present = attendance.filter(status = Attendance.Status.PRESENT)
            print(attendance)
            print(days_present)
            if student.id in existing_reports:
                report = existing_reports[student.id]
                report.overall_score = overall
                report.report_scheme = report_scheme
                report.academic_year = academic_year
                report.overall_attendance = days_present.count()
                report.total_school_days = attendance.count()
                to_update.append(report)
            else:
                to_create.append(
                    StudentReport(
                        school=school,
                        student=student,
                        academic_year=academic_year,
                        term=term,
                        student_class=klass,
                        report_scheme=report_scheme,
                        overall_score=overall,
                        status=StudentReport.ReportStatus.DRAFT,
                        overall_attendance = days_present.count(),
                        total_school_days = attendance.count()
                    )
                )

        if to_create:
            StudentReport.objects.bulk_create(to_create)
        if to_update:
            StudentReport.objects.bulk_update(to_update, ["overall_score", "report_scheme", "academic_year", "total_school_days", "overall_attendance"])

        # Re-fetch with PKs
        all_reports = {
            r.student_id: r
            for r in StudentReport.objects.filter(
                school=school,
                student_id__in=student_ids,
                term=term,
                student_class=klass,
            )
        }

        # ------------------------------------------------------------------ #
        # 7. Upsert StudentReportSubjectScore rows (bulk)                     #
        # ------------------------------------------------------------------ #
        
        report_ids = [r.id for r in all_reports.values()]
        StudentReportSubjectScore.objects.filter(student_report_id__in=report_ids).delete()

        subject_score_rows: list[StudentReportSubjectScore] = []
        for student in students:
            report = all_reports.get(student.id)
            if not report:
                continue
            for row in student_subject_scores.get(student.id, {}).get("rows", []):
                subject_score_rows.append(
                    StudentReportSubjectScore(
                        student_report=report,
                        student=student,
                        subject_id=row["subject_id"],
                        sba_score=row["sba_score"],
                        exam_score=row["exam_score"],
                        total_score=row["total_score"],
                        grade=row["grade"],
                    )
                )

        StudentReportSubjectScore.objects.bulk_create(subject_score_rows)

        # ------------------------------------------------------------------ #
        # 8. Compute and save per-subject ranks within the class             #
        # ------------------------------------------------------------------ #
        _assign_subject_ranks(report_ids)

    return {
        "generated": len(to_create),
        "updated": len(to_update),
        "reports": (
            StudentReport.objects.filter(id__in=report_ids)
            .select_related("student", "student_class", "term", "academic_year")
            .prefetch_related("subject_scores__subject")
            .order_by("-overall_score")
        ),
    }

def _assign_subject_ranks(report_ids: list[int]) -> None:
    """
    For each subject, rank students in this class by total_score descending.
    Ties share the same rank.
    """
    scores = (
        StudentReportSubjectScore.objects.filter(student_report_id__in=report_ids)
        .order_by("subject_id", "-total_score")
        .values("id", "subject_id", "total_score")
    )

    # Group by subject
    by_subject: dict[int, list[dict]] = defaultdict(list)
    for s in scores:
        by_subject[s["subject_id"]].append(s)

    to_update: list[StudentReportSubjectScore] = []
    for subject_id, rows in by_subject.items():
        rank = 1
        for i, row in enumerate(rows):
            if i > 0 and row["total_score"] < rows[i - 1]["total_score"]:
                rank = i + 1
            obj = StudentReportSubjectScore(id=row["id"], rank=rank)
            to_update.append(obj)

    if to_update:
        StudentReportSubjectScore.objects.bulk_update(to_update, ["rank"])