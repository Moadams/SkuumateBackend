from django.urls import path

from .views import (
    NotificationDetailView,
    NotificationListCreateView,
    NotificationPreviewView,
    NotificationProviderDetailView,
    NotificationProviderListCreateView,
    NotificationRecipientsListView,
    NotificationTemplateDetailView,
    NotificationTemplateListCreateView,
    SMSBundleListView,
    SMSHistoryView,
    SMSLedgerListView,
    SMSPurchaseListCreateView,
    SMSWalletView,
    SendTestNotificationView,
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
    path(
        "notifications/preview/",
        NotificationPreviewView.as_view(),
        name="notification-preview",
    ),
    path("notifications/<uuid:pk>/", NotificationDetailView.as_view(), name="notification-detail"),
    path(
        "notifications/<uuid:notification_id>/recipients/",
        NotificationRecipientsListView.as_view(),
        name="notification-recipients",
    ),

    # SMS credits & history
    path("sms/wallet/", SMSWalletView.as_view(), name="sms-wallet"),
    path("sms/bundles/", SMSBundleListView.as_view(), name="sms-bundle-list"),
    path(
        "sms/purchases/",
        SMSPurchaseListCreateView.as_view(),
        name="sms-purchase-list",
    ),
    path("sms/history/", SMSHistoryView.as_view(), name="sms-history"),
    path("sms/ledger/", SMSLedgerListView.as_view(), name="sms-ledger"),
]
