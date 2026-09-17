from django.urls import path
from .views import AuditLogListView, ClearAuditLogsView, HealthCheckView
from .media import PrivateMediaView

urlpatterns = [
    path("private-media/<path:path>", PrivateMediaView.as_view(), name="private-media"),
    path("health/", HealthCheckView.as_view(), name="health-check"),
    path("audit-logs/", AuditLogListView.as_view(), name="audit-logs"),
    path("audit-logs/clear/", ClearAuditLogsView.as_view(), name="clear-audit-logs"),
]
