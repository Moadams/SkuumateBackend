from core.school_permissions import school_permission
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, status
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.views import APIView

from core.exceptions import PaymentGatewayError
from core.mixins import AuditLogMixin
from core.models import AuditLog
from core.responses import ApiResponse
from core.utils import log_action
from subscriptions.permissions import HasAnnouncementAccess
from subscriptions.utils import check_feature

from .models import (
    NotificationProvider, NotificationTemplate,
    Notification, NotificationRecipient,
    SMSBundle, SMSPurchase, SMSLedgerEntry,
)
from .serializers import (
    NotificationProviderSerializer, NotificationTemplateSerializer,
    NotificationListSerializer, NotificationDetailSerializer,
    NotificationCreateSerializer, NotificationPreviewSerializer,
    NotificationRecipientSerializer, SendTestSerializer,
    SMSBundleSerializer, SMSPurchaseCreateSerializer, SMSPurchaseSerializer,
    SMSLedgerEntrySerializer, SMSSentHistorySerializer,
)
from .filters import (
    NotificationProviderFilter, NotificationTemplateFilter, NotificationFilter,
    SMSPurchaseFilter, SMSHistoryFilter, SMSLedgerFilter,
)
from .services.broadcast import BroadcastService, BroadcastValidationError
from .services.email_service import EmailService
from .services.sms_service import SMSService
from .services.sms_credits import SMSCreditService


# ─── Providers ─────────────────────────────────────────────────────

class NotificationProviderListCreateView(AuditLogMixin, generics.ListCreateAPIView):
    permission_classes = [school_permission(read="settings.manage", write="settings.manage")]
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
    permission_classes = [school_permission(read="settings.manage", write="settings.manage")]
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
    permission_classes = [school_permission(read="settings.manage", write="settings.manage")]

    def post(self, request):
        serializer = SendTestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        provider = serializer.validated_data["provider"]
        recipient = serializer.validated_data["recipient"]
        subject = serializer.validated_data["subject"]
        message = serializer.validated_data["message"]

        if provider.channel == NotificationProvider.Channel.EMAIL or (
            provider.channel == NotificationProvider.Channel.BOTH
            and "@" in recipient
        ):
            success, msg = EmailService.send(
                provider, recipient, subject, message,
                school_name=provider.school.name if provider.school else None,
            )
        elif provider.channel in (
            NotificationProvider.Channel.SMS,
            NotificationProvider.Channel.BOTH,
        ):
            # This view serves both channels, so the SMS entitlement is checked
            # on the branch rather than in permission_classes.
            check_feature(provider.school or request.user.school, "sms")
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
    permission_classes = [
        school_permission(read="announcements.view", write="announcements.manage"),
        HasAnnouncementAccess,
    ]
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
    permission_classes = [
        school_permission(read="announcements.view", write="announcements.manage"),
        HasAnnouncementAccess,
    ]
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
    permission_classes = [
        school_permission(read="announcements.view", write="announcements.manage"),
        HasAnnouncementAccess,
    ]
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

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            notification, _plan = BroadcastService.enqueue(
                request.user.school,
                user=request.user,
                title=data["title"],
                message_body=data["message_body"],
                channel=data["channel"],
                recipient_type=data["recipient_type"],
                recipient_ids=data.get("recipient_ids"),
                student_ids=data.get("student_ids"),
                staff_ids=data.get("staff_ids"),
                class_id=data.get("class_id"),
                template=data.get("template"),
                template_variables=data.get("template_variables"),
            )
        except BroadcastValidationError as exc:
            return ApiResponse.error(str(exc), errors=exc.details or None)
        except ValueError as exc:
            return ApiResponse.error(str(exc))

        log_action(
            action=AuditLog.Action.CREATE,
            resource=self.audit_resource,
            resource_id=str(notification.pk),
            description=(
                f"Notification '{notification.title}' queued via "
                f"{notification.channel}"
            ),
            request=self.request,
            metadata={
                **request.data,
                "queued_recipients": notification.total_recipients,
                "sms_credits_charged": notification.sms_credits_charged,
            },
        )

        return ApiResponse.created(
            data=NotificationDetailSerializer(
                notification, context=self.get_serializer_context()
            ).data,
            message="Notification queued for delivery.",
        )


class NotificationPreviewView(APIView):
    """Dry run: resolve the audience and report what a send would cost."""

    permission_classes = [
        school_permission(read="announcements.view", write="announcements.manage"),
        HasAnnouncementAccess,
    ]

    def post(self, request):
        serializer = NotificationPreviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            preview = BroadcastService.preview(
                request.user.school,
                channel=data["channel"],
                recipient_type=data["recipient_type"],
                message_body=data["message_body"],
                recipient_ids=data.get("recipient_ids"),
                student_ids=data.get("student_ids"),
                staff_ids=data.get("staff_ids"),
                class_id=data.get("class_id"),
            )
        except ValueError as exc:
            return ApiResponse.error(str(exc))

        return ApiResponse.success(
            data=preview,
            message=(
                "Audience is ready to send."
                if preview["can_send"]
                else "This notification cannot be sent yet."
            ),
        )


