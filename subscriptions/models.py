from datetime import timedelta

from django.db import models
from django.utils import timezone

from core.models import TimestampedModel


class Feature(TimestampedModel):
    """A platform-level capability that may be granted to packages."""
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=80, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("category", "name")

    def __str__(self):
        return self.name


class Package(TimestampedModel):
    """
    A sellable platform package.
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
        help_text="Price per billing period",
    )
    setup_fee = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="One-time setup fee",
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
        help_text="Maximum student count for pricing. null = unlimited",
    )

    # ── Visibility ────────────────────────────────────────────────
    is_active = models.BooleanField(default=True)
    is_public = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("display_order", "price")

    def __str__(self):
        return (
            f"{self.name} — {self.currency} {self.price}/"
            f"{self.get_billing_period_display().lower()}"
        )

    @property
    def is_free(self) -> bool:
        return self.price == 0


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
        constraints = (
            models.UniqueConstraint(
                fields=["package", "feature"],
                name="uniq_package_feature",
            ),
        )
        ordering = ("feature__category", "feature__name")

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
        default=Status.ACTIVE,
    )
    is_paid = models.BooleanField(default=False)

    term = models.ForeignKey(
        "academics.Term",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="subscriptions",
        help_text="The academic term this subscription covers",
    )

    start_date = models.DateField(default=timezone.now)
    end_date = models.DateField()
    grace_end_date = models.DateField(null=True, blank=True)

    # ── Activation ────────────────────────────────────────────────
    activated_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="activated_subscriptions",
    )
    notes = models.TextField(blank=True)
    is_current = models.BooleanField(default=False)

    ACTIVE_DAYS = 90
    GRACE_DAYS = 7

    class Meta:
        ordering = ("-start_date",)

    def __str__(self):
        plan_name = self.plan.name if self.plan else "No plan"
        return f"{self.school.name} — {plan_name} ({self.status})"

    # ── Status helpers ────────────────────────────────────────────

    @property
    def is_on_trial(self) -> bool:
        return self.status == self.Status.ACTIVE

    @property
    def is_accessible(self) -> bool:
        return self.status in (
            self.Status.ACTIVE,
            self.Status.ACTIVE,
            self.Status.GRACE,
        )

    @property
    def is_read_only(self) -> bool:
        return self.status == self.Status.GRACE

    @property
    def is_locked(self) -> bool:
        return self.status in (
            self.Status.LOCKED,
            self.Status.CANCELLED,
        )

    @property
    def days_remaining(self) -> int:
        now = timezone.now()
        target = self.end_date
        if self.status == self.Status.GRACE and self.grace_end_date:
            target = self.grace_end_date
        return max(0, (target - now).days)

    def sync_status(self):
        """Roll a subscription forward as time passes (trial → grace → locked)."""
        now = timezone.now()
        changed = False

        if self.status in (self.Status.ACTIVE, self.Status.ACTIVE):
            if now > self.end_date:
                self.status = self.Status.GRACE
                self.grace_end_date = self.end_date + timedelta(days=self.GRACE_DAYS)
                changed = True

        elif self.status == self.Status.GRACE:
            if self.grace_end_date and now > self.grace_end_date:
                self.status = self.Status.EXPIRED
                changed = True

        if changed:
            self.save(update_fields=["status", "grace_end_date"])

        return self

    def save(self, *args, **kwargs):
        self.sync_status()
        super().save(*args, **kwargs)


class SubscriptionPayment(TimestampedModel):
    """
    A payment recorded against a subscription (or a payment intent awaiting
    completion). Real-gateway intents are created during ``initiate`` — until
    the payment succeeds no :class:`Subscription` row exists, so the payment
    stores its own ``school`` and ``plan`` references.
    """

    class PaymentStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCESSFUL = "successful", "Successful"
        FAILED = "failed", "Failed"

    class PaymentMode(models.TextChoices):
        CASH = "cash", "Cash"
        VIRTUAL = "virtual", "Virtual Payment"

    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.CASCADE,
        related_name="payments",
        null=True,
        blank=True,
        help_text="Linked subscription. Null while the payment is still an intent.",
    )
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="subscription_payments",
        null=True,
        blank=True,
    )
    plan = models.ForeignKey(
        Package,
        on_delete=models.PROTECT,
        related_name="payments",
        null=True,
        blank=True,
    )
    term = models.ForeignKey(
        "academics.Term",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="subscription_payments",
        help_text="The academic term the payment covers (for payment intents).",
    )
    coupon = models.ForeignKey('Coupon', null=True, blank=True, on_delete=models.PROTECT, related_name='payment_intents')
    discount_applied = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="GHS")
    payment_reference = models.CharField(max_length=255, blank=True)
    provider = models.CharField(max_length=50, blank=True)
    payment_mode = models.CharField(
        max_length=20,
        choices=PaymentMode.choices,
        default=PaymentMode.VIRTUAL,
    )
    status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
    )
    recorded_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_subscription_payments",
    )

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return (
            f"{self.get_payment_mode_display()} {self.amount} "
            f"{self.currency} ({self.status})"
        )

class Coupon(TimestampedModel):
    class DiscountType(models.TextChoices):
        PERCENTAGE = 'percentage', 'Percentage'
        FIXED = 'fixed', 'Fixed'

    class Duration(models.TextChoices):
        ONCE = 'once', 'Once'
        RECURRING = 'recurring', 'Recurring'
        FOREVER = 'forever', 'Forever'

    class Target(models.TextChoices):
        ALL = 'all', 'All'
        SPECIFIC_PLAN = 'specific_plan', 'Specific plan'

    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        EXPIRED = 'expired', 'Expired'
        DISABLED = 'disabled', 'Disabled'

    code = models.CharField(max_length=20, unique=True)
    description = models.TextField(null=True, blank=True)
    discount_type = models.CharField(max_length=10, choices=DiscountType.choices)
    discount_value = models.DecimalField(max_digits=10, decimal_places=2)
    duration = models.CharField(max_length=10, choices=Duration.choices)
    target = models.CharField(max_length=20, choices=Target.choices)
    target_plan = models.ForeignKey(Package, null=True, blank=True, on_delete=models.PROTECT)
    max_usage = models.PositiveIntegerField(null=True, blank=True)
    usage_count = models.PositiveIntegerField(default=0, editable=False, db_index=True)
    expiry_date = models.DateTimeField(null=True, blank=True, db_index=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    created_by = models.ForeignKey('accounts.User', on_delete=models.PROTECT, related_name='created_coupons')

    class Meta:
        ordering = ('-created_at', '-id')
        constraints = (
            models.CheckConstraint(condition=models.Q(discount_value__gt=0), name='coupon_positive_discount'),
            models.CheckConstraint(condition=~models.Q(discount_type='percentage') | models.Q(discount_value__gte=1, discount_value__lte=100), name='coupon_percentage_range'),
            models.CheckConstraint(condition=models.Q(max_usage__isnull=True) | models.Q(max_usage__gt=0), name='coupon_positive_limit'),
            models.CheckConstraint(condition=models.Q(target='all', target_plan__isnull=True) | models.Q(target='specific_plan', target_plan__isnull=False), name='coupon_target_matches_plan'),
            models.CheckConstraint(condition=models.Q(code=models.functions.Upper('code')), name='coupon_uppercase_code'),
        )

    def save(self, *args, **kwargs):
        self.code = self.code.upper()
        super().save(*args, **kwargs)

    @property
    def effective_status(self):
        if ((self.expiry_date and self.expiry_date < timezone.localdate())
                or (self.max_usage is not None and self.usage_count >= self.max_usage)):
            return self.Status.EXPIRED
        return self.status

    @property
    def is_active(self):
        return self.effective_status == self.Status.ACTIVE


class CouponRedemption(TimestampedModel):
    coupon = models.ForeignKey(Coupon, on_delete=models.PROTECT, related_name='redemptions')
    school = models.ForeignKey('schools.School', on_delete=models.PROTECT)
    subscription = models.OneToOneField(Subscription, on_delete=models.PROTECT, related_name='coupon_redemption')
    discount_applied = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        constraints = (
            models.CheckConstraint(condition=models.Q(discount_applied__gte=0), name='redemption_nonnegative_discount'),
        )
