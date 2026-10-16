from django.urls import path

from .views import (
    ClassBulkStudentsView,
    ClassStudentsListView,
    GuardianDetailView,
    GuardianListCreateView,
    StudentBulkCreateView,
    StudentDetailView,
    StudentEnrollmentHistoryView,
    StudentEnrollView,
    StudentExcelTemplateView,
    StudentExportView,
    StudentIDCardView,
    StudentIDCardsBulkView,
    StudentListCreateView,
    StudentVerifyView,
)

urlpatterns = [
    # Students
    path("students/", StudentListCreateView.as_view(), name="student-list"),
    path("students/bulk/", StudentBulkCreateView.as_view(), name="student-bulk-create"),
    path("students/bulk/template/", StudentExcelTemplateView.as_view(), name="student-bulk-template"),
    path("students/class-bulk/", ClassBulkStudentsView.as_view(), name="student-class-bulk"),
    path("students/export/", StudentExportView.as_view(), name="student-export"),

    # Student ID cards
    path("students/id-cards/", StudentIDCardsBulkView.as_view(), name="student-id-cards"),
    path("students/verify/<str:student_id>/", StudentVerifyView.as_view(), name="student-verify"),
    path("students/<uuid:pk>/id-card/", StudentIDCardView.as_view(), name="student-id-card"),

    path("students/<uuid:pk>/", StudentDetailView.as_view(), name="student-detail"),

    # Guardians
    path("students/<uuid:pk>/guardians/", GuardianListCreateView.as_view(), name="guardian-list"),
    path("guardians/<uuid:pk>/", GuardianDetailView.as_view(), name="guardian-detail"),

    # Enrollment
    path("students/<uuid:pk>/enroll/", StudentEnrollView.as_view(), name="student-enroll"),
    path("students/<uuid:pk>/enrollments/", StudentEnrollmentHistoryView.as_view(), name="student-enrollments"),
    path("class/<uuid:class_id>/students/", ClassStudentsListView.as_view(), name="class-students"),

]