"""Simulated email delivery for development."""
import uuid

from ..common import MessageSendResult, log_simulated
from .base import BaseEmailProvider


class SimulatedEmailProvider(BaseEmailProvider):
    """Development provider. Never touches an external system."""

    key = "simulate"
    label = "Simulated Email Provider"

    def send(self, to_email, subject, body, html_body=None, from_email=None, attachments=None):
        attachment_summary = ", ".join(
            f"{filename} ({len(payload)} bytes)"
            for filename, payload, _mimetype in attachments or ()
        )
        log_simulated(
            "EMAIL",
            "SEND",
            provider=self.label,
            to=to_email,
            from_email=from_email or "no-reply@skuumate.com",
            subject=subject,
            message=body,
            attachments=attachment_summary or None,
            reference=f"SIM-EMAIL-{uuid.uuid4().hex[:8].upper()}",
        )
        return MessageSendResult(True, self.key, "Email simulated (dev only).")