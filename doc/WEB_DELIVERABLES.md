# 静的 Web サイト — 実装成果（2026-04 時点）

道元『正法眼蔵』読解サイト（`web/`）のうち、**学習 UI・ビジュアル・ブランド・問答ドック**まわりで実装済みの内容を整理する。アーキテクチャ境界（Quarkus / Camel / Llama Stack）の変更は含まない。

---

## 1. ブランド・アイコン・タブ表示

| 種別 | パス・挙動 |
|------|------------|
| ファビコン | `web/favicon.ico`、`web/img/app-icon-dogen-{32,64,192,512,1024}.png` |
| Apple タッチ | `web/apple-touch-icon.png` |
| HTML 明示 | 主要ページの `<head>` に `<link rel="icon">` 等（トップ・認証・チャット・手編集巻など） |
| 動的補完 | `web/js/nav.js` の `installDogenIcons()` … `nav.js` の URL からサイトルートを解決し、未設定なら `<link>` を挿入（`data-dogen-icon="0"` で無効化可） |
| 生成ページ | `tools/gen_web_volumes.py` の `head_favicon_links()` で生成系 HTML に同様の link を埋め込み |

---

## 2. ホーム（トップ）

| 内容 | 説明 |
|------|------|
| タイトル画 | `web/index.html` に `img/表紙.png`（道元『正法眼蔵』のタイトル画）。`<figure class="home-cover">` でキャプション付き。LCP 向け `loading="eager"`。 |
| 補助イラスト | 五段階の直後に `img/正法眼蔵.png`（書物・学びのイメージ）。`<figure class="home-illustration">` で **`--max-wide`（本文カラム）幅いっぱい**に表示。表紙（`.home-cover`、やや狭め）との主従はサイズ差で示す。 |
| 構成 | 目的（ヒーロー）→ タイトル画 → **読み方の五段階**（`.home-steps`）→ 補助イラスト → 学習総覧＋コース → 入り口カード → 優先巻リスト。トップの SVG 4コマ（`genjo-intro-comic.svg`）は撤去済み（巻ページのラスタマンガ等は従来どおり）。 |

---

## 2.1 巻紹介 AI 4コマ（DALL-E 3）

- **生成**: `tools/gen_volume_intro_manga.py` が `OPENAI_API_KEY` で OpenAI Images API（`dall-e-3`）を呼び、`web/img/{slug}-manga-4panel.png` を出力する。各巻の **冒頭原文を長めに抜粋**しプロンプトに含め、「わかりやすく4コマ漫画で」と同趣旨の**日本語指示**を与える。既定は `quality=hd`。``--max-chars`` で抜粋長を調整可。既に手元イラストがある巻は `SKIP_SLUGS` で除外。
- **埋め込み**: `python3 tools/gen_web_volumes.py` 実行時、上記 PNG が存在する自動生成巻の `index.html` に `intro_manga_block` が差し込まれる。**辨道話**は `bendowa/index.html` をスクリプトがパッチする（手編集ファイル）。
- **安全フィルタ**: 漢文が拒否された場合は ``doc/modern_translations.json`` の **現代語訳**（冒頭を平文化してプロンプト化）で再試行し、続けて短文の漢文・短文の現代語訳、最後に **抽象プロンプト**へ順にリトライする。

## 3. 巻紹介ページへのラスタイラスト（PNG）

各巻の **手編集** `web/volumes/<slug>/index.html` に「図解（イラスト）」ブロックを追加。既存の SVG 図解・漫画ブロックは維持。画像は **`web/img/` を Git に含める**こと（未追跡のまま OpenShift の Git ビルドだけに頼ると 404 になる）。

| スラッグ | 巻題（サイト表記） | 画像ファイル |
|----------|-------------------|--------------|
| `75-02` | 摩訶般若波羅蜜 | `web/img/摩訶般若波羅蜜.png` |
| `75-03` | 佛性 | `web/img/仏性.png`（従来から） |
| `75-04` | 身心學道 | `web/img/身心学道.png` |
| `75-05` | 卽心是佛 | `web/img/即心是仏.png` |
| `75-25` | 谿聲山色 | `web/img/渓声山色.png` |
| `75-46` | 無情説法 | `web/img/無情説法.png` |

**手編集の保護**: 上記スラッグは `tools/gen_web_volumes.py` の `HAND_SLUGS` に含まれる。`python3 tools/gen_web_volumes.py` 実行時、これらの `index.html` は**上書きされない**（手編集のイラスト・本文構成を維持）。

---

## 4. 問答ドック（全ページ共通 FAB）

| 内容 | ファイル |
|------|-----------|
| FAB に道元アイコン＋「問答」ラベル | `web/js/chat-dock.js`（`dockFabIconSrc()` で `nav.js` / `chat-dock.js` からルート解決） |
| レイアウト・円形アイコン枠 | `web/css/chat-dock.css` |
| 読み込み | `web/js/nav.js` が `chat-dock.css` と `chat-dock.js` を注入 |

---

## 5. その他フロント（参照用）

- **問答 UI**: `web/js/chat.js`、Markdown 表示、stream フォールバック等（詳細はコミット履歴・`web/js/` を参照）。
- **巻読み補助**: `web/js/volume-reading.js`、学習マップ `web/volumes/learning-map.html`（生成または手元同期）。
- **現代語訳キャッシュ**: `doc/modern_translations.json` と `tools/gen_ai_modern_translations*.py` / `.sh`（運用手順は `deploy/README.md`）。

---

## 6. OpenShift（静的 `dogen-web`）への反映

バイナリビルドで **`web/` 全体**をイメージに取り込む。手順の正本は **`deploy/openshift/README.md`**。

```bash
# リポジトリルートで
zip -qr /tmp/dogen-web-binary.zip web deploy/openshift/Dockerfile.web
oc start-build dogen-web --from-archive=/tmp/dogen-web-binary.zip --follow --wait -n dogen
```

- 手元ディスク上の `web/` がそのままアーカイブに入る（未コミットファイルも含む）。
- **Git のみ**からビルドするパイプラインに切り替える場合は、**画像と HTML を必ずコミット**すること。

API 用の別イメージ（`dogen-api`）や OIDC パッチは本書の対象外。チャット API の Route 注入は `deploy/openshift/07-patch-web-api-url.sh`、OIDC は `09-configure-oidc.sh`（同 README）。

---

## 7. 改訂履歴

| 日付 | 内容 |
|------|------|
| 2026-04-28 | トップ再編（表紙・五段階・`正法眼蔵.png`）。SVG マンガ撤去、`正法眼蔵.png` を `--max-wide` 幅に拡大。 |
| 2026-04-29 | 巻紹介 AI 4コマ: 冒頭原文を長めにプロンプトへ埋め込み・日本語で「4コマで表現」指示、`quality=hd`、拒否時は短文抜粋→英語抽象プロンプトの段階リトライ、502/503 の再試行。PNG 再生成と `dogen-web` 反映。 |
