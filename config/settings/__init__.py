"""Select settings from the DJANGO_ENV label.

Labels:
  development — local manage.py default
  production — WSGI/ASGI and container default
"""

import os

from django.core.exceptions import ImproperlyConfigured

from config.envload import load_local_env

load_local_env()

ENVIRONMENT_LABEL = os.environ.get("DJANGO_ENV", "").strip().lower()

if ENVIRONMENT_LABEL == "production":
    from .production import *  # noqa: F403
elif ENVIRONMENT_LABEL == "development":
    from .development import *  # noqa: F403
elif not ENVIRONMENT_LABEL:
    raise ImproperlyConfigured(
        "DJANGO_ENV is not set. Use the 'development' or 'production' label."
    )
else:
    raise ImproperlyConfigured(
        f"Unknown DJANGO_ENV label {ENVIRONMENT_LABEL!r}. "
        "Use 'development' or 'production'."
    )
