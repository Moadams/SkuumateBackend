"""
Onboarding business rule — tracks which setup steps a school has
completed and flips the completion flag once all are satisfied.
"""
from typing import Dict

from .dto import OnboardingDTO, OnboardingStepsDTO


class OnboardingService:

    STEPS: tuple = (
        "academic_year",
        "term",
        "class",
        "subject",
        "subscription",
    )

    @staticmethod
    def steps(school) -> OnboardingStepsDTO:
        return {
            "academic_year": school.academic_years.exists(),
            "term": school.terms.exists(),
            "class": school.classes.exists(),
            "subject": school.subjects.exists(),
            "subscription": school.subscriptions.filter(
                status__in=["active", "trial"]
            ).exists(),
        }

    @staticmethod
    def is_complete(school) -> bool:
        return all(OnboardingService.steps(school).values())

    @staticmethod
    def check_and_complete(school) -> bool:
        """
        Marks the school as onboarded if every step is satisfied.
        Idempotent. Returns True when the flag is set.
        """
        if school.onboarding_completed:
            return True
        if not OnboardingService.is_complete(school):
            return False
        school.onboarding_completed = True
        school.save(update_fields=["onboarding_completed", "updated_at"])
        return True

    @staticmethod
    def build(school) -> OnboardingDTO:
        OnboardingService.check_and_complete(school)
        steps = OnboardingService.steps(school)
        return OnboardingDTO(
            onboarding_completed=school.onboarding_completed,
            steps=steps,
            completed_count=sum(steps.values()),
            total_steps=len(OnboardingService.STEPS),
        )