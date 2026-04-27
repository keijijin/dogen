#!/usr/bin/env bash
# dogen-api の Route ホストを静的サイト用 ConfigMap に書き込み、nginx を再起動する。
set -euo pipefail
NS="${NS:-dogen}"
HOST="$(oc get route dogen-api -n "${NS}" -o jsonpath='{.spec.host}')"
if [[ -z "${HOST}" ]]; then
  echo "Route dogen-api が見つかりません（namespace=${NS}）。" >&2
  exit 1
fi
URL="https://${HOST}"
JS="$(printf 'window.DOGEN_CHAT_API_BASE = "%s";' "${URL}")"
oc create configmap dogen-web-runtime-config -n "${NS}" \
  --from-literal=runtime-config.js="${JS}" \
  --dry-run=client -o yaml | oc apply -f -
oc rollout restart deployment/dogen-web -n "${NS}"
echo "DOGEN_CHAT_API_BASE=${URL}"
