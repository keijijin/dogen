# dogen-chat（問答 Bot API）

Quarkus 3.20 + Apache Camel 4（camel-quarkus）で、**Llama Stack** の `POST /v1/chat/completions` に中継します。

## 前提

- JDK 21、Maven 3.9+
- ローカルで Llama Stack が起動していること（例: `deploy/local` の Podman Compose、`http://127.0.0.1:8321`）
- OpenAI キーは **Llama Stack 側**に設定済みであること

## 設定

`src/main/resources/application.yaml` を参照。

| キー | 説明 |
|------|------|
| `llama.stack.base-url` | Llama Stack のオリジン（末尾スラッシュ不要） |
| `dogen.chat.default-model` | リクエストに `model` が無いときに送るモデル名。Llama Stack starter では **`openai/gpt-4o-mini`** のようにプロバイダ接頭辞が必要なことが多い。利用可能 ID は `curl -sS http://127.0.0.1:8321/v1/models`（Compose 時はポート `LLAMA_STACK_PORT`）で確認。 |
| `dogen.chat.upstream-authorization` | **Llama Stack へ送る `Authorization` ヘッダ**（既定 `Bearer fake`）。ブラウザの OIDC アクセストークンはここに流さない。 |
| `dogen.chat.rag.enabled` / `top-k` / `embedding-model` | 埋め込みは Llama Stack `POST /v1/embeddings`。`rag_chunk`（PostgreSQL `float8[]`）をアプリ内でコサイン類似し、system メッセージに注入。`%compose` では既定で RAG 有効。Llama Stack 側の vector ストアは **Qdrant**（`deploy/local/compose.yaml` の `QDRANT_URL`）。 |
| `dogen.chat.web-search.enabled` / `api-key` / `max-results` | **Tavily** `https://api.tavily.com/search`。`api-key` は未設定のままにし、使うときだけ環境変数 `DOGEN_CHAT_WEB_SEARCH_API_KEY` を設定（空文字は避ける）。 |
| `quarkus.http.port` | 既定 `8081`（静的サイトの 8080 と競合回避） |

### マネージド IdP（`quarkus-oidc`）

プロファイル **`oidc`** を追加し、**`OIDC_AUTH_SERVER_URL`** に IdP の Issuer（例: Keycloak なら `https://<ホスト>/realms/<レルム名>`）を設定すると、`/api/v1/chat`・`/sessions`・`/feedback` が **Bearer 必須**になります。例: `QUARKUS_PROFILE=compose,oidc`。静的サイトの問答パネルは `localStorage.dogen_bearer_token` にアクセストークンを入れると `Authorization` に付与します。

ログイン済みのとき JWT の `sub` を `chat_session.client_subject` に保存し、セッション一覧・履歴は **同一主体の行だけ**返します。匿名時は `client_subject IS NULL` のセッションのみです。

フロントの OIDC（PKCE）・画面の流れは **`web/auth/index.html`** と **`web/js/oidc-config.js`** を参照してください。

## 起動

### JVM で直接（開発）

```bash
cd backend
mvn quarkus:dev
```

- API: `http://127.0.0.1:8081/api/v1/chat`
- ヘルス: `GET http://127.0.0.1:8081/api/v1/health`

### Podman Compose（`postgres` + `qdrant` + `llama-stack` + 本 API）

リポジトリルートから `deploy/README.md` の手順に従い、`deploy/local` で `podman compose --env-file .env up -d --build` を実行する。`dogen-api` は **`backend/Containerfile` をリポジトリルートをコンテキストにして**ビルドする（親 `pom.xml` が必要）。プロファイル **`compose`** で Postgres の `dogen_app` とサービス名 `llama-stack` に接続する。

## エンドポイント（`doc/DESIGN.md` 7 章）

- `POST /api/v1/chat` … OpenAI Chat Completions 互換の JSON を Llama Stack に転送。新規セッション時は応答ヘッダ `X-Session-Id`。最後の user メッセージと assistant 応答を DB に保存し、`X-User-Message-Id` / `X-Assistant-Message-Id` を返す場合あり。
- `POST /api/v1/feedback` … `messageId`（上記ヘッダの UUID）と `rating` / `comment`。
- `GET /api/v1/sessions` … 保存済みチャットセッション一覧（更新順）。
- `GET /api/v1/sessions/{id}/messages` … セッションのメッセージ履歴（時系列）。`POST /chat` で `sessionId` を渡すと、送信前に DB 履歴とマージして Llama に送る。
- `GET /api/v1/health` … 簡易生存確認。

## テスト

```bash
mvn test
```

Dev Services で PostgreSQL を起動します。Llama Stack 未起動時は統合テストはスキップされ、ヘルスのみ検証されます。

## 本番（概要）

`%prod` で `JDBC_URL` / `JDBC_USER` / `JDBC_PASSWORD` を設定し、OpenShift では Llama Stack へはクラスタ内 URL を指定します。
