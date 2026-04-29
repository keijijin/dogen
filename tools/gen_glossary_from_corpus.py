#!/usr/bin/env python3
"""『正法眼蔵』原文（doc/正法眼蔵.txt）から難解用語を拾い、解説を生成して用語ページを書き換える。

バックエンド（自動判定）:

- **dogen-api（推奨: OpenShift）** … 環境変数 ``DOGEN_CHAT_API_BASE`` が非空のとき（例: Route の ``https://…``）。
  問答と同じ ``POST /api/v1/chat`` 経由で Llama Stack（RAG 含む）を利用する。
  ``DOGEN_CHAT_BEARER`` に ``Bearer <token>`` を設定（OpenShift では ``tools/gen_glossary_openshift.sh`` が Keycloak から取得）。
- **OpenAI 直** … 上記が空で ``OPENAI_API_KEY`` があるとき。従来どおり ``tools/openai_chat.py``。

フェーズ:
  1. 本文開始行以降をチャンク分割し、各チャンクで候補語を JSON で抽出。
  2. 語を正規化して重複除去し、上限まで残す。
  3. バッチで各語の読み（ひらがな）と解説本文を生成。
  4. ``doc/glossary_ai_cache.json`` にキャッシュ（``--force`` で再取得）。
  5. ``web/glossary/index.html`` を再生成。

環境変数（OpenAI 直）:
  - ``OPENAI_API_KEY``、``DOGEN_AI_TOOLS_MODEL``、``OPENAI_BASE_URL``

環境変数（dogen-api）:
  - ``DOGEN_CHAT_API_BASE``、``DOGEN_CHAT_BEARER``、任意 ``DOGEN_CHAT_MODEL``

使用例::

    python3 tools/gen_glossary_from_corpus.py --dry-run
    DOGEN_CHAT_API_BASE=https://… DOGEN_CHAT_BEARER='Bearer …' python3 tools/gen_glossary_from_corpus.py --max-terms 24
    python3 tools/gen_glossary_from_corpus.py --openai-only --max-chunks 6
    python3 tools/gen_glossary_from_corpus.py --render-only

``--openai-only``: ``DOGEN_CHAT_API_BASE`` が設定されていても OpenAI 直を使う。
``--render-only``: 既存の ``doc/glossary_ai_cache.json`` から HTML のみ再生成。
"""
from __future__ import annotations

import argparse
import hashlib
import html as html_module
import importlib.util
import json
import os
import re
import sys
import time
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC_TXT = ROOT / "doc" / "正法眼蔵.txt"
CACHE_PATH = ROOT / "doc" / "glossary_ai_cache.json"
GLOSSARY_HTML = ROOT / "web" / "glossary" / "index.html"


def _load_gw():
    p = ROOT / "tools" / "gen_web_volumes.py"
    spec = importlib.util.spec_from_file_location("gen_web_volumes", p)
    if spec is None or spec.loader is None:
        raise RuntimeError("gen_web_volumes load failed")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


gw = _load_gw()


def _corpus_body(lines: list[str]) -> str:
    """目次・メタを除き、七十五巻本文開始行から末尾まで。"""
    start_1b = gw.BODY_75_STARTS_1BASED[0]
    a = start_1b - 1
    return "\n".join(lines[a:])


def _chunk_text(text: str, *, size: int, stride: int) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(text):
        out.append(text[i : i + size])
        i += stride
    return out


