from django.urls import path, include
from . import views

urlpatterns = [
    path("exams/assessment-types/", views.AssessmentTypeListCreateView().as_view(),  name = "assessment-types"),
    path("exams/assessment-types/<uuid:pk>/", views.AssementTypeDetailView().as_view(), name = "assessment-type-detail"),
    path("exams/report-scheme/", views.ReportSchemeListCreateView.as_view(), name="report-scheme"),
    path("exams/report-scheme/<uuid:pk>/", views.ReportSchemeDetailView.as_view(), name = "report-scheme-detail"),
    path(
        "exams/marks/class/<uuid:class_id>/assessment/<uuid:assessment_id>/subject/<uuid:subject_id>/", 
        views.StudentMarkBulkView.as_view(), 
        name="student-mark-bulk"
    ),
]