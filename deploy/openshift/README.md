# OpenShift デプロイ（名前空間 `dogen`）

## 前提

- `oc` ログイン済み
- `deploy/local/.env` に `OPENAI_API_KEY` があるか、シェルで `export` 済み

## 手順（概要）

1. `./00-project-and-secrets.sh` … プロジェクト作成（既存なら切替）と `dogen-secrets`
2. `oc apply -f 01-postgres.yaml -f 02-qdrant.yaml -f 03-llama-stack.yaml -n dogen`
3. 基盤 Pod が Ready になるまで待つ
4. `oc apply -f 04-imagestreams-buildconfigs.yaml -n dogen`
5. **API イメージ**（リポジトリルートで）:

   ```bash
   zip -qr /tmp/dogen-api-binary.zip pom.xml backend/pom.xml backend/src backend/Containerfile
   oc start-build dogen-api --from-archive=/tmp/dogen-api-binary.zip --follow --wait -n dogen
   ```

6. **Web イメージ**:

   ```bash
   zip -qr /tmp/dogen-web-binary.zip web deploy/openshift/Dockerfile.web
   oc start-build dogen-web --from-archive=/tmp/dogen-web-binary.zip --follow --wait -n dogen
   ```

7. `oc apply -f 05-dogen-api.yaml -f 06-dogen-web.yaml -n dogen`（未適用なら）
8. `./07-patch-web-api-url.sh` … チャット UI 用に API の HTTPS Route を `runtime-config.js` に書き込み
9. **ログイン（OIDC）**: `oc apply -f 08-keycloak.yaml -n dogen` → `dogen-secrets` に `KEYCLOAK_ADMIN` / `KEYCLOAK_ADMIN_PASSWORD` があることを確認（`00-project-and-secrets.sh` で付与）→ `./09-configure-oidc.sh`（Keycloak 公開 URL・Web の redirect ・ `dogen-api` の `compose,oidc` ・`dogen-oidc-config` を設定）  
   `./09-configure-oidc.sh` は SPA が **同一オリジン `/auth/kc/`** 経由で well-known / token を取るよう **nginx（`dogen-web-nginx-site`）と `authority` を同時に**更新します（ITP 等で Keycloak への直接 `fetch` が失敗する環境向け）。  
   **`dogen-oidc-config` は `06-dogen-web.yaml` に含めていません**（以前は含めており、`oc apply -f 06` のたびに `enabled:false` に戻り問答が **403** になる不具合がありました）。初回は `00-project-and-secrets.sh` がスタブの ConfigMap を作成します。  
   **`05-dogen-api.yaml` を当て直すと `QUARKUS_PROFILE` が `compose` のみに戻る**ため、OIDC 利用中はそのあと **再度 `./09-configure-oidc.sh`** を実行してください。

## 問答が 403 / Failed to fetch になるときの原因追究

ブラウザの問答ドックは **`https://<dogen-web>/`** から **`https://<dogen-api>/api/v1/...`** へ `fetch` します。症状ごとの**典型原因**は次のとおりです。

### 1. HTTP 403（Network タブでレスポンスが 403）

`application.yaml` の **`%oidc`** で `GET/POST /api/v1/chat`・`/api/v1/sessions` 等が **`policy: authenticated`** です。**レスポンスが返っている**ので、ブラウザまでは届いており、**dogen-api 上の Quarkus が「認証できない」と判断した状態**です。

| 状況 | 意味 |
|------|------|
| **`Authorization` が無い、または `Bearer fake`** | `compose,oidc` では有効な JWT が必須。`Bearer fake` は JWT として無効 → 401/403。フロントは `localStorage.dogen_bearer_token`（access token）を付ける必要があります。 |
| **トークンは付いているが 403** | JWT の**署名・有効期限・クレーム**が Quarkus の期待と一致していない。例: **`OIDC_AUTH_SERVER_URL`（Issuer）と JWT の `iss` の不一致**（Keycloak の hostname と実トークンがズレる）、**期限切れ**、**別レルム／別 IdP のトークン**。現在は `%oidc` で `quarkus-smallrye-jwt` の `mp.jwt.verify.publickey.location` / `mp.jwt.verify.issuer` により JWKS + issuer を検証します。 |
| **`oc apply -f 05-dogen-api.yaml` の直後** | マニフェストの既定は **`QUARKUS_PROFILE=compose` のみ**のため、**`compose,oidc` と `OIDC_AUTH_SERVER_URL` が消える**ことがあります。その状態で古いフロントが誤ったトークンを送ると、または OIDC 無効と有効の組み合わせがズレると、挙動が不整合になります。**`./09-configure-oidc.sh` を再実行**してください。 |

