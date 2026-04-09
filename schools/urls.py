from django.urls import path
from .views import OnboardingStatusView, SchoolListExportView, SchoolListView, SchoolOnboardView, SchoolDetailView, SuperadminDashboardView

urlpatterns = [
    # Superadmin — school management
    path("schools/", SchoolListView.as_view(), name="school-list"),
    path("schools/export/", SchoolListExportView.as_view(), name="school-list-export"),
    
    path("schools/onboard/", SchoolOnboardView.as_view(), name="school-onboard"),
    path("schools/onboarding-status/", OnboardingStatusView.as_view(), name="onboarding-status"),
    path("schools/me/", SchoolDetailView.as_view(), name="school-detail"),
    path("superadmin/overview/", SuperadminDashboardView.as_view(), name="school-overview"),
]