from django.urls import path

from . import views

urlpatterns = [
    path("", views.GuardianListCreateView.as_view(), name="guardian-account-list-create"),
    path("me/students/", views.GuardianStudentView.as_view(), name="guardian-account-my-students"),
    path(
        "me/students/<uuid:student_id>/",
        views.GuardianStudentDetailView.as_view(),
        name="guardian-account-my-student-detail",
    ),
    path(
        "me/students/<uuid:student_id>/reports/",
        views.GuardianStudentReportListView.as_view(),
        name="guardian-account-my-student-reports",
    ),
    path(
        "me/students/<uuid:student_id>/reports/<uuid:report_id>/",
        views.GuardianStudentReportDetailView.as_view(),
        name="guardian-account-my-student-report-detail",
    ),
    path(
        "me/students/<uuid:student_id>/invoices/",
        views.GuardianStudentInvoiceListView.as_view(),
        name="guardian-account-my-student-invoices",
    ),
    path(
        "me/students/<uuid:student_id>/invoices/<uuid:invoice_id>/",
        views.GuardianStudentInvoiceDetailView.as_view(),
        name="guardian-account-my-student-invoice-detail",
    ),
    path(
        "me/students/<uuid:student_id>/payments/",
        views.GuardianStudentPaymentListView.as_view(),
        name="guardian-account-my-student-payments",
    ),
    path(
        "me/students/<uuid:student_id>/academic-years/",
        views.GuardianStudentAcademicYearListView.as_view(),
        name="guardian-account-my-student-academic-years",
    ),
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
