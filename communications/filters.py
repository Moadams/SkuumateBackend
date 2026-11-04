import django_filters
from .models import (
    NotificationProvider, NotificationTemplate, Notification,
    NotificationRecipient, SMSPurchase, SMSLedgerEntry,
)


class NotificationProviderFilter(django_filters.FilterSet):
    channel = django_filters.ChoiceFilter(choices=NotificationProvider.Channel.choices)
    provider_type = django_filters.ChoiceFilter(choices=NotificationProvider.ProviderType.choices)
    is_active = django_filters.BooleanFilter()
    is_default = django_filters.BooleanFilter()

    class Meta:
        model = NotificationProvider
        fields = ["channel", "provider_type", "is_active", "is_default"]


class NotificationTemplateFilter(django_filters.FilterSet):
    channel = django_filters.ChoiceFilter(choices=NotificationTemplate.Channel.choices)
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = NotificationTemplate
        fields = ["channel", "is_active"]


class NotificationFilter(django_filters.FilterSet):
    channel = django_filters.ChoiceFilter(choices=Notification.Channel.choices)
    recipient_type = django_filters.ChoiceFilter(choices=Notification.RecipientType.choices)
    status = django_filters.ChoiceFilter(choices=Notification.Status.choices)
    sent_from = django_filters.DateFilter(field_name="sent_at", lookup_expr="gte")
    sent_to = django_filters.DateFilter(field_name="sent_at", lookup_expr="lte")
    created_from = django_filters.DateFilter(field_name="created_at", lookup_expr="gte")
    created_to = django_filters.DateFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = Notification
        fields = ["channel", "recipient_type", "status"]


class SMSPurchaseFilter(django_filters.FilterSet):
    status = django_filters.ChoiceFilter(choices=SMSPurchase.Status.choices)
    bundle = django_filters.UUIDFilter(field_name="bundle_id")
    created_from = django_filters.DateFilter(field_name="created_at", lookup_expr="gte")
    created_to = django_filters.DateFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = SMSPurchase
        fields = ["status", "bundle"]


class SMSHistoryFilter(django_filters.FilterSet):
    status = django_filters.ChoiceFilter(
        choices=NotificationRecipient.DeliveryStatus.choices
    )
    recipient_type = django_filters.ChoiceFilter(
        choices=NotificationRecipient.RecipientType.choices
    )
    notification = django_filters.UUIDFilter(field_name="notification_id")
    sent_from = django_filters.DateFilter(field_name="sent_at", lookup_expr="gte")
    sent_to = django_filters.DateFilter(field_name="sent_at", lookup_expr="lte")

    class Meta:
        model = NotificationRecipient
        fields = ["status", "recipient_type", "notification"]


class SMSLedgerFilter(django_filters.FilterSet):
    kind = django_filters.ChoiceFilter(choices=SMSLedgerEntry.Kind.choices)
    notification = django_filters.UUIDFilter(field_name="notification_id")
    created_from = django_filters.DateFilter(field_name="created_at", lookup_expr="gte")
    created_to = django_filters.DateFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = SMSLedgerEntry
        fields = ["kind", "notification"]
