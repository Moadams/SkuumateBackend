from rest_framework import generics
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from core.permissions import IsAdmin
from core.models import AuditLog
from core.serializers import AuditLogSerializer
from subscriptions.permissions import HasAuditLogAccess


class AuditLogListView(generics.ListAPIView):
    permission_classes = [IsAdmin,HasAuditLogAccess]
    serializer_class = AuditLogSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["action", "resource"]
    search_fields = ["description", "resource", "actor__email"]
    ordering_fields = ["timestamp", "action", "resource"]
    ordering = ["-timestamp"]

    def get_queryset(self):
        return AuditLog.objects.filter(school=self.request.user.school)