#!/usr/bin/env bash
# OpenShift 名前空間 dogen とシークレット作成（OPENAI_API_KEY は必須）
# 使い方:
#   export OPENAI_API_KEY=sk-...
#   ./deploy/openshift/00-project-and-secrets.sh
# または deploy/local/.env を読み込み済みのシェルで実行。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
if [[ -f "${ROOT}/deploy/local/.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "${ROOT}/deploy/local/.env"
  set +a
fi
if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo "OPENAI_API_KEY が未設定です。export するか deploy/local/.env に記入してください。" >&2
  exit 1
fi
POSTGRES_USER="${POSTGRES_USER:-llamastack}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-$(openssl rand -base64 24)}"
POSTGRES_DB="${POSTGRES_DB:-llamastack}"
KEYCLOAK_ADMIN="${KEYCLOAK_ADMIN:-admin}"
KEYCLOAK_ADMIN_PASSWORD="${KEYCLOAK_ADMIN_PASSWORD:-admin}"

NS="${NS:-dogen}"
oc new-project "${NS}" --display-name="dogen" --description="正法眼蔵学習・問答" 2>/dev/null || oc project "${NS}"

# Web Pod が参照する OIDC ConfigMap（06 には含めない。初回のみスタブ作成、09 で本設定に差し替え）
if ! oc get configmap dogen-oidc-config -n "${NS}" >/dev/null 2>&1; then
  oc create configmap dogen-oidc-config -n "${NS}" \
    --from-file=oidc-config.js="${ROOT}/deploy/openshift/oidc-config.stub.js"
  echo "ConfigMap dogen-oidc-config をスタブで作成しました。OpenShift でログインを使う場合は Keycloak 後に ./deploy/openshift/09-configure-oidc.sh を実行してください。"
fi

oc create secret generic dogen-secrets \
  --from-literal=POSTGRES_USER="${POSTGRES_USER}" \
  --from-literal=POSTGRES_PASSWORD="${POSTGRES_PASSWORD}" \
  --from-literal=POSTGRES_DB="${POSTGRES_DB}" \
  --from-literal=OPENAI_API_KEY="${OPENAI_API_KEY}" \
  --from-literal=KEYCLOAK_ADMIN="${KEYCLOAK_ADMIN}" \
  --from-literal=KEYCLOAK_ADMIN_PASSWORD="${KEYCLOAK_ADMIN_PASSWORD}" \
  -n "${NS}" \
  --dry-run=client -o yaml | oc apply -f -

echo "Postgres 資格情報は Secret dogen-secrets に保存済み（OPENAI_API_KEY を除き kubectl describe secret で確認可）。"
