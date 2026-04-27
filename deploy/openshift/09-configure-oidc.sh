#!/usr/bin/env bash
# Keycloak Route に合わせて Issuer / トークンを揃え、Keycloak クライアントに Web の redirect を登録し、
# dogen-api に OIDC を有効化、dogen-oidc-config で SPA の authority を更新する。
# 前提: 08-keycloak.yaml 適用済み、dogen-secrets に KEYCLOAK_* あり
set -euo pipefail
NS="${NS:-dogen}"
oc project "${NS}" >/dev/null

KC_HOST="$(oc get route keycloak -n "${NS}" -o jsonpath='{.spec.host}')"
WEB_HOST="$(oc get route dogen-web -n "${NS}" -o jsonpath='{.spec.host}')"
if [[ -z "${KC_HOST}" || -z "${WEB_HOST}" ]]; then
  echo "Route keycloak または dogen-web が未作成です。先に OpenShift マニフェストを apply してください。" >&2
  exit 1
fi

export KC_HOST
export WEB_HOST

# Route 外側は TLS 終端。.well-known の issuer / エンドポイントを https にする（ホスト名はフル URL）
oc set env deployment/keycloak -n "${NS}" \
  "KC_HOSTNAME=https://${KC_HOST}/" \
  "KC_HOSTNAME_STRICT_HTTPS=true" \
  "KC_HOSTNAME_URL=https://${KC_HOST}/" \
  "KC_HOSTNAME_ADMIN_URL=https://${KC_HOST}/" >/dev/null
oc rollout restart deployment/keycloak -n "${NS}"
oc rollout status deployment/keycloak -n "${NS}" --timeout=400s

echo "Keycloak 起動待ち (${KC_HOST})..."
# 8080 では /health/ready が無い。OIDC の well-known で判断する
for _ in $(seq 1 60); do
  if curl -sfk "https://${KC_HOST}/realms/dogen/.well-known/openid-configuration" >/dev/null 2>&1; then
    break
  fi
  sleep 5
done

if ! curl -sfk "https://${KC_HOST}/realms/dogen/.well-known/openid-configuration" >/dev/null; then
  echo "Keycloak レルム dogen のメタデータに接続できません。oc logs -n ${NS} deployment/keycloak" >&2
  exit 1
fi

# well-known の issuer と Quarkus の OIDC_AUTH_SERVER_URL を一致させる（ズレると JWT 検証で 403）
ISSUER="$(
  curl -sfk "https://${KC_HOST}/realms/dogen/.well-known/openid-configuration" \
    | python3 -c "import json,sys; print(json.load(sys.stdin).get('issuer','').rstrip('/'), end='')"
)"
if [[ -z "${ISSUER}" ]]; then
  echo "issuer の取得に失敗しました。Keycloak のメタデータを確認してください。" >&2
  exit 1
fi

b64d() { python3 -c "import base64,sys; print(base64.b64decode(sys.argv[1]).decode())" "$1"; }
ADMIN="$(b64d "$(oc get secret dogen-secrets -n "${NS}" -o jsonpath='{.data.KEYCLOAK_ADMIN}')")"
PASS="$(b64d "$(oc get secret dogen-secrets -n "${NS}" -o jsonpath='{.data.KEYCLOAK_ADMIN_PASSWORD}')")"

RAW="$(curl -sk -X POST "https://${KC_HOST}/realms/master/protocol/openid-connect/token" \
  -d "client_id=admin-cli" \
  -d "username=${ADMIN}" \
  -d "password=${PASS}" \
  -d "grant_type=password")"
if ! TOKEN="$(printf '%s' "${RAW}" | python3 -c "import json,sys
d=json.load(sys.stdin)
t=d.get('access_token')
if not t:
  print(d.get('error_description',d), file=sys.stderr)
  sys.exit(1)
print(t, end='')")"
then
  echo "Keycloak 管理 API トークン取得失敗: ${RAW}" >&2
  exit 1
fi

CL="$(curl -sk -H "Authorization: Bearer ${TOKEN}" \
  "https://${KC_HOST}/admin/realms/dogen/clients?clientId=dogen-web&exact=true")"
CID="$(printf '%s' "${CL}" | python3 -c "import json,sys; a=json.load(sys.stdin);
assert len(a)==1, 'client dogen-web not found'; print(a[0]['id'])")"

