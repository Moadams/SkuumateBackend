from django.urls import path

from .views.superadmin_views import SchoolListCreateView, SuperSchoolDetailView
from .views.views import (
    ProspectiveSchoolApprovalView,
    ProspectiveSchoolListView,
    PublicSchoolRegistrationView,
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

    path("schools/register/", PublicSchoolRegistrationView.as_view(), name="public-school-registration"),
    path("schools/prospective/", ProspectiveSchoolListView.as_view(), name="prospective-school-list"),
    path("schools/prospective/<uuid:pk>/approval/", ProspectiveSchoolApprovalView.as_view(), name="prospective-school-approval"),
]