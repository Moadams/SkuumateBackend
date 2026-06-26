from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
import datetime

import logging



logger = logging.getLogger(__name__)


def send_templated_email(
    subject: str,
    template: str,
    context: dict,
    recipient: str,
    from_email: str = None,
):
    """
    Sends an HTML email using a Django template.

    Usage:
        send_templated_email(
            subject="Welcome to SkuuMate",
            template="emails/welcome_school.html",
            context={"admin_name": "Kwame", ...},
            recipient="kwame@school.edu.gh",
        )
    """
    from_email = from_email or settings.DEFAULT_FROM_EMAIL

    try:
        html_content = render_to_string(template, context)

        # Plain text fallback — strip tags for basic readability
        text_content = _html_to_text(context)

        email = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=from_email,
            to=[recipient],
        )
        email.attach_alternative(html_content, "text/html")
        email.send(fail_silently=False)

        logger.info(f"Email sent: '{subject}' → {recipient}")

    except Exception as e:
        # Log but don't crash the request — email failure
        # should never break school creation
        logger.error(
            f"Failed to send email '{subject}' to {recipient}: {e}",
            exc_info=True,
        )

def send_forgot_password_mail(
    name: str,
    email: str,
    reset_link: str
):
    """
    Sends the forgot password email.
    """
    

    context = {
        "name": name,
        "email": email,
        "reset_link": reset_link,
        "login_url": f"{settings.FRONTEND_URL}",
        "frontend_url": settings.FRONTEND_URL,
        "support_email": "info@hubtekgh.com",
        "support_phone": "+233(0)241874219",
        "support_url": f"{settings.FRONTEND_URL}/support",
        "current_year": datetime.date.today().year,
    }

    send_templated_email(
        subject="Forgot Password Request for SkuuMate",
        template="emails/forgot_password.html",
        context=context,
        recipient=email,
    )

def send_welcome_school_email(
    admin_name: str,
    admin_email: str,
    reset_link: str,
    school_name: str
):
    """
    Sends the welcome + credentials email after school onboarding.
    """
    

    context = {
        "admin_name": admin_name,
        "admin_email": admin_email,
        "reset_link": reset_link,
        "school_name": school_name,
        "login_url": f"{settings.FRONTEND_URL}",
        "frontend_url": settings.FRONTEND_URL,
        "support_email": "info@hubtekgh.com",
        "support_phone": "+233(0)241874219",
        "current_year": datetime.date.today().year,
    }

    send_templated_email(
        subject="Welcome to SkuuMate — Your Account is Ready",
        template="emails/welcome_school.html",
        context=context,
        recipient=admin_email,
    )


def _html_to_text(context: dict) -> str:
    """Minimal plain text fallback for email clients that block HTML."""
    name = context.get("name") or context.get("admin_name") or context.get("staff_name") or "there"
    email = context.get("email") or context.get("admin_email") or context.get("staff_email") or ""
    reset_link = context.get("reset_link", "")
    login_url = context.get("login_url", "")
    support_email = context.get("support_email", "info@hubtekgh.com")
    support_phone = context.get("support_phone", "")
    year = context.get("current_year", "")

    # Forgot-password email
    if "name" in context and "reset_link" in context and "admin_name" not in context:
        return (
            f"Reset your SkuuMate password\n\n"
            f"Hi {name},\n\n"
            f"We received a request to reset your SkuuMate account password. "
            f"If you didn't make this request, you can safely ignore this email.\n\n"
            f"To reset your password, visit:\n{reset_link}\n\n"
            f"This link expires in 24 hours.\n\n"
            f"Need help? Contact us at {support_email} or {support_phone}\n\n"
            f"© {year} SkuuMate by HubTek Primex Enterprise"
        )

    # Welcome / staff-welcome email
    school_name = context.get("school_name", "your school")
    return (
        f"Welcome to SkuuMate!\n\n"
        f"Hi {name},\n\n"
        f"Your account for {school_name} has been created.\n\n"
        f"LOGIN CREDENTIALS\n"
        f"─────────────────\n"
        f"Portal URL : {login_url}\n"
        f"Email      : {email}\n"
        f"Password   : {reset_link}\n\n"
        f"Please change your password after your first login.\n\n"
        f"NEXT STEPS\n"
        f"──────────\n"
        f"1. Log in to your dashboard\n"
        f"2. Set up your academic year and terms\n"
        f"3. Create classes and subjects\n"
        f"4. Register your students\n"
        f"5. Choose a subscription plan before your trial ends\n\n"
        f"Need help? Contact us at {support_email} "
        f"or {support_phone}\n\n"
        f"© {year} SkuuMate by HubTek Primex Enterprise"
    )


def send_staff_welcome_mail(
        staff_name: str,
        staff_email: str,
        reset_link: str,
        school_name: str
):
    context = {
        "staff_name":staff_name,
        "staff_email": staff_email,
        "reset_link": reset_link,
        "school_name":school_name,
        "login_url": f"{settings.FRONTEND_URL}",
        "frontend_url": settings.FRONTEND_URL,
        "support_email": "info@hubtekgh.com",
        "support_phone": "+233(0)241874219",
        "current_year": datetime.date.today().year,
    }

    send_templated_email(
        subject = "Your staff account is ready",
        template = "emails/staff_welcome.html",
        context = context,
        recipient = staff_email
    )