import logging
from datetime import datetime

from django.conf import settings
from django.template.loader import render_to_string

from communications.models import NotificationProvider
from integrations.registry import get_email_provider

logger = logging.getLogger(__name__)


class EmailService:
    """Send emails through the configured provider (via the integrations layer)."""

    TEMPLATE = "emails/base_notification.html"

    @staticmethod
    def send(provider, to_email, subject, body, html_body=None, school_name=None, attachments=None):
        """
        Send an email using the given provider configuration.

        Wraps the body in the base HTML template so all notifications
        carry the SkuuMate branding, then delegates to the provider
        resolved by ``integrations.registry.get_email_provider``.

        Args:
            provider: NotificationProvider instance (channel=email) or ``None``
                to use the project's default SMTP settings.
            to_email: str recipient address
            subject: str email subject
            body: str plain text body
            html_body: str optional pre-rendered HTML (overrides template wrapping)
            school_name: str optional school name for the email footer
            attachments: optional list of ``(filename, bytes, mimetype)`` tuples

        Returns:
            (success: bool, message: str)
        """
        if provider is None:
            provider_type = "smtp"
            config = {}
        else:
            provider_type = provider.provider_type
            config = provider.config

        if not html_body:
            if not school_name:
                school_name = (
                    provider.school.name
                    if provider is not None and provider.school
                    else "School"
                )
            html_body = render_to_string(EmailService.TEMPLATE, {
                "title": subject,
                "body": body.replace("\n", "<br/>"),
                "school_name": school_name,
                "current_year": datetime.now().year,
            })

        from_email = config.get("from_email") or getattr(settings, "DEFAULT_FROM_EMAIL", None)
        integration_provider = get_email_provider(provider_type, config=config)
        result = integration_provider.send(
            to_email=to_email,
            subject=subject,
            body=body,
            html_body=html_body,
            from_email=from_email,
            attachments=attachments,
        )

        if not result.success:
            logger.warning("Email send failed via %s: %s", provider_type, result.message)
        return result.success, result.message