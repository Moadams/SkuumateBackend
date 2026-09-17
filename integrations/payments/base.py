"""Abstract payment gateway contract."""
from abc import abstractmethod
from dataclasses import dataclass, field

from ..common import BaseProvider, ProviderResult


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


class BasePaymentProvider(BaseProvider):
    """Abstract payment gateway (merchant-of-record flow).

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

    def verify_webhook(
        self, payload: dict, headers: dict | None = None
    ) -> PaymentVerificationResult:
        raise NotImplementedError(
            f"{self.label} does not support webhook verification."
        )

    def verify_reference(
        self, reference: str, amount: float | None = None
    ) -> PaymentVerificationResult:
        """Confirm a transaction by its gateway reference.

        Used after a payment callback, when the frontend submits the returned
        reference to complete a subscription. Implementations should query the
        gateway for the transaction's status and amount.
        """
        raise NotImplementedError(
            f"{self.label} does not support reference verification."
        )