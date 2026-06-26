"""
WSGI config for skuumate project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

from skuumate.settings.loader import load as load_settings
load_settings()

application = get_wsgi_application()
