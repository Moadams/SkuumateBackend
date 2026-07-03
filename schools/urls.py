from django.urls import path
from .views.views import (
    SchoolListExportView,
    SchoolProfileView,
    SchoolOnboardingStatusView,
)
from .views.superadmin_views import SuperSchoolDetailView, SchoolListCreateView

urlpatterns = [
    # Superadmin — school management
    path("schools/", SchoolListCreateView.as_view(), name="school-list"),
    path("schools/<uuid:school_id>/", SuperSchoolDetailView.as_view(), name="school-detail"),
    path("schools/export/", SchoolListExportView.as_view(), name="school-list-export"),

    # Admin — school profile
    path("schools/me/", SchoolProfileView.as_view(), name="school-profile"),
    path("schools/me/onboarding/", SchoolOnboardingStatusView.as_view(), name="school-onboarding"),
]