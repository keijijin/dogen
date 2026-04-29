# AGENTS.md — エージェント・コントリビュータ向け

このリポジトリは、道元『正法眼蔵』を読み解く学習サイトと、根拠付き問答 Bot（RAG）を目指すプロジェクトです。実装は進行中で、現時点では主にドキュメント・デプロイ定義・原典テキストが置かれています。

## 作業を始める前に読むもの（優先順）

1. **`doc/DESIGN.md`** — システム分割、REST・DB・Camel・セキュリティ・OpenShift の**構築設計の正本**。
2. **`doc/PLAN.md`** — プロダクト方針、サイト構成、ロードマップ。
3. **`deploy/README.md`** — ローカル（Podman Compose）と OpenShift の要点。

アーキテクチャやコンポーネント境界を変える変更では、`doc/DESIGN.md`（必要なら `doc/PLAN.md`）を更新するか、意図的に変えない理由を明記してください。

## Cursor ルール

永続的なエージェント指示は **`.cursor/rules/*.mdc`** にあります（コアは常時適用、deploy / backend はパスに応じて適用）。本ファイルと二重している場合は、**ルールと設計書を一致**させてください。

## リポジトリの地図

| パス | 内容 |
|------|------|
| `doc/PLAN.md` | 方針・サイトマップ案・フェーズ |
| `doc/WEB_DELIVERABLES.md` | 静的 Web の実装成果（イラスト埋め込み・ファビコン・問答ドック・OpenShift 反映手順） |
| `doc/RECENT_CHANGES.md` | ツール・静的 Web・OpenShift 周りの変更メモ（運用向け） |
| `doc/CHAT_GUARDRAILS_PLAN.md` | 問答の無関係入力ガードレール計画・ユーザ視点の機能リスト（案） |
| `doc/DESIGN.md` | API・DB・Quarkus/Camel/Llama Stack の設計 |
| `doc/正法眼蔵.txt` | 訳文テキスト（目次・各巻・辨道話等） |
| `doc/*.pdf` | 全訳 PDF（取り扱いは権利に注意） |
| `deploy/local/` | Podman Compose、`env.example`、DB バックアップ/リストア（`scripts/`、`cron/`、`launchd/`） |
| `deploy/README.md` | 起動手順・OpenShift メモ |
| `web/` | 静的ホームページ（HTML / CSS / JS） |
| `tools/gen_web_volumes.py` | 巻一覧・巻ページ再生成（`doc/正法眼蔵.txt` 冒頭抜粋＋手編集スラッグはスキップ） |
| `tools/gen_volume_intro_manga.py` | 巻紹介用 AI 4コマ PNG（Responses API / gpt-4.1-mini + image_generation）生成・辨道話 HTML パッチ。詳細は `doc/WEB_DELIVERABLES.md` 2.1 |
| `tools/dogen_chat_client.py` | dogen-api `POST /api/v1/chat` の薄いクライアント（現代語訳・用語生成などから利用） |
| `tools/gen_glossary_openshift.sh` | 用語辞典生成を OpenShift の Route + Keycloak トークンで実行（`deploy/README.md` 参照） |
| `tools/gen_glossary_from_corpus.py` | 用語辞典 HTML・`doc/glossary_ai_cache.json`（OpenAI 直または `DOGEN_CHAT_API_BASE` で dogen-api） |
| `tools/regen_volume_intro_from_corpus.py` | 巻紹介の導入・語彙・クイズ等をコーパス＋OpenAI で再生成（手編集巻はスキップ） |
| `tools/openai_chat.py` | Chat / JSON パース強化・Responses 画像生成の共通ヘルパ |
| `backend/` | Quarkus + Camel（`doc/DESIGN.md` 4 章の想定。未作成の場合あり） |

## 技術スタック（要約）

- **JDK 21**、**Quarkus**、**Apache Camel 4** — 外向き API と外部統合。
- **Llama Stack**（OpenAI 互換 API）— RAG / ベクトル / エージェント寄りの処理の集約。
- **OpenAI** — 推論（キーはサーバー側のみ。リポジトリにコミットしない）。
- **PostgreSQL**（アプリ DB・Llama Stack の KV/SQL メタ）+ **Qdrant**（Llama Stack の vector I/O。詳細は `deploy/local/compose.yaml` と `doc/DESIGN.md`）。

## ローカルで Llama Stack を動かす

```bash
cp deploy/local/env.example deploy/local/.env
# .env に OPENAI_API_KEY を設定

cd deploy/local
podman compose --env-file .env up -d
```

疎通: `http://localhost:8321/v1/health`（詳細は `deploy/README.md`）。

## コーパスと権利

- テキスト・PDFの**索引化・公開・モデル学習**は、**著作権・利用許諾の範囲内**に限る。
- Bot 回答は**出典（巻・チャンク等）**を可能な限り付ける設計を前提とする（`doc/DESIGN.md`、`.cursor/rules`）。

## 秘密情報

- **`.env`、API キー、パスワードをコミットしない。**
- サンプルは `deploy/local/env.example` のようにプレースホルダのみ。

## フロント（静的サイト）

- 本体は `web/`（HTML / `css/main.css` / `js/nav.js`）。
- プレビュー: **`deploy/local` で `podman compose --env-file .env up -d`** とし、ブラウザで `http://localhost:8080/`（サービス `web`、ポートは `WEB_PUBLISH_PORT`）を開く。手元だけなら従来どおり `python3 -m http.server -d web 8080` でも可（Python 3.14 系では `-d` をポートより前に置く）。
- 巻一覧と各巻ページは `python3 tools/gen_web_volumes.py` で再生成する。手編集を保つスラッグは `tools/gen_web_volumes.py` の `HAND_SLUGS`（現状 75-01,02,03,04,05,20,25,46）。巻別 PNG イラスト・ファビコン・問答 FAB 等の一覧は **`doc/WEB_DELIVERABLES.md`**。
- **問答 Bot UI**: `web/chat/index.html` が `http://127.0.0.1:8081` の API を呼ぶ。API は **`deploy/local` の Podman Compose**（`dogen-api`）または `mvn quarkus:dev` で起動する。手順は `deploy/README.md`。

## バックエンド（問答 API）

- ディレクトリ: `backend/`（Quarkus 3.20 + Camel 4.10）。
- 開発: `cd backend && mvn quarkus:dev`（既定ポート **8081**）。
- エンドポイント: `POST /api/v1/chat` 等。詳細は `backend/README.md` と `doc/DESIGN.md`。

## ビルド・テスト（backend 追加後）

`backend/` に Quarkus プロジェクトが追加されたら、そのディレクトリの `README` または親 `pom.xml` に従い、例として `./mvnw verify` 等で検証する。現時点で `backend/` が無い場合はスキップしてよい。

## 改訂

| 日付 | 内容 |
|------|------|
| 2026-04-24 | 初版 |
| 2026-04-28 | `doc/WEB_DELIVERABLES.md` を追加し地図・フロント節から参照 |
| 2026-04-28 | `doc/CHAT_GUARDRAILS_PLAN.md` を追加（問答ガード・UX リスト）、`doc/PLAN.md` 3.6 から参照 |
