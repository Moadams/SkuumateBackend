from django.db import models
from django.utils import timezone
from datetime import timedelta
from core.models import TimestampedModel


class Plan(TimestampedModel):

    class PlanType(models.TextChoices):
        LITE = "lite", "Lite"
        ADVANTAGE = "advantage", "Advantage"
        ENTERPRISE = "enterprise", "Enterprise"

    name = models.CharField(max_length=100)
    plan_type = models.CharField(
        max_length=20,
        choices=PlanType.choices,
        unique=True,
    )
    description = models.TextField(blank=True)
    tagline = models.CharField(max_length=255, blank=True)

    # ── Pricing ──────────────────────────────────────────────────
    price_per_term = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Price in GHS per academic term"
    )
    setup_fee = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="One-time setup fee in GHS"
    )

    # ── Hard limits ──────────────────────────────────────────────
    min_students = models.PositiveIntegerField(
        default=0,
        help_text="Minimum student count for this plan"
    )
    max_students = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Maximum student count. null = unlimited"
    )

    # ── Core features (all plans) ────────────────────────────────
    has_student_records = models.BooleanField(default=True)
    has_class_subject_setup = models.BooleanField(default=True)
    has_score_entry = models.BooleanField(default=True)
    has_report_cards = models.BooleanField(default=True)
    has_basic_broadsheet = models.BooleanField(default=True)
    has_fee_billing = models.BooleanField(default=True)
    has_payment_tracking = models.BooleanField(default=True)
    has_debtors_list = models.BooleanField(default=True)
    has_sms_alerts = models.BooleanField(default=True)
    has_admin_teacher_portal = models.BooleanField(default=True)
    has_attendance = models.BooleanField(default=True)

    # ── Advantage+ features ───────────────────────────────────────
    has_advanced_finance = models.BooleanField(default=False)
    has_income_expense_tracking = models.BooleanField(default=False)
    has_full_broadsheet = models.BooleanField(default=False)
    has_term_comparison = models.BooleanField(default=False)
    has_audit_logs = models.BooleanField(default=False)
    has_announcements = models.BooleanField(default=False)
    has_extended_sms = models.BooleanField(default=False)
    has_student_portal = models.BooleanField(default=False)
    has_export = models.BooleanField(default=False)

    # ── Enterprise features ───────────────────────────────────────
    has_advanced_analytics = models.BooleanField(default=False)
    has_multi_year_tracking = models.BooleanField(default=False)
    has_department_access_control = models.BooleanField(default=False)
    has_custom_report_cards = models.BooleanField(default=False)
    has_custom_report_formats = models.BooleanField(default=False)
    has_custom_branding = models.BooleanField(default=False)
    has_data_migration = models.BooleanField(default=False)
    has_priority_support = models.BooleanField(default=False)

    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["price_per_term"]

    def __str__(self):
        return f"{self.name} — GHS {self.price_per_term}/term"


class Subscription(TimestampedModel):

    class Status(models.TextChoices):
        TRIAL = "trial", "Trial"
        PENDING_PAYMENT = "pending_payment", "Pending Payment"
        ACTIVE = "active", "Active"
        PAST_DUE = "past_due", "Past Due"
        EXPIRED = "expired", "Expired"
        GRACE = "grace", "Grace Period"
        LOCKED = "locked", "Locked"
        CANCELLED = "cancelled", "Cancelled"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="subscriptions",
    )
    plan = models.ForeignKey(
        Plan,
        blank=True,
        null=True,
        on_delete=models.PROTECT,
        related_name="subscriptions",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.TRIAL,
    )
    is_paid = models.BooleanField(default=False)

    # ── Term reference ────────────────────────────────────────────
    # Subscription is tied to an academic term
    term = models.ForeignKey(
        "academics.Term",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="subscriptions",
        help_text="The academic term this subscription covers",
    )

    start_date = models.DateTimeField(default=timezone.now)
    end_date = models.DateTimeField()
    grace_end_date = models.DateTimeField(null=True, blank=True)

    # ── Activation ────────────────────────────────────────────────
    activated_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="activated_subscriptions",
    )
    notes = models.TextField(blank=True)
    is_current = models.BooleanField(default = False)

    TRIAL_DAYS = 90
    GRACE_DAYS = 7

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return f"{self.school.name} — {self.plan.name} ({self.status})"

    @property
    def activate(self):
        
        trail_days = self.TRIAL_DAYS if self.status == self.Status.TRIAL else 0
        self.start_date = self.term.start_date if self.term else timezone.now()
        self.end_date = self.start_date + timedelta(days=trail_days) if self.status == self.Status.TRIAL else self.term.end_date if self.term else self.start_date + timedelta(trail_days)
        self.grace_end_date = None
        Subscription.objects.filter(school=self.school, is_current=True).update(is_current=False)
        self.is_current = True
        self.save(update_fields=["status", "start_date", "end_date", "grace_end_date"])

    @property
    def is_on_trial(self):
        return self.status == self.Status.TRIAL

    @property
    def is_accessible(self):
        return self.status in (
            self.Status.TRIAL,
            self.Status.ACTIVE,
            self.Status.GRACE,
        )

    @property
    def is_read_only(self):
        return self.status == self.Status.GRACE

    @property
    def is_locked(self):
        return self.status in (
            self.Status.LOCKED,
            self.Status.CANCELLED,
        )

    @property
    def days_remaining(self):
        now = timezone.now()
        target = self.grace_end_date if self.status == self.Status.GRACE else self.end_date
        return max(0, (target - now).days)

    def sync_status(self):
        now = timezone.now()
        changed = False

        if self.status in (self.Status.TRIAL, self.Status.ACTIVE):
            if now > self.end_date:
                self.status = self.Status.GRACE
                self.grace_end_date = self.end_date + timedelta(days=self.GRACE_DAYS)
                changed = True

        elif self.status == self.Status.GRACE:
            if self.grace_end_date and now > self.grace_end_date:
                self.status = self.Status.LOCKED
                changed = True

        if changed:
            self.save(update_fields=["status", "grace_end_date"])

        return self


class SubscriptionPayment(TimestampedModel):
    class PaymentStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCESSFUL = "successful", "Successful"
        FAILED = "failed", "Failed"

    subscription = models.ForeignKey(
        Subscription, on_delete=models.CASCADE, related_name="payments"
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_reference = models.CharField(max_length=255, blank=True)
    provider = models.CharField(max_length=50, blank=True)
    status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
    )
