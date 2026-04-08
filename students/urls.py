from django.urls import path
from .views import (
    StudentListCreateView, StudentDetailView, StudentExportView,
    GuardianListCreateView, GuardianDetailView,
    StudentEnrollView, StudentEnrollmentHistoryView,
)

urlpatterns = [
    # Students
    path("students/", StudentListCreateView.as_view(), name="student-list"),
    path("students/export/", StudentExportView.as_view(), name="student-export"),
    path("students/<uuid:pk>/", StudentDetailView.as_view(), name="student-detail"),

    # Guardians
    path("students/<uuid:pk>/guardians/", GuardianListCreateView.as_view(), name="guardian-list"),
    path("guardians/<uuid:pk>/", GuardianDetailView.as_view(), name="guardian-detail"),

    # Enrollment
    path("students/<uuid:pk>/enroll/", StudentEnrollView.as_view(), name="student-enroll"),
    path("students/<uuid:pk>/enrollments/", StudentEnrollmentHistoryView.as_view(), name="student-enrollments"),
]