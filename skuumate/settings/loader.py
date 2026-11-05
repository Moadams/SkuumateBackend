import os

from decouple import config
from django.core.exceptions import ImproperlyConfigured

ENV_MAP = {
    "localdev": "skuumate.settings.localdev",
    "testing": "skuumate.settings.testing",
    "production": "skuumate.settings.production",
}

DEFAULT = "skuumate.settings.localdev"


def load():
    env = (config("APP_ENV", None) or "").strip().lower()
    if not env:
        raise ImproperlyConfigured(
            "APP_ENV environment variable is not set. "
            f"Expected one of: {', '.join(sorted(ENV_MAP))}."
        )

    module = ENV_MAP.get(env)
    if module is None:
        # Never silently fall back to development settings: an unknown value
        # (e.g. a typo like "prod") must fail loudly instead of starting the
        # app with DEBUG on and no production hardening.
        raise ImproperlyConfigured(
            f"Unknown APP_ENV {env!r}. "
            f"Expected one of: {', '.join(sorted(ENV_MAP))}."
        )

    # An explicit DJANGO_SETTINGS_MODULE (e.g. CI's skuumate.settings.ci)
    # still wins; APP_ENV is the fallback selector.
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", module)
