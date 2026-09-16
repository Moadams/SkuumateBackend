from django.urls import path

from subscriptions.views.superadmin_views import (
    FeatureActivateDeactivateView,
    FeatureListCreateView,
    FeatureRetrieveUpdateView,
    PackageActivateDeactivateView,
    PackageListCreateView,
    PackageRetrieveUpdateView,
    SchoolSubscriptionView,
)
from .views.views import (
    PackageListView,
    PackageFeaturesView,
    CurrentSubscriptionView,
    InitiatePaymentView,
    PaymentWebhookView,
    SubscribeToPlanView,
)

urlpatterns = [
    # ── Public package browsing (read-only, for signup/selection) ──
    path("plans/", PackageListView.as_view(), name="plan-list"),
    path("plans/features/", PackageFeaturesView.as_view(), name="plan-features"),

    # ── Super administrator — package management ───────────────────
    path("packages/", PackageListCreateView.as_view(), name="package-list-create"),
    path("packages/<uuid:pk>/", PackageRetrieveUpdateView.as_view(), name="package-retrieve-update"),
    path("packages/<uuid:pk>/activate/", PackageActivateDeactivateView.as_view(), name="package-activate"),
    path("packages/<uuid:pk>/deactivate/", PackageActivateDeactivateView.as_view(), name="package-deactivate"),

    # ── Super administrator — feature management ───────────────────
    path("features/", FeatureListCreateView.as_view(), name="feature-list-create"),
    path("features/<uuid:pk>/", FeatureRetrieveUpdateView.as_view(), name="feature-retrieve-update"),
    path("features/<uuid:pk>/activate/", FeatureActivateDeactivateView.as_view(), name="feature-activate"),
    path("features/<uuid:pk>/deactivate/", FeatureActivateDeactivateView.as_view(), name="feature-deactivate"),

    # ── Subscriptions ──────────────────────────────────────────────
    path("subscription/", CurrentSubscriptionView.as_view(), name="current-subscription"),
    path("subscriptions/schools/", SchoolSubscriptionView.as_view(), name="manual-school-subscription"),
    path("subscription/pay/", InitiatePaymentView.as_view(), name="initiate-payment"),
    path("subscription/webhook/<str:provider>/", PaymentWebhookView.as_view(), name="payment-webhook"),
    path("subscription/subscribe/", SubscribeToPlanView.as_view(), name="subscribe"),
]