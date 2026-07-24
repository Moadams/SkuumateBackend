from decimal import Decimal
from django.db import models, transaction
from django.db.models import Sum
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, status
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.views import APIView

from core.mixins import AuditLogMixin, ExportMixin
from core.models import AuditLog
from core.permissions import IsAdmin, IsFinanceManager, OrPermission
from core.responses import ApiResponse
from core.utils import log_action

from .models import (
    IncomeType, ExpenseType, FeeComponent,
    SchoolFeeInvoice, InvoiceLineItem, FeePayment,
    PaymentAllocation, OtherIncome, Expense,
)
from .serializers import (
    IncomeTypeSerializer, ExpenseTypeSerializer, FeeComponentSerializer,
    SchoolFeeInvoiceListSerializer, SchoolFeeInvoiceDetailSerializer,
    SchoolFeeInvoiceCreateSerializer, BulkInvoiceSerializer,
    FeePaymentListSerializer, FeePaymentCreateSerializer,
    OtherIncomeSerializer, ExpenseSerializer,
)
from .filters import (
    FeeComponentFilter, SchoolFeeInvoiceFilter, FeePaymentFilter,
    OtherIncomeFilter, ExpenseFilter,
)


class IsAdminOrFinanceManager(OrPermission):
    permissions = [IsAdmin, IsFinanceManager]


class IsAdminOrFinanceManagerReadOnly(OrPermission):
    permissions = [IsAdmin, IsFinanceManager]


# ─── Fee Components ────────────────────────────────────────────────

