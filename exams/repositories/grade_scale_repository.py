from academics.models import GradeScale


class GradeScaleRepository:

    @staticmethod
    def get(grading_system, school=None):
        qs = GradeScale.objects.filter(grading_system=grading_system)
        if school is not None:
            qs = qs.filter(school=school)
        return list(qs.order_by("min_score"))