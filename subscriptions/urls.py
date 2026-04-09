from django.urls import path
from .views import (
    PlanListView,
    PlanFeaturesView,        
    CurrentSubscriptionView,
    ManualActivationView,
    InitiatePaymentView,
    PaymentWebhookView,
    SubscribeToPlanView,
)

urlpatterns = [
    path("plans/", PlanListView.as_view(), name="plan-list"),
    path("plans/features/", PlanFeaturesView.as_view(), name="plan-features"),  
    path("subscription/", CurrentSubscriptionView.as_view(), name="current-subscription"),
    path("subscription/pay/", InitiatePaymentView.as_view(), name="initiate-payment"),
    path("subscription/webhook/<str:provider>/", PaymentWebhookView.as_view(), name="payment-webhook"),
    path("schools/<uuid:school_id>/subscription/activate/", ManualActivationView.as_view(), name="manual-activate"),
    path("subscription/subscribe/", SubscribeToPlanView.as_view(), name="subscribe"),
]