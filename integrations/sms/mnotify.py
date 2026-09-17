"""Real MNotify SMS gateway (mtn/telecel/aerotel bulk SMS, Ghana)."""
from django.conf import settings

from ..common import MessageSendResult
from .base import BaseSMSProvider


class MNotifySMSProvider(BaseSMSProvider):
    API_URL = "https://apps.mnotify.net/smsapi"

    key = "mnotify"
    label = "MNotify"

    def _api_key(self):
        return self.config.get("api_key") or getattr(settings, "MNOTIFY_API_KEY", "")

    def _sender_id(self):
        return self.config.get("sender_id") or getattr(settings, "MNOTIFY_SENDER_ID", "SkuuMate")

    def send(self, to_phone, message):
        api_key = self._api_key()
        if not api_key:
            return MessageSendResult(False, self.key, "MNotify API key not configured.")
        try:
            import requests
            response = requests.get(
                self.API_URL,
                params={
                    "key": api_key,
                    "to": to_phone,
                    "msg": message,
                    "sender_id": self._sender_id(),
                },
                timeout=30,
            )
            data = response.text.strip()
            ok = response.status_code == 200 and data.startswith(("200", "OK", "905"))
            return MessageSendResult(ok, self.key, "Sent via MNotify." if ok else f"MNotify error: {data}", raw=data)
        except Exception as exc:
            self.log_error(exc)
            return MessageSendResult(False, self.key, str(exc))