from django.urls import path

from .views.superadmin_views import SchoolListCreateView, SuperSchoolDetailView
from .views.views import (
    SchoolDetailsView,
    SchoolListExportView,
    SchoolOnboardingStatusView,
    SchoolProfileView,
)

urlpatterns = [
    # Superadmin — school management
    path("schools/", SchoolListCreateView.as_view(), name="school-list"),
    path("schools/<uuid:school_id>/", SuperSchoolDetailView.as_view(), name="school-detail"),
    path("schools/export/", SchoolListExportView.as_view(), name="school-list-export"),

    # Admin — school profile
    path("schools/me/", SchoolProfileView.as_view(), name="school-profile"),
    path("schools/me/details/", SchoolDetailsView.as_view(), name="school-details"),
    path("schools/me/onboarding/", SchoolOnboardingStatusView.as_view(), name="school-onboarding"),
]