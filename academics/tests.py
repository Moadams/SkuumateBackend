from datetime import date

from django.core.cache import cache
from django.test import TestCase

from academics.models import AcademicYear, Class, Subject, Term
from core.cache import CacheKeys
from schools.models import School


class AcademicsCacheInvalidationTests(TestCase):
    """Every academic write must drop the school's cached onboarding payload."""

    def setUp(self):
        cache.clear()
        self.school = School.objects.create(name="Cache School")

    def seed_onboarding_cache(self):
        cache.set(CacheKeys.school_onboarding(str(self.school.id)), {"stale": True})

    def assert_cache_dropped(self):
        self.assertIsNone(cache.get(CacheKeys.school_onboarding(str(self.school.id))))

    def _year(self):
        return AcademicYear.objects.create(
            school=self.school,
            name="2026/27",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )

    def test_academic_writes_invalidate_the_school_cache(self):
        year = self._year()
        term = Term.objects.create(
            school=self.school,
            academic_year=year,
            name=Term.TermName.TERM_1,
            start_date=date(2026, 1, 10),
            end_date=date(2026, 4, 10),
        )
        klass = Class.objects.create(school=self.school, name="Primary 1")

        operations = {
            "subject": lambda: Subject.objects.create(
                school=self.school, name="Mathematics"
            ),
            "class": lambda: Class.objects.create(
                school=self.school, name="Primary 2"
            ),
            "class_delete": lambda: klass.delete(),
            "academic_year": lambda: AcademicYear.objects.create(
                school=self.school,
                name="2027/28",
                start_date=date(2027, 1, 1),
                end_date=date(2027, 12, 31),
            ),
            "term": lambda: Term.objects.create(
                school=self.school,
                academic_year=year,
                name=Term.TermName.TERM_2,
                start_date=date(2026, 5, 1),
                end_date=date(2026, 8, 1),
            ),
            "term_delete": lambda: term.delete(),
        }

        for name, operation in operations.items():
            with self.subTest(operation=name):
                self.seed_onboarding_cache()
                operation()
                self.assert_cache_dropped()
