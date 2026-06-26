import django_filters
from .models import NotificationProvider, NotificationTemplate, Notification


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
