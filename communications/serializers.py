from rest_framework import serializers

from core.tenant_serializers import SchoolRelatedFieldsMixin

from .models import (
    NotificationProvider, NotificationTemplate,
    Notification, NotificationRecipient,
    SMSBundle, SMSPurchase, SMSLedgerEntry,
)
from .services.sender import NotificationSender


def _validate_audience(attrs):
    """Require the identifiers each recipient type needs.

    The service still resolves every identifier against the caller's school;
    this only catches incomplete payloads early with a field-level message.
    """
    recipient_type = attrs["recipient_type"]
    student_ids = attrs.get("student_ids") or []
    staff_ids = attrs.get("staff_ids") or []
    recipient_ids = attrs.get("recipient_ids") or []

    if recipient_type in ("specific_students", "guardians_of"):
        if not student_ids and not recipient_ids:
            raise serializers.ValidationError(
                {"student_ids": "Select at least one student."}
            )
    elif recipient_type == "specific_staff":
        if not staff_ids and not recipient_ids:
            raise serializers.ValidationError(
                {"staff_ids": "Select at least one staff member."}
            )
    elif recipient_type == "specific_recipients":
        if not student_ids and not staff_ids:
            raise serializers.ValidationError(
                {"student_ids": "Select at least one student or staff member."}
            )
    elif recipient_type == "class":
        if not attrs.get("class_id"):
            raise serializers.ValidationError(
                {"class_id": "Select a class."}
            )
    return attrs


class NotificationProviderSerializer(serializers.ModelSerializer):
    channel_display = serializers.CharField(source="get_channel_display", read_only=True)
    provider_type_display = serializers.CharField(source="get_provider_type_display", read_only=True)

    class Meta:
        model = NotificationProvider
        fields = [
            "id", "name", "channel", "channel_display",
            "provider_type", "provider_type_display",
            "config", "is_active", "is_default",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class NotificationTemplateSerializer(serializers.ModelSerializer):
    channel_display = serializers.CharField(source="get_channel_display", read_only=True)

    class Meta:
        model = NotificationTemplate
        fields = [
            "id", "name", "subject", "body", "channel", "channel_display",
            "variables", "is_active", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class NotificationRecipientSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    channel_display = serializers.CharField(source="get_channel_display", read_only=True)

    class Meta:
        model = NotificationRecipient
        fields = [
            "id", "channel", "channel_display", "recipient_type", "recipient_id",
            "recipient_name", "recipient_contact",
            "status", "status_display", "attempts", "provider",
            "credit_cost", "credit_refunded",
            "error_message", "next_attempt_at", "sent_at",
        ]
        read_only_fields = fields


class NotificationListSerializer(serializers.ModelSerializer):
    channel_display = serializers.CharField(source="get_channel_display", read_only=True)
    recipient_type_display = serializers.CharField(source="get_recipient_type_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    sent_by_name = serializers.SerializerMethodField()
    recipient_count = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = [
            "id", "title", "channel", "channel_display",
            "recipient_type", "recipient_type_display",
            "status", "status_display",
            "sent_by", "sent_by_name",
            "sent_at", "recipient_count", "total_recipients",
            "sms_credits_charged", "queued_at", "completed_at",
            "created_at",
        ]
        read_only_fields = fields

    def get_sent_by_name(self, obj):
        if obj.sent_by:
            return f"{obj.sent_by.first_name} {obj.sent_by.last_name}"
        return None

    def get_recipient_count(self, obj):
        return obj.recipients.count()


class NotificationDetailSerializer(serializers.ModelSerializer):
    channel_display = serializers.CharField(source="get_channel_display", read_only=True)
    recipient_type_display = serializers.CharField(source="get_recipient_type_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    sent_by_name = serializers.SerializerMethodField()
    template_name = serializers.CharField(source="template.name", read_only=True, allow_null=True)
    recipients = NotificationRecipientSerializer(many=True, read_only=True)
    sent_count = serializers.SerializerMethodField()
    failed_count = serializers.SerializerMethodField()
    pending_count = serializers.SerializerMethodField()
    skipped_count = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = [
            "id", "title", "message_body", "channel", "channel_display",
            "recipient_type", "recipient_type_display",
            "template", "template_name",
            "metadata", "status", "status_display",
            "sent_by", "sent_by_name",
            "sent_at", "recipients", "total_recipients",
            "sms_credits_charged", "queued_at", "completed_at",
            "sent_count", "failed_count", "pending_count", "skipped_count",
            "created_at", "updated_at",
        ]
        read_only_fields = fields

    def get_sent_by_name(self, obj):
        if obj.sent_by:
            return f"{obj.sent_by.first_name} {obj.sent_by.last_name}"
        return None

    def get_sent_count(self, obj):
        return obj.recipients.filter(status="sent").count()

    def get_failed_count(self, obj):
        return obj.recipients.filter(status="failed").count()

    def get_pending_count(self, obj):
        return obj.recipients.filter(
            status__in=["pending", "processing"]
        ).count()

    def get_skipped_count(self, obj):
        return obj.recipients.filter(status="skipped").count()


class NotificationCreateSerializer(SchoolRelatedFieldsMixin, serializers.Serializer):
    school_related_fields = ("template",)

    template = serializers.PrimaryKeyRelatedField(
        queryset=NotificationTemplate.objects.all(),
        required=False, allow_null=True,
    )
    title = serializers.CharField(max_length=200)
    message_body = serializers.CharField(
        required=False, allow_blank=True, max_length=5000
    )
    channel = serializers.ChoiceField(choices=Notification.Channel.choices)
    recipient_type = serializers.ChoiceField(choices=Notification.RecipientType.choices)
    # ``recipient_ids`` is kept for the legacy payloads; it is interpreted as
    # student ids or staff ids depending on ``recipient_type``.
    recipient_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, default=list,
    )
    student_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, default=list,
    )
    staff_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, default=list,
    )
    class_id = serializers.UUIDField(required=False, allow_null=True)
    template_variables = serializers.JSONField(required=False, default=dict)

    def validate(self, attrs):
        if attrs.get("template") and not attrs.get("message_body"):
            template = attrs["template"]
            variables = attrs.get("template_variables", {})
            try:
                subject, body = NotificationSender.render_template(template, variables)
                attrs["title"] = subject or attrs.get("title", template.name)
                attrs["message_body"] = body
            except Exception as e:
                raise serializers.ValidationError(
                    f"Template rendering failed: {str(e)}"
                )

        if not attrs.get("message_body") and not attrs.get("template"):
            raise serializers.ValidationError(
                "Either message_body or template is required."
            )

        return _validate_audience(attrs)


class NotificationPreviewSerializer(serializers.Serializer):
    message_body = serializers.CharField(max_length=5000)
    channel = serializers.ChoiceField(choices=Notification.Channel.choices)
    recipient_type = serializers.ChoiceField(choices=Notification.RecipientType.choices)
    recipient_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, default=list,
    )
    student_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, default=list,
    )
    staff_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, default=list,
    )
    class_id = serializers.UUIDField(required=False, allow_null=True)

    def validate(self, attrs):
        return _validate_audience(attrs)


