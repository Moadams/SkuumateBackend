"""Real SendGrid email delivery."""
import base64

from django.conf import settings

from ..common import MessageSendResult
from .base import BaseEmailProvider


class SendGridEmailProvider(BaseEmailProvider):
    key = "sendgrid"
    label = "SendGrid"

    def _api_key(self):
        return self.config.get("api_key") or getattr(settings, "SENDGRID_API_KEY", "")

    def send(self, to_email, subject, body, html_body=None, from_email=None, attachments=None):
        api_key = self._api_key()
        if not api_key:
            return MessageSendResult(False, self.key, "SendGrid API key not configured.")
        from_email = from_email or self.config.get("from_email") or settings.DEFAULT_FROM_EMAIL
        try:
            from sendgrid import SendGridAPIClient
            from sendgrid.helpers.mail import (
                Attachment,
                Content,
                Disposition,
                FileContent,
                FileName,
                FileType,
                HtmlContent,
                Mail,
            )
            content = HtmlContent(html_body) if html_body else Content("text/plain", body or "")
            mail_obj = Mail(
                from_email=from_email,
                to_emails=to_email,
                subject=subject,
                html_content=content,
            )
            if attachments:
                mail_obj.attachment = [
                    Attachment(
                        FileContent(base64.b64encode(payload).decode("ascii")),
                        FileName(filename),
                        FileType(mimetype),
                        Disposition("attachment"),
                    )
                    for filename, payload, mimetype in attachments
                ]
            response = SendGridAPIClient(api_key).send(mail_obj)
            ok = response.status_code in (200, 201, 202)
            return MessageSendResult(ok, self.key, "Sent via SendGrid." if ok else f"SendGrid error: {response.status_code}", raw={"status_code": response.status_code})
        except Exception as exc:
            self.log_error(exc)
            return MessageSendResult(False, self.key, str(exc))