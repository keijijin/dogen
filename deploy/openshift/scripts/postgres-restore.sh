#!/usr/bin/env bash
# OpenShift 用: ローカルの .sql.gz バックアップを指定 DB へリストアする（DB を再作成）。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
ENV_FILE="${ROOT_DIR}/deploy/local/.env"

usage() {
  echo "使い方: $0 --database <dogen_app|POSTGRES_DB名> --file <バックアップ.sql.gz> [--yes]" >&2
  echo "  --yes  確認プロンプトを省略（自動実行向け）" >&2
  exit 1
}

TARGET_DB=""
BACKUP_FILE=""
ASSUME_YES=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --database) TARGET_DB="${2:-}"; shift 2 ;;
    --file) BACKUP_FILE="${2:-}"; shift 2 ;;
    --yes) ASSUME_YES=1; shift ;;
    -h|--help) usage ;;
    *) echo "不明な引数: $1" >&2; usage ;;
  esac
done

[[ -n "${TARGET_DB}" && -n "${BACKUP_FILE}" ]] || usage

if ! [[ "${TARGET_DB}" =~ ^[a-zA-Z_][a-zA-Z0-9_]*$ ]]; then
  echo "データベース名は英数字とアンダースコアのみ使用できます: ${TARGET_DB}" >&2
  exit 1
fi

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

BACKUP_FILE="$(cd "$(dirname "${BACKUP_FILE}")" && pwd)/$(basename "${BACKUP_FILE}")"
if [[ ! -f "${BACKUP_FILE}" ]]; then
  echo "ファイルがありません: ${BACKUP_FILE}" >&2
  exit 1
fi

gzip -t < "${BACKUP_FILE}" >/dev/null

if [[ "${ASSUME_YES}" -ne 1 ]]; then
  echo "次の DB を削除してからリストアします: ${TARGET_DB}"
  echo "  バックアップ: ${BACKUP_FILE}"
  echo "  Namespace: ${NS}, Deployment: ${POSTGRES_DEPLOYMENT}"
  echo "続行する場合は yes と入力してください。"
  read -r line
  [[ "${line}" == "yes" ]] || { echo "中止しました。"; exit 2; }
fi

oc exec -i -n "${NS}" "deployment/${POSTGRES_DEPLOYMENT}" -- \
  env PGPASSWORD="${POSTGRES_PASSWORD}" \
  psql -U "${POSTGRES_USER}" -d postgres -v ON_ERROR_STOP=1 <<SQL
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = '${TARGET_DB}' AND pid <> pg_backend_pid();
DROP DATABASE IF EXISTS "${TARGET_DB}";
CREATE DATABASE "${TARGET_DB}" OWNER "${POSTGRES_USER}";
SQL

gunzip -c "${BACKUP_FILE}" | oc exec -i -n "${NS}" "deployment/${POSTGRES_DEPLOYMENT}" -- \
  env PGPASSWORD="${POSTGRES_PASSWORD}" \
  psql -U "${POSTGRES_USER}" -d "${TARGET_DB}" -v ON_ERROR_STOP=1

echo "リストア完了: ${TARGET_DB}"