class FeeComponentListCreateView(AuditLogMixin, ExportMixin, generics.ListCreateAPIView):
    permission_classes = [IsAdminOrFinanceManager]
    serializer_class = FeeComponentSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = FeeComponentFilter
    search_fields = ["name"]
    ordering_fields = ["name", "created_at"]
    ordering = ["name"]
    audit_resource = "FeeComponent"

    def get_queryset(self):
        return FeeComponent.objects.filter(school=self.request.user.school)

    def get_audit_description(self, instance):
        return f"Fee component {instance.name} created"

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return ApiResponse.success(data=serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return ApiResponse.created(
            data=serializer.data,
            message="Fee component created successfully.",
        )


class FeeComponentDetailView(AuditLogMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminOrFinanceManager]
    serializer_class = FeeComponentSerializer
    audit_resource = "FeeComponent"

    def get_queryset(self):
        return FeeComponent.objects.filter(school=self.request.user.school)

    def get_audit_description(self, instance):
        if self.request.method in ["PUT","PATCH"]:
            return f"Fee component {instance.name} updated"
        elif self.request.method == "DELETE":
            return f"Fee component {instance.name} deleted"
        else:
            return f"Fee component {instance.name} retrieved"

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        return ApiResponse.success(data=self.get_serializer(instance).data)



# ─── Income Types ──────────────────────────────────────────────────

class IncomeTypeListCreateView(AuditLogMixin, generics.ListCreateAPIView):
    permission_classes = [IsAdminOrFinanceManager]
    serializer_class = IncomeTypeSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ["name"]
    ordering_fields = ["name", "created_at"]
    ordering = ["name"]
    audit_resource = "IncomeType"

    def get_queryset(self):
        return IncomeType.objects.filter(school=self.request.user.school)

    def get_audit_description(self, instance):
        return f"Income type '{instance.name}' created"

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return ApiResponse.success(data=serializer.data)



class IncomeTypeDetailView(AuditLogMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminOrFinanceManager]
    serializer_class = IncomeTypeSerializer
    audit_resource = "IncomeType"

    def get_queryset(self):
        return IncomeType.objects.filter(school=self.request.user.school)

    def get_audit_description(self, instance):
        if self.request.method in ["PUT", "PATCH"]:
            return f"Income type {instance.name} updated"
        elif self.request.method == "DELETE":
            return f"Income type {instance.name} deleted"
        else:
            return f"Income type {instance.name} retrieved"


# ─── Expense Types ─────────────────────────────────────────────────

class ExpenseTypeListCreateView(AuditLogMixin, generics.ListCreateAPIView):
    permission_classes = [IsAdminOrFinanceManager]
    serializer_class = ExpenseTypeSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ["name"]
    ordering_fields = ["name", "created_at"]
    ordering = ["name"]
    audit_resource = "ExpenseType"

    def get_queryset(self):
        return ExpenseType.objects.filter(school=self.request.user.school)
    
    def get_audit_description(self, instance):
        return f"Expense type '{instance.name}' created"

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return ApiResponse.success(data=serializer.data)


class ExpenseTypeDetailView(AuditLogMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminOrFinanceManager]
    serializer_class = ExpenseTypeSerializer
    audit_resource = "ExpenseType"

    def get_queryset(self):
        return ExpenseType.objects.filter(school=self.request.user.school)

    def get_audit_description(self, instance):
        if self.request.method in ["PUT", "PATCH"]:
            return f"Expense type {instance.name} updated"
        elif self.request.method == "DELETE":
            return f"Expense type {instance.name} deleted"
        else:
            return f"Expense type {instance.name} retrieved"

# ─── School Fee Invoices ───────────────────────────────────────────

class SchoolFeeInvoiceListCreateView(AuditLogMixin, generics.ListCreateAPIView):
    permission_classes = [IsAdminOrFinanceManager]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = SchoolFeeInvoiceFilter
    search_fields = ["invoice_number", "student__first_name", "student__last_name", "student__student_id"]
    ordering_fields = ["created_at", "due_date", "total_amount", "status"]
    ordering = ["-created_at"]
    audit_resource = "SchoolFeeInvoice"

    def get_serializer_class(self):
        if self.request.method == "POST":
            return SchoolFeeInvoiceCreateSerializer
        return SchoolFeeInvoiceListSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["school"] = self.request.user.school
        return ctx


    def get_audit_description(self, instance):
        return f"Student invoice {instance.id} created."

    def get_queryset(self):
        return SchoolFeeInvoice.objects.filter(
            school=self.request.user.school
        ).select_related("student", "academic_year", "term", "klass")

    

class SchoolFeeInvoiceDetailView(AuditLogMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminOrFinanceManager]
    audit_resource = "SchoolFeeInvoice"

    def get_serializer_class(self):
        if self.request.method in ("PUT", "PATCH"):
            return SchoolFeeInvoiceCreateSerializer
        return SchoolFeeInvoiceDetailSerializer

    def get_queryset(self):
        return SchoolFeeInvoice.objects.filter(
            school=self.request.user.school
        ).select_related("student", "academic_year", "term", "klass").prefetch_related(
            "line_items__fee_component", "line_items__payment_allocations", "payments"
        )

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["school"] = self.request.user.school
        return ctx

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        return ApiResponse.success(data=self.get_serializer(instance).data)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return ApiResponse.success(
            data=SchoolFeeInvoiceDetailSerializer(serializer.instance).data,
            message="Invoice updated successfully.",
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.payments.exists():
            return ApiResponse.error(
                message="Cannot delete an invoice with payments.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        self.perform_destroy(instance)
        return ApiResponse.success(message="Invoice deleted successfully.")


class BulkInvoiceCreateView(APIView):
    permission_classes = [IsAdminOrFinanceManager]

    @transaction.atomic
    def post(self, request):
        school = request.user.school
        serializer = BulkInvoiceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        from academics.models import AcademicYear, Term, Class
        from students.models import Student

        try:
            academic_year = AcademicYear.objects.get(pk=serializer.validated_data["academic_year"], school=school)
        except AcademicYear.DoesNotExist:
            return ApiResponse.error(message="Academic year not found.", status_code=404)

        try:
            term = Term.objects.get(pk=serializer.validated_data["term"], school=school)
        except Term.DoesNotExist:
            return ApiResponse.error(message="Term not found.", status_code=404)

        klass = None
        klass_id = serializer.validated_data.get("klass")
        if klass_id:
            try:
                klass = Class.objects.get(pk=klass_id, school=school)
            except Class.DoesNotExist:
                return ApiResponse.error(message="Class not found.", status_code=404)

        students = Student.objects.filter(
            pk__in=serializer.validated_data["students"],
            school=school,
        )
        if not students.exists():
            return ApiResponse.error(message="No valid students found.", status_code=400)

        line_items_data = serializer.validated_data["line_items"]
        due_date = serializer.validated_data.get("due_date")
        notes = serializer.validated_data.get("notes", "")

        created = []
        skipped = []
        for student in students:
            exists = SchoolFeeInvoice.objects.filter(
                school=school, student=student,
                academic_year=academic_year, term=term,
            ).exists()
            if exists:
                skipped.append(str(student.id))
                continue

            invoice = SchoolFeeInvoice.objects.create(
                school=school,
                student=student,
                academic_year=academic_year,
                term=term,
                klass=klass,
                due_date=due_date,
                notes=notes,
            )
            total = 0
            for item in line_items_data:
                InvoiceLineItem.objects.create(
                    invoice=invoice,
                    fee_component=item["fee_component"],
                    amount=item["amount"],
                )
                total += float(item["amount"])
            invoice.total_amount = str(total)
            invoice.save(update_fields=["total_amount"])
            created.append(invoice.id)

        log_action(
            action=AuditLog.Action.CREATE,
            resource="SchoolFeeInvoice",
            description=f"Bulk created {len(created)} invoices, {len(skipped)} skipped",
            request=request,
            metadata={"created": len(created), "skipped": len(skipped)},
        )

        return ApiResponse.created(
            data={
                "created_count": len(created),
                "skipped_count": len(skipped),
                "invoice_ids": [str(pid) for pid in created],
            },
            message=f"{len(created)} invoice(s) created successfully.",
        )


# ─── Fee Payments ──────────────────────────────────────────────────

class FeePaymentListCreateView(AuditLogMixin, generics.ListCreateAPIView):
    permission_classes = [IsAdminOrFinanceManager]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = FeePaymentFilter
    search_fields = ["invoice__invoice_number", "reference_number"]
    ordering_fields = ["payment_date", "amount_paid", "created_at"]
    ordering = ["-payment_date"]
    audit_resource = "FeePayment"

    def get_serializer_class(self):
        if self.request.method == "POST":
            return FeePaymentCreateSerializer
        return FeePaymentListSerializer

    def get_queryset(self):
        return FeePayment.objects.filter(
            school=self.request.user.school
        ).select_related("invoice__student", "received_by")

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["school"] = self.request.user.school
        return ctx

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return ApiResponse.success(data=serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = serializer.save()
        log_action(
            action=AuditLog.Action.CREATE,
            resource=self.audit_resource,
            resource_id=str(payment.pk),
            description=f"Payment of {payment.amount_paid} received for {payment.invoice.invoice_number}",
            request=self.request,
        )
        return ApiResponse.created(
            data=FeePaymentListSerializer(payment).data,
            message="Payment recorded successfully.",
        )


class FeePaymentDetailView(AuditLogMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminOrFinanceManager]
    serializer_class = FeePaymentListSerializer
    audit_resource = "FeePayment"

    def get_queryset(self):
        return FeePayment.objects.filter(
            school=self.request.user.school
        ).select_related("invoice__student", "received_by")

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        return ApiResponse.success(data=self.get_serializer(instance).data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return ApiResponse.success(message="Payment deleted successfully.")


class InvoicePaymentsListView(generics.ListAPIView):
    permission_classes = [IsAdminOrFinanceManager]
    serializer_class = FeePaymentListSerializer

    def get_queryset(self):
        invoice_id = self.kwargs.get("invoice_id")
        return FeePayment.objects.filter(
            school=self.request.user.school,
            invoice_id=invoice_id,
        ).select_related("invoice__student", "received_by")

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return ApiResponse.success(data=serializer.data)


# ─── Other Income ──────────────────────────────────────────────────

class OtherIncomeListCreateView(AuditLogMixin, generics.ListCreateAPIView):
    permission_classes = [IsAdminOrFinanceManager]
    serializer_class = OtherIncomeSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = OtherIncomeFilter
    search_fields = ["description", "reference_number"]
    ordering_fields = ["date", "amount", "created_at"]
    ordering = ["-date"]
    audit_resource = "OtherIncome"

    def get_queryset(self):
        return OtherIncome.objects.filter(
            school=self.request.user.school
        ).select_related("income_type", "received_by")

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["school"] = self.request.user.school
        return ctx

    def perform_create(self, serializer):
        instance = serializer.save(
            school=self.request.user.school,
            received_by=self.request.user,
        )
        log_action(
            action=AuditLog.Action.CREATE,
            resource=self.audit_resource,
            resource_id=str(instance.pk),
            description=f"Other income '{instance.description}' recorded",
            request=self.request,
        )
        return instance

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return ApiResponse.success(data=serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return ApiResponse.created(
            data=serializer.data,
            message="Income recorded successfully.",
        )


class OtherIncomeDetailView(AuditLogMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminOrFinanceManager]
    serializer_class = OtherIncomeSerializer
    audit_resource = "OtherIncome"

    def get_queryset(self):
        return OtherIncome.objects.filter(
            school=self.request.user.school
        ).select_related("income_type", "received_by")

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        return ApiResponse.success(data=self.get_serializer(instance).data)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return ApiResponse.success(
            data=serializer.data,
            message="Income updated successfully.",
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return ApiResponse.success(message="Income deleted successfully.")


# ─── Expenses ──────────────────────────────────────────────────────

class ExpenseListCreateView(AuditLogMixin, generics.ListCreateAPIView):
    permission_classes = [IsAdminOrFinanceManager]
    serializer_class = ExpenseSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = ExpenseFilter
    search_fields = ["description", "reference_number", "receipt_number"]
    ordering_fields = ["date", "amount", "created_at"]
    ordering = ["-date"]
    audit_resource = "Expense"

    def get_queryset(self):
        return Expense.objects.filter(
            school=self.request.user.school
        ).select_related("expense_type", "created_by")

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["school"] = self.request.user.school
        return ctx

    def perform_create(self, serializer):
        instance = serializer.save(
            school=self.request.user.school,
            created_by=self.request.user,
        )
        log_action(
            action=AuditLog.Action.CREATE,
            resource=self.audit_resource,
            resource_id=str(instance.pk),
            description=f"Expense '{instance.description}' recorded",
            request=self.request,
        )
        return instance

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return ApiResponse.success(data=serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return ApiResponse.created(
            data=serializer.data,
            message="Expense recorded successfully.",
        )


class ExpenseDetailView(AuditLogMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminOrFinanceManager]
    serializer_class = ExpenseSerializer
    audit_resource = "Expense"

    def get_queryset(self):
        return Expense.objects.filter(
            school=self.request.user.school
        ).select_related("expense_type", "created_by")

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        return ApiResponse.success(data=self.get_serializer(instance).data)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return ApiResponse.success(
            data=serializer.data,
            message="Expense updated successfully.",
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return ApiResponse.success(message="Expense deleted successfully.")


# ─── Financial Overview Dashboard ──────────────────────────────────

class FinancialOverviewView(APIView):
    permission_classes = [IsAdminOrFinanceManager]

    def get(self, request):
        school = request.user.school
        academic_year_id = request.query_params.get("academic_year_id")
        term_id = request.query_params.get("term_id")

        # ── Filter helpers ─────────────────────────────────────────
        invoice_qs = SchoolFeeInvoice.objects.filter(school=school)
        payment_qs = FeePayment.objects.filter(school=school)
        other_income_qs = OtherIncome.objects.filter(school=school)
        expense_qs = Expense.objects.filter(school=school)

        if academic_year_id:
            invoice_qs = invoice_qs.filter(academic_year_id=academic_year_id)
            payment_qs = payment_qs.filter(invoice__academic_year_id=academic_year_id)
        if term_id:
            invoice_qs = invoice_qs.filter(term_id=term_id)
            payment_qs = payment_qs.filter(invoice__term_id=term_id)

        # ── Summary cards ──────────────────────────────────────────
        total_fee_income = payment_qs.aggregate(total=Sum("amount_paid"))["total"] or 0
        total_other_income = other_income_qs.aggregate(total=Sum("amount"))["total"] or 0
        total_income = float(total_fee_income) + float(total_other_income)
        total_expenses = expense_qs.aggregate(total=Sum("amount"))["total"] or 0
        net_income = total_income - float(total_expenses)

        invoice_status_agg = list(
            invoice_qs.values("status")
            .annotate(count=models.Count("id"), total=models.Sum("total_amount"))
            .order_by("status")
        )
        pending_amount = invoice_qs.filter(is_fully_paid=False).aggregate(
            total=models.Sum("total_amount")
        )["total"] or 0
        overdue_count = invoice_qs.filter(
            status=SchoolFeeInvoice.Status.OVERDUE
        ).count()

        # ── Monthly trends (last 12 months) ────────────────────────
        from datetime import date, timedelta
        today = date.today()
        twelve_months_ago = today - timedelta(days=365)
        months = []
        for i in range(12):
            first = date(today.year, today.month, 1) - timedelta(days=30 * (11 - i))
            month_start = first.replace(day=1)
            if month_start.month == 12:
                month_end = date(month_start.year + 1, 1, 1)
            else:
                month_end = date(month_start.year, month_start.month + 1, 1)

            fee = payment_qs.filter(
                payment_date__gte=month_start, payment_date__lt=month_end
            ).aggregate(total=Sum("amount_paid"))["total"] or 0

            other = other_income_qs.filter(
                date__gte=month_start, date__lt=month_end
            ).aggregate(total=Sum("amount"))["total"] or 0

            exp = expense_qs.filter(
                date__gte=month_start, date__lt=month_end
            ).aggregate(total=Sum("amount"))["total"] or 0

            months.append({
                "month": month_start.strftime("%Y-%m"),
                "label": month_start.strftime("%b %Y"),
                "fee_income": str(fee),
                "other_income": str(other),
                "total_income": str(float(fee) + float(other)),
                "expenses": str(exp),
            })

        # ── Income breakdown (for pie charts) ──────────────────────
        allocations_qs = PaymentAllocation.objects.filter(payment__school=school)
        if academic_year_id:
            allocations_qs = allocations_qs.filter(payment__invoice__academic_year_id=academic_year_id)
        if term_id:
            allocations_qs = allocations_qs.filter(payment__invoice__term_id=term_id)

        fee_by_component = list(
            allocations_qs
            .values(name=models.F("line_item__fee_component__name"))
            .annotate(total=Sum("amount"))
            .order_by("-total")
        )
        other_by_type = list(
            other_income_qs
            .values(name=models.F("income_type__name"))
            .annotate(total=Sum("amount"))
            .order_by("-total")
        )
        expense_by_type = list(
            expense_qs
            .values(name=models.F("expense_type__name"))
            .annotate(total=Sum("amount"))
            .order_by("-total")
        )

        # ── Recent transactions ────────────────────────────────────
        recent_payments = list(
            payment_qs.select_related("invoice__student", "invoice__academic_year")
            .order_by("-payment_date", "-created_at")[:10]
            .values(
                type=models.Value("fee_payment", output_field=models.CharField()),
                date=models.F("payment_date"),
                description=models.F("invoice__invoice_number"),
                student_name=models.F("invoice__student__first_name"),
                amount=models.F("amount_paid"),
            )
        )
        recent_other = list(
            other_income_qs.select_related("income_type")
            .order_by("-date", "-created_at")[:5]
            .values(
                type=models.Value("other_income", output_field=models.CharField()),
                income_date=models.F("date"),
                income_description=models.F("description"),
                category=models.F("income_type__name"),
                income_amount=models.F("amount"),
            )
        )
        recent_expenses = list(
            expense_qs.select_related("expense_type")
            .order_by("-date", "-created_at")[:5]
            .values(
                type=models.Value("expense", output_field=models.CharField()),
                expense_date=models.F("date"),
                income_description=models.F("description"),
                category=models.F("expense_type__name"),
                expense_amount=models.F("amount"),
            )
        )

        def serialize_value(val):
            if isinstance(val, dict):
                return {k: serialize_value(v) for k, v in val.items()}
            if isinstance(val, list):
                return [serialize_value(v) for v in val]
            if isinstance(val, (Decimal, float)):
                return str(val)
            return val

        return ApiResponse.success(
            data=serialize_value({
                "summary": {
                    "total_fee_income": total_fee_income,
                    "total_other_income": total_other_income,
                    "total_income": total_income,
                    "total_expenses": total_expenses,
                    "net_income": net_income,
                    "pending_invoice_amount": pending_amount,
                    "overdue_invoice_count": overdue_count,
                },
                "invoice_status_distribution": [
                    {
                        "status": item["status"],
                        "count": item["count"],
                        "total_amount": item["total"],
                    }
                    for item in invoice_status_agg
                ],
                "monthly_trends": months,
                "income_breakdown": {
                    "by_component": [
                        {"name": item["name"], "total": item["total"]}
                        for item in fee_by_component
                    ],
                    "by_income_type": [
                        {"name": item["name"], "total": item["total"]}
                        for item in other_by_type
                    ],
                },
                "expense_breakdown": {
                    "by_type": [
                        {"name": item["name"], "total": item["total"]}
                        for item in expense_by_type
                    ],
                },
                "recent_transactions": {
                    "payments": recent_payments,
                    "other_income": recent_other,
                    "expenses": recent_expenses,
                },
            })
        )


# ─── Reports ───────────────────────────────────────────────────────

class IncomeStatementView(APIView):
    permission_classes = [IsAdminOrFinanceManager]

    def get(self, request):
        school = request.user.school
        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")
        academic_year_id = request.query_params.get("academic_year_id")
        term_id = request.query_params.get("term_id")

        # ── Base querysets ────────────────────────────────────────
        allocations_qs = PaymentAllocation.objects.filter(
            payment__school=school,
        )
        other_income_qs = OtherIncome.objects.filter(school=school)
        expenses_qs = Expense.objects.filter(school=school)

        # ── Apply filters ─────────────────────────────────────────
        if start_date:
            allocations_qs = allocations_qs.filter(payment__payment_date__gte=start_date)
            other_income_qs = other_income_qs.filter(date__gte=start_date)
            expenses_qs = expenses_qs.filter(date__gte=start_date)
        if end_date:
            allocations_qs = allocations_qs.filter(payment__payment_date__lte=end_date)
            other_income_qs = other_income_qs.filter(date__lte=end_date)
            expenses_qs = expenses_qs.filter(date__lte=end_date)
        if academic_year_id:
            allocations_qs = allocations_qs.filter(
                payment__invoice__academic_year_id=academic_year_id
            )
        if term_id:
            allocations_qs = allocations_qs.filter(
                payment__invoice__term_id=term_id
            )

        # ── Fee income grouped by fee component (DB aggregation) ──
        fee_by_component = list(
            allocations_qs
            .values(name=models.F("line_item__fee_component__name"))
            .annotate(total=Sum("amount"))
            .order_by("-total")
        )

        # ── Other income grouped by income type (DB aggregation) ──
        other_by_type = list(
            other_income_qs
            .values(name=models.F("income_type__name"))
            .annotate(total=Sum("amount"))
            .order_by("-total")
        )

        # ── Expenses grouped by expense type (DB aggregation) ─────
        expense_by_type = list(
            expenses_qs
            .values(name=models.F("expense_type__name"))
            .annotate(total=Sum("amount"))
            .order_by("-total")
        )

        # ── Compute totals from grouped results (no extra queries) ─
        total_fee_income = sum(item["total"] for item in fee_by_component) or 0
        total_other_income = sum(item["total"] for item in other_by_type) or 0
        total_income = float(total_fee_income) + float(total_other_income)
        total_expenses = sum(item["total"] for item in expense_by_type) or 0
        net_income = total_income - float(total_expenses)

        return ApiResponse.success(data={
            "income": {
                "fee_income": {
                    "items": [
                        {"name": item["name"], "total": str(item["total"])}
                        for item in fee_by_component
                    ],
                    "total": str(total_fee_income),
                },
                "other_income": {
                    "items": [
                        {"name": item["name"], "total": str(item["total"])}
                        for item in other_by_type
                    ],
                    "total": str(total_other_income),
                },
                "total_income": str(total_income),
            },
            "expenses": {
                "items": [
                    {"name": item["name"], "total": str(item["total"])}
                    for item in expense_by_type
                ],
                "total_expenses": str(total_expenses),
            },
            "net_income": str(net_income),
            "filters": {
                "start_date": start_date,
                "end_date": end_date,
                "academic_year_id": academic_year_id,
                "term_id": term_id,
            },
        })


class IncomeByTypeReportView(APIView):
    permission_classes = [IsAdminOrFinanceManager]

    def get(self, request):
        school = request.user.school
        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")
        academic_year_id = request.query_params.get("academic_year_id")
        term_id = request.query_params.get("term_id")

        # Fee income by component
        allocations_qs = PaymentAllocation.objects.filter(
            payment__school=school,
        )
        if start_date:
            allocations_qs = allocations_qs.filter(payment__payment_date__gte=start_date)
        if end_date:
            allocations_qs = allocations_qs.filter(payment__payment_date__lte=end_date)
        if academic_year_id:
            allocations_qs = allocations_qs.filter(payment__invoice__academic_year_id=academic_year_id)
        if term_id:
            allocations_qs = allocations_qs.filter(payment__invoice__term_id=term_id)

        fee_income_by_component = (
            allocations_qs
            .values("line_item__fee_component__name")
            .annotate(total=Sum("amount"))
            .order_by("-total")
        )

        # Other income by income type
        other_income_qs = OtherIncome.objects.filter(school=school)
        if start_date:
            other_income_qs = other_income_qs.filter(date__gte=start_date)
        if end_date:
            other_income_qs = other_income_qs.filter(date__lte=end_date)

        other_income_by_type = (
            other_income_qs
            .values("income_type__name")
            .annotate(total=Sum("amount"))
            .order_by("-total")
        )

        return ApiResponse.success(data={
            "fee_income_by_component": [
                {"component": item["line_item__fee_component__name"], "total": str(item["total"])}
                for item in fee_income_by_component
            ],
            "other_income_by_type": [
                {"income_type": item["income_type__name"], "total": str(item["total"])}
                for item in other_income_by_type
            ],
        })


class ExpenseByTypeReportView(APIView):
    permission_classes = [IsAdminOrFinanceManager]

    def get(self, request):
        school = request.user.school
        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")

        expenses_qs = Expense.objects.filter(school=school)
        if start_date:
            expenses_qs = expenses_qs.filter(date__gte=start_date)
        if end_date:
            expenses_qs = expenses_qs.filter(date__lte=end_date)

        expenses_by_type = (
            expenses_qs
            .values("expense_type__name")
            .annotate(total=Sum("amount"))
            .order_by("-total")
        )

        total_expenses = expenses_qs.aggregate(total=Sum("amount"))["total"] or 0

        return ApiResponse.success(data={
            "total_expenses": str(total_expenses),
            "expenses_by_type": [
                {"expense_type": item["expense_type__name"], "total": str(item["total"])}
                for item in expenses_by_type
            ],
        })
