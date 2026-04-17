def resolve_grade(grading_system, score):
    """
    Given a GradingSystem and a numeric score,
    returns the matching GradeScale or None.

    Usage:
        grade = resolve_grade(grading_system, 78.5)
        print(grade.grade)   → "B2"
        print(grade.label)   → "Very Good"
    """
    from academics.models import GradeScale
    from decimal import Decimal

    score = Decimal(str(score))
    score = int(score)  # Floor the score

    return (
        GradeScale.objects
        .filter(
            grading_system=grading_system,
            min_score__lte=score,
            max_score__gte=score,
        )
        .first()
    )