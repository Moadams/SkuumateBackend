from rest_framework import serializers

from .models import (
    NotificationProvider, NotificationTemplate,
    Notification, NotificationRecipient,
)
from .services.sender import NotificationSender


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

    class Meta:
        model = NotificationRecipient
        fields = [
            "id", "recipient_type", "recipient_id",
            "recipient_name", "recipient_contact",
            "status", "status_display", "error_message", "sent_at",
        ]
        read_only_fields = [
            "id", "recipient_type", "recipient_id",
            "recipient_name", "recipient_contact",
            "status", "error_message", "sent_at",
        ]


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
            "sent_at", "recipient_count",
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

    class Meta:
        model = Notification
        fields = [
            "id", "title", "message_body", "channel", "channel_display",
            "recipient_type", "recipient_type_display",
            "template", "template_name",
            "metadata", "status", "status_display",
            "sent_by", "sent_by_name",
            "sent_at", "recipients",
            "sent_count", "failed_count", "pending_count",
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
        return obj.recipients.filter(status="pending").count()


class NotificationCreateSerializer(serializers.Serializer):
    template = serializers.PrimaryKeyRelatedField(
        queryset=NotificationTemplate.objects.all(),
        required=False, allow_null=True,
    )
    title = serializers.CharField(max_length=200)
    message_body = serializers.CharField(required=False, allow_blank=True)
    channel = serializers.ChoiceField(choices=Notification.Channel.choices)
    recipient_type = serializers.ChoiceField(choices=Notification.RecipientType.choices)
    recipient_ids = serializers.ListField(
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

        if attrs["recipient_type"] in ("specific_students", "specific_staff", "guardians_of"):
            if not attrs.get("recipient_ids"):
                raise serializers.ValidationError(
                    f"recipient_ids is required for {attrs['recipient_type']}."
                )

        if attrs["recipient_type"] == "class" and not attrs.get("class_id"):
            raise serializers.ValidationError("class_id is required for class recipient type.")

        return attrs


class SendTestSerializer(serializers.Serializer):
    provider = serializers.PrimaryKeyRelatedField(
        queryset=NotificationProvider.objects.all(),
    )
    recipient = serializers.CharField(max_length=200)
    subject = serializers.CharField(max_length=200, required=False, default="Test Notification")
    message = serializers.CharField(max_length=500, default="This is a test message from SkuuMate.")
