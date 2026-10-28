from django.urls import path

from . import views

urlpatterns = [
    path("", views.GuardianListCreateView.as_view(), name="guardian-list-create"),
]
