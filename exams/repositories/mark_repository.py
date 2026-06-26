from exams.models import StudentMark


class MarkRepository:

    @staticmethod
    def get_marks(*, school, klass, term, students, report_scheme):
        student_ids = [s.id for s in students]

        sba_ids = list(report_scheme.sba_components.values_list("id", flat=True))
        exam_id = report_scheme.main_exam.id
 
        qs = StudentMark.objects.filter(
            school=school,
            student_id__in=student_ids,
            student_class=klass,
            term=term,
        ).select_related("assessment").only("student_id", "subject_id", "assessment_id", "score")

        return qs, sba_ids, exam_id