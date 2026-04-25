#!/usr/bin/env bash
# PostgreSQL（Compose の postgres コンテナ）をダンプし、7 日より古いバックアップを削除する。
# 既定: 毎日 0:30 に cron / launchd から実行する想定（例は deploy/local/cron / launchd を参照）。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${LOCAL_DIR}/.env"

if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "${ENV_FILE}"
  set +a
fi

POSTGRES_USER="${POSTGRES_USER:-llamastack}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-llamastack}"
POSTGRES_DB="${POSTGRES_DB:-llamastack}"
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-dogen-postgres}"
BACKUP_DIR="${BACKUP_DIR:-${LOCAL_DIR}/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"

if command -v podman >/dev/null 2>&1; then
  CR="podman"
elif command -v docker >/dev/null 2>&1; then
  CR="docker"
else
  echo "podman または docker が必要です。" >&2
  exit 1
fi

if ! "${CR}" ps --format '{{.Names}}' 2>/dev/null | grep -qx "${POSTGRES_CONTAINER}"; then
  echo "コンテナが見つかりません: ${POSTGRES_CONTAINER}（Compose を起動済みか確認）" >&2
  exit 1
fi

mkdir -p "${BACKUP_DIR}"
TS="$(date +%Y%m%d-%H%M%S)"

dump_one() {
  local db="$1"
  local out="${BACKUP_DIR}/${db}-${TS}.sql.gz"
  "${CR}" exec -e PGPASSWORD="${POSTGRES_PASSWORD}" "${POSTGRES_CONTAINER}" \
    pg_dump -U "${POSTGRES_USER}" --no-owner --no-acl "${db}" | gzip -c >"${out}"
  echo "OK ${out}"
}

dump_one "dogen_app"
dump_one "${POSTGRES_DB}"

# 1 週間（RETENTION_DAYS 日）より古い同一パターンのダンプを削除
find "${BACKUP_DIR}" -maxdepth 1 -type f \( -name 'dogen_app-*.sql.gz' -o -name "${POSTGRES_DB}-*.sql.gz" \) -mtime "+${RETENTION_DAYS}" -print -delete

echo "完了: 保持日数=${RETENTION_DAYS}（これより古い dogen_app / ${POSTGRES_DB} の .sql.gz のみ削除）"
