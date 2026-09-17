"""Real Paystack payment gateway."""
import hashlib
import hmac
import uuid
from urllib.parse import urljoin

from django.conf import settings

from .base import BasePaymentProvider, PaymentInitResult, PaymentVerificationResult


class PaystackPaymentProvider(BasePaymentProvider):
    """Real Paystack gateway (also handles ``momo`` mobile-money flows)."""

    key = "paystack"
    label = "Paystack"
    INIT_URL = "https://api.paystack.co/transaction/initialize"
    CURRENCY_SCALE = 100  # paystack uses the minor unit (cedis -> pesewas)

    def _secret_key(self):
        return self.config.get("secret_key") or getattr(settings, "PAYSTACK_SECRET_KEY", "")

    def _public_key(self):
        return self.config.get("public_key") or getattr(settings, "PAYSTACK_PUBLIC_KEY", "")

    def _scaled_amount(self, amount):
        return int(round(amount * self.CURRENCY_SCALE))

    def initiate(self, email, amount, currency, metadata=None):
        try:
            import requests
        except ImportError:
            return PaymentInitResult(False, self.key, "requests package not installed.")

        secret_key = self._secret_key()
        if not secret_key:
            return PaymentInitResult(False, self.key, "Paystack secret key not configured.")

        reference = uuid.uuid4().hex
        callback = urljoin(getattr(settings, "FRONTEND_URL", ""), "/subscriptions/callback")
        payload = {
            "email": email,
            "amount": self._scaled_amount(amount),
            "currency": currency or "GHS",
            "reference": reference,
            "callback_url": callback,
            "metadata": metadata or {},
        }

        try:
            response = requests.post(
                self.INIT_URL,
                json=payload,
                headers={"Authorization": f"Bearer {secret_key}"},
                timeout=30,
            )
            data = response.json()
            if response.status_code == 200 and data.get("status"):
                return PaymentInitResult(
                    success=True,
                    provider=self.key,
                    message=data.get("message", "Payment initialized."),
                    reference=reference,
                    payment_url=data["data"]["authorization_url"],
                    amount=amount,
                    currency=currency or "GHS",
                    raw=data,
                )
            return PaymentInitResult(False, self.key, data.get("message", "Paystack returned an error."), raw=data)
        except Exception as exc:
            self.log_error(exc)
            return PaymentInitResult(False, self.key, str(exc))

    def verify_webhook(self, payload, headers=None):
        """Verify the Paystack signature, then parse the event payload."""
        payload = payload or {}
        headers = headers or {}
        secret_key = self._secret_key()
        if not secret_key:
            return PaymentVerificationResult(False, self.key, "Paystack secret key not configured.")

        expected = hmac.new(secret_key.encode(), payload.get("_raw_body", b""), hashlib.sha512).hexdigest()
        provided = headers.get("X-Paystack-Signature") or headers.get("x-paystack-signature")
        if provided and not hmac.compare_digest(provided, expected):
            return PaymentVerificationResult(False, self.key, "Invalid Paystack signature.")

        event = payload.get("event")
        data = payload.get("data") or {}
        reference = data.get("reference", "")
        status = "success" if data.get("status") == "success" else (data.get("status") or "")
        return PaymentVerificationResult(
            success=status == "success",
            provider=self.key,
            message=f"Paystack event '{event}' received." if event else "Paystack callback received.",
            reference=reference,
            status=status,
            amount=float((data.get("amount") or 0) / self.CURRENCY_SCALE),
            metadata=data.get("metadata") or {},
            raw=payload,
        )