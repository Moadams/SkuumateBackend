"""Real Africa's Talking SMS gateway."""
from django.conf import settings

from ..common import MessageSendResult
from .base import BaseSMSProvider


class AfricasTalkingSMSProvider(BaseSMSProvider):
    key = "africas_talking"
    label = "Africa's Talking"

    def send(self, to_phone, message):
        username = self.config.get("username") or getattr(settings, "AFRICASTALKING_USERNAME", "")
        api_key = self.config.get("api_key") or getattr(settings, "AFRICASTALKING_API_KEY", "")
        sender_id = self.config.get("from_number") or getattr(settings, "AFRICASTALKING_FROM", "")
        if not username or not api_key:
            return MessageSendResult(False, self.key, "Africa's Talking credentials not fully configured.")
        try:
            import africastalking
            africastalking.initialize(username, api_key)
            sms = africastalking.SMS
            response = sms.send(message, [to_phone], sender_id or None)
            return MessageSendResult(True, self.key, "Sent via Africa's Talking.", raw=response)
        except Exception as exc:
            self.log_error(exc)
            return MessageSendResult(False, self.key, str(exc))