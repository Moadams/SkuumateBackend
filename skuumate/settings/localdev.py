from .base import *

DEBUG = True

ALLOWED_HOSTS = ["*"]

# ─── Database ──────────────────────────────────────────────────────
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# ─── Email — print to console ──────────────────────────────────────
# EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# ─── CORS — allow local dev servers ────────────────────────────────
CORS_ALLOW_ALL_ORIGINS = True

# ─── DRF — enable browsable API in dev ─────────────────────────────
REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = (
    "rest_framework.renderers.JSONRenderer",
    "rest_framework.renderers.BrowsableAPIRenderer",
)

# ─── Debug toolbar (optional) ──────────────────────────────────────
try:
    import debug_toolbar  # noqa: F401
    INSTALLED_APPS += ["debug_toolbar"]
    MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")
    INTERNAL_IPS = ["127.0.0.1"]
except ImportError:
    pass
