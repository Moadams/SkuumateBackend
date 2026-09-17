"""Read-only review of tenancy and ledger consistency. Never repairs records."""
import json
from decimal import Decimal

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError
from django.db.models import Count, F, Q, Sum
from django.db.models.functions import Lower, Trim


class Command(BaseCommand):
    help = "Report cross-school links, inconsistent invoices and missing staff access without changing data."

    def add_arguments(self, parser):
        parser.add_argument("--database", default="default")
        parser.add_argument("--fail-on-issues", action="store_true")

    def handle(self, *args, **options):
        database = options["database"]
        findings = {}
        unavailable = []

        def check(name, callback):
            try:
                findings[name] = callback()
            except DatabaseError:
                unavailable.append(name)

        school_models = [m for m in apps.get_models() if any(f.name == "school" for f in m._meta.fields)]
        for model in school_models:
            for field in model._meta.fields:
                if not field.is_relation or field.name == "school" or not field.related_model:
                    continue
                if not any(f.name == "school" for f in field.related_model._meta.fields):
                    continue
                if (model._meta.label, field.name) in (("core.AuditLog", "actor"), ("subscriptions.Subscription", "activated_by")):
                    continue  # Platform operators legitimately act across schools.
                key = f"cross_school.{model._meta.label}.{field.name}"
                check(key, lambda m=model, f=field: m.objects.using(database).filter(**{f"{f.name}__isnull": False}).exclude(**{f"{f.name}__school_id": F("school_id")}).count())

        from schools.models import School
        from staff.models import StaffProfile
        from finance.models import SchoolFeeInvoice, FeePayment, PaymentAllocation
        check("school_codes.missing", lambda: School.objects.using(database).filter(Q(school_code__isnull=True) | Q(school_code="")).count())
        check("school_codes.duplicate_groups", lambda: School.objects.using(database).exclude(Q(school_code__isnull=True) | Q(school_code="")).annotate(code=Lower(Trim("school_code"))).values("code").annotate(n=Count("pk")).filter(n__gt=1).count())
        check("staff.unconfigured_access", lambda: StaffProfile.objects.using(database).exclude(role="admin").filter(positions__isnull=True, permission_grants__isnull=True, status="active").count())
        check("staff.foreign_positions", lambda: StaffProfile.objects.using(database).filter(positions__isnull=False).exclude(positions__school_id=F("school_id")).distinct().count())
        check("allocations.wrong_invoice", lambda: PaymentAllocation.objects.using(database).exclude(payment__invoice_id=F("line_item__invoice_id")).count())

        def invoice_checks():
            totals = statuses = overpaid = 0
            for invoice in SchoolFeeInvoice.objects.using(database).iterator():
                lines = invoice.line_items.using(database).aggregate(total=Sum("amount"))["total"] or Decimal("0")
                paid = invoice.payments.using(database).aggregate(total=Sum("amount_paid"))["total"] or Decimal("0")
                totals += lines != invoice.total_amount
                overpaid += paid > invoice.total_amount
                if invoice.status not in ("cancelled", "draft"):
                    expected = "paid" if paid >= invoice.total_amount else "partially_paid" if paid > 0 else "issued"
                    status_ok = invoice.status == expected or (expected == "issued" and invoice.status == "overdue")
                    statuses += not status_ok or invoice.is_fully_paid != (paid >= invoice.total_amount)
            return {"line_total_mismatch": totals, "status_mismatch": statuses, "overpaid": overpaid}
        check("invoices", invoice_checks)

        def payment_checks():
            missing = mismatch = 0
            for payment in FeePayment.objects.using(database).iterator():
                amount = payment.allocations.using(database).aggregate(total=Sum("amount"))["total"]
                missing += amount is None
                mismatch += amount is not None and amount != payment.amount_paid
            return {"missing_allocations": missing, "allocation_total_mismatch": mismatch}
        check("payments", payment_checks)
        report = {"read_only": True, "findings": findings, "unavailable_checks": unavailable}
        self.stdout.write(json.dumps(report, indent=2))
        def has_issues(value):
            return any(has_issues(v) for v in value.values()) if isinstance(value, dict) else bool(value)
        if options["fail_on_issues"] and (has_issues(findings) or unavailable):
            raise CommandError("Integrity issues or unavailable checks found; no data was changed.")
