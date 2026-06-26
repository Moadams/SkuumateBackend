from django.contrib import admin

from .models import (
    IncomeType, ExpenseType, FeeComponent,
    SchoolFeeInvoice, InvoiceLineItem, FeePayment,
    PaymentAllocation, OtherIncome, Expense,
)


@admin.register(IncomeType)
class IncomeTypeAdmin(admin.ModelAdmin):
    list_display = ["name", "school"]
    search_fields = ["name"]


@admin.register(ExpenseType)
class ExpenseTypeAdmin(admin.ModelAdmin):
    list_display = ["name", "school"]
    search_fields = ["name"]


@admin.register(FeeComponent)
class FeeComponentAdmin(admin.ModelAdmin):
    list_display = ["name", "school", "is_active"]
    search_fields = ["name"]
    list_filter = ["is_active"]


class InvoiceLineItemInline(admin.TabularInline):
    model = InvoiceLineItem
    extra = 0
    readonly_fields = ["amount"]


class PaymentAllocationInline(admin.TabularInline):
    model = PaymentAllocation
    extra = 0
    readonly_fields = ["amount"]


class FeePaymentInline(admin.TabularInline):
    model = FeePayment
    extra = 0
    readonly_fields = ["amount_paid", "payment_date", "payment_method"]


@admin.register(SchoolFeeInvoice)
class SchoolFeeInvoiceAdmin(admin.ModelAdmin):
    list_display = ["invoice_number", "student", "term", "total_amount", "status", "is_fully_paid", "due_date"]
    search_fields = ["invoice_number", "student__first_name", "student__last_name"]
    list_filter = ["status", "is_fully_paid", "term"]
    inlines = [InvoiceLineItemInline, FeePaymentInline]


@admin.register(FeePayment)
class FeePaymentAdmin(admin.ModelAdmin):
    list_display = ["invoice", "amount_paid", "payment_date", "payment_method"]
    search_fields = ["invoice__invoice_number", "reference_number"]
    list_filter = ["payment_method", "payment_date"]
    inlines = [PaymentAllocationInline]


@admin.register(OtherIncome)
class OtherIncomeAdmin(admin.ModelAdmin):
    list_display = ["income_type", "amount", "date", "description"]
    search_fields = ["description", "reference_number"]
    list_filter = ["income_type", "date"]


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ["expense_type", "amount", "date", "description"]
    search_fields = ["description", "reference_number", "receipt_number"]
    list_filter = ["expense_type", "date"]
