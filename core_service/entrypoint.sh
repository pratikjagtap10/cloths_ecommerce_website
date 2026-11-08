#!/bin/sh
# Runs before the main command (gunicorn / event consumer / pytest).
set -e

if [ "${RUN_STARTUP_TASKS:-1}" = "1" ]; then
  echo "==> Applying database migrations"
  python manage.py migrate --noinput

  if [ "${SEED_DEMO_DATA:-1}" = "1" ]; then
    echo "==> Loading demo data (skipped if already loaded)"
    python manage.py seed_demo
  fi
fi

exec "$@"