def _pick_lemmas_from_chunk(chunk: str, *, model: str | None) -> list[dict]:
    from openai_chat import openai_chat_json, with_retries

    def _once() -> dict:
        return openai_chat_json(
            [
                {
                    "role": "system",
                    "content": (
                        "道元『正法眼蔵』の学習用語抽出。与えられたテキスト断片に**実際に部分文字列として現れる**"
                        "漢字を中心とした語・熟語のみを候補にすること（幻覚禁止）。"
                        "JSON のみ返す。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "以下のテキスト断片から、学習者にとって難解になりやすい語を最大10件選び、"
                        'JSON オブジェクト {"candidates":[{"lemma":"原文表記","reason":"一行理由"}]} の形で返す。\n\n'
                        f"【断片】\n{chunk[:10500]}"
                    ),
                },
            ],
            model=model,
            temperature=0.2,
        )

    data = with_retries(_once, attempts=3)
    raw = data.get("candidates")
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for it in raw:
        if not isinstance(it, dict):
            continue
        lem = it.get("lemma")
        reason = it.get("reason", "")
        if not isinstance(lem, str):
            continue
        lem = lem.strip()
        if len(lem) < 2 or len(lem) > 24:
            continue
        norm_chunk = chunk.replace("\n", "").replace("\r", "")
        if lem not in norm_chunk and lem not in chunk:
            continue
        out.append({"lemma": lem, "reason": str(reason).strip()[:200]})
    return out


def _pick_lemmas_from_chunk_dogen(
    chunk: str,
    api_base: str,
    bearer: str,
    *,
    chat_model: str | None,
) -> list[dict]:
    from dogen_chat_client import call_chat_messages

    user = (
        "以下のテキスト断片から、学習者にとって難解になりやすい語を最大10件選び、"
        '**JSON のみ**（前後に説明を付けない）で '
        '{"candidates":[{"lemma":"原文表記","reason":"一行理由"}]} の形で返す。\n\n'
        f"【断片】\n{chunk[:10500]}"
    )
    raw = call_chat_messages(
        api_base,
        bearer,
        [
            {
                "role": "system",
                "content": (
                    "道元『正法眼蔵』の学習用語抽出。与えられたテキスト断片に**実際に部分文字列として現れる**"
                    "漢字を中心とした語・熟語のみを候補にすること（幻覚禁止）。\n"
                    "応答は **JSON オブジェクトだけ**（1 行でも可）。マークダウン・コードフェンス・説明文は禁止。"
                ),
            },
            {"role": "user", "content": user},
        ],
        model=chat_model,
        retries=3,
        timeout_s=120,
    )
    from openai_chat import parse_json_object

    try:
        data = parse_json_object(raw)
    except (ValueError, json.JSONDecodeError) as e:
        print(f"WARN lemma pick (dogen-api): JSON の解釈に失敗したためこのチャンクをスキップ: {e}", file=sys.stderr)
        print(f"  raw prefix: {raw[:500]!r}", file=sys.stderr)
        return []
    raw_list = data.get("candidates")
    if not isinstance(raw_list, list):
        return []
    out: list[dict] = []
    for it in raw_list:
        if not isinstance(it, dict):
            continue
        lem = it.get("lemma")
        reason = it.get("reason", "")
        if not isinstance(lem, str):
            continue
        lem = lem.strip()
        if len(lem) < 2 or len(lem) > 24:
            continue
        norm_chunk = chunk.replace("\n", "").replace("\r", "")
        if lem not in norm_chunk and lem not in chunk:
            continue
        out.append({"lemma": lem, "reason": str(reason).strip()[:200]})
    return out


def _enrich_batch(batch: list[dict], corpus_sample: str, *, model: str | None) -> list[dict]:
    from openai_chat import openai_chat_json, with_retries

    lemmata = [b["lemma"] for b in batch]
    payload = json.dumps(lemmata, ensure_ascii=False)

    def _once() -> dict:
        return openai_chat_json(
            [
                {
                    "role": "system",
                    "content": (
                        "道元『正法眼蔵』の用語解説。与えられた語リストと原文サンプルに根拠を寄せ、"
                        "推測は推測と明示するか避ける。解説はプレーンテキスト（HTML 禁止）。JSON のみ。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"語リスト（JSON）: {payload}\n\n"
                        "各語について、ひらがなの読み（現代一般的な読みでよい）と、"
                        "80〜220 字程度の解説（『正法眼蔵』における用法の手掛かり）を付与。\n"
                        '返却形式: {"entries":[{"lemma":"…","reading_hiragana":"…","definition":"…"}]}'
                        "\n\n【原文サンプル（冒頭のみ）】\n"
                        f"{corpus_sample[:6000]}"
                    ),
                },
            ],
            model=model,
            temperature=0.35,
        )

    data = with_retries(_once, attempts=4)
    ent = data.get("entries")
    if not isinstance(ent, list):
        return []
    out: list[dict] = []
    for it in ent:
        if not isinstance(it, dict):
            continue
        lem = str(it.get("lemma", "")).strip()
        rd = str(it.get("reading_hiragana", "")).strip()
        df = str(it.get("definition", "")).strip()
        if not lem or not rd or not df:
            continue
        rd = unicodedata.normalize("NFKC", rd)
        out.append({"lemma": lem, "reading_hiragana": rd, "definition": df})
    return out


