"""Subscription lifecycle services.

All subscription state changes (trials, activations, renewals) must go
through :class:`SubscriptionService` so the invariants the rest of the
platform relies on (a single ``is_current`` subscription per school,
correct status transitions, payment linkage) stay in one place.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from django.db import transaction
from django.utils import timezone

from academics.services import AcademicsService
from core.exceptions import PaymentGatewayError
from core.payments.factory import get_payment_gateway
from subscriptions.models import Subscription, SubscriptionPayment
from subscriptions.serializers import SchoolSubscribeSerializer

SUBSCRIPTION_DAYS = {
    "MONTH": 30,
    "YEAR": 365
}

@dataclass
class ActivationResult:
    """Outcome of an activation request, with idempotency handling."""
    subscription: Subscription
    created: bool


class SubscriptionService:
    """Coordinates creating and activating subscriptions for a school."""

    # ── Read-side helpers ─────────────────────────────────────────

    @staticmethod
    def subscribe_school(data: SchoolSubscribeSerializer, school):
        """Subscribe a school to a plan, starting a trial or paid subscription."""
        plan = data.validated_data["plan"]
        term = data.validated_data.get("term")
        is_paid = data.validated_data.get("is_paid", False)
        payment_method = data.validated_data.get("payment_method")
        payment_reference = data.validated_data.get("payment_reference")
        activated_by = data.context["request"].user

        if is_paid:
            subscription, payment = SubscriptionService._create_pending_subscription_payment(school, data)
            
            payment_gateway = get_payment_gateway()
            verification_result = payment_gateway.verify_purchase(
                gateway_reference=payment_method,
                payload={"reference": payment_reference, "amount": plan.price, "currency": plan.currency},
            )
            if not verification_result.success:
                raise PaymentGatewayError(f"Payment verification failed: {verification_result.error}")
            
            subscription = SubscriptionService._activate_subscription(
                subscription=subscription,
                payment=payment,
                activated_by=activated_by
            )
            return ActivationResult(subscription=subscription, created=True)
        else:
            if not SubscriptionService.is_eligible_for_trial(school):
                raise ValueError("School is not eligible for a trial subscription.")
            
            subscription = SubscriptionService.start_trial(
                school=school,
                plan=plan,
                term=term,
                activated_by=activated_by,
            )
            return ActivationResult(subscription=subscription, created=True)

    @staticmethod
    @transaction.atomic
    def _create_pending_subscription_payment(school, data: SchoolSubscribeSerializer) -> tuple[Subscription, SubscriptionPayment]:
        """Create a pending subscription payment record for a school."""
        plan = data.validated_data["plan"]
        payment_method = data.validated_data.get("payment_method")
        payment_reference = data.validated_data.get("payment_reference")
        start_date, end_date = SubscriptionService._get_start_and_end_dates(data.validated_data.get("term"))

        subscription = Subscription.objects.create(
            school=school,
            plan=plan,
            status=Subscription.Status.PENDING_PAYMENT,
            is_paid=True,
            start_date=start_date,
            end_date=end_date,
            term = getattr(data.validated_data, "term", None),
            is_current=False,
            
        )

        subscription_payment =  SubscriptionPayment.objects.create(
            subscription=subscription,
            school=school,
            plan=plan,
            term = getattr(data.validated_data, "term", None),
            amount=plan.price,
            payment_mode=payment_method,
            payment_reference=payment_reference,
            status=SubscriptionPayment.PaymentStatus.PENDING,
            recorded_by=data.context["request"].user,
        )
        return subscription, subscription_payment

    @staticmethod
    @transaction.atomic
    def _activate_subscription(subscription: Subscription, payment: SubscriptionPayment | None, activated_by) -> Subscription:
        """Activate a subscription and link it to a successful payment if provided."""
        subscription.status = Subscription.Status.ACTIVE
        subscription.is_current = True
        subscription.activated_by = activated_by
        if subscription.term:
            start_date = subscription.term.start_date
            end_date = subscription.term.end_date + timedelta(days=1) 
        else:
            start_date = datetime.now().date()
            end_date = start_date + timedelta(days=SUBSCRIPTION_DAYS.get(subscription.plan.billing_period, 30))
        grace_period = end_date + timedelta(days=Subscription.GRACE_DAYS)   
        subscription.start_date = start_date
        subscription.end_date = end_date
        subscription.grace_end_date = grace_period
        subscription.save(update_fields=["status", "is_current", "activated_by", "updated_at", "start_date", "end_date", "grace_end_date"])

        other_active_subscriptions = Subscription.objects.filter(
            school=subscription.school,
            status__in=[Subscription.Status.ACTIVE, Subscription.Status.GRACE],
        ).exclude(pk=subscription.pk)
        other_active_subscriptions.update(status=Subscription.Status.CANCELLED, is_current=False)

        if payment:
            payment.status = SubscriptionPayment.PaymentStatus.SUCCESSFUL
            payment.subscription = subscription
            payment.save(update_fields=["status", "subscription", "updated_at"])

        return subscription

    @staticmethod
    def get_current(school) -> Optional[Subscription]:
        """Return the school's current (live) subscription, if any."""
        subscription = (
            school.subscriptions
            .filter(is_current=True)
            .select_related("plan")
            .order_by("-start_date")
            .first()
        )
        if subscription:
            subscription.sync_status()
        return subscription

    @staticmethod
    def is_eligible_for_trial(school) -> bool:
        """A school is eligible for a trial when it has no record of trial subscriptions"""
        has_trial = Subscription.objects.filter(
            school=school,
            is_paid=False,
        ).exists()
        return not has_trial

    
    @staticmethod
    @transaction.atomic
    def start_trial(
        school,
        plan,
        term=None,
        activated_by=None,
    ) -> Subscription:
        
        school.subscriptions.filter(
            status__in=[Subscription.Status.ACTIVE, Subscription.Status.GRACE]
        ).update(status=Subscription.Status.CANCELLED, is_current=False)

        resolved_term = term or AcademicsService._current_term(school)
        start_date, end_date = SubscriptionService._get_start_and_end_dates(resolved_term)

        return Subscription.objects.create(
            school=school,
            plan=plan,
            term=term,
            status=Subscription.Status.ACTIVE,
            start_date=start_date,
            end_date=end_date,
            is_paid=False,
            activated_by=activated_by,
            notes="Free trial subscription",
            is_current=True,
        )

    @staticmethod
    def _get_start_and_end_dates(term):
        """Return the start and end dates for a subscription based on the term."""
        if term:
            start_date = term.start_date
            end_date = term.end_date + timedelta(days=1)  # Include the last day of the term
        else:
            today = datetime.now().date()
            start_date = today
            end_date = today + timedelta(days=Subscription.ACTIVE_DAYS)
        return start_date, end_date
