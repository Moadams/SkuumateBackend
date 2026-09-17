"""Provider registry & factory.

The registry maps provider keys to concrete classes. ``get_*_provider``
returns either the **simulated** provider (``INTEGRATION_MODE = "simulate"``,
the development default) or the **real** provider (``INTEGRATION_MODE =
"live"``), so application code never branches on environment.

Credentials resolution order:
    1. per-call ``config`` dict (e.g. a school's ``NotificationProvider`` row)
    2. ``DJANGO_SETTINGS_MODULE`` env vars (see ``skuumate/settings/base.py``)
"""
from django.conf import settings

from .email import (
    NullEmailProvider,
    SendGridEmailProvider,
    SimulatedEmailProvider,
    SMTPEmailProvider,
    MailgunEmailProvider,
)
from .payments import (
    PaystackPaymentProvider,
    SimulatedPaymentProvider,
    StripePaymentProvider,
)
from .sms import (
    AfricasTalkingSMSProvider,
    ArkeselSMSProvider,
    MNotifySMSProvider,
    SimulatedSMSProvider,
    TwilioSMSProvider,
)

# ─── Registries ────────────────────────────────────────────────────
EMAIL_PROVIDERS = {
    "smtp": SMTPEmailProvider,
    "sendgrid": SendGridEmailProvider,
    "mailgun": MailgunEmailProvider,
    "simulate": SimulatedEmailProvider,
}

SMS_PROVIDERS = {
    "twilio": TwilioSMSProvider,
    "africas_talking": AfricasTalkingSMSProvider,
    "mnotify": MNotifySMSProvider,
    "arkesel": ArkeselSMSProvider,
    "simulate": SimulatedSMSProvider,
}

PAYMENT_PROVIDERS = {
    "paystack": PaystackPaymentProvider,
    "stripe": StripePaymentProvider,
    # Mobile Money flows through Paystack (Paystack supports MoMo wallets).
    "momo": PaystackPaymentProvider,
    "simulate": SimulatedPaymentProvider,
}

# ─── Mode helpers ──────────────────────────────────────────────────
def integration_mode():
    """Return ``simulate`` (development) or ``live`` (production)."""
    mode = getattr(settings, "INTEGRATION_MODE", "simulate") or "simulate"
    return str(mode).strip().lower()


def is_simulated():
    return integration_mode() == "simulate"


# ─── Factories ─────────────────────────────────────────────────────
def get_payment_provider(name=None, config=None):
    """Payment provider for ``name`` (``paystack`` | ``stripe`` | ``momo``)."""
    name = (name or "stripe").strip().lower()
    if is_simulated():
        return SimulatedPaymentProvider(config)
    return PAYMENT_PROVIDERS.get(name, SimulatedPaymentProvider)(config)


def get_sms_provider(name=None, config=None):
    """SMS provider for ``name`` (``twilio`` | ``africas_talking`` | ``mnotify`` | ``arkesel``)."""
    name = (name or "twilio").strip().lower()
    if is_simulated():
        return SimulatedSMSProvider(config)
    return SMS_PROVIDERS.get(name, SimulatedSMSProvider)(config)


def get_email_provider(name=None, config=None):
    """Email provider for ``name`` (``smtp`` | ``sendgrid`` | ``mailgun``)."""
    name = (name or "smtp").strip().lower()
    if is_simulated():
        return SimulatedEmailProvider(config)
    return EMAIL_PROVIDERS.get(name, NullEmailProvider)(config)