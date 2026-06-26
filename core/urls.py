from django.urls import path
from .views import AuditLogListView, ClearAuditLogsView

urlpatterns = [
    path("audit-logs/", AuditLogListView.as_view(), name="audit-logs"),
    path("audit-logs/clear/", ClearAuditLogsView.as_view(), name="clear-audit-logs"),
]