def _enrich_batch_dogen(
    batch: list[dict],
    corpus_sample: str,
    api_base: str,
    bearer: str,
    *,
    chat_model: str | None,
) -> list[dict]:
    from dogen_chat_client import call_chat_messages
    from openai_chat import parse_json_object

    lemmata = [b["lemma"] for b in batch]
    payload = json.dumps(lemmata, ensure_ascii=False)
    user = (
        f"語リスト（JSON）: {payload}\n\n"
        "各語について、ひらがなの読み（現代一般的な読みでよい）と、"
        "80〜220 字程度の解説（『正法眼蔵』における用法の手掛かり）を付与。"
        "根拠は与えられた原文サンプルおよび（利用可能なら）会話に注入された出典に限定すること。\n"
        '**JSON オブジェクトだけ**（マークダウン・コードフェンス・説明文禁止）。'
        '{"entries":[{"lemma":"…","reading_hiragana":"…","definition":"…"}]} の形。\n\n'
        "【原文サンプル（冒頭のみ）】\n"
        f"{corpus_sample[:6000]}"
    )
    raw = call_chat_messages(
        api_base,
        bearer,
        [
            {
                "role": "system",
                "content": (
                    "道元『正法眼蔵』の用語解説。推測は推測と明示するか避ける。"
                    "解説はプレーンテキスト（HTML 禁止）。"
                    "応答は JSON オブジェクトのみ（マークダウン・フェンス・前置き禁止）。"
                ),
            },
            {"role": "user", "content": user},
        ],
        model=chat_model,
        retries=4,
        timeout_s=180,
    )
    try:
        data = parse_json_object(raw)
    except (ValueError, json.JSONDecodeError) as e:
        print(f"WARN enrich batch (dogen-api): JSON の解釈に失敗: {e}", file=sys.stderr)
        print(f"  raw prefix: {raw[:500]!r}", file=sys.stderr)
        return []
    ent = data.get("entries")
    if not isinstance(ent, list):
        return []
    out: list[dict] = []
    for it in ent:
        if not isinstance(it, dict):
            continue
        lem = str(it.get("lemma", "")).strip()
        rd = str(it.get("reading_hiragana", "")).strip()
        df = str(it.get("definition", "")).strip()
        if not lem or not rd or not df:
            continue
        rd = unicodedata.normalize("NFKC", rd)
        out.append({"lemma": lem, "reading_hiragana": rd, "definition": df})
    return out


def _merge_unique(candidates: list[dict], max_terms: int) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for c in candidates:
        lem = unicodedata.normalize("NFKC", c["lemma"].strip())
        key = lem
        if key in seen:
            continue
        seen.add(key)
        out.append({"lemma": lem, "reason": c.get("reason", "")})
        if len(out) >= max_terms:
            break
    return out


def _sort_key_reading(e: dict) -> tuple[str, str]:
    r = e.get("reading_hiragana") or ""
    return (r, e.get("lemma", ""))


