"""
ASGI config for skuumate project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

from skuumate.settings.loader import load as load_settings
load_settings()

application = get_asgi_application()
