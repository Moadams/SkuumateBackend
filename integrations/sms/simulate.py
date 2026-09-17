"""Simulated SMS gateway for development."""
import uuid

from ..common import MessageSendResult, log_simulated
from .base import BaseSMSProvider


class SimulatedSMSProvider(BaseSMSProvider):
    """Development provider. Never touches an external system."""

    key = "simulate"
    label = "Simulated SMS Gateway"

    def send(self, to_phone, message):
        log_simulated(
            "SMS",
            "SEND",
            provider=self.label,
            to=to_phone,
            message=message,
            reference=f"SIM-SMS-{uuid.uuid4().hex[:8].upper()}",
        )
        return MessageSendResult(True, self.key, "SMS simulated (dev only).")