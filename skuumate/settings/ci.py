"""CI uses the production database engine with isolated test credentials."""
from .testing import *

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": config("DB_NAME", default="skuumate_test"),
        "USER": config("DB_USER", default="root"),
        "PASSWORD": config("DB_PASSWORD", default="root"),
        "HOST": config("DB_HOST", default="127.0.0.1"),
        "PORT": config("DB_PORT", default="3306"),
        "OPTIONS": {"charset": "utf8mb4", "init_command": "SET sql_mode='STRICT_TRANS_TABLES'"},
    },
}

# Exercise the real migration graph in CI; local unit tests remain fast.
MIGRATION_MODULES = {}
