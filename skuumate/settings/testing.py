from .base import *

DEBUG = True

SECRET_KEY = "test-secret-key-not-for-production"

ALLOWED_HOSTS = ["*"]

# ─── Database — in-memory SQLite ───────────────────────────────────
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# ─── Email — prevent accidental sends ──────────────────────────────
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# ─── Cache — simple ────────────────────────────────────────────────
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.dummy.DummyCache",
    }
}

# ─── Password hashers — fast for tests ─────────────────────────────
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# ─── Disable password validators for speed ─────────────────────────
AUTH_PASSWORD_VALIDATORS = []

# ─── CORS — allow all (tests don't check CORS but keep permissive) ─
CORS_ALLOW_ALL_ORIGINS = True

# ─── Storage — use local for tests ─────────────────────────────────
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

# ─── Disable migration during tests for speed ──────────────────────
class DisableMigrations:
    def __contains__(self, item):
        return True

    def __getitem__(self, item):
        return None

MIGRATION_MODULES = DisableMigrations()
