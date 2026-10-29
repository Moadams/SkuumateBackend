import django_filters

from exams.models import StudentReport
from finance.models import FeePayment, SchoolFeeInvoice


class GuardianReportFilter(django_filters.FilterSet):
    academic_year = django_filters.UUIDFilter(field_name="academic_year_id")
    term = django_filters.UUIDFilter(field_name="term_id")

    class Meta:
        model = StudentReport
        fields = ("academic_year", "term")


class GuardianInvoiceFilter(django_filters.FilterSet):
    academic_year = django_filters.UUIDFilter(field_name="academic_year_id")
    term = django_filters.UUIDFilter(field_name="term_id")

    class Meta:
        model = SchoolFeeInvoice
        fields = ("academic_year", "term")


class GuardianInvoicePaymentFilter(django_filters.FilterSet):
    invoice = django_filters.UUIDFilter(field_name="invoice_id")
    academic_year = django_filters.UUIDFilter(field_name="invoice__academic_year_id")
    term = django_filters.UUIDFilter(field_name="invoice__term_id")
    payment_method = django_filters.ChoiceFilter(choices=FeePayment.PaymentMethod.choices)
    payment_date_from = django_filters.DateFilter(field_name="payment_date", lookup_expr="gte")
    payment_date_to = django_filters.DateFilter(field_name="payment_date", lookup_expr="lte")

    class Meta:
        model = FeePayment
        fields = ("invoice", "academic_year", "term", "payment_method")