def _reading_group_title(reading: str) -> str:
    if not reading:
        return "その他"
    c = reading[0]
    # ひらがな五十音の粗い行見出し
    rows = [
        ("あ行", "あいうえおぁぃぅぇぉアイウエオァィゥェォ"),
        ("か行", "かきくけこがぎぐげごきゃきゅきょカキクケコガギグゲゴキャキュキョ"),
        ("さ行", "さしすせそざじずぜぞしゃしゅしょサシスセソザジズゼゾシャシュショ"),
        ("た行", "たちつてとだぢづでどちゃちゅちょタチツテトダヂヅデドチャチュチョ"),
        ("な行", "なにぬねのにゃにゅにょナニヌネノニャニュニョ"),
        ("は行", "はひふへほばびぶべぼぱぴぷぺぽひゃひゅひょふゃふゅふょハヒフヘホバビブベボパピプペポヒャヒュヒョ"),
        ("ま行", "まみむめもみゃみゅみょマミムメモミャミュミョ"),
        ("や行", "やゆよゃゅょヤユヨャュョ"),
        ("ら行", "らりるれろりゃりゅりょラリルレロリャリュリョ"),
        ("わ行", "わをんーォヮワヲンーワヮ"),
    ]
    for title, chars in rows:
        if c in chars:
            return title
    return "その他"


def _render_glossary_html(entries: list[dict], *, generation_backend: str = "openai") -> str:
    """既存ナビ・手編集ブロックを保ち、AI 節を差し込む。"""
    # 手編集 dl（巻ページ id 互換）
    manual = """
        <h2>手編集サンプル（巻ページ・テーマからのリンク互換）</h2>
        <dl>
          <dt id="soku">即（卽）</dt>
          <dd>「すなわち一致する」「離れず即している」など、中道や相即を表す接辞として多用されます。</dd>
          <dt id="shusho">修証</dt>
          <dd>修行と悟りを切り離さずに論じる語。悟りだけ先にある、とも修行だけが実、とも片づけにくい箇所で繰り返し出ます。</dd>
          <dt>迷悟</dt>
          <dd>迷いとさとりの対語。対立を超えて論じられることが多いです。</dd>
        </dl>
"""
    # AI 部: 行グループごとに dl
    entries = sorted(entries, key=_sort_key_reading)
    groups: dict[str, list[dict]] = {}
    for e in entries:
        g = _reading_group_title(e.get("reading_hiragana", ""))
        groups.setdefault(g, []).append(e)

    order = ["あ行", "か行", "さ行", "た行", "な行", "は行", "ま行", "や行", "ら行", "わ行", "その他"]
    parts: list[str] = []
    src = (
        "<code>tools/gen_glossary_from_corpus.py</code> が <code>doc/正法眼蔵.txt</code> の本文を分割し、"
        "<strong>dogen-api（問答 API）</strong>経由で抽出・解説したものです（Llama Stack・RAG の挙動は本番設定に依存）。"
        if generation_backend == "dogen-chat"
        else "<code>tools/gen_glossary_from_corpus.py</code> が <code>doc/正法眼蔵.txt</code> の本文を分割し、"
        "<strong>OpenAI API</strong> で抽出・解説したものです。"
    )
    parts.append(
        f"""
        <h2>『正法眼蔵』原文に基づく用語（AI 補助）</h2>
        <p class="notice">
          以下は {src}
          <strong>モデル出力であり誤りがあり得ます</strong>。
          重要な理解は必ず原文・教本・師の説と照合してください。出典テキスト:
          <a href="https://shomonji.or.jp/zazen/doc/genzou.html">https://shomonji.or.jp/zazen/doc/genzou.html</a>
        </p>
"""
    )
    for gname in order:
        if gname not in groups:
            continue
        parts.append(f"        <h3>{html_module.escape(gname)}</h3>\n        <dl>")
        for e in groups[gname]:
            lid = hashlib.sha256(e["lemma"].encode("utf-8")).hexdigest()[:12]
            dt = html_module.escape(e["lemma"])
            rd = html_module.escape(e.get("reading_hiragana", ""))
            dd = html_module.escape(e.get("definition", ""))
            parts.append(f'          <dt id="gloss-{lid}">{dt}<span class="notice" style="font-size:0.85rem">（{rd}）</span></dt>')
            parts.append(f"          <dd>{dd}</dd>")
        parts.append("        </dl>")

    ai_block = "\n".join(parts)

    return f"""<!DOCTYPE html>
<html lang="ja">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <link rel="icon" type="image/png" sizes="32x32" href="../img/app-icon-dogen-32.png" />
    <link rel="icon" href="../favicon.ico" sizes="any" />
    <link rel="apple-touch-icon" href="../apple-touch-icon.png" />
    <title>用語辞典 — 正法眼蔵読解</title>
    <link rel="stylesheet" href="../css/main.css" />
  </head>
  <body>
    <header class="site-header">
      <div class="site-header__inner">
        <a class="site-logo" href="../index.html">正法眼蔵読解</a>
        <button type="button" class="nav-toggle" aria-expanded="false" aria-controls="site-nav">メニュー</button>
        <nav id="site-nav" class="site-nav" aria-label="主要ナビゲーション">
          <a href="../guide/index.html">学習ガイド</a>
          <a href="../volumes/index.html">巻一覧</a>
          <a href="../themes/index.html">テーマ</a>
          <a href="index.html">用語</a>
          <a href="../chat/index.html">問答 Bot</a>
          <a href="../site/index.html">サイト情報</a>
        </nav>
      </div>
    </header>

    <main>
      <article class="prose">
        <h1>用語辞典</h1>
        <p>頻出語・難解語を横断的に説明するページです。上段は手編集の固定項目、下段は原文コーパスからの AI 補助索引です。</p>

{manual}
{ai_block}

        <p><a href="../volumes/index.html">巻一覧</a> · <a href="../index.html">ホーム</a></p>
      </article>
    </main>

    <footer class="site-footer">
      <p><a href="../index.html">ホーム</a> · 正法眼蔵読解</p>
    </footer>
    <script src="../js/nav.js" defer></script>
  </body>
</html>
"""


