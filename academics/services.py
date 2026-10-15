class AcademicsService:

    @staticmethod
    def _current_term(school):
        from academics.models import Term
        return Term.objects.filter(school=school, is_current=True).first()


# Ghana Education Service BECE "Stanine" (Standard Nine) scale. Grades run 1–9
# with *lower* grades being better; BECE results are aggregated over the best
# six subjects (6 is the best possible aggregate). A score of 50 and above
# (grades 1–6) is treated as a pass.
GES_BECE_GRADING_SYSTEM_NAME = "GES BECE"

GES_BECE_GRADE_SCALES = [
    {"grade": "1", "label": "Highest", "min_score": "90.00", "max_score": "100.00", "is_passing": True},
    {"grade": "2", "label": "Higher", "min_score": "80.00", "max_score": "89.00", "is_passing": True},
    {"grade": "3", "label": "High", "min_score": "70.00", "max_score": "79.00", "is_passing": True},
    {"grade": "4", "label": "High Average", "min_score": "60.00", "max_score": "69.00", "is_passing": True},
    {"grade": "5", "label": "Average", "min_score": "55.00", "max_score": "59.00", "is_passing": True},
    {"grade": "6", "label": "Low Average", "min_score": "50.00", "max_score": "54.00", "is_passing": True},
    {"grade": "7", "label": "Low", "min_score": "45.00", "max_score": "49.00", "is_passing": False},
    {"grade": "8", "label": "Lower", "min_score": "40.00", "max_score": "44.00", "is_passing": False},
    {"grade": "9", "label": "Lowest", "min_score": "0.00", "max_score": "39.00", "is_passing": False},
]


class GradingSystemService:
    """Default grading systems seeded for a school."""

    @staticmethod
    def seed_ges_bece(school):
        """Create the GES BECE grading system (and its nine bands) for ``school``.

        Idempotent: safe to call more than once for the same school.
        """
        from django.db import transaction

        from academics.models import GradeScale, GradingSystem

        with transaction.atomic():
            grading_system, _ = GradingSystem.objects.get_or_create(
                school=school,
                name=GES_BECE_GRADING_SYSTEM_NAME,
                defaults={
                    "description": (
                        "Ghana Education Service BECE (Standard Nine) grading "
                        "scale."
                    ),
                    "max_score": 100,
                    "pass_mark": 50,
                },
            )
            for position, scale in enumerate(GES_BECE_GRADE_SCALES, start=1):
                GradeScale.objects.get_or_create(
                    grading_system=grading_system,
                    grade=scale["grade"],
                    defaults={
                        "school": school,
                        "label": scale["label"],
                        "min_score": scale["min_score"],
                        "max_score": scale["max_score"],
                        "is_passing": scale["is_passing"],
                        "position": position,
                    },
                )
        return grading_system
