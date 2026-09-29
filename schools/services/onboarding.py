"""
Onboarding business rule — tracks which setup steps a school has
completed and flips the completion flag once all are satisfied.

A school is considered onboarded when:
    1. The school profile contains all required core fields (+ school_code)
    2. At least one academic year is marked ``is_current``
    3. At least one term is marked ``is_current``
    4. There is at least one class AND one subject
    5. The school has an active or trial subscription

The stored ``School.onboarding_completed`` flag is a denormalization for
reporting/filtering only. Consumers must decide the onboarding screen from
the computed ``steps`` map, so the experience can never disagree with the
data after a step is later removed by the school.
"""
from typing import Dict, List, Optional

from .dto import OnboardingDTO, OnboardingStepsDTO

PROFILE_REQUIRED_FIELDS = (
    "name",
    "email",
    "phone",
    "address",
    "city",
    "country",
    "school_code",
)


def _profile_missing_fields(school) -> List[str]:
    """Return the required profile fields that are missing or blank."""
    missing = []
    for field in PROFILE_REQUIRED_FIELDS:
        value = getattr(school, field, None)
        if not value or not str(value).strip():
            missing.append(field)
    return missing


class OnboardingService:

    STEPS: tuple = (
        "school_profile",
        "academic_year",
        "term",
        "class_subject",
        "subscription",
    )

    @staticmethod
    def profile_missing_fields(school) -> List[str]:
        return _profile_missing_fields(school)

    @staticmethod
    def steps(school) -> OnboardingStepsDTO:
        return {
            "school_profile": not _profile_missing_fields(school),
            "academic_year": school.academic_years.filter(is_current=True).exists(),
            "term": school.terms.filter(is_current=True).exists(),
            "class_subject": school.classes.exists() and school.subjects.exists(),
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
    def current_step(school) -> Optional[str]:
        """First incomplete step in flow order, or None when completed."""
        steps = OnboardingService.steps(school)
        for key in OnboardingService.STEPS:
            if not steps[key]:
                return key
        return None

    @staticmethod
    def _resume_data(school, request=None):
        """Thin summary of already-saved data so the frontend can prefill
        each onboarding step without re-fetching full list endpoints."""
        profile = {field: getattr(school, field, None) for field in PROFILE_REQUIRED_FIELDS}
        logo = getattr(school, "logo", None)
        # ImageFieldFile is not JSON-serializable; return the URL or None.
        profile["logo"] = (
            request.build_absolute_uri(logo.url) if request else logo.url
        ) if bool(logo) else None

        return {
            "school": profile,
            "academic_years": list(
                school.academic_years.values("id", "name", "start_date", "end_date", "is_current")
                .order_by("-start_date")[:5]
            ),
            "terms": list(
                school.terms.values("id", "academic_year", "name", "start_date", "end_date", "is_current")
                .order_by("academic_year", "name")[:15]
            ),
            "classes": list(school.classes.values("id", "name", "is_active").order_by("name")[:50]),
            "subjects": list(school.subjects.values("id", "name", "code", "is_active").order_by("name")[:50]),
        }

    @staticmethod
    def build(school, include_data: bool = False, request=None) -> OnboardingDTO:
        OnboardingService.check_and_complete(school)
        steps = OnboardingService.steps(school)
        return OnboardingDTO(
            onboarding_completed=school.onboarding_completed,
            steps=steps,
            completed_count=sum(steps.values()),
            total_steps=len(OnboardingService.STEPS),
            current_step=OnboardingService.current_step(school),
            profile={
                "done": steps["school_profile"],
                "missing_fields": _profile_missing_fields(school),
            },
            data=OnboardingService._resume_data(school, request) if include_data else {},
        )