def main() -> int:
    sys.path.insert(0, str(ROOT / "tools"))
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="API 呼び出しと書き込みを行わない")
    ap.add_argument("--force", action="store_true", help="キャッシュを無視して再抽出・再解説")
    ap.add_argument("--render-only", action="store_true", help="キャッシュから HTML のみ生成")
    ap.add_argument("--max-chunks", type=int, default=18, help="原文チャンク処理の上限（課金抑制）")
    ap.add_argument("--max-terms", type=int, default=48, help="用語の最大件数")
    ap.add_argument("--chunk-size", type=int, default=11000)
    ap.add_argument("--chunk-stride", type=int, default=9500)
    ap.add_argument("--model", type=str, default="", help="モデル ID（OpenAI 直: DOGEN_AI_TOOLS_MODEL。API: DOGEN_CHAT_MODEL）")
    ap.add_argument(
        "--api-base",
        default="",
        metavar="URL",
        help="dogen-api オリジン（未指定時は DOGEN_CHAT_API_BASE。設定されていれば OpenAI より優先）",
    )
    ap.add_argument(
        "--bearer",
        default="",
        metavar="HDR",
        help="Authorization ヘッダ（未指定時は DOGEN_CHAT_BEARER、匿名 Compose では Bearer fake）",
    )
    ap.add_argument(
        "--openai-only",
        action="store_true",
        help="DOGEN_CHAT_API_BASE があっても OpenAI 直で実行する",
    )
    args = ap.parse_args()

    model = args.model.strip() or None

    def _resolve_backend() -> str:
        if args.openai_only:
            return "openai"
        base = (args.api_base or os.environ.get("DOGEN_CHAT_API_BASE") or "").strip()
        if base:
            return "dogen-chat"
        return "openai"

    backend = _resolve_backend()
    api_base = (args.api_base or os.environ.get("DOGEN_CHAT_API_BASE") or "").strip()
    bearer = (args.bearer or os.environ.get("DOGEN_CHAT_BEARER") or "Bearer fake").strip()
    chat_model = (args.model or os.environ.get("DOGEN_CHAT_MODEL") or "").strip() or None

    if args.render_only:
        if not CACHE_PATH.is_file():
            print("ERROR: cache missing:", CACHE_PATH, file=sys.stderr)
            return 1
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        entries = data.get("entries")
        if not isinstance(entries, list):
            print("ERROR: invalid cache", file=sys.stderr)
            return 1
        gen_be = str(data.get("backend") or "openai")
        html = _render_glossary_html(entries, generation_backend=gen_be)
        if not args.dry_run:
            GLOSSARY_HTML.write_text(html, encoding="utf-8")
        print("render-only:", len(entries), "entries ->", GLOSSARY_HTML, "backend=", gen_be)
        return 0

    lines = gw.load_doc_lines()
    body = _corpus_body(lines)

    if args.dry_run:
        chunks = _chunk_text(body, size=args.chunk_size, stride=args.chunk_stride)[: args.max_chunks]
        print(
            "dry-run: backend=",
            backend,
            "chunks=",
            len(chunks),
            "body chars=",
            len(body),
            flush=True,
        )
        return 0

    if not args.force and CACHE_PATH.is_file():
        try:
            cached = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
            if isinstance(cached.get("entries"), list) and len(cached["entries"]) > 0:
                gen_be = str(cached.get("backend") or "openai")
                html = _render_glossary_html(cached["entries"], generation_backend=gen_be)
                if not args.dry_run:
                    GLOSSARY_HTML.write_text(html, encoding="utf-8")
                print("Used existing cache:", CACHE_PATH, "entries=", len(cached["entries"]))
                print("Wrote", GLOSSARY_HTML)
                print("(Use --force to rebuild from API)")
                return 0
        except Exception:
            pass

    if backend == "openai":
        from openai_chat import try_load_local_openai_key

        try_load_local_openai_key()
        if not (os.environ.get("OPENAI_API_KEY") or "").strip():
            print(
                "ERROR: OPENAI_API_KEY が未設定です。dogen-api を使う場合は DOGEN_CHAT_API_BASE を設定してください。",
                file=sys.stderr,
            )
            return 1
    else:
        print("backend: dogen-api (OpenShift / ローカル問答 API)", api_base, flush=True)

    chunks = _chunk_text(body, size=args.chunk_size, stride=args.chunk_stride)[: args.max_chunks]
    all_cand: list[dict] = []
    for i, ch in enumerate(chunks):
        print(f"chunk {i+1}/{len(chunks)} …", flush=True)
        if backend == "dogen-chat":
            all_cand.extend(_pick_lemmas_from_chunk_dogen(ch, api_base, bearer, chat_model=chat_model))
        else:
            all_cand.extend(_pick_lemmas_from_chunk(ch, model=model))
        time.sleep(0.35)

    merged = _merge_unique(all_cand, args.max_terms)
    print("unique lemmas:", len(merged))

    corpus_head = body[:12000]
    enriched: list[dict] = []
    batch_size = 6
    for i in range(0, len(merged), batch_size):
        batch = merged[i : i + batch_size]
        print("enrich batch", i // batch_size + 1, "…", flush=True)
        if backend == "dogen-chat":
            part = _enrich_batch_dogen(batch, corpus_head, api_base, bearer, chat_model=chat_model)
        else:
            part = _enrich_batch(batch, corpus_head, model=model)
        by_lem = {
            unicodedata.normalize("NFKC", str(x.get("lemma", "")).strip()): x
            for x in part
            if isinstance(x, dict) and str(x.get("lemma", "")).strip()
        }
        for b in batch:
            lem = unicodedata.normalize("NFKC", b["lemma"])
            if lem in by_lem:
                enriched.append(by_lem[lem])
        time.sleep(0.45)

    cache_obj = {"version": 1, "entries": enriched, "backend": backend}
    CACHE_PATH.write_text(json.dumps(cache_obj, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote cache", CACHE_PATH, "entries=", len(enriched), "backend=", backend)

    html = _render_glossary_html(enriched, generation_backend=backend)
    GLOSSARY_HTML.write_text(html, encoding="utf-8")
    print("wrote", GLOSSARY_HTML)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
