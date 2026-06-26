import django_filters
from .models import FeeComponent, SchoolFeeInvoice, FeePayment, OtherIncome, Expense


class FeeComponentFilter(django_filters.FilterSet):
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = FeeComponent
        fields = ["is_active"]


class SchoolFeeInvoiceFilter(django_filters.FilterSet):
    student = django_filters.UUIDFilter(field_name="student__id")
    academic_year = django_filters.UUIDFilter(field_name="academic_year__id")
    term = django_filters.UUIDFilter(field_name="term__id")
    klass = django_filters.UUIDFilter(field_name="klass__id")
    status = django_filters.ChoiceFilter(choices=SchoolFeeInvoice.Status.choices)
    is_fully_paid = django_filters.BooleanFilter()
    due_date_from = django_filters.DateFilter(field_name="due_date", lookup_expr="gte")
    due_date_to = django_filters.DateFilter(field_name="due_date", lookup_expr="lte")
    created_from = django_filters.DateFilter(field_name="created_at", lookup_expr="gte")
    created_to = django_filters.DateFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = SchoolFeeInvoice
        fields = [
            "student", "academic_year", "term", "klass",
            "status", "is_fully_paid",
        ]


class FeePaymentFilter(django_filters.FilterSet):
    invoice = django_filters.UUIDFilter(field_name="invoice__id")
    student = django_filters.UUIDFilter(field_name="invoice__student__id")
    payment_method = django_filters.ChoiceFilter(choices=FeePayment.PaymentMethod.choices)
    payment_date_from = django_filters.DateFilter(field_name="payment_date", lookup_expr="gte")
    payment_date_to = django_filters.DateFilter(field_name="payment_date", lookup_expr="lte")

    class Meta:
        model = FeePayment
        fields = ["invoice", "payment_method"]


class OtherIncomeFilter(django_filters.FilterSet):
    income_type = django_filters.UUIDFilter(field_name="income_type__id")
    date_from = django_filters.DateFilter(field_name="date", lookup_expr="gte")
    date_to = django_filters.DateFilter(field_name="date", lookup_expr="lte")

    class Meta:
        model = OtherIncome
        fields = ["income_type"]


class ExpenseFilter(django_filters.FilterSet):
    expense_type = django_filters.UUIDFilter(field_name="expense_type__id")
    date_from = django_filters.DateFilter(field_name="date", lookup_expr="gte")
    date_to = django_filters.DateFilter(field_name="date", lookup_expr="lte")

    class Meta:
        model = Expense
        fields = ["expense_type"]
