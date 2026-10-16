from django.urls import path

from subscriptions.views.packages import (
    FeatureActivateDeactivateView,
    FeatureListCreateView,
    FeatureRetrieveUpdateView,
    PackageActivateDeactivateView,
    PackageFeaturesView,
    PackageListCreateView,
    PackageListView,
    PackageRetrieveUpdateView,
)
from subscriptions.views.subscriptions import (
    CurrentSubscriptionView,
    MySubscriptionListView,
    SchoolSubscribeView,
)
from subscriptions.views.superadmin import (
    AdminPaymentListView,
    AdminSubscribeView,
    AdminSubscriptionDetailView,
    AdminSubscriptionListView,
)

urlpatterns = [
    path("plans/", PackageListView.as_view(), name="plan-list"),
    path("plans/features/", PackageFeaturesView.as_view(), name="plan-features"),

    # ── School — subscriptions & payments ──────────────────────────
    path("subscriptions/", MySubscriptionListView.as_view(), name="subscription-list"),
    path("subscriptions/current/", CurrentSubscriptionView.as_view(), name="subscription-current"),
    path("subscriptions/subscribe/", SchoolSubscribeView.as_view(), name="school-subscribe"),

    # ── Super administrator — package & feature management ─────────
    path("packages/", PackageListCreateView.as_view(), name="package-list-create"),
    path("packages/<uuid:pk>/", PackageRetrieveUpdateView.as_view(), name="package-retrieve-update"),
    path("packages/<uuid:pk>/activate/", PackageActivateDeactivateView.as_view(), name="package-activate"),
    path("packages/<uuid:pk>/deactivate/", PackageActivateDeactivateView.as_view(), name="package-deactivate"),

    path("features/", FeatureListCreateView.as_view(), name="feature-list-create"),
    path("features/<uuid:pk>/", FeatureRetrieveUpdateView.as_view(), name="feature-retrieve-update"),
    path("features/<uuid:pk>/activate/", FeatureActivateDeactivateView.as_view(), name="feature-activate"),
    path("features/<uuid:pk>/deactivate/", FeatureActivateDeactivateView.as_view(), name="feature-deactivate"),

    # ── Super administrator — subscription management ──────────────
    path("admin/subscriptions/", AdminSubscriptionListView.as_view(), name="admin-subscription-list"),
    path("admin/subscriptions/subscribe/", AdminSubscribeView.as_view(), name="admin-subscription-subscribe"),
    path("admin/subscriptions/<uuid:pk>/", AdminSubscriptionDetailView.as_view(), name="admin-subscription-detail"),
    path("admin/payments/", AdminPaymentListView.as_view(), name="admin-payment-list"),

    # ── Legacy superadmin helper (kept for compatibility) ──────────
    path("subscriptions/schools/", AdminSubscribeView.as_view(), name="manual-school-subscription"),
]