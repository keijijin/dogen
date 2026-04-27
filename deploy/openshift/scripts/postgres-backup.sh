#!/usr/bin/env bash
# OpenShift 上の Postgres(dogen_app + POSTGRES_DB)をローカルへバックアップする。
# 既定: deploy/openshift/backups に *.sql.gz を保存し、7日より古いファイルを削除する。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPENSHIFT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ROOT_DIR="$(cd "${OPENSHIFT_DIR}/../.." && pwd)"
ENV_FILE="${ROOT_DIR}/deploy/local/.env"

if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "${ENV_FILE}"
  set +a
fi

if ! command -v oc >/dev/null 2>&1; then
  echo "oc コマンドが必要です。" >&2
  exit 1
fi

NS="${NS:-dogen}"
POSTGRES_DEPLOYMENT="${POSTGRES_DEPLOYMENT:-postgres}"
POSTGRES_SECRET="${POSTGRES_SECRET:-dogen-secrets}"
BACKUP_DIR="${BACKUP_DIR:-${OPENSHIFT_DIR}/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"

if ! oc get deployment "${POSTGRES_DEPLOYMENT}" -n "${NS}" >/dev/null 2>&1; then
  echo "Deployment が見つかりません: ${POSTGRES_DEPLOYMENT} (ns=${NS})" >&2
  exit 1
fi

if ! oc get secret "${POSTGRES_SECRET}" -n "${NS}" >/dev/null 2>&1; then
  echo "Secret が見つかりません: ${POSTGRES_SECRET} (ns=${NS})" >&2
  exit 1
fi

decode_secret() {
  local key="$1"
  oc get secret "${POSTGRES_SECRET}" -n "${NS}" -o "jsonpath={.data.${key}}" | base64 --decode
}

POSTGRES_USER="$(decode_secret POSTGRES_USER)"
POSTGRES_PASSWORD="$(decode_secret POSTGRES_PASSWORD)"
POSTGRES_DB="$(decode_secret POSTGRES_DB)"

mkdir -p "${BACKUP_DIR}"
TS="$(date +%Y%m%d-%H%M%S)"

dump_one() {
  local db="$1"
  local out="${BACKUP_DIR}/${db}-${TS}.sql.gz"
  oc exec -n "${NS}" "deployment/${POSTGRES_DEPLOYMENT}" -- \
    env PGPASSWORD="${POSTGRES_PASSWORD}" \
    pg_dump -U "${POSTGRES_USER}" --no-owner --no-acl "${db}" | gzip -c > "${out}"
  echo "OK ${out}"
}

dump_one "dogen_app"
dump_one "${POSTGRES_DB}"

find "${BACKUP_DIR}" -maxdepth 1 -type f \
  \( -name 'dogen_app-*.sql.gz' -o -name "${POSTGRES_DB}-*.sql.gz" \) \
  -mtime "+${RETENTION_DAYS}" -print -delete

echo "完了: ns=${NS}, deployment=${POSTGRES_DEPLOYMENT}, 保持日数=${RETENTION_DAYS}"
