from django.db import transaction
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, status
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.views import APIView

from core.mixins import AuditLogMixin
from core.models import AuditLog
from core.permissions import IsAdmin, IsSuperAdmin
from core.responses import ApiResponse
from core.utils import log_action

from .models import (
    NotificationProvider, NotificationTemplate,
    Notification, NotificationRecipient,
)
from .serializers import (
    NotificationProviderSerializer, NotificationTemplateSerializer,
    NotificationListSerializer, NotificationDetailSerializer,
    NotificationCreateSerializer, NotificationRecipientSerializer,
    SendTestSerializer,
)
from .filters import (
    NotificationProviderFilter, NotificationTemplateFilter, NotificationFilter,
)
from .services.email_service import EmailService
from .services.sms_service import SMSService
from .services.sender import NotificationSender


# ─── Providers ─────────────────────────────────────────────────────

class NotificationProviderListCreateView(AuditLogMixin, generics.ListCreateAPIView):
    permission_classes = [IsAdmin]
    serializer_class = NotificationProviderSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = NotificationProviderFilter
    search_fields = ["name", "provider_type"]
    ordering_fields = ["channel", "name", "created_at"]
    ordering = ["channel", "name"]
    audit_resource = "NotificationProvider"

    def get_queryset(self):
        return NotificationProvider.objects.filter(school=self.request.user.school)

    def perform_create(self, serializer):
        instance = serializer.save(school=self.request.user.school)
        log_action(
            action=AuditLog.Action.CREATE,
            resource=self.audit_resource,
            resource_id=str(instance.pk),
            description=f"Provider '{instance.name}' created",
            request=self.request,
        )
        return instance

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return ApiResponse.success(data=serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return ApiResponse.created(
            data=serializer.data,
            message="Provider created successfully.",
        )


class NotificationProviderDetailView(AuditLogMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdmin]
    serializer_class = NotificationProviderSerializer
    audit_resource = "NotificationProvider"

    def get_queryset(self):
        return NotificationProvider.objects.filter(school=self.request.user.school)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        return ApiResponse.success(data=self.get_serializer(instance).data)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return ApiResponse.success(
            data=serializer.data,
            message="Provider updated successfully.",
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return ApiResponse.success(message="Provider deleted successfully.")


class SendTestNotificationView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request):
        serializer = SendTestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        provider = serializer.validated_data["provider"]
        recipient = serializer.validated_data["recipient"]
        subject = serializer.validated_data["subject"]
        message = serializer.validated_data["message"]

        if provider.channel == NotificationProvider.Channel.EMAIL:
            success, msg = EmailService.send(
                provider, recipient, subject, message,
                school_name=provider.school.name if provider.school else None,
            )
        elif provider.channel == NotificationProvider.Channel.SMS:
            success, msg = SMSService.send(provider, recipient, message)
        else:
            return ApiResponse.error(message=f"Unknown channel: {provider.channel}")

        if success:
            return ApiResponse.success(
                data={"provider": provider.name, "recipient": recipient},
                message=msg,
            )
        return ApiResponse.error(message=msg, status_code=400)


# ─── Templates ─────────────────────────────────────────────────────

class NotificationTemplateListCreateView(AuditLogMixin, generics.ListCreateAPIView):
    permission_classes = [IsAdmin]
    serializer_class = NotificationTemplateSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = NotificationTemplateFilter
    search_fields = ["name", "subject"]
    ordering_fields = ["name", "created_at"]
    ordering = ["name"]
    audit_resource = "NotificationTemplate"

    def get_queryset(self):
        return NotificationTemplate.objects.filter(school=self.request.user.school)

    def perform_create(self, serializer):
        instance = serializer.save(school=self.request.user.school)
        log_action(
            action=AuditLog.Action.CREATE,
            resource=self.audit_resource,
            resource_id=str(instance.pk),
            description=f"Template '{instance.name}' created",
            request=self.request,
        )
        return instance

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return ApiResponse.success(data=serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return ApiResponse.created(
            data=serializer.data,
            message="Template created successfully.",
        )


class NotificationTemplateDetailView(AuditLogMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdmin]
    serializer_class = NotificationTemplateSerializer
    audit_resource = "NotificationTemplate"

    def get_queryset(self):
        return NotificationTemplate.objects.filter(school=self.request.user.school)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        return ApiResponse.success(data=self.get_serializer(instance).data)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return ApiResponse.success(
            data=serializer.data,
            message="Template updated successfully.",
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return ApiResponse.success(message="Template deleted successfully.")


# ─── Notifications ─────────────────────────────────────────────────

class NotificationListCreateView(AuditLogMixin, generics.ListCreateAPIView):
    permission_classes = [IsAdmin]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = NotificationFilter
    search_fields = ["title", "message_body"]
    ordering_fields = ["created_at", "sent_at", "title"]
    ordering = ["-created_at"]
    audit_resource = "Notification"

    def get_serializer_class(self):
        if self.request.method == "POST":
            return NotificationCreateSerializer
        return NotificationListSerializer

    def get_queryset(self):
        return Notification.objects.filter(school=self.request.user.school)

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["school"] = self.request.user.school
        return ctx

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return ApiResponse.success(data=serializer.data)

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        school = request.user.school
        data = serializer.validated_data

        # Build metadata with filter criteria
        metadata = {}
        if data.get("recipient_ids"):
            metadata["recipient_ids"] = [str(rid) for rid in data["recipient_ids"]]
        if data.get("class_id"):
            metadata["class_id"] = str(data["class_id"])
        metadata["template_variables"] = data.get("template_variables", {})

        notification = Notification.objects.create(
            school=school,
            template=data.get("template"),
            title=data["title"],
            message_body=data["message_body"],
            channel=data["channel"],
            recipient_type=data["recipient_type"],
            metadata=metadata,
            sent_by=request.user,
        )

        # Resolve recipients and send
        notification = NotificationSender.send(notification)

        log_action(
            action=AuditLog.Action.CREATE,
            resource=self.audit_resource,
            resource_id=str(notification.pk),
            description=f"Notification '{notification.title}' sent via {notification.channel}",
            request=self.request,
            metadata=request.data
        )

        return ApiResponse.created(
            data=NotificationDetailSerializer(notification).data,
            message="Notification sent successfully.",
        )


class NotificationDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAdmin]
    serializer_class = NotificationDetailSerializer

    def get_queryset(self):
        return Notification.objects.filter(
            school=self.request.user.school
        ).prefetch_related("recipients")

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        return ApiResponse.success(data=self.get_serializer(instance).data)


class NotificationRecipientsListView(generics.ListAPIView):
    permission_classes = [IsAdmin]
    serializer_class = NotificationRecipientSerializer

    def get_queryset(self):
        return NotificationRecipient.objects.filter(
            notification_id=self.kwargs["notification_id"],
            notification__school=self.request.user.school,
        )

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return ApiResponse.success(data=serializer.data)
