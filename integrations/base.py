"""Abstract base classes for third-party integrations (payment, SMS, email).

The pattern:
  * ``BaseProvider`` subclasses declare the contract every integration must obey.
  * ``Simulated*`` providers are used in development: they simply print the
    transaction to the console and return a successful result, so the whole
    feature flows end-to-end without touching any external system.
  * Real providers (Paystack/Stripe/Twilio/SMTP/...) inherit the same ABC so
    the application code never changes when toggling environments — it only
    swaps which provider the registry returns.
"""
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


def log_simulated(channel: str, kind: str, **fields):
    """Pretty-print a simulated third-party interaction to the console."""
    lines = [f"[SIMULATED {channel}] {kind}"]
    for key in ("to", "from", "subject", "message", "amount", "currency", "provider", "reference"):
        value = fields.get(key)
        if value not in (None, ""):
            lines.append(f"  {key}: {value}")
    for key, value in fields.items():
        if key not in ("to", "from", "subject", "message", "amount", "currency", "provider", "reference"):
            lines.append(f"  {key}: {value}")
    print("\n".join(lines))


@dataclass
class ProviderResult:
    """Common result shape returned by every integration method."""

    success: bool
    provider: str = ""
    message: str = ""
    raw: dict = field(default_factory=dict)


@dataclass
class PaymentInitResult(ProviderResult):
    """Outcome of initiating a payment (redirect the user to ``payment_url``)."""

    reference: str = ""
    payment_url: str = ""
    amount: float = 0.0
    currency: str = ""


@dataclass
class PaymentVerificationResult(ProviderResult):
    """Outcome of verifying a provider webhook callback."""

    reference: str = ""
    status: str = ""
    amount: float = 0.0
    metadata: dict = field(default_factory=dict)


@dataclass
class MessageSendResult(ProviderResult):
    """Outcome of sending a notification (email/SMS)."""

    pass


class BaseProvider(ABC):
    """Root ABC for every integration provider."""

    key = "base"
    label = "Base Provider"

    def __init__(self, config=None):
        self.config = config or {}

    def log_error(self, exc):
        logger.exception("%s (%s) failed: %s", self.label, self.key, exc)


class BasePaymentProvider(BaseProvider):
    """Abstract payment gateway. Currently supports a Merchant-of-record flow.

    Implementations:
      * ``initiate`` creates a payment session / checkout and returns the URL
        the frontend should redirect the user to.
      * ``verify_webhook`` validates an incoming provider callback and returns
        a canonical ``PaymentVerificationResult``.
    """

    key = "payment_base"

    @abstractmethod
    def initiate(
        self,
        email: str,
        amount: float,
        currency: str,
        metadata: dict | None = None,
    ) -> PaymentInitResult:
        """Create a payment and return a redirect URL + reference."""

    def verify_webhook(self, payload: dict, headers: dict | None = None) -> PaymentVerificationResult:
        raise NotImplementedError(
            f"{self.label} does not support webhook verification."
        )


class BaseSMSProvider(BaseProvider):
    """Abstract SMS gateway."""

    key = "sms_base"

    @abstractmethod
    def send(self, to_phone: str, message: str) -> MessageSendResult:
        """Send an SMS to ``to_phone``."""


class BaseEmailProvider(BaseProvider):
    """Abstract email delivery channel."""

    key = "email_base"

    @abstractmethod
    def send(
        self,
        to_email: str,
        subject: str,
        body: str,
        html_body: str | None = None,
        from_email: str | None = None,
    ) -> MessageSendResult:
        """Send an email to ``to_email``."""