**セッション一覧が空のドロップダウン**だけの場合、`GET /api/v1/sessions` が **200 で `[]`** なら認証は通っており、単に該当ユーザーの行が DB に無いだけです。**403 なら一覧取得時点で認証失敗**です。

確認コマンドの例:

```bash
oc get deployment dogen-api -n dogen -o jsonpath='{range .spec.template.spec.containers[0].env[*]}{.name}{"="}{.value}{"\n"}{end}' | grep -E '^(QUARKUS_PROFILE|OIDC_AUTH_SERVER_URL)='
oc logs -n dogen deployment/dogen-api --tail=80
```

### 2. Failed to fetch（Network で (failed) や CORS エラー）

**TCP／TLS／CORS プリフライト**でレスポンスまで届いていません。

| 状況 | 意味 |
|------|------|
| **HTTPS のサイトから `http://127.0.0.1:8081` を叩いている** | **混在コンテンツ**でブラウザがブロック。`07-patch-web-api-url.sh` で `runtime-config.js` に **API の HTTPS URL** を入れ、**強制再読み込み**してください。 |
| **CORS** | `compose` プロファイルでは `quarkus.http.cors.origins` が **`/.*/`** です。`compose,oidc` のときも `%oidc` が CORS を上書きしていなければ同様です。OPTIONS が認証で弾かれる場合は API イメージ側の **`api-cors-preflight`（OPTIONS permit）** が入っているか確認してください。 |

### 2.1 HTTP 406（`/api/v1/chat/stream`）

`POST /api/v1/chat/stream` は `text/event-stream` 専用です。`Accept: application/json` のまま叩くと **406 Not Acceptable** になります。  
`web/js/chat-dock.js` は `Accept: text/event-stream` を送る実装になっているため、発生時は **Web イメージ更新漏れ** または **ブラウザキャッシュ**（ハードリロード未実施）を疑ってください。

### 3. フロントの `oidc-config.js`（`dogen-oidc-config`）

`enabled: false` のままだと、ローカル向けの **`Bearer fake`** 分岐に寄りやすく、API が `compose,oidc` のときに **403** になります。`06-dogen-web.yaml` から **OIDC ConfigMap を外した**ので、`06` の apply だけで `enabled` が戻ることはありません。**`09-configure-oidc.sh` 後にブラウザで `/js/oidc-config.js` を開き `enabled: true` か確認**してください。

## 注意

- 制限付き SCC では公式 `nginx`（ポート 80）は使えないため、**`Dockerfile.web` は `nginxinc/nginx-unprivileged`**（8080）を使用しています。
- サービス名 **`llama-stack`** は Kubernetes の service link で `LLAMA_STACK_PORT` を汚染するため、Llama Stack Pod では **`enableServiceLinks: false`** にしています。
- Postgres のデータディレクトリは **`PGDATA=/var/lib/postgresql/data/pgdata`**（ボリューム直下の `lost+found` 回避）。

## OpenShift DB バックアップ / リストア（ローカルファイル）

OpenShift 上の Postgres を**ローカルファイルにバックアップ**し、必要時に**リストア**できます。対象 DB は `dogen_app` と Secret `POSTGRES_DB`（既定 `llamastack`）です。

```bash
chmod +x deploy/openshift/scripts/postgres-backup.sh deploy/openshift/scripts/postgres-restore.sh

# 手動バックアップ（deploy/openshift/backups/*.sql.gz）
./deploy/openshift/scripts/postgres-backup.sh

# リストア例（対象DBを DROP/CREATE して復元）
./deploy/openshift/scripts/postgres-restore.sh --database dogen_app --file deploy/openshift/backups/dogen_app-20260427-063001.sql.gz
```

環境変数（任意）:

| 変数 | 既定 | 説明 |
|------|------|------|
| `NS` | `dogen` | OpenShift namespace |
| `POSTGRES_DEPLOYMENT` | `postgres` | Postgres Deployment 名 |
| `POSTGRES_SECRET` | `dogen-secrets` | `POSTGRES_USER/PASSWORD/DB` を読む Secret |
| `BACKUP_DIR` | `deploy/openshift/backups` | バックアップ出力先 |
| `RETENTION_DAYS` | `7` | この日数より古い `dogen_app-*.sql.gz` / `${POSTGRES_DB}-*.sql.gz` を削除 |

### 毎日 6:30 の自動バックアップ

- **cron**: `deploy/openshift/cron/crontab.example` を絶対パスへ置換し、`crontab -e` へ追加（`30 6 * * *`）。
- **launchd（macOS）**: `deploy/openshift/launchd/jp.dogen.openshift-postgres-backup.plist.example` を絶対パスへ置換し、`~/Library/LaunchAgents/` に置いて `launchctl load`。
