"""Contact normalisation and validation shared by broadcasts."""
import re

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email

_PHONE_RE = re.compile(r"^\+?\d{9,15}$")


def normalise_phone(value):
    """Keep digits and a single leading ``+`` so providers accept the number."""
    cleaned = re.sub(r"[^\d+]", "", value or "")
    if cleaned.count("+") > 1:
        cleaned = "+" + cleaned.replace("+", "")
    return cleaned


def is_valid_phone(value):
    """True when the number is usable by an SMS gateway."""
    return bool(_PHONE_RE.match(normalise_phone(value)))


def is_valid_email(value):
    """True when the value is a syntactically valid email address."""
    value = (value or "").strip()
    if not value:
        return False
    try:
        validate_email(value)
    except DjangoValidationError:
        return False
    return True