class SendTestSerializer(serializers.Serializer):
    provider = serializers.PrimaryKeyRelatedField(
        queryset=NotificationProvider.objects.none(),
    )
    recipient = serializers.CharField(max_length=200)
    subject = serializers.CharField(max_length=200, required=False, default="Test Notification")
    message = serializers.CharField(max_length=500, default="This is a test message from SkuuMate.")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only the caller's own providers may be used. Without a school
        # context (e.g. a platform actor) nothing is selectable, so a school
        # can never send through another tenant's credentials.
        school = self.context.get("school")
        if school is not None:
            self.fields["provider"].queryset = NotificationProvider.objects.filter(
                school=school
            )


# ─── SMS credits ───────────────────────────────────────────────────

class SMSBundleSerializer(serializers.ModelSerializer):
    unit_price = serializers.DecimalField(
        max_digits=12, decimal_places=4, read_only=True
    )

    class Meta:
        model = SMSBundle
        fields = [
            "id", "name", "code", "credits", "price", "currency",
            "unit_price", "description", "is_active", "display_order",
            "created_at", "updated_at",
        ]
        read_only_fields = fields


class SMSPurchaseCreateSerializer(serializers.Serializer):
    bundle = serializers.UUIDField()
    payment_reference = serializers.CharField(max_length=100)
    provider = serializers.ChoiceField(
        choices=["paystack", "momo", "simulate"], default="paystack"
    )


class SMSPurchaseSerializer(serializers.ModelSerializer):
    bundle_name = serializers.CharField(source="bundle.name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    purchased_by_name = serializers.SerializerMethodField()

    class Meta:
        model = SMSPurchase
        fields = [
            "id", "bundle", "bundle_name", "credits", "amount", "currency",
            "provider", "payment_reference", "status", "status_display",
            "failure_reason", "purchased_by", "purchased_by_name",
            "completed_at", "created_at",
        ]
        read_only_fields = fields

    def get_purchased_by_name(self, obj):
        if obj.purchased_by:
            return f"{obj.purchased_by.first_name} {obj.purchased_by.last_name}"
        return None


class SMSLedgerEntrySerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    notification_title = serializers.CharField(
        source="notification.title", read_only=True, allow_null=True
    )
    purchase_reference = serializers.CharField(
        source="purchase.payment_reference", read_only=True, allow_null=True
    )
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = SMSLedgerEntry
        fields = [
            "id", "kind", "kind_display", "credits", "balance_after",
            "description", "notification", "notification_title",
            "purchase", "purchase_reference", "created_by", "created_by_name",
            "created_at",
        ]
        read_only_fields = fields

    def get_created_by_name(self, obj):
        if obj.created_by:
            return f"{obj.created_by.first_name} {obj.created_by.last_name}"
        return None


class SMSSentHistorySerializer(serializers.ModelSerializer):
    notification_title = serializers.CharField(
        source="notification.title", read_only=True
    )
    notification_channel = serializers.CharField(
        source="notification.channel", read_only=True
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = NotificationRecipient
        fields = [
            "id", "notification", "notification_title", "notification_channel",
            "recipient_type", "recipient_id", "recipient_name", "recipient_contact",
            "status", "status_display", "attempts", "provider",
            "credit_cost", "credit_refunded", "error_message", "sent_at",
            "created_at",
        ]
        read_only_fields = fields
