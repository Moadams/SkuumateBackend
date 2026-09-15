"""Legacy facade — kept so other apps can call onboarding completion
checks without importing the application layer directly.

Prefer importing `OnboardingService` from `schools.services` in new code.
"""
from schools.services.onboarding import OnboardingService


def check_and_complete_onboarding(school):
    """
    Checks whether the school has completed all required onboarding steps.
    If all conditions are met and the flag isn't set yet, flips it to True.

    Call this after creating any of the above resources.
    """
    OnboardingService.check_and_complete(school)