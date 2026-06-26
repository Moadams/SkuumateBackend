from django.urls import path
from .views import (
    PermissionListView,
    StaffPositionListCreateView,
    StaffPositionDetailView,
    StaffListCreateView,
    StaffDetailView,
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
    )
]

