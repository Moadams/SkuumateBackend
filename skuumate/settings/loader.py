import os
from decouple import config

ENV_MAP = {
    "localdev": "skuumate.settings.localdev",
    "testing": "skuumate.settings.testing",
    "production": "skuumate.settings.production",
}

DEFAULT = "skuumate.settings.localdev"


def load():
    env = config("APP_ENV", None)
    if env is None:
        raise Exception("APP_ENV environment variable is not set.")
    module = ENV_MAP.get(env.lower(), DEFAULT)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", module)
