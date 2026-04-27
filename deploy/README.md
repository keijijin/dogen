# ローカル開発（Podman Compose）/ OpenShift メモ

## ローカル: Podman Compose

前提: [Podman](https://podman.io/) 4.x と `podman compose`（または `podman-compose`）。

1. 環境ファイルを用意する。

   ```bash
   cp deploy/local/env.example deploy/local/.env
   # .env に OPENAI_API_KEY を設定する
   ```

2. **Postgres のデータを消して初期化し直す場合**（`dogen_app` を作り直したいときなど。既存ボリュームを消すので注意）:

   ```bash
   cd deploy/local
   podman compose --env-file .env down
   podman volume rm dogen-local_dogen_pgdata 2>/dev/null || true
   ```

   Qdrant の永続データも消す場合は `dogen-local_dogen_qdrant_data` も `podman volume rm` する。

3. 起動する。

   ```bash
   cd deploy/local
   podman compose --env-file .env up -d --build
   ```

4. 疎通

   - **Llama Stack**: `http://localhost:8321/v1/health` が `OK` を含むこと
   - **dogen-api（問答 Bot API）**: `http://localhost:8081/api/v1/health`（ポートは `CHAT_API_PORT`）
   - **Keycloak**: `http://127.0.0.1:8180/`（ポートは `KEYCLOAK_PUBLISH_PORT`）
   - OpenAI 互換（Llama 経由）: `http://localhost:8321/v1`
   - **Qdrant**（任意）: `http://localhost:6333/`（公開ポートは `QDRANT_PUBLISH_PORT`）
   - **静的サイト**: Compose の **`web`（nginx）** が `http://localhost:8080/`（ポートは `WEB_PUBLISH_PORT`）で `web/` を配信。例: `http://localhost:8080/chat/index.html` から API を呼ぶ（CORS は `application.yaml` の `%compose` 等を参照）。**`podman compose` は `deploy/local` で実行**し、ボリューム `../../web` が正しく解決されるようにする。手元だけなら従来どおり `python3 -m http.server -d web 8080` でも可。

### ログイン画面（OIDC）の出し方

このリポジトリに**独自のログイン HTML は無く**、ナビの **「ログイン」** を押すと **IdP が用意する認可画面**へブラウザが飛び、そこがログイン UI になります。

1. **静的サイトを HTTP(S) で配信する**（推奨: Compose の **`web`** コンテナ → `http://127.0.0.1:8080/` 等。代替: `python3 -m http.server -d web 8080`）。`file://` ではリダイレクトが成立しにくいです。
2. **`web/js/oidc-config.js`** で次を設定する:
   - `enabled: true`
   - `authority` … 使う IdP の Issuer（`OIDC_AUTH_SERVER_URL` と同じ文字列にする）
   - `client_id` … IdP で登録した **公開クライアント（SPA）** のクライアント ID
3. **IdP 管理画面**でリダイレクト URI に  
   `http://127.0.0.1:8080/auth/callback.html`（ポート・ホストは実際のサイトの origin に合わせる）を登録する。
4. **`nav.js` を読み込むページ**（多くの `web/**/*.html`）を開くと、ナビ末尾に **ログイン / ログアウト** が出ます。OIDC 用スクリプトを読み込ませたくないページだけ、`<script src=".../nav.js" data-dogen-oidc="0">` にする。

API がトークンを検証するには別途 **`QUARKUS_PROFILE=compose,oidc`** と **`OIDC_AUTH_SERVER_URL`** が必要です（上記「ユーザ管理（OIDC）と Compose」）。フロントだけ有効にすると、IdP の画面は出ますが API は匿名のままです。

### サービス一覧（`deploy/local/compose.yaml`）

| サービス | 役割 |
|----------|------|
| `postgres` | Llama Stack の Postgres ストア用 DB、`dogen_app`（`postgres-init` で作成） |
| `qdrant` | Llama Stack の vector I/O（`remote::qdrant`、`QDRANT_URL`） |
| `llama-stack` | OpenAI 互換 API・RAG 等 |
| `dogen-api` | Quarkus + Camel。Llama Stack と Postgres に接続 |
| `web` | **nginx**。リポジトリの `web/` をホストの `WEB_PUBLISH_PORT`（既定 8080）で配信 |
| `keycloak` | **アカウント管理 / ログイン UI**（OIDC IdP）。realm import は `deploy/local/keycloak/realm-dogen.json` |

### Llama Stack イメージ

- 固定タグ: `llamastack/distribution-starter:0.7.1`（2026-04-08 時点の PyPI / GitHub に追従する場合は `compose.yaml` の `image` を `:latest` にし、`podman compose pull` で更新）

### PostgreSQL と Qdrant

- Postgres は **`library/postgres:16`**（アプリ用 `dogen_app` と Llama のメタ用 DB）
- **Qdrant** はベクトルストア専用。Llama Stack には `QDRANT_URL=http://qdrant:6333` を渡す（`deploy/local/compose.yaml` 参照）。API キーを使う場合は `.env` の `QDRANT_API_KEY` を設定する。
- `deploy/local/postgres-init/01-create-dogen-app.sh` で **`dogen_app`** を作成し、`dogen-api` の Flyway がスキーマを適用する。

### DB バックアップとリストア（PostgreSQL）

`deploy/local/scripts/` に **手動実行用**のシェルを置く（対象は `dogen_app` と `.env` の `POSTGRES_DB`、既定 `llamastack`）。バックアップは `deploy/local/backups/` に `*.sql.gz` で保存し、**`RETENTION_DAYS` 日（既定 7）より古い**同名パターンのファイルを削除する。

```bash
chmod +x deploy/local/scripts/postgres-backup.sh deploy/local/scripts/postgres-restore.sh

# 手動バックアップ（Compose で postgres が起動していること）
./deploy/local/scripts/postgres-backup.sh

# リストア例（DBを DROP してから復元する。続行は対話で yes）
./deploy/local/scripts/postgres-restore.sh --database dogen_app --file deploy/local/backups/dogen_app-20260426-003045.sql.gz
```

環境変数（任意・`deploy/local/.env` に追記可）:

| 変数 | 既定 | 説明 |
|------|------|------|
| `BACKUP_DIR` | `deploy/local/backups` | ダンプ出力先 |
| `RETENTION_DAYS` | `7` | この日数より古い `dogen_app-*.sql.gz` / `${POSTGRES_DB}-*.sql.gz` を削除 |
| `POSTGRES_CONTAINER` | `dogen-postgres` | `podman ps` に出るコンテナ名 |

**毎日 0:30 の自動実行**

- **cron（Linux / macOS 共通）**: `deploy/local/cron/crontab.example` の 1 行を、リポジトリの**絶対パス**に書き換えて `crontab -e` に追加する（`30 0 * * *` = 毎日 0 時 30 分）。
- **launchd（macOS）**: `deploy/local/launchd/jp.dogen.postgres-backup.plist.example` のパスを置換し、`cp` して `launchctl load` する手順は plist 内コメントではなく README のため、例として `~/Library/LaunchAgents/jp.dogen.postgres-backup.plist` にコピー後:

  ```bash
  launchctl load ~/Library/LaunchAgents/jp.dogen.postgres-backup.plist
  ```

`llamastack` 用 DBをリストアする際は、接続中の **Llama Stack コンテナを止める**か接続を切ってから実行すること（メタ不整合を避けるため）。

**Qdrant** のベクトルデータは別ボリュームのため、本スクリプトの対象外。必要なら `dogen-local_dogen_qdrant_data` のスナップショットや Qdrant のスナップショット API を別途運用する。

### ユーザ管理（OIDC）と Compose

本リポジトリに**専用ユーザテーブルは無く**、ログイン時は JWT の **`sub`** を `chat_session.client_subject` に保存してセッションを分離する（匿名は `client_subject IS NULL`）。

| 層 | 状態 |
|----|------|
| フロント | PKCE・`localStorage.dogen_bearer_token`・ナビのログイン UI は実装済み（`web/js/oidc-config.js` の **`enabled: false` が既定**） |
| API | `quarkus-oidc` 済み。プロファイル **`compose,oidc`** かつ **`OIDC_AUTH_SERVER_URL`** で `/api/v1/chat` 等が Bearer 必須になる |
| DB | `V1__chat_init.sql` の `chat_session.client_subject` のみ（プロフィール・ロール・アプリ内ユーザマスタは無し） |

**現状の Podman Compose** … `keycloak` コンテナを同梱しているため、ログインを有効にする場合は **Keycloak の Issuer** を指定します（API 側は内部 URL、フロント側は host 側の公開 URL）。

**`OIDC_AUTH_SERVER_URL` とは（新規に「OIDC サーバ」を必ず建てる必要はありません）**

- これは **既に存在する OpenID Connect（OIDC）プロバイダの「発行者（Issuer）URL」** です。Quarkus がこの URL から `/.well-known/openid-configuration` を読み、JWT の署名検証に使う鍵などを取得します。
- **ログイン機能を使わない**場合は、**`QUARKUS_PROFILE=compose` のみ**（`oidc` を外す）でよく、問答は匿名セッション＋`Bearer fake` で動きます。
- **ログインを有効にする**場合だけ、次のいずれかが必要です（**ゼロからプロトコルを実装する話ではなく**、既製の IdP を 1 つ指すだけです）。
  - **マネージド IdP**（Auth0、Okta、ZITADEL、Google の IdP 等）… 管理画面に **Issuer** または **OpenID のメタデータ URL** が表示されるので、そのベース URLを `OIDC_AUTH_SERVER_URL` と **`oidc-config.js` の `authority`** に同じ値で入れる。
  - **自前コンテナ**（Keycloak、ZITADEL 自ホスト、Authentik 等）… 組織方針でオンプレに置きたいときの選択。**必須ではない**。

**Compose で有効化する手順（Keycloak）**

1. `deploy/local/.env`（または `env.example` をコピーした `.env`）で Keycloak 管理者とポート（必要なら）を設定する。

   ```bash
   KEYCLOAK_ADMIN=admin
   KEYCLOAK_ADMIN_PASSWORD=admin
   # KEYCLOAK_PUBLISH_PORT=8180
   ```

2. `dogen-api`（Quarkus）側は既定で OIDC を有効にしている（`compose.yaml` の `QUARKUS_PROFILE=compose,oidc`）。Issuer は既定で内部 URL を使う:

   - `OIDC_AUTH_SERVER_URL=http://keycloak:8080/realms/dogen`

   ※変更する場合は `.env` で上書きできる。

3. フロント（静的サイト）は `web/js/oidc-config.js` が既定で次を指す（host 側 URL）:

   - `authority=http://127.0.0.1:8180/realms/dogen`
   - `client_id=dogen-web`

   `WEB_PUBLISH_PORT` や Keycloak の公開ポートを変える場合は、`deploy/local/keycloak/realm-dogen.json` の `redirectUris` / `webOrigins` と合わせて調整する。

4. `podman compose --env-file .env up -d --build` で起動（または再起動）する。

補足: OIDC を無効化して匿名運用に戻す場合は、`.env` に `QUARKUS_PROFILE=compose` を設定する。

## OpenShift（概要）

マニフェストと手順の例は **`deploy/openshift/`**（プロジェクト `dogen`、Postgres / Qdrant / Llama Stack / `dogen-api` / 静的 `dogen-web`、Route 2 本）。初回は `00-project-and-secrets.sh`（`OPENAI_API_KEY` 必須）→ 番号付き YAML の `oc apply` → バイナリビルドは **`zip` アーカイブ推奨**（macOS の `tar` はクラスタ側で展開に失敗することがあります）→ `07-patch-web-api-url.sh` でチャット用 API の Route URL を nginx に注入。

OpenShift の Postgres は `deploy/openshift/scripts/postgres-backup.sh` / `postgres-restore.sh` で**ローカルファイルへ退避・復元**できる。既定バックアップ先は `deploy/openshift/backups`、保持期間は 7 日。毎日 6:30 の自動実行テンプレートは `deploy/openshift/cron/crontab.example` と `deploy/openshift/launchd/jp.dogen.openshift-postgres-backup.plist.example`。

| Compose | OpenShift |
|---------|-----------|
| API キー等 | `Secret` + `Deployment` の env |
| Postgres 接続 | `Secret` |
| Qdrant | `StatefulSet` またはマネージド Qdrant、`ClusterIP`（Llama Stack からのみ到達） |
| コンテナ | `Deployment` または StatefulSet + `Service` |
| 外向き HTTP | Quarkus（`dogen-api`）に `Route` / Ingress。静的サイトは nginx `Deployment` + `Route` 等。Llama Stack は ClusterIP のみ |
| 永続化 | Postgres・Llama の `/data`・Qdrant ストレージに `PersistentVolumeClaim` |

ネットワークポリシーでは、原則として Quarkus が Llama Stack の 8321 に到達できればよい。Qdrant は Llama Stack からのみ許可する構成を推奨する。
