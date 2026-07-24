from django.urls import path
from .views import AuditLogListView, ClearAuditLogsView, HealthCheckView

urlpatterns = [
    path("health/", HealthCheckView.as_view(), name="health-check"),
    path("audit-logs/", AuditLogListView.as_view(), name="audit-logs"),
    path("audit-logs/clear/", ClearAuditLogsView.as_view(), name="clear-audit-logs"),
]