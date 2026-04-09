def check_and_complete_onboarding(school):
    """
    Checks whether the school has completed all required onboarding steps.
    If all conditions are met and the flag isn't set yet, flips it to True.

    Conditions:
        - At least one academic year
        - At least one term
        - At least one class
        - At least one subject

    Call this after creating any of the above resources.
    """
    if school.onboarding_completed:
        return

    has_academic_year = school.academic_years.exists()
    has_term = school.terms.exists()
    has_class = school.classes.exists()
    has_subject = school.subjects.exists()
    has_subscription = school.subscriptions.filter(
                status__in=["active", "trial"]
            ).exists()

    if all([has_academic_year, has_term, has_class, has_subject, has_subscription]):
        school.onboarding_completed = True
        school.save(update_fields=["onboarding_completed", "updated_at"])