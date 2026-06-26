import os

ENV_MAP = {
    "localdev": "skuumate.settings.localdev",
    "testing": "skuumate.settings.testing",
    "production": "skuumate.settings.production",
}

DEFAULT = "skuumate.settings.localdev"


def load():
    env = os.environ.get("APP_ENV", "localdev").lower()
    module = ENV_MAP.get(env, DEFAULT)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", module)
