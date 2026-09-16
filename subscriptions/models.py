from django.db import models
from django.utils import timezone
from datetime import timedelta
from core.models import TimestampedModel


class Feature(TimestampedModel):
    """A platform-level capability that may be granted to packages."""
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=80, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["category", "name"]

    def __str__(self):
        return self.name


class Package(TimestampedModel):
    """
    A sellable platform package (supersedes the legacy ``Plan`` model).
    Feature entitlements live in ``PackageFeature`` and usage restrictions
    in ``PackageLimit`` so new capabilities never require schema changes.
    """

    class PlanType(models.TextChoices):
        LITE = "lite", "Lite"
        ADVANTAGE = "advantage", "Advantage"
        ENTERPRISE = "enterprise", "Enterprise"

    class BillingPeriod(models.TextChoices):
        TERM = "TERM", "Term"
        MONTH = "MONTH", "Month"
        YEAR = "YEAR", "Year"

    name = models.CharField(max_length=100)
    code = models.CharField(max_length=100, unique=True)
    plan_type = models.CharField(
        max_length=20,
        choices=PlanType.choices,
        blank=True,
        null=True,
        help_text="Legacy display tier. Not used for feature gating.",
    )
    description = models.TextField(blank=True)
    tagline = models.CharField(max_length=255, blank=True)

    # ── Pricing ──────────────────────────────────────────────────
    price = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Price per billing period"
    )
    setup_fee = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="One-time setup fee"
    )
    billing_period = models.CharField(
        max_length=10,
        choices=BillingPeriod.choices,
        default=BillingPeriod.TERM,
    )
    currency = models.CharField(max_length=3, default="GHS")

    # ── Student range (pricing/display metadata) ─────────────────
    minimum_students = models.PositiveIntegerField(default=0)
    maximum_students = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Maximum student count for pricing. null = unlimited"
    )

    # ── Visibility ────────────────────────────────────────────────
    is_active = models.BooleanField(default=True)
    is_public = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "price"]

    def __str__(self):
        return f"{self.name} — {self.currency} {self.price}/{self.get_billing_period_display().lower()}"


class PackageFeature(TimestampedModel):
    """Entitlement linking a package to a feature."""
    package = models.ForeignKey(
        Package,
        on_delete=models.CASCADE,
        related_name="package_features",
    )
    feature = models.ForeignKey(
        Feature,
        on_delete=models.CASCADE,
        related_name="package_features",
    )
    is_enabled = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["package", "feature"],
                name="uniq_package_feature",
            ),
        ]
        ordering = ["feature__category", "feature__name"]

    def __str__(self):
        return f"{self.package.name} → {self.feature.name}"


class PackageLimit(TimestampedModel):
    """A numeric usage restriction for a package."""
    package = models.ForeignKey(
        Package,
        on_delete=models.CASCADE,
        related_name="package_limits",
    )
    key = models.CharField(max_length=80)
    name = models.CharField(max_length=120)
    value = models.PositiveIntegerField()
    description = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["package", "key"],
                name="uniq_package_limit_key",
            ),
        ]
        ordering = ["key"]

    def __str__(self):
        return f"{self.package.name} → {self.key}={self.value}"


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
        Package,
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