from django.urls import path
from . import views


urlpatterns = [
    path("exams/assessment-types/", views.AssessmentTypeListCreateView().as_view(),  name = "assessment-types")
]