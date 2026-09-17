"""Abstract email delivery contract."""
from abc import abstractmethod

from ..common import BaseProvider, MessageSendResult


class BaseEmailProvider(BaseProvider):
    """Abstract email sender."""

    key = "email_base"

    @abstractmethod
    def send(
        self,
        to_email: str,
        subject: str,
        body: str,
        html_body: str | None = None,
        from_email: str | None = None,
    ) -> MessageSendResult:
        """Deliver an email."""