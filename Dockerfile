FROM python:3.13-slim

LABEL org.opencontainers.image.title="labs3" \
      org.opencontainers.image.description="Labs3 Django application" \
      com.awisee.environment="production"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_ENV=production \
    DJANGO_SETTINGS_MODULE=config.settings

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Collect static files during the image build. These values are not kept in the image.
RUN DJANGO_SECRET_KEY=build-time-collector-not-a-runtime-secret-key-9f3a7c2e8b14 \
    DJANGO_ALLOWED_HOSTS=localhost \
    POSTGRES_DB=build \
    POSTGRES_USER=build \
    POSTGRES_PASSWORD=build \
    python manage.py collectstatic --noinput \
    && chown -R app:app /app

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/')"

CMD ["gunicorn", "config.wsgi:application", "--config", "gunicorn.conf.py"]
