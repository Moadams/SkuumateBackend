"""Real SMTP email delivery via Django's email backend."""
from django.conf import settings
from django.core import mail

from ..common import MessageSendResult
from .base import BaseEmailProvider


class SMTPEmailProvider(BaseEmailProvider):
    """Sends email with Django's SMTP connection.

    A per-school ``config["host"]`` creates a custom connection; otherwise the
    project's default ``EMAIL_BACKEND`` connection is used (so the test locmem
    backend keeps working).
    """

    key = "smtp"
    label = "SMTP"

    def _connection(self):
        host = self.config.get("host")
        if not host:
            return mail.get_connection()
        return mail.get_connection(
            backend=getattr(settings, "EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend"),
            host=host,
            port=self.config.get("port") or getattr(settings, "EMAIL_PORT", 587),
            username=self.config.get("username") or getattr(settings, "EMAIL_HOST_USER", None),
            password=self.config.get("password") or getattr(settings, "EMAIL_HOST_PASSWORD", None),
            use_tls=self.config.get("use_tls", True),
        )

    def send(self, to_email, subject, body, html_body=None, from_email=None, attachments=None):
        from_email = from_email or self.config.get("from_email") or settings.DEFAULT_FROM_EMAIL
        try:
            email = mail.EmailMultiAlternatives(
                subject=subject,
                body=body or "",
                from_email=from_email,
                to=[to_email],
                connection=self._connection(),
            )
            if html_body:
                email.attach_alternative(html_body, "text/html")
            for filename, content, mimetype in attachments or ():
                email.attach(filename, content, mimetype)
            email.send(fail_silently=False)
            return MessageSendResult(True, self.key, "Sent via SMTP.")
        except Exception as exc:
            self.log_error(exc)
            return MessageSendResult(False, self.key, str(exc))