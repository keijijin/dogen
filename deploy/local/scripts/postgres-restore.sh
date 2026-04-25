#!/usr/bin/env bash
# postgres-backup.sh で作成した .sql.gz を指定 DBへリストアする（DBを落として作り直す）。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${LOCAL_DIR}/.env"

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

POSTGRES_USER="${POSTGRES_USER:-llamastack}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-llamastack}"
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-dogen-postgres}"

if command -v podman >/dev/null 2>&1; then
  CR="podman"
elif command -v docker >/dev/null 2>&1; then
  CR="docker"
else
  echo "podman または docker が必要です。" >&2
  exit 1
fi

if ! "${CR}" ps --format '{{.Names}}' 2>/dev/null | grep -qx "${POSTGRES_CONTAINER}"; then
  echo "コンテナが見つかりません: ${POSTGRES_CONTAINER}" >&2
  exit 1
fi

BACKUP_FILE="$(cd "$(dirname "${BACKUP_FILE}")" && pwd)/$(basename "${BACKUP_FILE}")"
if [[ ! -f "${BACKUP_FILE}" ]]; then
  echo "ファイルがありません: ${BACKUP_FILE}" >&2
  exit 1
fi

gzip -t <"${BACKUP_FILE}" >/dev/null

if [[ "${ASSUME_YES}" -ne 1 ]]; then
  echo "次の DB を削除してからリストアします: ${TARGET_DB}"
  echo "  バックアップ: ${BACKUP_FILE}"
  echo "続行する場合は yes と入力してください。"
  read -r line
  [[ "${line}" == "yes" ]] || { echo "中止しました。"; exit 2; }
fi

# 接続を切ってから DROP / CREATE（template0 は触らない）
"${CR}" exec -i -e PGPASSWORD="${POSTGRES_PASSWORD}" "${POSTGRES_CONTAINER}" \
  psql -U "${POSTGRES_USER}" -d postgres -v ON_ERROR_STOP=1 <<SQL
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = '${TARGET_DB}' AND pid <> pg_backend_pid();
DROP DATABASE IF EXISTS "${TARGET_DB}";
CREATE DATABASE "${TARGET_DB}" OWNER "${POSTGRES_USER}";
SQL

gunzip -c "${BACKUP_FILE}" | "${CR}" exec -i -e PGPASSWORD="${POSTGRES_PASSWORD}" "${POSTGRES_CONTAINER}" \
  psql -U "${POSTGRES_USER}" -d "${TARGET_DB}" -v ON_ERROR_STOP=1

echo "リストア完了: ${TARGET_DB}"
