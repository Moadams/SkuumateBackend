import logging
from datetime import datetime

from django.core.mail import send_mail, EmailMultiAlternatives
from django.template.loader import render_to_string

from communications.models import NotificationProvider

logger = logging.getLogger(__name__)


class EmailService:
    """Send emails through the configured provider."""

    TEMPLATE = "emails/base_notification.html"

    @staticmethod
    def send(provider, to_email, subject, body, html_body=None, school_name=None):
        """
        Send an email using the given provider configuration.

        Wraps the body in the base HTML template so all notifications
        carry the SkuuMate branding.

        Args:
            provider: NotificationProvider instance (channel=email)
            to_email: str recipient address
            subject: str email subject
            body: str plain text body
            html_body: str optional pre-rendered HTML (overrides template wrapping)

        Returns:
            (success: bool, message: str)
        """
        provider_type = provider.provider_type
        config = provider.config

        if not html_body:
            if not school_name:
                school_name = provider.school.name if provider.school else "School"
            html_body = render_to_string(EmailService.TEMPLATE, {
                "title": subject,
                "body": body.replace("\n", "<br/>"),
                "school_name": school_name,
                "current_year": datetime.now().year,
            })

        try:
            if provider_type == NotificationProvider.ProviderType.SMTP:
                return EmailService._send_via_smtp(config, to_email, subject, body, html_body, school_name)
            elif provider_type == NotificationProvider.ProviderType.SENDGRID:
                return EmailService._send_via_sendgrid(config, to_email, subject, body, html_body)
            elif provider_type == NotificationProvider.ProviderType.MAILGUN:
                return EmailService._send_via_mailgun(config, to_email, subject, body, html_body)
            else:
                return False, f"Unsupported email provider: {provider_type}"
        except Exception as e:
            logger.exception("Email send failed via %s: %s", provider_type, e)
            return False, str(e)

    @staticmethod
    def _send_via_smtp(config, to_email, subject, body, html_body, school_name=None):
        from django.conf import settings

        host = config.get("host", settings.EMAIL_HOST)
        port = config.get("port", settings.EMAIL_PORT)
        username = config.get("username", settings.EMAIL_HOST_USER)
        password = config.get("password", settings.EMAIL_HOST_PASSWORD)
        use_tls = config.get("use_tls", settings.EMAIL_USE_TLS)
        use_ssl = config.get("use_ssl", settings.EMAIL_USE_SSL)
        from_email = f"{school_name} <{config.get("from_email", settings.DEFAULT_FROM_EMAIL)}>"
        

        from django.core.mail import get_connection
        connection = get_connection(
            host=host, port=port,
            username=username, password=password,
            use_tls=use_tls, use_ssl=use_ssl,
            fail_silently=False,
        )
        
        msg = EmailMultiAlternatives(subject, body, from_email, [to_email], connection=connection)
        msg.attach_alternative(html_body, "text/html")
        msg.send()
        return True, "Sent via SMTP"

    @staticmethod
    def _send_via_sendgrid(config, to_email, subject, body, html_body):
        api_key = config.get("api_key", "")
        from_email = config.get("from_email", "")

        if not api_key:
            return False, "SendGrid API key not configured"

        try:
            import sendgrid
            from sendgrid.helpers.mail import Mail, Email, Content

            sg = sendgrid.SendGridAPIClient(api_key=api_key)
            mail = Mail(Email(from_email), to_email, subject, Content("text/html", html_body))
            sg.client.mail.send.post(request_body=mail.get())
            return True, "Sent via SendGrid"
        except ImportError:
            return False, "sendgrid package not installed"
        except Exception as e:
            return False, str(e)

    @staticmethod
    def _send_via_mailgun(config, to_email, subject, body, html_body):
        api_key = config.get("api_key", "")
        domain = config.get("domain", "")
        from_email = config.get("from_email", "")

        if not api_key or not domain:
            return False, "Mailgun API key or domain not configured"

        try:
            import requests
            response = requests.post(
                f"https://api.mailgun.net/v3/{domain}/messages",
                auth=("api", api_key),
                data={
                    "from": from_email,
                    "to": [to_email],
                    "subject": subject,
                    "text": body,
                    "html": html_body,
                },
                timeout=30,
            )
            if response.status_code == 200:
                return True, "Sent via Mailgun"
            return False, response.json().get("message", str(response.text))
        except ImportError:
            return False, "requests package not installed"
        except Exception as e:
            return False, str(e)
