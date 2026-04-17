from django.urls import path
from .views import (
    AcademicYearListCreateView, AcademicYearDetailView, AcademicYearExportView, AcademicYearTermsListView, ActivateTermView, BulkSubjectTeacherAssignView, ClassSubjectTeacherSummaryView, GradeResolverView, GradeScaleBulkSetView, GradeScaleUpdateView, GradingSystemDetailView, GradingSystemListCreateView, GradingSystemSetDefaultView, SubjectTeacherAssignView, SubjectTeacherDetailView, SubjectTeacherExportView, SubjectTeacherListView,
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

    # Grading Systems
    path(
        "grading-systems/",
        GradingSystemListCreateView.as_view(),
        name="grading-system-list",
    ),
    path(
        "grading-systems/<uuid:pk>/",
        GradingSystemDetailView.as_view(),
        name="grading-system-detail",
    ),
    path(
        "grading-systems/<uuid:pk>/set-default/",
        GradingSystemSetDefaultView.as_view(),
        name="grading-system-set-default",
    ),
    path(
        "grading-systems/<uuid:pk>/grades/",
        GradeScaleBulkSetView.as_view(),
        name="grade-scale-bulk",
    ),
    path(
        "grading-systems/<uuid:pk>/resolve/",
        GradeResolverView.as_view(),
        name="grade-resolver",
    ),

    # Individual grade scale
    path(
        "grade-scales/<uuid:pk>/",
        GradeScaleUpdateView.as_view(),
        name="grade-scale-detail",
    ),


    # Subject Teacher Assignments
    path(
        "subject-teachers/",
        SubjectTeacherListView.as_view(),
        name="subject-teacher-list",
    ),
    path(
        "subject-teachers/assign/",
        SubjectTeacherAssignView.as_view(),
        name="subject-teacher-assign",
    ),
    path(
        "subject-teachers/bulk-assign/",
        BulkSubjectTeacherAssignView.as_view(),
        name="subject-teacher-bulk-assign",
    ),
    path(
        "subject-teachers/export/",
        SubjectTeacherExportView.as_view(),
        name="subject-teacher-export",
    ),
    path(
        "subject-teachers/<uuid:pk>/",
        SubjectTeacherDetailView.as_view(),
        name="subject-teacher-detail",
    ),
    path(
        "subject-teachers/class/<uuid:class_id>/summary/",
        ClassSubjectTeacherSummaryView.as_view(),
        name="class-subject-teacher-summary",
    ),
]