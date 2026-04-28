#!/usr/bin/env bash
set -euo pipefail

NS="${NS:-dogen}"
SLUGS="${SLUGS:-}"
FORCE="${FORCE:-0}"
MAX_CHARS="${MAX_CHARS:-1200}"
RETRIES="${RETRIES:-4}"
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
    "https://${KC_HOST}/admin/realms/${NS}/clients?clientId=dogen-web" | jq -r '.[0].id'
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
        "https://${KC_HOST}/admin/realms/${NS}/clients?clientId=dogen-web" | jq -r '.[0].directAccessGrantsEnabled'
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

ARGS=(--max-chars "${MAX_CHARS}" --retries "${RETRIES}")
if [[ "${FORCE}" == "1" ]]; then
  ARGS+=(--force)
fi
if [[ -n "${SLUGS}" ]]; then
  ARGS+=(--slugs "${SLUGS}")
fi

echo "[4/5] run translation generator"
DOGEN_CHAT_API_BASE="https://${API_HOST}" \
DOGEN_CHAT_BEARER="Bearer ${ACCESS}" \
PYTHONUNBUFFERED=1 python3 tools/gen_ai_modern_translations.py "${ARGS[@]}"

echo "[5/5] complete (cleanup via trap)"
echo "AI translation cache generated. Next: DOGEN_GENERATE_FULLTEXT=1 python3 tools/gen_web_volumes.py"
