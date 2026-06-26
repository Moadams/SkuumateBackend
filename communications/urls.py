from django.urls import path

from .views import (
    NotificationProviderListCreateView, NotificationProviderDetailView,
    SendTestNotificationView,
    NotificationTemplateListCreateView, NotificationTemplateDetailView,
    NotificationListCreateView, NotificationDetailView,
    NotificationRecipientsListView,
)

urlpatterns = [
    # Providers
    path("providers/", NotificationProviderListCreateView.as_view(), name="provider-list"),
    path("providers/<uuid:pk>/", NotificationProviderDetailView.as_view(), name="provider-detail"),
    path("providers/test/", SendTestNotificationView.as_view(), name="provider-test"),

    # Templates
    path("templates/", NotificationTemplateListCreateView.as_view(), name="template-list"),
    path("templates/<uuid:pk>/", NotificationTemplateDetailView.as_view(), name="template-detail"),

    # Notifications
    path("notifications/", NotificationListCreateView.as_view(), name="notification-list"),
    path("notifications/<uuid:pk>/", NotificationDetailView.as_view(), name="notification-detail"),
    path(
        "notifications/<uuid:notification_id>/recipients/",
        NotificationRecipientsListView.as_view(),
        name="notification-recipients",
    ),
]
