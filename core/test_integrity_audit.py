import json
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from core import test_security
from finance.models import SchoolFeeInvoice


class IntegrityAuditTests(TestCase):
    def test_detects_invalid_link_without_changing_records(self):
        from schools.models import School
        from academics.models import AcademicYear, Term
        first = School.objects.create(name="First", school_code="S")
        second = School.objects.create(name="Second", school_code="s")
        year = AcademicYear.objects.create(school=first, name="2026", start_date="2026-01-01", end_date="2026-12-31")
        term = Term.objects.create(school=second, academic_year=year, name="term_1", start_date="2026-01-01", end_date="2026-04-01")
        output = StringIO()
        call_command("audit_integrity", stdout=output)
        data = json.loads(output.getvalue())
        self.assertEqual(data["findings"]["cross_school.academics.Term.academic_year"], 1)
        self.assertEqual(data["findings"]["school_codes.duplicate_groups"], 1)
        term.refresh_from_db()
        self.assertEqual(term.school_id, second.pk)
        self.assertEqual(term.academic_year_id, year.pk)
