from decimal import Decimal

from django.db import models

from core.models import TimestampedModel


class NotificationProvider(TimestampedModel):

    class Channel(models.TextChoices):
        EMAIL = "email", "Email"
        SMS = "sms", "SMS"
        BOTH = "both", "Both"

    class ProviderType(models.TextChoices):
        # Email
        SMTP = "smtp", "SMTP"
        # SMS
        MNOTIFY = "mnotify", "mNotify"
        ARKESEL = "arkesel", "Arkesel"

    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="notification_providers")
    name = models.CharField(max_length=100)
    channel = models.CharField(max_length=10, choices=Channel.choices)
    provider_type = models.CharField(max_length=30, choices=ProviderType.choices)
    config = models.JSONField(default=dict, help_text="Provider credentials and settings")
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)

    class Meta:
        ordering = ["channel", "name"]
        unique_together = ["school", "name"]

    def __str__(self):
        return f"{self.name} ({self.get_channel_display()})"


class NotificationTemplate(TimestampedModel):

    class Channel(models.TextChoices):
        EMAIL = "email", "Email"
        SMS = "sms", "SMS"
        BOTH = "both", "Both"

    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="notification_templates")
    name = models.CharField(max_length=100)
    subject = models.CharField(max_length=200, blank=True, help_text="Email subject line")
    body = models.TextField(help_text="Message body. Use {{variable_name}} for placeholders.")
    channel = models.CharField(max_length=10, choices=Channel.choices, default=Channel.EMAIL)
    variables = models.JSONField(default=list, blank=True, help_text="List of variable names used in the template")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        unique_together = ["school", "name"]

    def __str__(self):
        return self.name


class Notification(TimestampedModel):

    class Channel(models.TextChoices):
        EMAIL = "email", "Email"
        SMS = "sms", "SMS"
        BOTH = "both", "Both"

    class RecipientType(models.TextChoices):
        ALL_STUDENTS = "all_students", "All Students"
        ALL_STAFF = "all_staff", "All Staff"
        SPECIFIC_STUDENTS = "specific_students", "Specific Students"
        SPECIFIC_STAFF = "specific_staff", "Specific Staff"
        SPECIFIC_RECIPIENTS = "specific_recipients", "Selected Students and Staff"
        CLASS = "class", "Whole Class"
        GUARDIANS_OF = "guardians_of", "Guardians of Students"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        QUEUED = "queued", "Queued"
        PROCESSING = "processing", "Processing"
        SENT = "sent", "Sent"
        PARTIAL = "partial", "Partially Sent"
        FAILED = "failed", "Failed"

    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="notifications")
    template = models.ForeignKey(
        NotificationTemplate, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="notifications",
    )
    title = models.CharField(max_length=200)
    message_body = models.TextField()
    channel = models.CharField(max_length=10, choices=Channel.choices)
    recipient_type = models.CharField(max_length=30, choices=RecipientType.choices)
    metadata = models.JSONField(default=dict, blank=True, help_text="Filter criteria or extra data")
    sent_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="sent_notifications",
    )
    sent_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    total_recipients = models.PositiveIntegerField(
        default=0, help_text="Number of queued channel deliveries"
    )
    sms_credits_charged = models.PositiveIntegerField(
        default=0, help_text="SMS credits reserved when the campaign was queued"
    )
    queued_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class ReportDelivery(TimestampedModel):
    """One guardian/channel delivery attempt for a published report card.

    Rows are created inside the publish transaction (a transactional outbox)
    and processed later by ``manage.py dispatch_report_deliveries``. Shared
    hosting has no reliable long-running worker, so cron + a database queue is
    used instead of threads/Celery.
    """

    class Channel(models.TextChoices):
        EMAIL = "email", "Email"
        SMS = "sms", "SMS"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped"

    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="report_deliveries"
    )
    student_report = models.ForeignKey(
        "exams.StudentReport", on_delete=models.CASCADE, related_name="deliveries"
    )
    guardian = models.ForeignKey(
        "guardian.Guardian", on_delete=models.CASCADE, related_name="report_deliveries"
    )
    channel = models.CharField(max_length=10, choices=Channel.choices)
    recipient = models.CharField(
        max_length=255, help_text="Email address or phone number snapshot"
    )
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.PENDING
    )
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    locked_by = models.CharField(max_length=64, blank=True)
    last_error = models.TextField(blank=True)
    provider = models.CharField(max_length=30, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "report delivery"
        verbose_name_plural = "report deliveries"
        constraints = [
            models.UniqueConstraint(
                fields=["student_report", "guardian", "channel"],
                name="unique_report_delivery_per_channel",
            )
        ]
        indexes = [
            models.Index(
                fields=["status", "next_attempt_at"],
                name="report_delivery_due_idx",
            )
        ]

    def __str__(self):
        return f"{self.student_report_id} → {self.guardian_id} ({self.channel})"


class NotificationRecipient(TimestampedModel):

    class RecipientType(models.TextChoices):
        STUDENT = "student", "Student"
        STAFF = "staff", "Staff"
        GUARDIAN = "guardian", "Guardian"
        USER = "user", "User"

    class Channel(models.TextChoices):
        EMAIL = "email", "Email"
        SMS = "sms", "SMS"

    class DeliveryStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped"

    notification = models.ForeignKey(
        Notification, on_delete=models.CASCADE,
        related_name="recipients",
    )
    recipient_type = models.CharField(max_length=10, choices=RecipientType.choices)
    recipient_id = models.UUIDField(null=True, blank=True)
    recipient_name = models.CharField(max_length=200, blank=True)
    recipient_contact = models.CharField(max_length=200, blank=True, help_text="Email or phone used")
    channel = models.CharField(
        max_length=10, choices=Channel.choices, default=Channel.SMS
    )
    status = models.CharField(max_length=12, choices=DeliveryStatus.choices, default=DeliveryStatus.PENDING)
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    locked_by = models.CharField(max_length=64, blank=True)
    provider = models.CharField(max_length=30, blank=True)
    credit_cost = models.PositiveSmallIntegerField(
        default=1, help_text="SMS credits reserved for this delivery"
    )
    credit_refunded = models.BooleanField(default=False)
    error_message = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["recipient_name"]
        indexes = [
            models.Index(
                fields=["status", "next_attempt_at"],
                name="notification_recipient_due_idx",
            ),
        ]

    def __str__(self):
        return f"{self.recipient_name} ({self.get_status_display()})"


class SMSBundle(TimestampedModel):
    """A platform-defined pack of SMS credits that schools can buy."""

    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50, unique=True)
    credits = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="GHS")
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "price"]
        verbose_name = "SMS bundle"
        verbose_name_plural = "SMS bundles"

    def __str__(self):
        return f"{self.name} ({self.credits} credits)"

    @property
    def unit_price(self):
        if not self.credits:
            return Decimal("0.00")
        return (self.price / self.credits).quantize(Decimal("0.0001"))


