"""
School finance business rules — revenue, expenses, outstanding
balances, and collection rates for a given school and term.
"""
from decimal import Decimal
from typing import Optional

from django.db.models import Count, OuterRef, Subquery, Sum

from .dto import FinanceDTO


class SchoolFinanceService:
    """All finance reads are scoped to a school (and optionally a term)."""

    @staticmethod
    def term_revenue(school, term) -> Decimal:
        from finance.models import FeePayment

        if term is None:
            return Decimal("0")
        result = (
            FeePayment.objects
            .filter(
                school=school,
                payment_date__gte=term.start_date,
                payment_date__lte=term.end_date,
            )
            .aggregate(total=Sum("amount_paid"))
        )
        return result["total"] or Decimal("0")

    @staticmethod
    def term_expenses(school, term) -> Decimal:
        from finance.models import Expense

        if term is None:
            return Decimal("0")
        result = (
            Expense.objects
            .filter(
                school=school,
                date__gte=term.start_date,
                date__lte=term.end_date,
            )
            .aggregate(total=Sum("amount"))
        )
        return result["total"] or Decimal("0")

    @staticmethod
    def outstanding_balance(school) -> Decimal:
        """Sum of (invoice total − paid) for every open invoice."""
        from finance.models import FeePayment, SchoolFeeInvoice

        paid_subquery = (
            FeePayment.objects
            .filter(invoice=OuterRef("pk"))
            .values("invoice")
            .annotate(total=Sum("amount_paid"))
            .values("total")
        )
        open_invoices = (
            SchoolFeeInvoice.objects
            .filter(school=school, is_fully_paid=False)
            .exclude(status=SchoolFeeInvoice.Status.CANCELLED)
            .annotate(paid=Subquery(paid_subquery))
        )
        return sum(
            (invoice.total_amount - (invoice.paid or Decimal("0")))
            for invoice in open_invoices
        )

    @staticmethod
    def overdue_invoice_count(school) -> int:
        from finance.models import SchoolFeeInvoice

        return SchoolFeeInvoice.objects.filter(
            school=school,
            is_fully_paid=False,
            status=SchoolFeeInvoice.Status.OVERDUE,
        ).count()

    @staticmethod
    def invoice_status_breakdown(school) -> dict:
        from finance.models import SchoolFeeInvoice

        breakdown = (
            SchoolFeeInvoice.objects
            .filter(school=school)
            .values("status")
            .annotate(count=Count("id"))
        )
        return {row["status"]: row["count"] for row in breakdown}

    @staticmethod
    def collected_percentage(school) -> float:
        """Percentage of total issued amount that has been collected."""
        from finance.models import SchoolFeeInvoice

        issued = SchoolFeeInvoice.objects.filter(
            school=school, is_fully_paid=False
        ).exclude(status=SchoolFeeInvoice.Status.CANCELLED)
        issued_total = float(
            issued.aggregate(total=Sum("total_amount"))["total"] or 0
        )
        if issued_total == 0:
            return 0
        outstanding = float(SchoolFinanceService.outstanding_balance(school))
        return round(((issued_total - outstanding) / issued_total) * 100, 1)

    @staticmethod
    def build(school, term) -> FinanceDTO:
        from finance.models import ExpenseType, FeeComponent, IncomeType

        revenue = SchoolFinanceService.term_revenue(school, term)
        expenses = SchoolFinanceService.term_expenses(school, term)

        return FinanceDTO(
            currency="GHS",
            term_revenue=revenue,
            term_expenses=expenses,
            term_net=revenue - expenses,
            outstanding_balance=SchoolFinanceService.outstanding_balance(school),
            overdue_invoices=SchoolFinanceService.overdue_invoice_count(school),
            collected_percentage=SchoolFinanceService.collected_percentage(school),
            invoice_status_breakdown=SchoolFinanceService.invoice_status_breakdown(school),
            income_types=list(
                IncomeType.objects.filter(school=school).values_list("name", flat=True)
            ),
            expense_types=list(
                ExpenseType.objects.filter(school=school).values_list("name", flat=True)
            ),
            fee_components=list(
                FeeComponent.objects.filter(
                    school=school, is_active=True
                ).values_list("name", flat=True)
            ),
        )