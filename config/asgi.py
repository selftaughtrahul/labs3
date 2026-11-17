"""ASGI entrypoint. Defaults to the production label."""

import os

from django.core.asgi import get_asgi_application

from config.envload import load_local_env

load_local_env()
os.environ.setdefault("DJANGO_ENV", "production")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_asgi_application()
