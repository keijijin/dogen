#!/bin/bash
set -euo pipefail
# dogen-chat 用 DB（初回データディレクトリ作成時のみ実行される）
if psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -tAc "SELECT 1 FROM pg_database WHERE datname='dogen_app'" | grep -qx 1; then
  echo "database dogen_app already exists"
else
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -c "CREATE DATABASE dogen_app OWNER \"$POSTGRES_USER\";"
fi