CJ="$(curl -sk -H "Authorization: Bearer ${TOKEN}" "https://${KC_HOST}/admin/realms/dogen/clients/${CID}")"
printf '%s' "${CJ}" | KC_HOST="${KC_HOST}" WEB_HOST="${WEB_HOST}" python3 -c "
import json, os, sys
c = json.load(sys.stdin)
w = os.environ['WEB_HOST']
ruri = f'https://{w}/*'
orig = f'https://{w}'
c.setdefault('redirectUris', [])
c.setdefault('webOrigins', [])
if ruri not in c['redirectUris']:
  c['redirectUris'].append(ruri)
if orig not in c['webOrigins']:
  c['webOrigins'].append(orig)
# RFC9068 の typ=at+jwt は Quarkus 3.20 系の JWT 検証と相性が悪いことがある → 従来の JWT ヘッダに固定
c.setdefault('attributes', {})
c['attributes']['access.token.header.type.rfc9068'] = 'false'
print(json.dumps(c))
" | curl -skS -X PUT "https://${KC_HOST}/admin/realms/dogen/clients/${CID}" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d @-

export KC_HOST
export WEB_HOST
python3 - <<'PY'
import json
import os
import pathlib

kc = os.environ["KC_HOST"]
web = os.environ["WEB_HOST"]

oidc = {
    "enabled": True,
    "authority": f"https://{web}/auth/kc/realms/dogen",
    "keycloak_public_origin": f"https://{kc}",
    "browser_oidc_proxy_prefix": f"https://{web}/auth/kc",
    "client_id": "dogen-web",
    "redirect_path": "/auth/callback.html",
    "post_logout_redirect_path": "/",
    "save_return_path": True,
    "scope": "openid profile email",
}
pathlib.Path("/tmp/dogen-oidc-config.js").write_text(
    "window.DOGEN_OIDC = " + json.dumps(oidc, ensure_ascii=False) + ";\n", encoding="utf-8"
)

nginx = """# OIDC: ブラウザは同一オリジン /auth/kc/ のみ fetch し、nginx が Keycloak に転送する
server {
    listen 8080;
    listen [::]:8080;
    server_name localhost;
    root /usr/share/nginx/html;
    index index.html;

    location = /js/oidc-config.js {
        add_header Cache-Control "no-store, no-cache, must-revalidate, max-age=0" always;
        try_files $uri =404;
    }

    location = /js/runtime-config.js {
        add_header Cache-Control "no-store, no-cache, must-revalidate, max-age=0" always;
        try_files $uri =404;
    }

    location /auth/kc/ {
        proxy_pass http://keycloak:8080/;
        proxy_http_version 1.1;
        proxy_set_header Host %(kc_host)s;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Host %(kc_host)s;
        proxy_set_header X-Forwarded-Port 443;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location / {
        try_files $uri $uri/ =404;
    }
}
""" % {"kc_host": kc}

pathlib.Path("/tmp/dogen-web-default.conf").write_text(nginx, encoding="utf-8")
PY

oc create configmap dogen-oidc-config -n "${NS}" --from-file=oidc-config.js=/tmp/dogen-oidc-config.js --dry-run=client -o yaml | oc apply -f -
oc create configmap dogen-web-nginx-site -n "${NS}" --from-file=default.conf=/tmp/dogen-web-default.conf --dry-run=client -o yaml | oc apply -f -
rm -f /tmp/dogen-oidc-config.js /tmp/dogen-web-default.conf

oc set env deployment/dogen-api -n "${NS}" \
  "QUARKUS_PROFILE=compose,oidc" \
  "OIDC_AUTH_SERVER_URL=${ISSUER}"
oc rollout restart deployment/dogen-api -n "${NS}"
oc rollout restart deployment/dogen-web -n "${NS}"
oc rollout status deployment/dogen-api -n "${NS}" --timeout=120s
oc rollout status deployment/dogen-web -n "${NS}" --timeout=120s

echo "OIDC Issuer: ${ISSUER}"
echo "https://${WEB_HOST}/  でログイン（デモ: demo / demo）"
echo ""
echo "--- 切り分け（問答が 403 のとき） ---"
echo "dogen-api の環境変数（compose,oidc と Issuer がここに無いと JWT 検証で 403 になります）:"
oc get deployment dogen-api -n "${NS}" -o jsonpath='{range .spec.template.spec.containers[0].env[*]}{.name}{"="}{.value}{"\n"}{end}' 2>/dev/null | grep -E '^(QUARKUS_PROFILE|OIDC_AUTH_SERVER_URL)=' || echo "(取得できませんでした)"
echo "dogen-oidc-config の enabled 行:"
oc get configmap dogen-oidc-config -n "${NS}" -o jsonpath='{.data.oidc-config\.js}' 2>/dev/null | grep -o '"enabled":[^,}]*' || echo "(取得できませんでした)"
