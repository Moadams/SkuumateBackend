"""Real Twilio SMS gateway."""
from django.conf import settings

from ..common import MessageSendResult
from .base import BaseSMSProvider


class TwilioSMSProvider(BaseSMSProvider):
    key = "twilio"
    label = "Twilio"

    def send(self, to_phone, message):
        account_sid = self.config.get("account_sid") or getattr(settings, "TWILIO_ACCOUNT_SID", "")
        auth_token = self.config.get("auth_token") or getattr(settings, "TWILIO_AUTH_TOKEN", "")
        from_number = self.config.get("from_number") or getattr(settings, "TWILIO_FROM_NUMBER", "")
        if not account_sid or not auth_token or not from_number:
            return MessageSendResult(False, self.key, "Twilio credentials not fully configured.")
        try:
            from twilio.rest import Client
            client = Client(account_sid, auth_token)
            client.messages.create(body=message, from_=from_number, to=to_phone)
            return MessageSendResult(True, self.key, "Sent via Twilio.")
        except Exception as exc:
            self.log_error(exc)
            return MessageSendResult(False, self.key, str(exc))