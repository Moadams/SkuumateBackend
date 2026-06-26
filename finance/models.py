from django.db import models
from core.models import TimestampedModel


class IncomeType(TimestampedModel):
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="income_types")
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]
        unique_together = ["school", "name"]

    def __str__(self):
        return self.name


class ExpenseType(TimestampedModel):
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="expense_types")
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]
        unique_together = ["school", "name"]

    def __str__(self):
        return self.name


class FeeComponent(TimestampedModel):
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="fee_components")
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        unique_together = ["school", "name"]

    def __str__(self):
        return self.name


class SchoolFeeInvoice(TimestampedModel):

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ISSUED = "issued", "Issued"
        PARTIALLY_PAID = "partially_paid", "Partially Paid"
        PAID = "paid", "Paid"
        CANCELLED = "cancelled", "Cancelled"
        OVERDUE = "overdue", "Overdue"

    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="fee_invoices")
    student = models.ForeignKey("students.Student", on_delete=models.CASCADE, related_name="fee_invoices")
    academic_year = models.ForeignKey("academics.AcademicYear", on_delete=models.CASCADE, related_name="fee_invoices")
    term = models.ForeignKey("academics.Term", on_delete=models.CASCADE, related_name="fee_invoices")
    klass = models.ForeignKey("academics.Class", on_delete=models.SET_NULL, null=True, blank=True, related_name="fee_invoices")
    invoice_number = models.CharField(max_length=30, unique=True, editable=False)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    due_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    is_fully_paid = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
        unique_together = ["school", "student", "academic_year", "term"]

    def __str__(self):
        return f"{self.invoice_number} - {self.student} ({self.term})"

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            self.invoice_number = self._generate_invoice_number()
        super().save(*args, **kwargs)

    def _generate_invoice_number(self):
        import datetime
        
        year = datetime.date.today().year
        prefix = self.school.school_code.upper() if self.school.school_code else "SCH"
        last = SchoolFeeInvoice.objects.filter(
            school=self.school,
            invoice_number__startswith=f"{prefix}-INV-{year}"
        ).count() + 1
        return f"{prefix}-INV-{year}-{last:04d}"


class InvoiceLineItem(TimestampedModel):
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="line_items", null=True)
    invoice = models.ForeignKey(SchoolFeeInvoice, on_delete=models.CASCADE, related_name="line_items")
    fee_component = models.ForeignKey(FeeComponent, on_delete=models.CASCADE, related_name="line_items")
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ["fee_component__name"]
        unique_together = ["invoice", "fee_component"]

    def __str__(self):
        return f"{self.fee_component.name}: {self.amount}"


class FeePayment(TimestampedModel):

    class PaymentMethod(models.TextChoices):
        CASH = "cash", "Cash"
        BANK_TRANSFER = "bank_transfer", "Bank Transfer"
        MOBILE_MONEY = "mobile_money", "Mobile Money"
        CHEQUE = "cheque", "Cheque"

    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="fee_payments")
    invoice = models.ForeignKey(SchoolFeeInvoice, on_delete=models.CASCADE, related_name="payments")
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2)
    payment_date = models.DateField()
    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices)
    reference_number = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    received_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="received_payments"
    )

    class Meta:
        ordering = ["-payment_date", "-created_at"]

    def __str__(self):
        return f"{self.amount_paid} on {self.invoice.invoice_number}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self._update_invoice_status()

    def _update_invoice_status(self):
        total_paid = FeePayment.objects.filter(invoice=self.invoice).aggregate(
            total=models.Sum("amount_paid")
        )["total"] or 0
        invoice = self.invoice
        if total_paid >= invoice.total_amount:
            invoice.status = SchoolFeeInvoice.Status.PAID
            invoice.is_fully_paid = True
        elif total_paid > 0:
            invoice.status = SchoolFeeInvoice.Status.PARTIALLY_PAID
        invoice.save(update_fields=["status", "is_fully_paid"])


class PaymentAllocation(TimestampedModel):
    payment = models.ForeignKey(FeePayment, on_delete=models.CASCADE, related_name="allocations")
    line_item = models.ForeignKey(InvoiceLineItem, on_delete=models.CASCADE, related_name="payment_allocations")
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ["line_item__fee_component__name"]

    def __str__(self):
        return f"{self.amount} to {self.line_item.fee_component.name}"


class OtherIncome(TimestampedModel):
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="other_incomes")
    income_type = models.ForeignKey(IncomeType, on_delete=models.CASCADE, related_name="incomes")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField()
    description = models.TextField()
    reference_number = models.CharField(max_length=100, blank=True)
    received_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="received_incomes"
    )

    class Meta:
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return f"{self.income_type.name}: {self.amount} ({self.date})"


class Expense(TimestampedModel):
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="expenses")
    expense_type = models.ForeignKey(ExpenseType, on_delete=models.CASCADE, related_name="expenses")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField()
    description = models.TextField()
    reference_number = models.CharField(max_length=100, blank=True)
    receipt_number = models.CharField(max_length=100, blank=True)
    created_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="created_expenses"
    )

    class Meta:
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return f"{self.expense_type.name}: {self.amount} ({self.date})"
