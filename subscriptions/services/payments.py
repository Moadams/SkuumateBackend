"""Payment orchestration for subscriptions.

Wraps the integration-layer payment providers (simulated or real) and
persists :class:`SubscriptionPayment` records so every initiated and
completed charge is auditable.
"""
from decimal import Decimal
from uuid import uuid4

from integrations.payments.base import PaymentInitResult

from django.db import transaction
from rest_framework import serializers

from integrations.registry import get_payment_provider
from subscriptions.models import SubscriptionPayment


class PaymentService:
    """Coordinates payment intents and successful-payment recording."""

    @staticmethod
    @transaction.atomic
    def initiate(school, user, plan, term, provider="simulate", include_setup_fee=False, coupon_code=None):
        """
        Start a payment with a gateway.

        Creates a pending :class:`SubscriptionPayment` (the payment intent)
        and returns the provider result plus the stored intent so the caller
        can hand ``reference``/``payment_url`` to the client.

        Raises ``ValidationError`` when the gateway rejects the charge.
        """
        amount = Decimal(plan.price)
        if include_setup_fee:
            amount += Decimal(plan.setup_fee)

        from subscriptions.services.coupons import CouponService
        coupon = CouponService.checkout_coupon(school, plan, coupon_code)
        discount_applied = Decimal('0.00')
        if coupon:
            discount_applied = CouponService.discount(coupon, amount)
            amount -= discount_applied

        if coupon and amount == 0:
            # Gateways do not support zero-value charges. Completion still
            # revalidates and redeems the persisted coupon atomically.
            result = PaymentInitResult(
                success=True, provider=provider, reference=f'COUPON-{uuid4().hex}',
                amount=0, currency=plan.currency,
            )
        else:
            provider_service = get_payment_provider(provider)
            result = provider_service.initiate(
                email=getattr(user, "email", ""),
                amount=float(amount),
                currency=plan.currency,
                metadata={
                    "school_id": str(school.id),
                    "plan_id": str(plan.id),
                    "term_id": str(term.id) if term else "",
                    "payment_type": "subscription",
                },
            )

        if not result.success:
            raise serializers.ValidationError(
                {"provider": f"Payment could not be initiated. {result.message}"}
            )

        payment = SubscriptionPayment.objects.create(
            school=school,
            plan=plan,
            term=term,
            amount=amount,
            coupon=coupon,
            discount_applied=discount_applied,
            currency=result.currency or plan.currency,
            payment_reference=result.reference,
            provider=result.provider or provider,
            payment_mode=SubscriptionPayment.PaymentMode.VIRTUAL,
            status=SubscriptionPayment.PaymentStatus.PENDING,
            recorded_by=user,
        )

        return result, payment

    @staticmethod
    def verify(reference: str, provider: str, amount: Decimal | None = None):
        """
        Ask the provider to confirm a transaction referenced by ``reference``.

        Returns the provider's :class:`PaymentVerificationResult`. In
        ``simulate`` mode the simulated provider always confirms; in live
        mode the real gateway is queried.
        """
        provider_service = get_payment_provider(provider)
        return provider_service.verify_reference(
            reference=reference,
            amount=float(amount) if amount is not None else None,
        )

    @staticmethod
    @transaction.atomic
    def record_successful_payment(
        subscription,
        school,
        plan,
        *,
        amount,
        provider="cash",
        reference="",
        payment_mode=SubscriptionPayment.PaymentMode.CASH,
        recorded_by=None,
        currency=None,
        term=None,
    ) -> SubscriptionPayment:
        """
        Persist a successful payment against a subscription.

        ``payment_mode`` distinguishes offline (``cash``) receipts from
        online/virtual (``virtual``) gateway charges.
        """
        return SubscriptionPayment.objects.create(
            subscription=subscription,
            school=school,
            plan=plan,
            term=term,
            amount=amount,
            currency=currency or plan.currency,
            payment_reference=reference,
            provider=provider,
            payment_mode=payment_mode,
            status=SubscriptionPayment.PaymentStatus.SUCCESSFUL,
            recorded_by=recorded_by,
        )