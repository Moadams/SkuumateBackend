from django.urls import path

from .views import (
    ClassBulkStudentsView,
    ClassStudentsListView,
    GuardianDetailView,
    GuardianListCreateView,
    PromotionBatchDetailView,
    PromotionBatchListCreateView,
    PromotionBatchReverseView,
    StudentBulkCreateView,
    StudentDetailView,
    StudentEnrollmentHistoryView,
    StudentEnrollView,
    StudentExcelTemplateView,
    StudentExportView,
    StudentIDCardsBulkView,
    StudentIDCardView,
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

    # Promotion
    path("students/promotions/", PromotionBatchListCreateView.as_view(), name="promotion-list"),
    path("students/promotions/<uuid:pk>/", PromotionBatchDetailView.as_view(), name="promotion-detail"),
    path("students/promotions/<uuid:pk>/reverse/", PromotionBatchReverseView.as_view(), name="promotion-reverse"),

    path("students/<uuid:pk>/", StudentDetailView.as_view(), name="student-detail"),

    # Guardians
    path("students/<uuid:pk>/guardians/", GuardianListCreateView.as_view(), name="guardian-list"),
    path("students/guardians/<uuid:pk>/", GuardianDetailView.as_view(), name="guardian-detail"),

    # Enrollment
    path("students/<uuid:pk>/enroll/", StudentEnrollView.as_view(), name="student-enroll"),
    path("students/<uuid:pk>/enrollments/", StudentEnrollmentHistoryView.as_view(), name="student-enrollments"),
    path("class/<uuid:class_id>/students/", ClassStudentsListView.as_view(), name="class-students"),

]
