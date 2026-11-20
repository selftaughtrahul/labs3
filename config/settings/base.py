"""Settings shared by every environment label."""

import os
from pathlib import Path

from .env import require_env

BASE_DIR = Path(__file__).resolve().parents[2]

_postgres_options = {}
_search_path = os.environ.get("POSTGRES_SEARCH_PATH", "").strip()
if _search_path:
    # PostgreSQL 15+ grants no CREATE on public unless the role owns the database.
    _postgres_options["options"] = f"-c search_path={_search_path}"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": require_env("POSTGRES_DB"),
        "USER": require_env("POSTGRES_USER"),
        "PASSWORD": require_env("POSTGRES_PASSWORD"),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": int(os.environ.get("POSTGRES_CONN_MAX_AGE", "60")),
        "CONN_HEALTH_CHECKS": True,
        "OPTIONS": _postgres_options,
    }
}

INSTALLED_APPS = [
    "jazzmin",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "accounts",
    "creators",
    "campaigns",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "accounts.User"

# Sign-in and sign-out go through the admin until a public login page exists.
LOGIN_URL = "admin:login"
LOGIN_REDIRECT_URL = "admin:index"
LOGOUT_REDIRECT_URL = "admin:login"

JAZZMIN_SETTINGS = {
    "site_title": "Creator Campaign Platform",
    "site_header": "Creator Campaign Platform",
    "site_brand": "Creator Campaign Platform",
    "welcome_sign": "Creators and campaigns",
    "copyright": "Creator Campaign Platform",
    "search_model": ["creators.Creator", "campaigns.Campaign"],
    "order_with_respect_to": ["creators", "campaigns", "accounts"],
    "icons": {
        "accounts.User": "fas fa-user",
        "creators.Creator": "fas fa-user-tie",
        "creators.CreatorRate": "fas fa-tags",
        "creators.Country": "fas fa-globe",
        "creators.Language": "fas fa-language",
        "creators.DeliverableType": "fas fa-clipboard-list",
        "campaigns.Campaign": "fas fa-bullhorn",
        "campaigns.CampaignCreator": "fas fa-handshake",
        "campaigns.Outreach": "fas fa-envelope",
        "campaigns.ClientShare": "fas fa-link",
        "auth.Group": "fas fa-users",
    },
    "default_icon_parents": "fas fa-folder",
    "default_icon_children": "fas fa-circle",
}
