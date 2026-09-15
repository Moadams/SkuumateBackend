"""
School details use case — assembles the full console overview projection
for a school by composing its section projectors and shared business
rule services.
"""
from .attendance import AttendanceStatsService
from .dto import SchoolDetailsDTO
from .finance import SchoolFinanceService
from .onboarding import OnboardingService
from .projectors import (
    AcademicsProjector,
    CommunicationsProjector,
    ExamsProjector,
    SchoolProjector,
    StaffProjector,
    StudentsProjector,
    SubscriptionProjector,
)


class SchoolDetailsService:
    """Use case: "give me everything about this school in one read model"."""

    def get_details(self, school) -> SchoolDetailsDTO:
        return SchoolDetailsDTO(
            school=SchoolProjector.build(school),
            subscription=SubscriptionProjector.build(school),
            academics=AcademicsProjector.build(school),
            staff=StaffProjector.build(school),
            students=StudentsProjector.build(school),
            finance=SchoolFinanceService.build(school, self._current_term(school)),
            attendance=AttendanceStatsService.build(school, self._current_term(school)),
            communications=CommunicationsProjector.build(school),
            exams=ExamsProjector.build(school),
            onboarding=OnboardingService.build(school),
        )

    @staticmethod
    def _current_term(school):
        return school.terms.filter(is_current=True).first()