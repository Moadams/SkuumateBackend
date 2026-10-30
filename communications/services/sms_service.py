import logging

from django.conf import settings

from integrations.registry import get_sms_provider, is_simulated

logger = logging.getLogger(__name__)


class SMSService:
    """Send SMS through the school's provider, or the system-wide one."""

    @staticmethod
    def system_provider_type():
        """Provider key configured for system-wide sends (``SMS_PROVIDER``).

        Development always has a usable gateway: when nothing is configured the
        simulated sender is selected. In live mode an empty setting means "not
        configured", so callers can skip instead of retrying a send that cannot
        succeed.

        Returns:
            str provider key, or ``""`` when live mode has no provider.
        """
        configured = (getattr(settings, "SMS_PROVIDER", "") or "").strip().lower()
        if configured:
            return configured
        return "simulate" if is_simulated() else ""

    @staticmethod
    def send(provider, to_phone, message):
        """
        Send an SMS using a school provider or the system fallback.

        Args:
            provider: NotificationProvider instance (channel=sms) or ``None``
                to use the system-wide provider selected by ``SMS_PROVIDER``.
            to_phone: str recipient phone number
            message: str SMS content

        Returns:
            (success: bool, message: str)
        """
        if provider is None:
            provider_type = SMSService.system_provider_type()
            if not provider_type:
                return False, "No system SMS provider configured (set SMS_PROVIDER)."
            config = {}
        else:
            provider_type = provider.provider_type
            config = provider.config

        integration_provider = get_sms_provider(provider_type, config=config)
        result = integration_provider.send(to_phone, message)

        if not result.success:
            logger.warning("SMS send failed via %s: %s", provider_type, result.message)
        return result.success, result.message
