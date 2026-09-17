from django.db import transaction
from django.db.models import Sum
from rest_framework import serializers
from decimal import Decimal
from core.tenant_serializers import SchoolRelatedFieldsMixin
from django.shortcuts import get_object_or_404

from .models import (
    Expense,
    ExpenseType,
    FeeComponent,
    FeePayment,
    IncomeType,
    InvoiceLineItem,
    OtherIncome,
    PaymentAllocation,
    SchoolFeeInvoice,
)


class IncomeTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = IncomeType
        fields = ["id", "name", "description", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class ExpenseTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpenseType
        fields = ["id", "name", "description", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class FeeComponentSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeeComponent
        fields = ["id", "name", "description", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class InvoiceLineItemSerializer(serializers.ModelSerializer):
    fee_component_name = serializers.CharField(source="fee_component.name", read_only=True)
    paid_amount = serializers.SerializerMethodField()
    balance = serializers.SerializerMethodField()

    class Meta:
        model = InvoiceLineItem
        fields = [
            "id", "fee_component", "fee_component_name",
            "amount", "paid_amount", "balance", "created_at",
        ]
        read_only_fields = ["id", "paid_amount", "balance", "created_at"]

    def get_paid_amount(self, obj):
        return str(obj.payment_allocations.aggregate(total=Sum("amount"))["total"] or 0)

    def get_balance(self, obj):
        paid = obj.payment_allocations.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        return str(obj.amount - paid)


class SchoolFeeInvoiceListSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    student_id_number = serializers.CharField(source="student.student_id", read_only=True)
    term_name = serializers.CharField(source="term.get_name_display", read_only=True)
    academic_year_name = serializers.CharField(source="academic_year.name", read_only=True)
    klass_name = serializers.CharField(source="klass.name", read_only=True, allow_null=True)

    class Meta:
        model = SchoolFeeInvoice
        fields = [
            "id", "invoice_number", "student", "student_name", "student_id_number",
            "academic_year", "academic_year_name", "term", "term_name",
            "klass", "klass_name", "total_amount", "status",
            "due_date", "is_fully_paid", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "invoice_number", "total_amount", "is_fully_paid", "created_at", "updated_at"]


class SchoolFeeInvoiceDetailSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    student_id_number = serializers.CharField(source="student.student_id", read_only=True)
    term_name = serializers.CharField(source="term.get_name_display", read_only=True)
    academic_year_name = serializers.CharField(source="academic_year.name", read_only=True)
    klass_name = serializers.CharField(source="klass.name", read_only=True, allow_null=True)
    line_items = InvoiceLineItemSerializer(many=True, read_only=True)
    total_paid = serializers.SerializerMethodField()
    balance_due = serializers.SerializerMethodField()

    class Meta:
        model = SchoolFeeInvoice
        fields = [
            "id", "invoice_number", "student", "student_name", "student_id_number",
            "academic_year", "academic_year_name", "term", "term_name",
            "klass", "klass_name", "total_amount", "total_paid", "balance_due",
            "status", "due_date", "notes", "is_fully_paid",
            "line_items", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "invoice_number", "total_amount", "total_paid", "balance_due", "is_fully_paid", "created_at", "updated_at"]

    def get_total_paid(self, obj):
        total = obj.payments.aggregate(total=Sum("amount_paid"))["total"] or 0
        return str(total)

    def get_balance_due(self, obj):
        total_paid = obj.payments.aggregate(total=Sum("amount_paid"))["total"] or Decimal("0.00")
        return str(obj.total_amount - total_paid)


class InvoiceLineItemCreateSerializer(SchoolRelatedFieldsMixin, serializers.Serializer):
    school_related_fields = ("fee_component",)
    fee_component = serializers.PrimaryKeyRelatedField(queryset=FeeComponent.objects.all())
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0.01"))

class SchoolFeeInvoiceCreateSerializer(SchoolRelatedFieldsMixin, serializers.ModelSerializer):
    school_related_fields = ("student", "academic_year", "term", "klass")
    line_items = InvoiceLineItemCreateSerializer(many=True, allow_empty=False)

    class Meta:
        model = SchoolFeeInvoice
        fields = [
            "student", "academic_year", "term", "klass",
            "due_date", "notes", "line_items",
        ]

    def validate(self, attrs):
        school = self.context["school"]
        student = attrs.get("student", getattr(self.instance, "student", None))
        year = attrs.get("academic_year", getattr(self.instance, "academic_year", None))
        term = attrs.get("term", getattr(self.instance, "term", None))
        if term.academic_year_id != year.pk:
            raise serializers.ValidationError({"term": "Term must belong to the selected academic year."})
        if SchoolFeeInvoice.objects.filter(school=school, student=student, academic_year=year, term=term).exclude(pk=getattr(self.instance, "pk", None)).exists():
            raise serializers.ValidationError(
                "There is already an existings Fee invoice for this student in this academic year and term"
            )


        return attrs

    def validate_line_items(self, value):
        school = self.context["school"]
        seen_components = {}
        for idx, item in enumerate(value):
            component = item["fee_component"]
            if component.school != school:
                raise serializers.ValidationError(
                    f"Fee component '{component.name}' does not belong to this school."
                )
            if component.id in seen_components:
                raise serializers.ValidationError(
                    f"Duplicate fee component '{component.name}' at line {seen_components[component.id] + 1} and line {idx + 1}. Each fee component can only appear once."
                )
            seen_components[component.id] = idx
        return value

    @transaction.atomic
    def create(self, validated_data):
        line_items_data = validated_data.pop("line_items")
        school = self.context["school"]
        from schools.models import School
        School.objects.select_for_update().get(pk=school.pk)
        if SchoolFeeInvoice.objects.filter(school=school, student=validated_data["student"], academic_year=validated_data["academic_year"], term=validated_data["term"]).exists():
            raise serializers.ValidationError("An invoice already exists for this student and term.")
        invoice = SchoolFeeInvoice.objects.create(
            **validated_data,
        )
        total = Decimal("0.00")
        for item_data in line_items_data:
            InvoiceLineItem.objects.create(
                school=school,
                invoice=invoice,
                fee_component=item_data["fee_component"],
                amount=item_data["amount"],
            )
            total += item_data["amount"]
        invoice.total_amount = total
        invoice.save(update_fields=["total_amount"])
        return invoice

    @transaction.atomic
    def update(self, instance, validated_data):
        instance = SchoolFeeInvoice.objects.select_for_update().get(pk=instance.pk)
        financial_fields = {"student", "academic_year", "term", "klass", "line_items"}
        if financial_fields.intersection(validated_data) and instance.payments.exists():
            raise serializers.ValidationError("An invoice with payments can only have its notes and due date changed.")
        items = validated_data.pop("line_items", None)
        for name, value in validated_data.items():
            setattr(instance, name, value)
        if items is not None:
            instance.line_items.all().delete()
            for item in items:
                InvoiceLineItem.objects.create(school=instance.school, invoice=instance, **item)
            instance.total_amount = sum((item["amount"] for item in items), Decimal("0.00"))
        instance.save()
        return instance


class BulkInvoiceSerializer(serializers.Serializer):
    students = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=False,
    )
    academic_year = serializers.UUIDField()
    term = serializers.UUIDField()
    klass = serializers.UUIDField(required=False, allow_null=True)
    line_items = InvoiceLineItemCreateSerializer(many=True, allow_empty=False)
    due_date = serializers.DateField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True)

    def validate_line_items(self, value):
        ids = [item["fee_component"].pk for item in value]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError("Fee components must not be repeated.")
        return value


class PaymentAllocationSerializer(SchoolRelatedFieldsMixin, serializers.ModelSerializer):
    school_related_fields = ("line_item",)
    school_relation_paths = {"line_item": "invoice__school"}
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0.01"))
    line_item_detail = InvoiceLineItemSerializer(source="line_item", read_only=True)

    class Meta:
        model = PaymentAllocation
        fields = ["id", "line_item", "line_item_detail", "amount", "created_at"]
        read_only_fields = ["id", "created_at"]


class FeePaymentListSerializer(serializers.ModelSerializer):
    invoice_number = serializers.CharField(source="invoice.invoice_number", read_only=True)
    student_name = serializers.CharField(source="invoice.student.full_name", read_only=True)
    payment_method_display = serializers.CharField(source="get_payment_method_display", read_only=True)
    received_by_name = serializers.SerializerMethodField()

    class Meta:
        model = FeePayment
        fields = [
            "id", "invoice", "invoice_number", "student_name",
            "amount_paid", "payment_date", "payment_method", "payment_method_display",
            "reference_number", "notes", "received_by", "received_by_name",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_received_by_name(self, obj):
        if obj.received_by:
            return f"{obj.received_by.first_name} {obj.received_by.last_name}"
        return None


class FeePaymentCreateSerializer(SchoolRelatedFieldsMixin, serializers.ModelSerializer):
    school_related_fields = ("invoice",)
    amount_paid = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    allocations = PaymentAllocationSerializer(many=True, required=False)

    class Meta:
        model = FeePayment
        fields = [
            "invoice", "amount_paid", "payment_date",
            "payment_method", "reference_number", "notes", "allocations",
        ]

    def validate(self, attrs):
        invoice = attrs["invoice"]
        allocations = attrs.get("allocations", [])
        if allocations:
            ids = [a["line_item"].pk for a in allocations]
            if len(ids) != len(set(ids)):
                raise serializers.ValidationError({"allocations": "Line items must not be repeated."})
            if any(a["line_item"].invoice_id != invoice.pk for a in allocations):
                raise serializers.ValidationError({"allocations": "All line items must belong to this invoice."})
            total_allocated = sum(a["amount"] for a in allocations)
            if total_allocated != attrs["amount_paid"]:
                raise serializers.ValidationError(
                    "Total allocation amount must equal the payment amount."
                )
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        allocations_data = validated_data.pop("allocations", [])
        school = self.context["school"]
        invoice = get_object_or_404(SchoolFeeInvoice.objects.select_for_update(), pk=validated_data["invoice"].pk, school=school)
        validated_data["invoice"] = invoice
        if invoice.status in (SchoolFeeInvoice.Status.CANCELLED, SchoolFeeInvoice.Status.DRAFT):
            raise serializers.ValidationError("Payments require an issued invoice.")
        paid = invoice.payments.aggregate(total=Sum("amount_paid"))["total"] or Decimal("0.00")
        if validated_data["amount_paid"] > invoice.total_amount - paid:
            raise serializers.ValidationError({"amount_paid": "Payment exceeds the outstanding balance."})
        # Omitted allocations are distributed deterministically so component
        # reports reconcile with the payment ledger.
        if not allocations_data:
            remaining = validated_data["amount_paid"]
            for item in invoice.line_items.order_by("created_at", "pk"):
                allocated = item.payment_allocations.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
                amount = min(remaining, item.amount - allocated)
                if amount > 0:
                    allocations_data.append({"line_item": item, "amount": amount})
                    remaining -= amount
                if remaining == 0:
                    break
            if remaining:
                raise serializers.ValidationError("Invoice line balances do not cover this payment.")
        for allocation in allocations_data:
            item = invoice.line_items.filter(pk=allocation["line_item"].pk).first()
            if item is None:
                raise serializers.ValidationError({"allocations": "Invoice lines changed. Reload the invoice before recording payment."})
            allocation["line_item"] = item
            allocated = item.payment_allocations.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
            if allocation["amount"] > item.amount - allocated:
                raise serializers.ValidationError({"allocations": "Allocation exceeds the line item balance."})
        user = self.context.get("request").user if self.context.get("request") else None
        payment = FeePayment.objects.create(
            school=school,
            received_by=user,
            **validated_data,
        )
        for alloc_data in allocations_data:
            PaymentAllocation.objects.create(
                payment=payment,
                line_item=alloc_data["line_item"],
                amount=alloc_data["amount"],
            )
        payment._update_invoice_status()
        return payment


class OtherIncomeSerializer(SchoolRelatedFieldsMixin, serializers.ModelSerializer):
    school_related_fields = ("income_type",)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    income_type_name = serializers.CharField(source="income_type.name", read_only=True)
    received_by_name = serializers.SerializerMethodField()

    class Meta:
        model = OtherIncome
        fields = [
            "id", "income_type", "income_type_name", "amount", "date",
            "description", "reference_number", "received_by", "received_by_name",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "income_type_name", "received_by", "created_at", "updated_at"]

    def get_received_by_name(self, obj):
        if obj.received_by:
            return f"{obj.received_by.first_name} {obj.received_by.last_name}"
        return None


class ExpenseSerializer(SchoolRelatedFieldsMixin, serializers.ModelSerializer):
    school_related_fields = ("expense_type",)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    expense_type_name = serializers.CharField(source="expense_type.name", read_only=True)
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Expense
        fields = [
            "id", "expense_type", "expense_type_name", "amount", "date",
            "description", "reference_number", "receipt_number",
            "created_by", "created_by_name", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_by", "created_at", "updated_at"]

    def get_created_by_name(self, obj):
        if obj.created_by:
            return f"{obj.created_by.first_name} {obj.created_by.last_name}"
        return None


class FeePaymentUpdateSerializer(serializers.ModelSerializer):
    """Allow descriptive corrections without invalidating recorded allocations."""
    class Meta:
        model = FeePayment
        fields = ["payment_date", "payment_method", "reference_number", "notes"]

    def validate(self, attrs):
        if {"invoice", "amount_paid", "allocations", "received_by"}.intersection(self.initial_data):
            raise serializers.ValidationError("Invoice, amount, allocations and receiver cannot be changed on a recorded payment.")
        return attrs
