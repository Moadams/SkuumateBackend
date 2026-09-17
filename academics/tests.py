from datetime import date

from django.core.cache import cache
from django.test import TestCase

from academics.models import AcademicYear, Class, Subject, Term
from core.cache import CacheKeys
from schools.models import School


class AcademicsCacheInvalidationTests(TestCase):

    def setUp(self):
        cache.clear()
        self.school = School.objects.create(name="Cache School")

    def seed_onboarding_cache(self):
        cache.set(CacheKeys.school_onboarding(str(self.school.id)), {"stale": True})

    def test_class_create_invalidates_school_cache(self):
        self.seed_onboarding_cache()
        Class.objects.create(school=self.school, name="Primary 1")
        self.assertIsNone(cache.get(CacheKeys.school_onboarding(str(self.school.id))))

    def test_class_delete_invalidates_school_cache(self):
        cls = Class.objects.create(school=self.school, name="Primary 1")
        self.seed_onboarding_cache()
        cls.delete()
        self.assertIsNone(cache.get(CacheKeys.school_onboarding(str(self.school.id))))

    def test_subject_create_invalidates_school_cache(self):
        self.seed_onboarding_cache()
        Subject.objects.create(school=self.school, name="Mathematics")
        self.assertIsNone(cache.get(CacheKeys.school_onboarding(str(self.school.id))))

    def test_year_create_invalidates_school_cache(self):
        self.seed_onboarding_cache()
        AcademicYear.objects.create(
            school=self.school,
            name="2026/27",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )
        self.assertIsNone(cache.get(CacheKeys.school_onboarding(str(self.school.id))))

    def test_term_create_invalidates_school_cache(self):
        year = AcademicYear.objects.create(
            school=self.school,
            name="2026/27",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )
        self.seed_onboarding_cache()
        Term.objects.create(
            school=self.school,
            academic_year=year,
            name=Term.TermName.TERM_1,
            start_date=date(2026, 1, 10),
            end_date=date(2026, 4, 10),
        )
        self.assertIsNone(cache.get(CacheKeys.school_onboarding(str(self.school.id))))