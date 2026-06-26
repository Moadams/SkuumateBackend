from django.urls import path

from .views import (
    SuperadminDashboardView,
    AdminDashboardView,
    FinanceManagerDashboardView,
    TeacherDashboardView,
)

urlpatterns = [
    path("dashboard/superadmin/", SuperadminDashboardView.as_view(), name="superadmin-dashboard"),
    path("dashboard/admin/", AdminDashboardView.as_view(), name="admin-dashboard"),
    path("dashboard/finance/", FinanceManagerDashboardView.as_view(), name="finance-dashboard"),
    path("dashboard/teacher/", TeacherDashboardView.as_view(), name="teacher-dashboard"),
]