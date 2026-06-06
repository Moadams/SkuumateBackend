
from datetime import date
import re

from rest_framework.serializers import ValidationError


def validate_name(value, field_name="Name"):
    if not value.replace(" ", "").isalpha():
        raise ValidationError(
            f"{field_name} must contain only letters and spaces."
        )
    
    if not re.match(r"^[A-Za-zÀ-ÿ\s'-]+$", value):
        raise ValidationError(f"{field_name} must contain only letters.")

    return value

def validate_phone_number(value, field_name="Phone number"):
    if not re.fullmatch(r"\+233\d{9}", value):
        raise ValidationError(f"{field_name} must be in the format '+233XXXXXXXXX'")
    return value

def validate_date(value, field_name="Date"):
    
    if value > date.today():
        raise ValidationError(f"{field_name} cannot be in the future.")
    return value