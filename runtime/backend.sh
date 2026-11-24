#!/bin/sh
set -eu
# manage.py generates a hexadecimal password, safe as a PostgreSQL URL component.
pw="$(cat /run/secrets/postgres-password)"
case "$pw" in ""|*[!0-9a-f]*) echo "Invalid generated database secret" >&2; exit 1;; esac
export DATABASE_URL="postgresql://openagents:${pw}@db:5432/openagents"
export YUMI_API_KEY="$(cat /run/secrets/deepseek-key)"
export ROUTER_LLM_API_KEY="$YUMI_API_KEY"
alembic upgrade head
exec /app/entrypoint.sh
