from django.urls import path
from .views.views import AdminDashboardView, OnboardingStatusView, SchoolListExportView, SchoolListView, SchoolOnboardView, SchoolDetailView
from .views.superadmin_views import SuperSchoolDetailView

urlpatterns = [
    # Superadmin — school management
    path("schools/", SchoolListView.as_view(), name="school-list"),
    path("schools/<uuid:school_id>/", SuperSchoolDetailView.as_view(), name="school-detail"),
    path("schools/export/", SchoolListExportView.as_view(), name="school-list-export"),
    
    path("schools/onboard/", SchoolOnboardView.as_view(), name="school-onboard"),
    path("schools/onboarding-status/", OnboardingStatusView.as_view(), name="onboarding-status"),
    path("schools/me/", SchoolDetailView.as_view(), name="school-detail"),
    path("dashboard/admin/", AdminDashboardView.as_view(), name="admin-dashboard"),
]