# 最近の変更記録（運用・デプロイ向け）

本リポジトリに入った**ツール・静的 Web・OpenShift 周り**の変更を、日付順メモとしてまとめる。正本の手順は `deploy/README.md` と `deploy/openshift/README.md`。

## 2026-04-29

### 巻紹介 4 コマ画像（AI）

- **DALL-E 3（`images/generations`）を廃止**し、OpenAI **Responses API**（`POST /v1/responses`）の **`image_generation`** ツールに切り替え。
- 会話モデル既定: **`gpt-4.1-mini`**（`DOGEN_IMAGE_RESPONSE_MODEL` で上書き）。実描画は API 側の GPT Image 系。
- 実装: `tools/gen_volume_intro_manga.py`、`tools/openai_chat.py`（`openai_image_png_via_responses`）。
- 七十五巻の自動対象巻について **`web/img/*-manga-4panel.png`** を再生成済み（`SKIP_SLUGS` は従来どおり手編集巻用）。

### 巻紹介テキスト・クイズ（オプション）

- `tools/regen_volume_intro_from_corpus.py` … **OpenAI Chat** で導入・語彙・深掘り・クイズを生成（`--offline` でヒューリスティックのみ）。`HAND_SLUGS` は上書きしない。

### 用語辞典

- `tools/gen_glossary_from_corpus.py` … 原文チャンクから候補語を取り、解説をバッチ生成して `doc/glossary_ai_cache.json` と `web/glossary/index.html` を更新。
- **`DOGEN_CHAT_API_BASE` が設定されているとき**は OpenAI ではなく **dogen-api（問答 API）**を使用（サイトと同系統）。
- `tools/gen_glossary_openshift.sh` … OpenShift 上の Route + Keycloak でトークン取得し上記を実行。
- `tools/dogen_chat_client.py` … `/api/v1/chat` 呼び出し共通化。`gen_ai_modern_translations.py` から利用。

### JSON パース（Llama 応答）

- `tools/openai_chat.py` の `parse_json_object` … 前後の説明文・スマートクォート・先頭 `{` からの括弧バランス切り出しで回復を試行。

### OpenShift シェル

- `tools/gen_ai_modern_translations_openshift.sh` / `tools/gen_glossary_openshift.sh` … Keycloak `clients?clientId=` の JSON が**配列／オブジェクト**どちらでも `jq` が動くよう修正。

### ドキュメント・環境例

- `doc/WEB_DELIVERABLES.md`（2.1 画像 API 記述更新、2.2 用語辞典）、`deploy/README.md`（用語生成手順）、`AGENTS.md`、`deploy/local/env.example`（`DOGEN_AI_TOOLS_MODEL` / `DOGEN_IMAGE_RESPONSE_MODEL`）。

### OpenShift への反映（静的サイト）

リポジトリルートで:

```bash
zip -qr /tmp/dogen-web-binary.zip web deploy/openshift/Dockerfile.web
oc start-build dogen-web --from-archive=/tmp/dogen-web-binary.zip --follow --wait -n dogen
```

API イメージ（`backend/` のみ変更時）は `deploy/openshift/README.md` の **dogen-api** の zip 手順。本変更セットでは **主に `web/` と `tools/`** のため、運用上は **`dogen-web` のビルドが中心**。
