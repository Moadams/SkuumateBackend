"""
Presentation layer — converts application-layer DTOs into the wire
format consumed by the frontend.

A presenter is the only component allowed to care about HTTP-specific
concerns: ISO date formatting, Decimal → float conversion, absolute
media URLs, and key naming. Services and DTOs remain framework-agnostic.
"""
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID


class BasePresenter:
    """Recursively renders a dataclass (or dict/list) into JSON-safe data."""

    def render(self, obj):
        if is_dataclass(obj):
            obj = asdict(obj)
        return self._format(obj)

    def _format(self, value):
        if isinstance(value, dict):
            return {key: self._format(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._format(item) for item in value]
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, UUID):
            return str(value)
        return value


class SchoolDetailsPresenter(BasePresenter):
    """Renders SchoolDetailsDTO (or onboarding status) for the API."""

    def __init__(self, request=None):
        self.request = request

    def present(self, dto) -> dict:
        payload = self.render(dto)
        self._resolve_logo(payload)
        return payload

    def _resolve_logo(self, payload):
        school = payload.get("school") or {}
        logo = school.get("logo")
        if logo and self.request and hasattr(self.request, "build_absolute_uri"):
            school["logo"] = self.request.build_absolute_uri(logo)