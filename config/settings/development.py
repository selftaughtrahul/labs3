"""Development label. Selected when DJANGO_ENV=development."""

import os

from .base import *  # noqa: F403
from .env import env_list

ENVIRONMENT_LABEL = "development"
DEBUG = True

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-labs3-development-only",
)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",  # noqa: F405
    }
}

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
