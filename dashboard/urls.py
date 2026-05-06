from django.urls import path

from .views import SuperadminDashboardView

urlpatterns = [
    path("dashboard/superadmin/", SuperadminDashboardView.as_view(), name="superadmin-dashboard"),
]