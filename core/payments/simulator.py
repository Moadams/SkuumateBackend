


from core.payments.base import (
    BasePaymentGateway,
    GatewayVerificationResult,
    PaymentGatewayResult,
)


class SimulatorPaymentGateway(BasePaymentGateway):
    """A no-op payment gateway for development and testing.

    ``initiate_purchase`` always succeeds and returns a synthetic
    gateway reference. ``verify_purchase`` always succeeds, so a
    purchase is completed (and the wallet credited) as soon as the
    confirm endpoint or webhook is called.
    """

    @property
    def name(self) -> str:
        return "simulator"

    def initiate_purchase(
        self,
        *,
        amount,
        currency: str,
        reference: str,
        description: str = "",
    ) -> PaymentGatewayResult:
        return PaymentGatewayResult(
            success=True,
            provider_reference=f"SIM-{reference}",
            checkout_url="",
            error=None,
        )

    def verify_purchase(
        self,
        *,
        gateway_reference: str,
        payload=None,
    ) -> GatewayVerificationResult:
        return GatewayVerificationResult(success=True, error=None)