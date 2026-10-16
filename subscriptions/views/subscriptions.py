from django.db import transaction
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from core.exceptions import PaymentGatewayError
from core.models import AuditLog
from core.permissions import IsAdmin
from core.responses import ApiResponse
from core.utils import log_action
from schools.utils import check_and_complete_onboarding
from subscriptions.filters import MySubscriptionFilter
from subscriptions.models import Subscription
from subscriptions.serializers import (
    SchoolSubscribeSerializer,
    SubscriptionListSerializer,
    SubscriptionSerializer,
)
from subscriptions.services.subscriptions import SubscriptionService


class MySubscriptionListView(generics.ListAPIView):
    """
    School user — list the school's subscriptions.

    """

    permission_classes = (IsAuthenticated,)
    serializer_class = SubscriptionListSerializer
    filterset_class = MySubscriptionFilter
    search_fields = ("plan__name", "plan__code")
    ordering_fields = ("start_date", "end_date", "created_at", "plan__name")
    ordering = ("-start_date",)

    def get_queryset(self):
        school = self.request.user.school
        if school is None:
            return Subscription.objects.none()
        return (
            school.subscriptions
            .select_related("plan", "term", "activated_by")
            .prefetch_related("payments")
        )


class CurrentSubscriptionView(APIView):
    """School user — returns the school's current subscription status."""

    permission_classes = (IsAuthenticated,)

    def get(self, request):
        school = request.user.school
        if school is None:
            return ApiResponse.error(message="No school associated with this account.", status_code=404)

        subscription = SubscriptionService.get_current(school)
        if not subscription:
            return ApiResponse.error(message="No subscription found.", status_code=404)

        return ApiResponse.success(data=SubscriptionSerializer(subscription).data)

class SchoolSubscribeView(APIView):
    """
    School admin — subscribe to a package.

    - New / never-paid schools get a free trial (no payment needed).
    - Everyone else pays through the frontend (e.g. Paystack Inline) and
      submits the resulting ``payment_reference``; the backend verifies the
      charge against the gateway before activating.
    """

    permission_classes = (IsAdmin,)
    @transaction.atomic
    def post(self, request):
        school = request.user.school
        if school is None:
            return ApiResponse.error(
                message="No school associated with this account.",
                status_code=404,
            )

        serializer = SchoolSubscribeSerializer(
            data=request.data, context={"school": school, "request": request}
        )
        serializer.is_valid(raise_exception=True)

        try:
            school_subscription = SubscriptionService.subscribe_school(data=serializer, school=school)
        except ValueError as e:
            return ApiResponse.error(
                message=str(e),
                status_code=400,
            )
        except PaymentGatewayError as e:
            return ApiResponse.error(
                message=str(e),
                status_code=400,
            )
        except Exception as e:
            return ApiResponse.error(
                message=str(e),
                status_code=500,
            )

        if school_subscription.created:
            message = f"Successfully subscribed to the {school_subscription.subscription.plan.name} package."
        else:
            message = f"Failed to subscribe to the {school_subscription.subscription.plan.name} package."

        log_action(
            action=AuditLog.Action.CREATE,
            resource="Subscription",
            resource_id=str(school_subscription.subscription.pk),
            description=(
                f"{school.name} subscribed to {school_subscription.subscription.plan.name} "
                f"({school_subscription.subscription.status})"
            ),
            request=request,
        )

        check_and_complete_onboarding(school)

        return ApiResponse.created(
            data=SubscriptionSerializer(school_subscription.subscription).data,
            message=message,
        )


