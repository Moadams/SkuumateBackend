"""Simulated payment gateway for development."""
import uuid

from ..common import log_simulated
from .base import BasePaymentProvider, PaymentInitResult, PaymentVerificationResult


class SimulatedPaymentProvider(BasePaymentProvider):
    """Development provider. Never touches an external system."""

    key = "simulate"
    label = "Simulated Payment Gateway"

    def initiate(self, email, amount, currency, metadata=None):
        reference = f"SIM-{uuid.uuid4().hex[:12].upper()}"
        log_simulated(
            "PAYMENT",
            "INITIATE",
            provider=self.label,
            to=email,
            amount=amount,
            currency=currency,
            reference=reference,
            requested_provider=(metadata or {}).get("provider", "simulate"),
        )
        return PaymentInitResult(
            success=True,
            provider=self.key,
            message="Payment simulated (dev only). Use the returned reference to complete the flow.",
            reference=reference,
            payment_url="",
            amount=amount,
            currency=currency,
        )

    def verify_webhook(self, payload, headers=None):
        payload = payload or {}
        reference = payload.get("reference") or f"SIM-{uuid.uuid4().hex[:12].upper()}"
        status = payload.get("status", "success")
        log_simulated(
            "PAYMENT",
            "WEBHOOK",
            provider=self.label,
            reference=reference,
            status=status,
            payload=payload,
        )
        return PaymentVerificationResult(
            success=True,
            provider=self.key,
            message="Webhook simulated (dev only).",
            reference=reference,
            status="success" if status in ("success", "paid") else status,
            amount=float(payload.get("amount", 0) or 0),
            metadata=payload.get("metadata") or {},
        )

    def verify_reference(self, reference, amount=None):
        reference = reference or f"SIM-{uuid.uuid4().hex[:12].upper()}"
        log_simulated(
            "PAYMENT",
            "VERIFY",
            provider=self.label,
            reference=reference,
            amount=amount,
        )
        return PaymentVerificationResult(
            success=True,
            provider=self.key,
            message="Payment verified (simulated, dev only).",
            reference=reference,
            status="success",
            amount=amount or 0,
        )