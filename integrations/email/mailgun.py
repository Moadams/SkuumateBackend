"""Real Mailgun email delivery."""
from django.conf import settings

from ..common import MessageSendResult
from .base import BaseEmailProvider


class MailgunEmailProvider(BaseEmailProvider):
    API_URL = "https://api.mailgun.net/v3"

    key = "mailgun"
    label = "Mailgun"

    def _api_key(self):
        return self.config.get("api_key") or getattr(settings, "MAILGUN_API_KEY", "")

    def _domain(self):
        return self.config.get("domain") or getattr(settings, "MAILGUN_DOMAIN", "")

    def send(self, to_email, subject, body, html_body=None, from_email=None):
        api_key = self._api_key()
        domain = self._domain()
        if not api_key or not domain:
            return MessageSendResult(False, self.key, "Mailgun API key / domain not configured.")
        from_email = from_email or self.config.get("from_email") or f"no-reply@{domain}"
        try:
            import requests
            data = {
                "from": from_email,
                "to": [to_email],
                "subject": subject,
                "text": body or "",
            }
            if html_body:
                data["html"] = html_body
            response = requests.post(
                f"{self.API_URL}/{domain}/messages",
                auth=("api", api_key),
                data=data,
                timeout=30,
            )
            ok = response.status_code == 200
            return MessageSendResult(ok, self.key, "Sent via Mailgun." if ok else f"Mailgun error: {response.status_code}", raw=response.json() if ok else response.text)
        except Exception as exc:
            self.log_error(exc)
            return MessageSendResult(False, self.key, str(exc))