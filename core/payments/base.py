from abc import ABC, abstractmethod


class PaymentGatewayResult:
    """Result of initiating a payment with a gateway."""

    __slots__ = (
        "checkout_url",
        "error",
        "provider_reference",
        "success",
    )

    def __init__(
        self,
        *,
        success,
        provider_reference=None,
        checkout_url="",
        error=None,
    ):
        self.success = success
        self.provider_reference = provider_reference
        self.checkout_url = checkout_url
        self.error = error


class GatewayVerificationResult:
    """Result of verifying that a payment actually succeeded."""

    __slots__ = ("error", "success")

    def __init__(self, *, success, error=None):
        self.success = success
        self.error = error


class BasePaymentGateway(ABC):
    """Abstract base class for payment gateways.

    Subclasses wrap a real payment provider (e.g. Paystack) and keep
    the domain code (services/views) gateway-agnostic.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def initiate_purchase(
        self,
        *,
        amount,
        currency: str,
        reference: str,
        description: str = "",
    ) -> PaymentGatewayResult:
        """Create a payment intent. Returns a standardized result."""
        raise NotImplementedError

    @abstractmethod
    def verify_purchase(
        self,
        *,
        gateway_reference: str,
        payload=None,
    ) -> GatewayVerificationResult:
        """Confirm a purchase completed successfully (webhook/ads/verify)."""
        raise NotImplementedError