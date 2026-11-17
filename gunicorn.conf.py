"""Gunicorn process settings for the production label."""

import os

bind = os.environ.get("GUNICORN_BIND", "0.0.0.0:8000")
workers = int(os.environ.get("WEB_CONCURRENCY", "3"))
accesslog = "-"
errorlog = "-"
graceful_timeout = int(os.environ.get("GUNICORN_GRACEFUL_TIMEOUT", "30"))
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "60"))
keepalive = int(os.environ.get("GUNICORN_KEEPALIVE", "5"))
