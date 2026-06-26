from django.urls import path

from .views import (
    FeeComponentListCreateView, FeeComponentDetailView,
    IncomeTypeListCreateView, IncomeTypeDetailView,
    ExpenseTypeListCreateView, ExpenseTypeDetailView,
    SchoolFeeInvoiceListCreateView, SchoolFeeInvoiceDetailView,
    BulkInvoiceCreateView,
    FeePaymentListCreateView, FeePaymentDetailView,
    InvoicePaymentsListView,
    OtherIncomeListCreateView, OtherIncomeDetailView,
    ExpenseListCreateView, ExpenseDetailView,
    FinancialOverviewView,
    IncomeStatementView, IncomeByTypeReportView, ExpenseByTypeReportView,
)

urlpatterns = [
    # Fee Components
    path("fee-components/", FeeComponentListCreateView.as_view(), name="fee-component-list"),
    path("fee-components/<uuid:pk>/", FeeComponentDetailView.as_view(), name="fee-component-detail"),

    # Income Types
    path("income-types/", IncomeTypeListCreateView.as_view(), name="income-type-list"),
    path("income-types/<uuid:pk>/", IncomeTypeDetailView.as_view(), name="income-type-detail"),

    # Expense Types
    path("expense-types/", ExpenseTypeListCreateView.as_view(), name="expense-type-list"),
    path("expense-types/<uuid:pk>/", ExpenseTypeDetailView.as_view(), name="expense-type-detail"),

    # Invoices
    path("invoices/", SchoolFeeInvoiceListCreateView.as_view(), name="invoice-list"),
    path("invoices/bulk/", BulkInvoiceCreateView.as_view(), name="invoice-bulk-create"),
    path("invoices/<uuid:pk>/", SchoolFeeInvoiceDetailView.as_view(), name="invoice-detail"),
    path("invoices/<uuid:invoice_id>/payments/", InvoicePaymentsListView.as_view(), name="invoice-payments"),

    # Payments
    path("payments/", FeePaymentListCreateView.as_view(), name="payment-list"),
    path("payments/<uuid:pk>/", FeePaymentDetailView.as_view(), name="payment-detail"),

    # Other Income
    path("other-incomes/", OtherIncomeListCreateView.as_view(), name="other-income-list"),
    path("other-incomes/<uuid:pk>/", OtherIncomeDetailView.as_view(), name="other-income-detail"),

    # Expenses
    path("expenses/", ExpenseListCreateView.as_view(), name="expense-list"),
    path("expenses/<uuid:pk>/", ExpenseDetailView.as_view(), name="expense-detail"),

    # Overview Dashboard
    path("overview/", FinancialOverviewView.as_view(), name="financial-overview"),

    # Reports
    path("reports/income-statement/", IncomeStatementView.as_view(), name="report-income-statement"),
    path("reports/income-by-type/", IncomeByTypeReportView.as_view(), name="report-income-by-type"),
    path("reports/expense-by-type/", ExpenseByTypeReportView.as_view(), name="report-expense-by-type"),
]
