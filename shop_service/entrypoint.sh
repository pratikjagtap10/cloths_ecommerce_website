#!/bin/sh
set -e

if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
  echo "==> Applying database migrations (Alembic)"
  alembic upgrade head
fi

exec "$@"