class SMSWallet(TimestampedModel):
    """The school's SMS credit balance.

    ``balance`` is authoritative and is only changed under a row lock. The
    ledger records every movement so purchase and usage history is auditable.
    """

    school = models.OneToOneField(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="sms_wallet",
    )
    balance = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "SMS wallet"
        verbose_name_plural = "SMS wallets"

    def __str__(self):
        return f"{self.school.name}: {self.balance} credits"


class SMSPurchase(TimestampedModel):
    """A successful (or attempted) purchase of an SMS bundle."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCESSFUL = "successful", "Successful"
        FAILED = "failed", "Failed"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="sms_purchases",
    )
    bundle = models.ForeignKey(
        SMSBundle,
        on_delete=models.PROTECT,
        related_name="purchases",
    )
    credits = models.PositiveIntegerField()
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="GHS")
    provider = models.CharField(max_length=30, blank=True)
    payment_reference = models.CharField(max_length=100, unique=True)
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.PENDING
    )
    failure_reason = models.TextField(blank=True)
    purchased_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sms_purchases",
    )
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.school.name}: {self.credits} credits ({self.status})"


class SMSLedgerEntry(TimestampedModel):
    """An append-only record of a movement in a school's SMS wallet."""

    class Kind(models.TextChoices):
        PURCHASE = "purchase", "Purchase"
        USAGE = "usage", "Usage"
        REFUND = "refund", "Refund"
        ADJUSTMENT = "adjustment", "Adjustment"
        BONUS = "bonus", "Bonus"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="sms_ledger_entries",
    )
    kind = models.CharField(max_length=15, choices=Kind.choices)
    credits = models.IntegerField(help_text="Signed: positive credits in, negative credits out")
    balance_after = models.PositiveIntegerField()
    description = models.CharField(max_length=255, blank=True)
    notification = models.ForeignKey(
        Notification,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sms_ledger_entries",
    )
    purchase = models.ForeignKey(
        SMSPurchase,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ledger_entries",
    )
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sms_ledger_entries",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "SMS ledger entry"
        verbose_name_plural = "SMS ledger entries"

    def __str__(self):
        return f"{self.get_kind_display()}: {self.credits:+d} ({self.school.name})"
