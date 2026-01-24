#!/bin/sh

echo "[entrypoint] Applying database migrations..."
uv run python manage.py migrate --no-input


echo "[entrypoint] Starting gunicorn..."
uv run gunicorn core.wsgi:application -b 0.0.0.0:8000 --workers 1
