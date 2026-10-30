"""Explicit failure when no SMS provider is configured."""
from ..common import MessageSendResult
from .base import BaseSMSProvider


class NullSMSProvider(BaseSMSProvider):
    """Return a clear failure instead of pretending an SMS was sent."""

    key = "null"
    label = "No SMS provider"

    def send(self, to_phone, message):
        return MessageSendResult(
            False,
            self.key,
            "No SMS provider configured for this channel.",
        )
