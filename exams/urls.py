from django.urls import path
from . import views


urlpatterns = [
    path("exams/assessment-types/", views.AssessmentTypeListCreateView().as_view(),  name = "assessment-types"),
    path("exams/assessment-types/<uuid:pk>/", views.AssementTypeDetailView().as_view(), name = "assessment-type-detail"),
    path("exams/report-scheme/", views.ReportSchemeListCreateView.as_view(), name="report-scheme"),
    path("exams/report-scheme/<uuid:pk>/", views.ReportSchemeDetailView.as_view(), name = "report-scheme-detail")
]