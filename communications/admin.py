from django.contrib import admin

from .models import (
    NotificationProvider, NotificationTemplate,
    Notification, NotificationRecipient,
)


class NotificationRecipientInline(admin.TabularInline):
    model = NotificationRecipient
    extra = 0
    readonly_fields = ["recipient_name", "recipient_contact", "status", "error_message", "sent_at"]


@admin.register(NotificationProvider)
class NotificationProviderAdmin(admin.ModelAdmin):
    list_display = ["name", "school", "channel", "provider_type", "is_active", "is_default"]
    list_filter = ["channel", "provider_type", "is_active"]
    search_fields = ["name"]


@admin.register(NotificationTemplate)
class NotificationTemplateAdmin(admin.ModelAdmin):
    list_display = ["name", "school", "channel", "is_active"]
    list_filter = ["channel", "is_active"]
    search_fields = ["name", "subject"]


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ["title", "school", "channel", "recipient_type", "status", "sent_at"]
    list_filter = ["channel", "recipient_type", "status"]
    search_fields = ["title", "message_body"]
    inlines = [NotificationRecipientInline]
    readonly_fields = ["sent_at", "status"]


@admin.register(NotificationRecipient)
class NotificationRecipientAdmin(admin.ModelAdmin):
    list_display = ["recipient_name", "notification", "status", "recipient_contact", "sent_at"]
    list_filter = ["status", "recipient_type"]
    search_fields = ["recipient_name", "recipient_contact"]
