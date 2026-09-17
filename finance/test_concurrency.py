from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier
from types import SimpleNamespace

from django.db import close_old_connections
from django.test import TransactionTestCase, skipUnlessDBFeature
from rest_framework.exceptions import ValidationError

from accounts.models import User
from academics.models import AcademicYear, Term
from finance.models import SchoolFeeInvoice, InvoiceLineItem, FeeComponent, FeePayment
from finance.serializers import FeePaymentCreateSerializer
from schools.models import School
from students.models import Student


@skipUnlessDBFeature("has_select_for_update")
class ConcurrentPaymentTests(TransactionTestCase):
    def test_two_payments_cannot_both_spend_the_same_balance(self):
        school = School.objects.create(name="Concurrency", school_code="CON")
        user = User.objects.create_user(email="con@example.com", school=school, role="admin")
        year = AcademicYear.objects.create(school=school, name="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
        term = Term.objects.create(school=school, academic_year=year, name="term_1", start_date=date(2026, 1, 1), end_date=date(2026, 4, 1))
        student = Student.objects.create(school=school, first_name="A", last_name="B", gender="male")
        invoice = SchoolFeeInvoice.objects.create(school=school, student=student, academic_year=year, term=term, total_amount="100.00")
        component = FeeComponent.objects.create(school=school, name="Tuition")
        InvoiceLineItem.objects.create(school=school, invoice=invoice, fee_component=component, amount="100.00")
        barrier = Barrier(2)

        def pay():
            close_old_connections()
            try:
                serializer = FeePaymentCreateSerializer(data={"invoice": str(invoice.pk), "amount_paid": "60.00", "payment_date": "2026-01-15", "payment_method": "cash"}, context={"school": school, "request": SimpleNamespace(user=user)})
                serializer.is_valid(raise_exception=True)
                barrier.wait(timeout=10)
                try:
                    serializer.save()
                    return "created"
                except ValidationError:
                    return "rejected"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(pay) for _ in range(2)]
            results = [future.result(timeout=20) for future in futures]
        self.assertCountEqual(results, ["created", "rejected"])
        self.assertEqual(FeePayment.objects.count(), 1)
