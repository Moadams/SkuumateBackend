"""Real Arkesel SMS gateway (Ghana)."""
from django.conf import settings

from ..common import MessageSendResult
from .base import BaseSMSProvider


class ArkeselSMSProvider(BaseSMSProvider):
    API_URL = "https://sms.arkesel.com/api/v2/sms/send"

    key = "arkesel"
    label = "Arkesel"

    def _api_key(self):
        return self.config.get("api_key") or getattr(settings, "ARKESEL_API_KEY", "")

    def _sender(self):
        return self.config.get("sender") or getattr(settings, "ARKESEL_SENDER", "SkuuMate")

    def send(self, to_phone, message):
        api_key = self._api_key()
        if not api_key:
            return MessageSendResult(False, self.key, "Arkesel API key not configured.")
        try:
            import requests
            response = requests.post(
                self.API_URL,
                json={
                    "api_key": api_key,
                    "sender": self._sender(),
                    "to": to_phone,
                    "message": message,
                },
                timeout=30,
            )
            data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {"raw": response.text}
            ok = response.status_code == 200 and data.get("code") in (None, "1101", 1101, "ok", "OK")
            return MessageSendResult(ok or bool(response.status_code == 200), self.key, "Sent via Arkesel." if ok else f"Arkesel error: {data}", raw=data)
        except Exception as exc:
            self.log_error(exc)
            return MessageSendResult(False, self.key, str(exc))