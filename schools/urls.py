from django.urls import path
from .views import SchoolOnboardView, SchoolDetailView

urlpatterns = [
    path("schools/onboard/", SchoolOnboardView.as_view(), name="school-onboard"),
    path("schools/me/", SchoolDetailView.as_view(), name="school-detail"),
]