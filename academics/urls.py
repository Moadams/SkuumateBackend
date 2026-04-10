from django.urls import path
from .views import (
    AcademicYearListCreateView, AcademicYearDetailView, AcademicYearExportView, AcademicYearTermsListView, ActivateTermView,
    TermListCreateView, TermDetailView, TermExportView,
    SubjectListCreateView, SubjectDetailView, SubjectExportView,
    ClassListCreateView, ClassDetailView, ClassExportView,
    ClassSubjectAssignView, ClassTeacherAssignView,
)

urlpatterns = [
    # Academic Years
    path("academic-years/", AcademicYearListCreateView.as_view(), name="academic-year-list"),
    path("academic-years/export/", AcademicYearExportView.as_view(), name="academic-year-export"),
    path("academic-years/<uuid:pk>/", AcademicYearDetailView.as_view(), name="academic-year-detail"),

    # Terms
    path("terms/", TermListCreateView.as_view(), name="term-list"),
    path("terms/export/", TermExportView.as_view(), name="term-export"),
    path("terms/<uuid:pk>/", TermDetailView.as_view(), name="term-detail"),
    path("academic-years/<uuid:academic_year_id>/terms/", AcademicYearTermsListView.as_view(), name="academic-year-term-list"),
    path("terms/<uuid:term_id>/activate/", ActivateTermView.as_view(), name="activate-term"),

    # Subjects
    path("subjects/", SubjectListCreateView.as_view(), name="subject-list"),
    path("subjects/export/", SubjectExportView.as_view(), name="subject-export"),
    path("subjects/<uuid:pk>/", SubjectDetailView.as_view(), name="subject-detail"),

    # Classes
    path("classes/", ClassListCreateView.as_view(), name="class-list"),
    path("classes/export/", ClassExportView.as_view(), name="class-export"),
    path("classes/<uuid:pk>/", ClassDetailView.as_view(), name="class-detail"),
    path("classes/<uuid:pk>/subjects/", ClassSubjectAssignView.as_view(), name="class-subjects"),
    path("classes/<uuid:pk>/teacher/", ClassTeacherAssignView.as_view(), name="class-teacher"),
]