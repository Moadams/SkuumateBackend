from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from core.permissions import CanAccessAuditLogs
from core.models import AuditLog
from core.serializers import AuditLogSerializer


class AuditLogListView(generics.ListAPIView):
    permission_classes = [
        CanAccessAuditLogs
    ]
    serializer_class = AuditLogSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["action", "resource"]
    search_fields = ["description", "resource", "actor__email"]
    ordering_fields = ["timestamp", "action", "resource"]
    ordering = ["-timestamp"]

    def get_queryset(self):
        if self.request.user.is_superuser:
            return AuditLog.objects.all()
        return AuditLog.objects.filter(school=self.request.user.school)


class ClearAuditLogsView(APIView):
    permission_classes = [CanAccessAuditLogs]

    def delete(self, request, *args, **kwargs):
        if request.user.is_superuser:
            audit_logs = AuditLog.objects.all()
        audit_logs = AuditLog.objects.filter(school=request.user.school)
        audit_logs.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
