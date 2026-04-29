#!/usr/bin/env bash
# OpenShift 上の dogen-api（Route）と Keycloak からトークンを取得し、
# tools/gen_glossary_from_corpus.py を問答 API 経由で実行する。
#
# 前提: oc ログイン済み、名前空間に route keycloak / dogen-api と secret dogen-secrets があること。
#
# 例:
#   MAX_CHUNKS=12 MAX_TERMS=36 FORCE=1 tools/gen_glossary_openshift.sh
#
# gen_ai_modern_translations_openshift.sh と同様、終了時に dogen-web の directAccessGrants を無効化する。

set -euo pipefail

# Keycloak GET .../clients?clientId= の応答は配列のほか、オブジェクトラップの版があるため共通化する
_jq_first_client='(if type == "array" and length > 0 then .[0] elif type == "object" and ((.clients | type) == "array") and ((.clients | length) > 0) then .clients[0] elif type == "object" and (.id | strings) then . else empty end)'

NS="${NS:-dogen}"
FORCE="${FORCE:-0}"
MAX_CHUNKS="${MAX_CHUNKS:-18}"
MAX_TERMS="${MAX_TERMS:-48}"
CURL_ARGS=(--max-time "${CURL_MAX_TIME:-40}" --connect-timeout "${CURL_CONNECT_TIMEOUT:-10}")

echo "[1/5] resolve routes/secrets"

KC_HOST="$(oc get route keycloak -n "${NS}" -o jsonpath='{.spec.host}')"
API_HOST="$(oc get route dogen-api -n "${NS}" -o jsonpath='{.spec.host}')"
KC_ADMIN="$(oc get secret dogen-secrets -n "${NS}" -o jsonpath='{.data.KEYCLOAK_ADMIN}' | base64 --decode)"
KC_PASS="$(oc get secret dogen-secrets -n "${NS}" -o jsonpath='{.data.KEYCLOAK_ADMIN_PASSWORD}' | base64 --decode)"

ADMIN_TOKEN="$(
  curl -ksS "${CURL_ARGS[@]}" -X POST "https://${KC_HOST}/realms/master/protocol/openid-connect/token" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    --data-urlencode grant_type=password \
    --data-urlencode client_id=admin-cli \
    --data-urlencode "username=${KC_ADMIN}" \
    --data-urlencode "password=${KC_PASS}" | jq -r '.access_token'
)"
CLIENT_UUID="$(
  curl -ksS "${CURL_ARGS[@]}" -H "Authorization: Bearer ${ADMIN_TOKEN}" \
    "https://${KC_HOST}/admin/realms/${NS}/clients?clientId=dogen-web" | jq -r "${_jq_first_client} | .id // empty"
)"

cleanup() {
  set +e
  echo "[cleanup] disable direct grants"
  for _ in 1 2 3; do
    curl -ksS "${CURL_ARGS[@]}" -H "Authorization: Bearer ${ADMIN_TOKEN}" \
      "https://${KC_HOST}/admin/realms/${NS}/clients/${CLIENT_UUID}" \
      | jq '.directAccessGrantsEnabled=false' >/tmp/dogen-web-client-off.json || continue
    curl -ksS "${CURL_ARGS[@]}" -o /dev/null -X PUT \
      "https://${KC_HOST}/admin/realms/${NS}/clients/${CLIENT_UUID}" \
      -H "Authorization: Bearer ${ADMIN_TOKEN}" \
      -H "Content-Type: application/json" \
      --data-binary @/tmp/dogen-web-client-off.json || continue
    FLAG="$(
      curl -ksS "${CURL_ARGS[@]}" -H "Authorization: Bearer ${ADMIN_TOKEN}" \
        "https://${KC_HOST}/admin/realms/${NS}/clients?clientId=dogen-web" | jq -r "${_jq_first_client} | .directAccessGrantsEnabled // empty"
    )"
    [[ "${FLAG}" == "false" ]] && break
  done
}
trap cleanup EXIT

echo "[2/5] enable direct grants temporarily"
curl -ksS "${CURL_ARGS[@]}" -H "Authorization: Bearer ${ADMIN_TOKEN}" \
  "https://${KC_HOST}/admin/realms/${NS}/clients/${CLIENT_UUID}" \
  | jq '.directAccessGrantsEnabled=true' >/tmp/dogen-web-client-on.json
curl -ksS "${CURL_ARGS[@]}" -o /dev/null -X PUT \
  "https://${KC_HOST}/admin/realms/${NS}/clients/${CLIENT_UUID}" \
  -H "Authorization: Bearer ${ADMIN_TOKEN}" \
  -H "Content-Type: application/json" \
  --data-binary @/tmp/dogen-web-client-on.json

echo "[3/5] fetch access token for demo user"
ACCESS="$(
  curl -ksS "${CURL_ARGS[@]}" -X POST "https://${KC_HOST}/realms/${NS}/protocol/openid-connect/token" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    --data-urlencode grant_type=password \
    --data-urlencode client_id=dogen-web \
    --data-urlencode username=demo \
    --data-urlencode password=demo \
    --data-urlencode scope='openid profile email' | jq -r '.access_token'
)"

ARGS=(--max-chunks "${MAX_CHUNKS}" --max-terms "${MAX_TERMS}")
if [[ "${FORCE}" == "1" ]]; then
  ARGS+=(--force)
fi

echo "[4/5] run glossary generator (dogen-api)"
DOGEN_CHAT_API_BASE="https://${API_HOST}" \
DOGEN_CHAT_BEARER="Bearer ${ACCESS}" \
PYTHONUNBUFFERED=1 python3 tools/gen_glossary_from_corpus.py "${ARGS[@]}"

echo "[5/5] complete (cleanup via trap)"
echo "Glossary cache + web/glossary/index.html updated via OpenShift dogen-api."
