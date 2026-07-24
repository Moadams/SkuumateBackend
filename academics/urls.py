from django.urls import path

from academics.views.academic_term_views import (
    AcademicYearTermsListView,
    ActivateTermView,
    TermDetailView,
    TermExportView,
    TermListCreateView,
)
from academics.views.academic_year_views import (
    AcademicYearDetailView,
    AcademicYearExportView,
    AcademicYearListCreateView,
)
from academics.views.class_views import (
    BulkAssignClassSubjectsView,
    ClassDetailView,
    ClassExportView,
    ClassListCreateView,
    ClassSubjectDetailView,
    ClassSubjectsListCreateView,
    ClassTeacherView,
    TeacherClassesView,
    UnassignClassTeacherView,
)
from academics.views.grade_views import (
    GradeScaleUpdateDestroyView,
    GradingScaleCreateListView,
    GradingSystemDetailView,
    GradingSystemListCreateView,
)
from academics.views.subject_views import (
    SubjectDetailView,
    SubjectExportView,
    SubjectListCreateView,
    SubjectTeacherListCreateView,
    UnassignSubjectTeacherView,
)

from .views.views import (
    BulkSubjectTeacherAssignView,
    ClassSubjectTeacherSummaryView,
    GradeResolverView,
    GradeScaleBulkSetView,
    TimeTableSlotListCreateView,
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
    path("classes/<uuid:class_id>/subjects/", ClassSubjectsListCreateView.as_view(), name="class-subjects"),
    path("classes/<uuid:class_id>/bulk-assign-subjects/", BulkAssignClassSubjectsView.as_view(), name="class-bulk-assign-subjects"),
    path("class-subjects/<uuid:pk>/", ClassSubjectDetailView.as_view(), name="class-subject-detail"),
    path("classes/<uuid:class_id>/teacher/", ClassTeacherView.as_view(), name="class-teacher"),
    path("class-teachers/<uuid:pk>/", UnassignClassTeacherView.as_view(), name="class-teacher-detail"),

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
    path("grading-systems/<uuid:grading_system_id>/scales/", GradingScaleCreateListView.as_view()),
    # path(
    #     "grading-systems/<uuid:pk>/set-default/",
    #     GradingSystemSetDefaultView.as_view(),
    #     name="grading-system-set-default",
    # ),
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
        GradeScaleUpdateDestroyView.as_view(),
        name="grade-scale-detail",
    ),


    # Subject Teacher Assignments
    path(
        "subject-teachers/",
        SubjectTeacherListCreateView.as_view(),
        name="subject-teacher-list",
    ),
    path(
        "subject-teachers/bulk-assign/",
        BulkSubjectTeacherAssignView.as_view(),
        name="subject-teacher-bulk-assign",
    ),

    path(
        "subject-teachers/<uuid:pk>/",
        UnassignSubjectTeacherView.as_view(),
        name="subject-teacher-detail",
    ),
    path(
        "subject-teachers/class/<uuid:class_id>/summary/",
        ClassSubjectTeacherSummaryView.as_view(),
        name="class-subject-teacher-summary",
    ),

    path("timetable-slots/<uuid:class_id>/", TimeTableSlotListCreateView.as_view(), name="timetable-slot-list-create"),


    # teacher routers
    path("teacher/me/classes/", TeacherClassesView.as_view(), name="teacher-classes"),
]
