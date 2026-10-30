"""No-op email delivery (for misconfigured providers in live mode)."""
from ..common import MessageSendResult
from .base import BaseEmailProvider


class NullEmailProvider(BaseEmailProvider):
    key = "null"
    label = "Null Email Provider"

    def send(self, to_email, subject, body, html_body=None, from_email=None, attachments=None):
        return MessageSendResult(False, self.key, "No email provider configured.")