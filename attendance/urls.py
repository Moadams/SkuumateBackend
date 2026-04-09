from django.urls import path
from .views import (
    BulkMarkAttendanceView,
    AttendanceListView,
    AttendanceExportView,
    AttendanceDetailView,
    ClassAttendanceSheetView,
    AttendanceSummaryListView,
    AttendanceSummaryExportView,
    StudentAttendanceReportView,
    ClassAttendanceReportView,
)

urlpatterns = [
    # Mark attendance
    path(
        "attendance/mark/",
        BulkMarkAttendanceView.as_view(),
        name="attendance-mark",
    ),

    # Records
    path(
        "attendance/",
        AttendanceListView.as_view(),
        name="attendance-list",
    ),
    path(
        "attendance/export/",
        AttendanceExportView.as_view(),
        name="attendance-export",
    ),
    path(
        "attendance/<uuid:pk>/",
        AttendanceDetailView.as_view(),
        name="attendance-detail",
    ),

    # Class attendance sheet (for marking screen)
    path(
        "attendance/class/<uuid:class_id>/sheet/",
        ClassAttendanceSheetView.as_view(),
        name="attendance-sheet",
    ),

    # Summaries
    path(
        "attendance/summaries/",
        AttendanceSummaryListView.as_view(),
        name="attendance-summary-list",
    ),
    path(
        "attendance/summaries/export/",
        AttendanceSummaryExportView.as_view(),
        name="attendance-summary-export",
    ),

    # Reports
    path(
        "attendance/report/student/<uuid:student_id>/",
        StudentAttendanceReportView.as_view(),
        name="student-attendance-report",
    ),
    path(
        "attendance/report/class/<uuid:class_id>/",
        ClassAttendanceReportView.as_view(),
        name="class-attendance-report",
    ),
]