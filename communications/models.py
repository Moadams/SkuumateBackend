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
        CLASS = "class", "Whole Class"
        GUARDIANS_OF = "guardians_of", "Guardians of Students"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
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

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class NotificationRecipient(TimestampedModel):

    class RecipientType(models.TextChoices):
        STUDENT = "student", "Student"
        STAFF = "staff", "Staff"
        GUARDIAN = "guardian", "Guardian"
        USER = "user", "User"

    class DeliveryStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    notification = models.ForeignKey(
        Notification, on_delete=models.CASCADE,
        related_name="recipients",
    )
    recipient_type = models.CharField(max_length=10, choices=RecipientType.choices)
    recipient_id = models.UUIDField(null=True, blank=True)
    recipient_name = models.CharField(max_length=200, blank=True)
    recipient_contact = models.CharField(max_length=200, blank=True, help_text="Email or phone used")
    status = models.CharField(max_length=10, choices=DeliveryStatus.choices, default=DeliveryStatus.PENDING)
    error_message = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["recipient_name"]

    def __str__(self):
        return f"{self.recipient_name} ({self.get_status_display()})"
