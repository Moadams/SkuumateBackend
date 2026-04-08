from django.urls import path
from .views import SchoolOnboardView, SchoolDetailView, SuperadminDashboardView

urlpatterns = [
    path("schools/onboard/", SchoolOnboardView.as_view(), name="school-onboard"),
    path("schools/me/", SchoolDetailView.as_view(), name="school-detail"),
    path("superadmin/overview/", SuperadminDashboardView.as_view(), name="school-overview"),
]