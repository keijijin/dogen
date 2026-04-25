# dogen（正法眼蔵読解）

道元『**正法眼蔵**』を読み解くための**学習用静的サイト**と、根拠（巻・チャンク等）を付けた**問答 Bot（RAG）**を目指すプロジェクトです。  
設計の正本は **`doc/DESIGN.md`**、プロダクト方針は **`doc/PLAN.md`** です。

## このリポジトリに含まれるもの

| 領域 | パス | 概要 |
|------|------|------|
| 静的サイト | [`web/`](web/) | HTML / CSS / JS。巻ページ・学習ガイド・問答 UI など |
| 問答 API | [`backend/`](backend/) | Quarkus + Camel。Llama Stack へ中継（詳細は [`backend/README.md`](backend/README.md)） |
| ローカル実行 | [`deploy/local/`](deploy/local/) | Podman Compose（Postgres / Qdrant / Llama Stack / dogen-api / nginx / **Keycloak**） |
| ドキュメント | [`doc/`](doc/) | `PLAN.md` / `DESIGN.md`、訳文テキスト（`正法眼蔵.txt`）など |
| ツール | [`tools/`](tools/) | 巻ページ生成など（例: `gen_web_volumes.py`） |

## クイックスタート（ローカル）

1. 環境ファイルを用意する（**秘密情報はコミットしない**）。

   ```bash
   cp deploy/local/env.example deploy/local/.env
   # .env に OPENAI_API_KEY 等を設定
   ```

2. Compose を起動する（**`deploy/local` で実行**すること）。

   ```bash
   cd deploy/local
   podman compose --env-file .env up -d --build
   ```

3. ブラウザで開く（既定ポートの例）。

   - 静的サイト: `http://127.0.0.1:8080/`
   - 問答 API: `http://127.0.0.1:8081/api/v1/health`
   - Llama Stack: `http://127.0.0.1:8321/v1/health`
   - Keycloak（アカウント管理）: `http://127.0.0.1:8180/`

詳細・トラブルシュート・OpenShift メモは **[`deploy/README.md`](deploy/README.md)** を参照してください。

## 技術スタック（要約）

- **JDK 21**、**Quarkus**、**Apache Camel 4** — 外向き API と外部統合
- **Llama Stack**（OpenAI 互換）— RAG / vector 等の集約
- **OpenAI** — 推論（**API キーはサーバー側のみ**。クライアントへ渡さない）
- **PostgreSQL** — アプリ DB、Llama Stack のメタ等
- **Qdrant** — Llama Stack の vector I/O（`remote::qdrant`）
- **Keycloak**（ローカル Compose）— **ログインアカウントの管理（IdP）**。フロントは PKCE、API は Bearer 検証（`compose,oidc`）

## ドキュメントの読み順（推奨）

1. [`doc/PLAN.md`](doc/PLAN.md) — 方針・サイト構成・ロードマップ  
2. [`doc/DESIGN.md`](doc/DESIGN.md) — API・DB・境界・運用の構築設計  
3. [`deploy/README.md`](deploy/README.md) — ローカル起動・OIDC・バックアップ等  

コントリビュータ向けの地図とルールは **[`AGENTS.md`](AGENTS.md)**、Cursor 向けルールは **[`.cursor/rules/`](.cursor/rules/)** です。

## 著作・コーパス

テキスト・PDF の**索引化・公開・学習利用**は、**著作権・利用許諾の範囲内**に限ります。Bot 回答は**出典（巻・チャンク等）**を可能な限り付ける設計を前提とします（`doc/DESIGN.md` 参照）。

## ライセンス

（未設定の場合は追記してください。）
