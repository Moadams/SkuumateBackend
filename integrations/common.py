"""Shared building blocks for the integrations layer."""
import logging
import sys
from abc import ABC
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


def _safe_print(text: str):
    """Print without blowing up on non-encodable characters (e.g. the
    box-drawing characters in email templates on a cp1252 Windows console)."""
    try:
        encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
        sys.stdout.write(f"{text}\n".encode(encoding, errors="replace").decode(encoding))
    except (UnicodeEncodeError, UnicodeDecodeError, AttributeError):
        sys.stdout.write(f"{text.encode('utf-8', errors='replace').decode('utf-8', errors='replace')}\n")


def log_simulated(channel: str, kind: str, **fields):
    """Pretty-print a simulated third-party interaction to the console."""
    lines = [f"[SIMULATED {channel}] {kind}"]
    preferred = ("to", "from", "subject", "message", "amount", "currency", "provider", "reference")
    for key in preferred:
        value = fields.get(key)
        if value not in (None, ""):
            lines.append(f"  {key}: {value}")
    for key, value in fields.items():
        if key not in preferred:
            lines.append(f"  {key}: {value}")
    _safe_print("\n".join(lines))


@dataclass
class ProviderResult:
    """Common result shape returned by every integration method."""

    success: bool
    provider: str = ""
    message: str = ""
    raw: dict = field(default_factory=dict)


@dataclass
class MessageSendResult(ProviderResult):
    """Outcome of sending a notification (email/SMS)."""

    pass


class BaseProvider(ABC):
    """Root ABC for every integration provider."""

    key = "base"
    label = "Base Provider"

    def __init__(self, config=None):
        self.config = config or {}

    def log_error(self, exc):
        logger.exception("%s (%s) failed: %s", self.label, self.key, exc)