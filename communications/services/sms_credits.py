"""SMS credit wallet, purchases and ledger accounting."""
from django.db import IntegrityError, transaction
from django.db.models import Q, Sum
from django.utils import timezone

from communications.models import (
    SMSBundle,
    SMSLedgerEntry,
    SMSPurchase,
    SMSWallet,
)
from core.exceptions import PaymentGatewayError
from integrations.registry import is_simulated
from subscriptions.services.payments import PaymentService


class SMSCreditService:
    """Keep the school wallet and its ledger consistent."""

    @classmethod
    def get_wallet(cls, school):
        wallet, _ = SMSWallet.objects.get_or_create(school=school)
        return wallet

    @classmethod
    def summary(cls, school):
        wallet = SMSWallet.objects.filter(school=school).first()
        totals = SMSLedgerEntry.objects.filter(school=school).aggregate(
            purchased=Sum(
                "credits", filter=Q(kind=SMSLedgerEntry.Kind.PURCHASE)
            ),
            used=Sum(
                "credits", filter=Q(kind=SMSLedgerEntry.Kind.USAGE)
            ),
            refunded=Sum(
                "credits", filter=Q(kind=SMSLedgerEntry.Kind.REFUND)
            ),
            adjusted=Sum(
                "credits",
                filter=Q(
                    kind__in=[
                        SMSLedgerEntry.Kind.ADJUSTMENT,
                        SMSLedgerEntry.Kind.BONUS,
                    ]
                ),
            ),
        )
        return {
            "balance": wallet.balance if wallet else 0,
            "total_purchased": totals["purchased"] or 0,
            "total_used": abs(totals["used"] or 0),
            "total_refunded": totals["refunded"] or 0,
            "total_adjusted": totals["adjusted"] or 0,
        }

    @classmethod
    def purchase(cls, school, user, *, bundle, payment_reference, provider="paystack"):
        """Verify a gateway reference and credit the school's wallet once."""
        reference = (payment_reference or "").strip()
        if not reference:
            raise ValueError("payment_reference is required.")
        if not bundle.is_active:
            raise ValueError("This SMS bundle is no longer available.")

        provider = (provider or "paystack").strip().lower()
        if provider == "simulate" and not is_simulated():
            raise ValueError("The simulated payment provider is not available.")

        existing = SMSPurchase.objects.filter(payment_reference=reference).first()
        if existing is not None:
            if existing.school_id != school.id:
                raise ValueError("This payment reference has already been used.")
            if existing.status == SMSPurchase.Status.SUCCESSFUL:
                return existing, False
            raise ValueError("This payment reference is already being processed.")

        verification = PaymentService.verify(
            reference=reference,
            provider=provider,
            amount=bundle.price,
        )
        if not verification.success:
            raise PaymentGatewayError(
                f"Payment verification failed: {verification.message}"
            )

        # Amount alone is not enough: a same-priced payment for something else
        # must not be converted into SMS credits, and a foreign-currency charge
        # must never match a GHS amount.
        if (
            verification.currency
            and verification.currency.upper() != bundle.currency.upper()
        ):
            raise PaymentGatewayError(
                "Payment currency does not match the bundle currency."
            )

        metadata = verification.metadata or {}
        purpose = metadata.get("purpose")
        if purpose and purpose != "sms_credits":
            raise PaymentGatewayError(
                "This payment was not made for SMS credits."
            )
        metadata_school = metadata.get("school_id")
        if metadata_school and str(metadata_school) != str(school.id):
            raise PaymentGatewayError(
                "This payment belongs to another school."
            )

        now = timezone.now()
        try:
            with transaction.atomic():
                wallet, _ = SMSWallet.objects.get_or_create(school=school)
                wallet = SMSWallet.objects.select_for_update().get(pk=wallet.pk)

                purchase = SMSPurchase.objects.create(
                    school=school,
                    bundle=bundle,
                    credits=bundle.credits,
                    amount=bundle.price,
                    currency=bundle.currency,
                    provider=provider,
                    payment_reference=reference,
                    status=SMSPurchase.Status.SUCCESSFUL,
                    purchased_by=user,
                    completed_at=now,
                )

                wallet.balance += bundle.credits
                wallet.save(update_fields=["balance", "updated_at"])

                SMSLedgerEntry.objects.create(
                    school=school,
                    kind=SMSLedgerEntry.Kind.PURCHASE,
                    credits=bundle.credits,
                    balance_after=wallet.balance,
                    description=f"Purchased {bundle.name}",
                    purchase=purchase,
                    created_by=user,
                )
        except IntegrityError:
            existing = SMSPurchase.objects.filter(payment_reference=reference).first()
            if (
                existing is not None
                and existing.school_id == school.id
                and existing.status == SMSPurchase.Status.SUCCESSFUL
            ):
                return existing, False
            raise

        return purchase, True

    @classmethod
    def adjust(cls, school, user, *, credits, description, kind=None):
        """Apply a signed manual adjustment (used by support tooling)."""
        if not credits:
            raise ValueError("credits must be non-zero.")
        kind = kind or SMSLedgerEntry.Kind.ADJUSTMENT
        with transaction.atomic():
            wallet, _ = SMSWallet.objects.get_or_create(school=school)
            wallet = SMSWallet.objects.select_for_update().get(pk=wallet.pk)
            new_balance = wallet.balance + int(credits)
            if new_balance < 0:
                raise ValueError("Adjustment would make the balance negative.")
            wallet.balance = new_balance
            wallet.save(update_fields=["balance", "updated_at"])
            return SMSLedgerEntry.objects.create(
                school=school,
                kind=kind,
                credits=int(credits),
                balance_after=new_balance,
                description=description,
                created_by=user,
            )

    @staticmethod
    def active_bundles():
        return SMSBundle.objects.filter(is_active=True).order_by(
            "display_order", "price"
        )
