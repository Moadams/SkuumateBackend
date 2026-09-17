import logging

from integrations.registry import get_sms_provider

logger = logging.getLogger(__name__)


class SMSService:
    """Send SMS through the configured provider (via the integrations layer)."""

    @staticmethod
    def send(provider, to_phone, message):
        """
        Send an SMS using the given provider configuration.

        Args:
            provider: NotificationProvider instance (channel=sms)
            to_phone: str recipient phone number
            message: str SMS content

        Returns:
            (success: bool, message: str)
        """
        provider_type = provider.provider_type
        config = provider.config

        integration_provider = get_sms_provider(provider_type, config=config)
        result = integration_provider.send(to_phone, message)

        if not result.success:
            logger.warning("SMS send failed via %s: %s", provider_type, result.message)
        return result.success, result.message