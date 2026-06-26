from django.urls import path
from . import views

urlpatterns = [
    path("exams/assessment-types/", views.AssessmentTypeListCreateView().as_view(),  name = "assessment-types"),
    path("exams/assessment-types/<uuid:pk>/", views.AssementTypeDetailView().as_view(), name = "assessment-type-detail"),
    path("exams/report-scheme/", views.ReportSchemeListCreateView.as_view(), name="report-scheme"),
    path("exams/report-scheme/<uuid:pk>/", views.ReportSchemeDetailView.as_view(), name = "report-scheme-detail"),
    path(
        "exams/classes/<uuid:class_id>/marks/",
        views.StudentMarksListView.as_view(),
        name="class-student-marks",
    ),
    path(
        "exams/marks/class/", 
        views.StudentMarkBulkView.as_view(), 
        name="student-mark-bulk"
    ),
    path("exams/generate-report/class/<uuid:class_id>/info/", views.ClassReportGenerationValidityView.as_view(), name="generate-report"),
    path("reports/generate/", views.GenerateClassReportView.as_view(), name="generate-reports"),
    path("reports/publish/",views.PublishStudentReportsView.as_view(), name="publish-reports"),
    path("reports/class/<uuid:class_id>/term/<uuid:term_id>/", views.StudentReportListView.as_view(), name="class-students-report"),
    path("reports/<uuid:pk>/", views.StudentReportDetailView.as_view(), name="student-report-detail"),
    path("reports/<uuid:pk>/teacher-remarks/", views.StudentReportTeacherRemarksView.as_view(), name="teacher-remarks"),
    path("reports/<uuid:pk>/head-teacher-remarks/", views.StudentReportHeadteacherRemarksView.as_view(), name="head-teacher-remarks"),
    path("reports/subject-score/term/<uuid:term_id>/subject/<uuid:subject_id>/class/<uuid:class_id>/", views.StudentReportSubjectScoreListView.as_view(), name = "student-report-subject-score"),
]