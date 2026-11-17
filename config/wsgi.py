"""WSGI entrypoint. Defaults to the production label."""

import os

from django.core.wsgi import get_wsgi_application

from config.envload import load_local_env

load_local_env()
os.environ.setdefault("DJANGO_ENV", "production")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_wsgi_application()
