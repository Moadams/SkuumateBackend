from django.urls import path

from . import views

urlpatterns = [
    path("", views.GuardianListCreateView.as_view(), name="guardian-account-list-create"),
    path("me/students/", views.GuardianStudentView.as_view(), name="guardian-account-my-students"),
    path("<uuid:pk>/", views.GuardianDetailView.as_view(), name="guardian-account-detail"),
    path(
        "<uuid:pk>/students/link/",
        views.GuardianLinkStudentsView.as_view(),
        name="guardian-account-link-students",
    ),
    path(
        "<uuid:pk>/students/unlink/",
        views.GuardianUnlinkStudentsView.as_view(),
        name="guardian-account-unlink-students",
    ),
]