class NotificationDetailView(generics.RetrieveAPIView):
    permission_classes = [
        school_permission(read="announcements.view", write="announcements.manage"),
        HasAnnouncementAccess,
    ]
    serializer_class = NotificationDetailSerializer

    def get_queryset(self):
        return Notification.objects.filter(
            school=self.request.user.school
        ).prefetch_related("recipients")

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        return ApiResponse.success(data=self.get_serializer(instance).data)


class NotificationRecipientsListView(generics.ListAPIView):
    permission_classes = [
        school_permission(read="announcements.view", write="announcements.manage"),
        HasAnnouncementAccess,
    ]
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


# ─── SMS credits ───────────────────────────────────────────────────

class SMSWalletView(APIView):
    """Current SMS balance plus lifetime purchase/usage totals."""

    permission_classes = [
        school_permission(read="announcements.view"),
        HasAnnouncementAccess,
    ]

    def get(self, request):
        return ApiResponse.success(
            data=SMSCreditService.summary(request.user.school),
            message="SMS wallet retrieved.",
        )


class SMSBundleListView(generics.ListAPIView):
    """Active platform-defined SMS bundles that a school can buy."""

    permission_classes = [school_permission(read="announcements.view")]
    serializer_class = SMSBundleSerializer
    pagination_class = None

    def get_queryset(self):
        return SMSCreditService.active_bundles()

    def list(self, request, *args, **kwargs):
        return ApiResponse.success(
            data=self.get_serializer(self.get_queryset(), many=True).data
        )


class SMSPurchaseListCreateView(generics.ListCreateAPIView):
    """List bundle purchases, or verify a gateway reference and credit it.

    The frontend collects the Paystack payment and posts the reference; the
    backend verifies it with the gateway before adding credits. Repeating the
    same reference is idempotent and never double-credits.
    """

    permission_classes = [
        school_permission(read="announcements.view", write="announcements.manage"),
        HasAnnouncementAccess,
    ]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = SMSPurchaseFilter
    ordering_fields = ["created_at", "amount", "credits"]
    ordering = ["-created_at"]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return SMSPurchaseCreateSerializer
        return SMSPurchaseSerializer

    def get_queryset(self):
        return SMSPurchase.objects.filter(
            school=self.request.user.school
        ).select_related("bundle", "purchased_by")

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
        data = serializer.validated_data

        bundle = SMSBundle.objects.filter(
            pk=data["bundle"], is_active=True
        ).first()
        if bundle is None:
            return ApiResponse.error(
                "This SMS bundle does not exist or is no longer available."
            )

        try:
            purchase, created = SMSCreditService.purchase(
                request.user.school,
                request.user,
                bundle=bundle,
                payment_reference=data["payment_reference"],
                provider=data["provider"],
            )
        except PaymentGatewayError as exc:
            return ApiResponse.error(str(exc), status_code=status.HTTP_402_PAYMENT_REQUIRED)
        except ValueError as exc:
            return ApiResponse.error(str(exc))

        if created:
            log_action(
                action=AuditLog.Action.CREATE,
                resource="SMSPurchase",
                resource_id=str(purchase.pk),
                description=(
                    f"Purchased {purchase.credits} SMS credits "
                    f"({purchase.bundle.name})"
                ),
                request=self.request,
            )

        return ApiResponse.created(
            data=SMSPurchaseSerializer(purchase).data,
            message=(
                "SMS bundle purchased successfully."
                if created
                else "This payment was already processed."
            ),
        )


class SMSHistoryView(generics.ListAPIView):
    """Every SMS delivery attempt made by the school."""

    permission_classes = [
        school_permission(read="announcements.view"),
        HasAnnouncementAccess,
    ]
    serializer_class = SMSSentHistorySerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = SMSHistoryFilter
    search_fields = [
        "recipient_name", "recipient_contact", "notification__title",
    ]
    ordering_fields = ["created_at", "sent_at", "recipient_name"]
    ordering = ["-created_at"]

    def get_queryset(self):
        return NotificationRecipient.objects.filter(
            notification__school=self.request.user.school,
            channel=NotificationRecipient.Channel.SMS,
        ).select_related("notification")

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return ApiResponse.success(data=serializer.data)


class SMSLedgerListView(generics.ListAPIView):
    """Credit movements: purchases, usage, refunds and adjustments."""

    permission_classes = [
        school_permission(read="announcements.view"),
        HasAnnouncementAccess,
    ]
    serializer_class = SMSLedgerEntrySerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = SMSLedgerFilter
    search_fields = ["description", "notification__title"]
    ordering_fields = ["created_at", "credits", "balance_after"]
    ordering = ["-created_at"]

    def get_queryset(self):
        return SMSLedgerEntry.objects.filter(
            school=self.request.user.school
        ).select_related("notification", "purchase", "created_by")

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return ApiResponse.success(data=serializer.data)
