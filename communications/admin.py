from django.contrib import admin

from .models import (
    NotificationProvider, NotificationTemplate,
    Notification, NotificationRecipient, ReportDelivery,
    SMSBundle, SMSWallet, SMSPurchase, SMSLedgerEntry,
)


class NotificationRecipientInline(admin.TabularInline):
    model = NotificationRecipient
    extra = 0
    readonly_fields = [
        "recipient_name", "recipient_contact", "channel", "status",
        "attempts", "credit_cost", "credit_refunded", "error_message",
        "sent_at",
    ]


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
    list_display = [
        "title", "school", "channel", "recipient_type", "status",
        "total_recipients", "sms_credits_charged", "sent_at",
    ]
    list_filter = ["channel", "recipient_type", "status"]
    search_fields = ["title", "message_body"]
    inlines = [NotificationRecipientInline]
    readonly_fields = [
        "sent_at", "status", "total_recipients", "sms_credits_charged",
        "queued_at", "completed_at",
    ]


@admin.register(NotificationRecipient)
class NotificationRecipientAdmin(admin.ModelAdmin):
    list_display = [
        "recipient_name", "notification", "channel", "status",
        "recipient_contact", "attempts", "credit_cost", "sent_at",
    ]
    list_filter = ["status", "recipient_type", "channel"]
    search_fields = ["recipient_name", "recipient_contact"]


@admin.register(ReportDelivery)
class ReportDeliveryAdmin(admin.ModelAdmin):
    list_display = [
        "student_report", "guardian", "channel", "status",
        "attempts", "sent_at", "next_attempt_at",
    ]
    list_filter = ["channel", "status", "school"]
    search_fields = [
        "recipient",
        "student_report__student__first_name",
        "student_report__student__last_name",
        "guardian__first_name",
        "guardian__last_name",
    ]
    readonly_fields = ["created_at", "updated_at", "locked_at", "locked_by"]


# ─── SMS credits ───────────────────────────────────────────────────

@admin.register(SMSBundle)
class SMSBundleAdmin(admin.ModelAdmin):
    list_display = [
        "name", "code", "credits", "price", "currency",
        "is_active", "display_order",
    ]
    list_filter = ["is_active", "currency"]
    search_fields = ["name", "code"]
    ordering = ["display_order", "price"]


@admin.register(SMSWallet)
class SMSWalletAdmin(admin.ModelAdmin):
    list_display = ["school", "balance", "updated_at"]
    search_fields = ["school__name"]
    readonly_fields = ["created_at", "updated_at"]


class SMSLedgerEntryInline(admin.TabularInline):
    model = SMSLedgerEntry
    extra = 0
    can_delete = False
    readonly_fields = [
        "kind", "credits", "balance_after", "description",
        "notification", "created_by", "created_at",
    ]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(SMSPurchase)
class SMSPurchaseAdmin(admin.ModelAdmin):
    list_display = [
        "school", "bundle", "credits", "amount", "status",
        "payment_reference", "completed_at",
    ]
    list_filter = ["status", "bundle", "provider"]
    search_fields = ["school__name", "payment_reference"]
    readonly_fields = ["created_at", "updated_at"]
    inlines = [SMSLedgerEntryInline]


@admin.register(SMSLedgerEntry)
class SMSLedgerEntryAdmin(admin.ModelAdmin):
    list_display = [
        "school", "kind", "credits", "balance_after",
        "description", "created_at",
    ]
    list_filter = ["kind", "school"]
    search_fields = ["description", "notification__title"]
    readonly_fields = [
        "school", "kind", "credits", "balance_after", "description",
        "notification", "purchase", "created_by", "created_at", "updated_at",
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
