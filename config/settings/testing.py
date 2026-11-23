"""SQLite database for unit tests when Postgres cannot create a test database."""

from .development import *

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}
