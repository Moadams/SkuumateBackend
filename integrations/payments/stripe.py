"""Real Stripe payment gateway (Checkout Sessions API)."""
from urllib.parse import urljoin

from django.conf import settings

from .base import BasePaymentProvider, PaymentInitResult, PaymentVerificationResult


class StripePaymentProvider(BasePaymentProvider):
    """Real Stripe gateway."""

    key = "stripe"
    label = "Stripe"

    def _secret_key(self):
        return self.config.get("secret_key") or getattr(settings, "STRIPE_SECRET_KEY", "")

    def _webhook_secret(self):
        return self.config.get("webhook_secret") or getattr(settings, "STRIPE_WEBHOOK_SECRET", "")

    def initiate(self, email, amount, currency, metadata=None):
        try:
            import stripe
        except ImportError:
            return PaymentInitResult(False, self.key, "stripe package not installed.")

        secret_key = self._secret_key()
        if not secret_key:
            return PaymentInitResult(False, self.key, "Stripe secret key not configured.")

        frontend = getattr(settings, "FRONTEND_URL", "")
        stripe.api_key = secret_key
        try:
            session = stripe.checkout.Session.create(
                mode="payment",
                customer_email=email,
                line_items=[{
                    "price_data": {
                        "currency": (currency or "USD").lower(),
                        "unit_amount": int(round(amount * 100)),
                        "product_data": {"name": "SkuuMate Subscription"},
                    },
                    "quantity": 1,
                }],
                client_reference_id=str((metadata or {}).get("school_id", "")),
                metadata=metadata or {},
                success_url=urljoin(frontend, "/subscriptions/success?session_id={CHECKOUT_SESSION_ID}"),
                cancel_url=urljoin(frontend, "/subscriptions/cancel"),
            )
            return PaymentInitResult(
                success=True,
                provider=self.key,
                message="Checkout session created.",
                reference=session.id,
                payment_url=session.url or "",
                amount=amount,
                currency=currency or "USD",
                raw={"session_id": session.id},
            )
        except Exception as exc:
            self.log_error(exc)
            return PaymentInitResult(False, self.key, str(exc))

    def verify_webhook(self, payload, headers=None):
        try:
            import stripe
        except ImportError:
            return PaymentVerificationResult(False, self.key, "stripe package not installed.")

        secret = self._webhook_secret()
        if not secret:
            return PaymentVerificationResult(False, self.key, "Stripe webhook secret not configured.")

        stripe.api_key = self._secret_key()
        sig_header = (headers or {}).get("Stripe-Signature") or (headers or {}).get("stripe-signature")
        try:
            event = stripe.Webhook.construct_event(payload.get("_raw_body", b""), sig_header, secret)
        except Exception as exc:
            return PaymentVerificationResult(False, self.key, f"Stripe signature verification failed: {exc}")

        if event["type"] == "checkout.session.completed":
            session = event["data"]["object"]
            return PaymentVerificationResult(
                success=True,
                provider=self.key,
                message="Checkout session completed.",
                reference=session.get("id", ""),
                status="success",
                amount=float((session.get("amount_total") or 0) / 100),
                metadata=session.get("metadata") or {},
                raw=event,
            )
        return PaymentVerificationResult(
            False,
            self.key,
            f"Ignored Stripe event: {event['type']}",
            reference=(event.get("data", {}).get("object") or {}).get("id", ""),
            raw=event,
        )