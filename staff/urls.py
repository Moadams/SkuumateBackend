from django.urls import path
from .views import (
    PermissionListView,
    ResetStaffPasswordView,
    StaffPositionListCreateView,
    StaffPositionDetailView,
    StaffListCreateView,
    StaffDetailView,
    StaffPhotoUploadView,
    StaffExportView,
    MyStaffProfileView,
)

urlpatterns = [
    # Permission registry
    path(
        "staff/permissions/",
        PermissionListView.as_view(),
        name="permission-list",
    ),

    # Positions
    path(
        "staff/positions/",
        StaffPositionListCreateView.as_view(),
        name="staff-position-list",
    ),
    path(
        "staff/positions/<uuid:pk>/",
        StaffPositionDetailView.as_view(),
        name="staff-position-detail",
    ),

    # Staff profiles
    path(
        "staff/",
        StaffListCreateView.as_view(),
        name="staff-list",
    ),
    path(
        "staff/export/",
        StaffExportView.as_view(),
        name="staff-export",
    ),
    path(
        "staff/me/",
        MyStaffProfileView.as_view(),
        name="staff-me",
    ),
    path(
        "staff/<uuid:pk>/",
        StaffDetailView.as_view(),
        name="staff-detail",
    ),
    path(
        "staff/<uuid:pk>/photo/",
        StaffPhotoUploadView.as_view(),
        name="staff-photo",
    ),
    path(
        "staff/<uuid:pk>/reset-password/",
        ResetStaffPasswordView.as_view(),
        name="staff-reset-password",
    )
]