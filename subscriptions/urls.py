from django.urls import path

from subscriptions.views.superadmin_views import PlanRetrieveUpdateView, SchoolSubscriptionView
from subscriptions.views.views import CurrentSubscriptionView, InitiatePaymentView, PaymentWebhookView, PlanFeaturesView, PlanListView, SubscribeToPlanView


urlpatterns = [
    
    path("plans/", PlanListView.as_view(), name="plan-list"),
    path("plans/<uuid:pk>/", PlanRetrieveUpdateView.as_view(), name="plan-detail"),
    path("plans/features/", PlanFeaturesView.as_view(), name="plan-features"),  
    path("subscription/", CurrentSubscriptionView.as_view(), name="current-subscription"),
    path("subscriptions/schools/", SchoolSubscriptionView.as_view(), name="manual-school-subscription"),
    path("subscription/pay/", InitiatePaymentView.as_view(), name="initiate-payment"),
    path("subscription/webhook/<str:provider>/", PaymentWebhookView.as_view(), name="payment-webhook"),
    path("subscription/subscribe/", SubscribeToPlanView.as_view(), name="subscribe"),
]