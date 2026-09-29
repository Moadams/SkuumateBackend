"""Subscription lifecycle services.

All subscription state changes (trials, activations, renewals) must go
through :class:`SubscriptionService` so the invariants the rest of the
platform relies on (a single ``is_current`` subscription per school,
correct status transitions, payment linkage) stay in one place.
"""
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

from django.db import transaction
from django.utils import timezone

from subscriptions.models import Subscription, SubscriptionPayment


def _term_end_datetime(term) -> "Optional[str]":
    """Convert a term's ``end_date`` (DateField) to a timezone-aware datetime."""
    if term is None or term.end_date is None:
        return None
    return timezone.make_aware(
        timezone.datetime.combine(term.end_date, timezone.datetime.min.time())
    )


@dataclass
class ActivationResult:
    """Outcome of an activation request, with idempotency handling."""
    subscription: Subscription
    created: bool


class SubscriptionService:
    """Coordinates creating and activating subscriptions for a school."""

    # ── Read-side helpers ─────────────────────────────────────────

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

    # ── Write-side lifecycle ───────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def start_trial(
        school,
        plan,
        term=None,
        activated_by=None,
    ) -> Subscription:
        """
        Start (or renew) a free trial for ``school`` on ``plan``.

        Any previous trial is cancelled and the new trial becomes the
        school's ``is_current`` subscription. The trial ends at the term's
        end date when a term is supplied, otherwise ``TRIAL_DAYS``.
        """
        school.subscriptions.filter(
            status=Subscription.Status.TRIAL
        ).update(status=Subscription.Status.CANCELLED)

        # A trial needs no money — abandon any uncompleted payment intents.
        SubscriptionPayment.objects.filter(
            school=school,
            status=SubscriptionPayment.PaymentStatus.PENDING,
        ).update(status=SubscriptionPayment.PaymentStatus.FAILED)

        resolved_term = term or SubscriptionService._current_term(school)
        end_date = (
            _term_end_datetime(resolved_term)
            or timezone.now() + timedelta(days=Subscription.TRIAL_DAYS)
        )

        return SubscriptionService._create_current(
            school=school,
            plan=plan,
            term=resolved_term,
            status=Subscription.Status.TRIAL,
            end_date=end_date,
            is_paid=False,
            activated_by=activated_by,
            notes=f"Free trial on {plan.name}",
        )

    @staticmethod
    @transaction.atomic
    def activate(
        school,
        plan,
        term=None,
        activated_by=None,
        is_paid=True,
        notes="",
        payment=None,
    ) -> Subscription:
        """
        Activate a paid subscription for ``school``.

        Any existing active/trial/grace/pending subscription is first
        cancelled and the new subscription becomes ``is_current``.
        ``payment`` (a :class:`SubscriptionPayment`) is linked to the new
        subscription and marked successful when provided.
        """
        school.subscriptions.filter(
            status__in=[
                Subscription.Status.ACTIVE,
                Subscription.Status.TRIAL,
                Subscription.Status.GRACE,
                Subscription.Status.PENDING_PAYMENT,
            ]
        ).update(status=Subscription.Status.CANCELLED)

        resolved_term = term or SubscriptionService._current_term(school)
        end_date = (
            _term_end_datetime(resolved_term)
            or timezone.now() + timedelta(days=Subscription.TRIAL_DAYS)
        )

        subscription = SubscriptionService._create_current(
            school=school,
            plan=plan,
            term=resolved_term,
            status=Subscription.Status.ACTIVE,
            end_date=end_date,
            is_paid=is_paid,
            activated_by=activated_by,
            notes=notes or f"Subscribed to {plan.name}",
        )

        SubscriptionService._link_payment(subscription, payment)

        return subscription

    @staticmethod
    @transaction.atomic
    def complete_payment(school, plan, term, payment, activated_by=None) -> ActivationResult:
        """
        Complete a previously-initiated payment idempotently.

        If ``payment`` was already completed and linked to a subscription,
        that subscription is returned instead of creating a duplicate.
        """
        if payment is not None:
            payment = SubscriptionPayment.objects.select_for_update().get(pk=payment.pk)
            if payment.school_id != school.pk or payment.plan_id != plan.pk:
                from rest_framework.exceptions import ValidationError
                raise ValidationError('Payment does not belong to this school and plan.')
        if (
            payment is not None
            and payment.status == SubscriptionPayment.PaymentStatus.SUCCESSFUL
            and payment.subscription_id is not None
        ):
            return ActivationResult(subscription=payment.subscription, created=False)

        subscription = SubscriptionService.activate(
            school=school,
            plan=plan,
            term=term,
            activated_by=activated_by,
            is_paid=True,
            payment=payment,
        )
        if payment is not None and payment.coupon_id:
            from subscriptions.services.coupons import CouponService
            CouponService.redeem(payment.coupon_id, subscription, payment.discount_applied)
        return ActivationResult(subscription=subscription, created=True)

    @staticmethod
    def free_trial_subscription(school, user) -> Optional[Subscription]:
        """
        Legacy signup hook — starts a plan-less trial when the school is
        first created (see ``schools.serializers.SchoolCreateSerializer``).
        """
        if school.subscriptions.filter(status=Subscription.Status.TRIAL).exists():
            return None

        subscription = Subscription.objects.create(
            school=school,
            status=Subscription.Status.TRIAL,
            start_date=timezone.now(),
            end_date=timezone.now() + timedelta(days=Subscription.TRIAL_DAYS),
            activated_by=user,
            is_current=True,
        )
        return subscription

    # ── Internal helpers ───────────────────────────────────────────

    @staticmethod
    def _create_current(school, plan, term, status, end_date, is_paid,
                        activated_by, notes) -> Subscription:
        # Exactly one live subscription per school.
        school.subscriptions.filter(is_current=True).update(is_current=False)
        return Subscription.objects.create(
            school=school,
            plan=plan,
            term=term,
            status=status,
            start_date=timezone.now(),
            end_date=end_date,
            is_paid=is_paid,
            activated_by=activated_by,
            notes=notes,
            is_current=True,
        )

    @staticmethod
    def _link_payment(subscription, payment) -> None:
        if payment is None:
            return
        payment.subscription = subscription
        payment.status = SubscriptionPayment.PaymentStatus.SUCCESSFUL
        payment.save(update_fields=["subscription", "status", "updated_at"])

    @staticmethod
    def _current_term(school):
        from academics.models import Term
        return Term.objects.filter(school=school, is_current=True).first()