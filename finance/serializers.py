from django.db import transaction
from rest_framework import serializers
from .models import (
    IncomeType, ExpenseType, FeeComponent,
    SchoolFeeInvoice, InvoiceLineItem, FeePayment,
    PaymentAllocation, OtherIncome, Expense
)
from django.db.models import Sum


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
        paid = float(obj.payment_allocations.aggregate(total=Sum("amount"))["total"] or 0)
        return str(float(obj.amount) - paid)


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
        total_paid = float(obj.payments.aggregate(total=Sum("amount_paid"))["total"] or 0)
        return str(float(obj.total_amount) - total_paid)


class InvoiceLineItemCreateSerializer(serializers.Serializer):
    fee_component = serializers.PrimaryKeyRelatedField(queryset=FeeComponent.objects.all())
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)


class SchoolFeeInvoiceCreateSerializer(serializers.ModelSerializer):
    line_items = InvoiceLineItemCreateSerializer(many=True)

    class Meta:
        model = SchoolFeeInvoice
        fields = [
            "student", "academic_year", "term", "klass",
            "due_date", "notes", "line_items",
        ]

    def validate(self, attrs):
        school = self.context["school"]
        if SchoolFeeInvoice.objects.filter(school = school, student = attrs.get("student"), academic_year = attrs.get("academic_year"), term=attrs.get("term")).exists():
            raise serializers.ValidationError(
                "There is already an existings Fee invoice for this student in this academic year and term"
            )
        return attrs

    def validate_line_items(self, value):
        school = self.context["school"]
        for item in value:
            component = item["fee_component"]
            if component.school != school:
                raise serializers.ValidationError(
                    f"Fee component '{component.name}' does not belong to this school."
                )
        return value

    @transaction.atomic
    def create(self, validated_data):
        line_items_data = validated_data.pop("line_items")
        school = self.context["school"]
        invoice = SchoolFeeInvoice.objects.create(
            **validated_data,
        )
        total = 0
        for item_data in line_items_data:
            InvoiceLineItem.objects.create(
                school=school,
                invoice=invoice,
                fee_component=item_data["fee_component"],
                amount=item_data["amount"],
            )
            total += float(item_data["amount"])
        invoice.total_amount = str(total)
        invoice.save(update_fields=["total_amount"])
        return invoice


class BulkInvoiceSerializer(serializers.Serializer):
    students = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=False,
    )
    academic_year = serializers.UUIDField()
    term = serializers.UUIDField()
    klass = serializers.UUIDField(required=False, allow_null=True)
    line_items = InvoiceLineItemCreateSerializer(many=True)
    due_date = serializers.DateField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True)


class PaymentAllocationSerializer(serializers.ModelSerializer):
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


class FeePaymentCreateSerializer(serializers.ModelSerializer):
    allocations = PaymentAllocationSerializer(many=True, required=False)

    class Meta:
        model = FeePayment
        fields = [
            "invoice", "amount_paid", "payment_date",
            "payment_method", "reference_number", "notes", "allocations",
        ]

    def validate(self, attrs):
        allocations = attrs.get("allocations", [])
        if allocations:
            total_allocated = sum(float(a["amount"]) for a in allocations)
            if abs(total_allocated - float(attrs["amount_paid"])) > 0.01:
                raise serializers.ValidationError(
                    "Total allocation amount must equal the payment amount."
                )
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        allocations_data = validated_data.pop("allocations", [])
        school = self.context["school"]
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


class OtherIncomeSerializer(serializers.ModelSerializer):
    income_type_name = serializers.CharField(source="income_type.name", read_only=True)
    received_by_name = serializers.SerializerMethodField()

    class Meta:
        model = OtherIncome
        fields = [
            "id", "income_type", "income_type_name", "amount", "date",
            "description", "reference_number", "received_by", "received_by_name",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_received_by_name(self, obj):
        if obj.received_by:
            return f"{obj.received_by.first_name} {obj.received_by.last_name}"
        return None


class ExpenseSerializer(serializers.ModelSerializer):
    expense_type_name = serializers.CharField(source="expense_type.name", read_only=True)
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Expense
        fields = [
            "id", "expense_type", "expense_type_name", "amount", "date",
            "description", "reference_number", "receipt_number",
            "created_by", "created_by_name", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_created_by_name(self, obj):
        if obj.created_by:
            return f"{obj.created_by.first_name} {obj.created_by.last_name}"
        return None
