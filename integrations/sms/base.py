"""Abstract SMS gateway contract."""
from abc import abstractmethod

from ..common import BaseProvider, MessageSendResult


class BaseSMSProvider(BaseProvider):
    """Abstract SMS gateway."""

    key = "sms_base"

    @abstractmethod
    def send(self, to_phone: str, message: str) -> MessageSendResult:
        """Send an SMS to ``to_phone``."""