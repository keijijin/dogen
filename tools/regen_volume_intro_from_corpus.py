#!/usr/bin/env python3
"""HAND_SLUGS（手編集）以外の巻の index.html を、OpenAI による紹介・語彙・深掘り・クイズで再生成する。

入力は ``doc/正法眼蔵.txt`` の当該巻冒頭（長さ上限あり）。**根拠は入力抜粋の範囲に限定**するよう
プロンプトで指示する（モデルの幻覚は利用者側で吟味すること）。

- 既定: ``OPENAI_API_KEY``（または ``deploy/local/.env``）と Chat Completions を使用。
- ``--offline``: 従来のヒューリスティックのみ（API 不要）。

七十五巻は ``gen_web_volumes.HAND_SLUGS`` をスキップ。十二巻はすべて対象。辨道話 index は触らない。

使用例::

    python3 tools/regen_volume_intro_from_corpus.py
    python3 tools/regen_volume_intro_from_corpus.py --slug 75-06
    python3 tools/regen_volume_intro_from_corpus.py --offline --dry-run

``tools/gen_web_volumes.py`` 実行後は ``HAND_SLUGS`` 以外の index が汎用テンプレに戻るため、
必要なら **その後に** 本スクリプトを再実行する。

紹介ページの用語・抜粋長を既存 HTML に揃えるだけの場合は ``tools/patch_intro_page_wording.py`` を参照。
"""
from __future__ import annotations

import argparse
import html as html_module
import importlib.util
import os
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VOL = ROOT / "web" / "volumes"


def _load_gen_web_volumes():
    path = ROOT / "tools" / "gen_web_volumes.py"
    spec = importlib.util.spec_from_file_location("gen_web_volumes", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gw = _load_gen_web_volumes()
SKIP_SLUGS: frozenset[str] = frozenset(gw.HAND_SLUGS)

# --offline 用の最小スキャン語
_OFFLINE_SCAN: tuple[str, ...] = (
    "修證",
    "諸法",
    "萬法",
    "佛性",
    "法界",
    "法身",
    "行佛",
    "威儀",
    "諸佛",
    "衆生",
    "菩提",
    "無明",
    "坐禪",
    "公案",
    "現成",
    "平常心",
    "古佛心",
    "曹谿",
    "行履",
    "承當",
    "脱落",
    "參學",
    "宗旨",
    "時節",
    "因緣",
    "恁麼",
    "法界",
    "身心",
)


def _opening_plain(lines: list[str], start_1b: int, next_start_1b: int, max_chars: int = 2400) -> str:
    paras = gw.extract_volume_paragraphs(lines, start_1b, next_start_1b)
    if not paras:
        return ""
    parts: list[str] = []
    n = 0
    for p in paras:
        block = "".join(p)
        if n + len(block) > max_chars:
            parts.append(block[: max_chars - n])
            break
        parts.append(block)
        n += len(block)
    return "".join(parts)


def _opening_for_slug(
    kind: str,
    idx: int,
    lines: list[str],
    body_starts: list[int],
) -> str:
    s1 = body_starts[idx - 1]
    s2 = body_starts[idx]
    return _opening_plain(lines, s1, s2)


def _term_counts_offline(opening: str) -> Counter[str]:
    c: Counter[str] = Counter()
    window = opening[:3800]
    for t in _OFFLINE_SCAN:
        k = window.count(t)
        if k:
            c[t] = k
    return c


def _volume_page_html(
    kind: str,
    num: int,
    title: str,
    excerpt_block: str,
    prev_next: str,
    intro_block: str,
    vocab_ul: str,
    deep_ul: str,
    quiz1: str,
    quiz2: str,
    slug: str,
    fulltext_link: bool,
    *,
    source_note: str,
) -> str:
    label = "七十五巻" if kind == "75" else "十二巻"
    anchor = "#75" if kind == "75" else "#12"
    esc_title = gw.html.escape(title)
    meta = gw.html.escape(
        f"正法眼蔵第{num}　{title}。紹介ページ（語彙・原文の要点抜粋・クイズ・{slug}）。"
    )
    manga = gw.intro_manga_block(slug)
    full_notice = (
        '<p class="notice"><strong>原文・現代語訳の全文</strong>は <a href="full.html">全文ページ</a>を参照してください。</p>'
        if fulltext_link
        else ""
    )
    return f"""<!DOCTYPE html>
<html lang="ja">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>第{num}　{esc_title} — 正法眼蔵読解</title>
    <meta name="description" content="{meta}" />
    {gw.head_favicon_links("../../")}
    <link rel="stylesheet" href="../../css/main.css" />
  </head>
  <body>
    <header class="site-header">
      <div class="site-header__inner">
        <a class="site-logo" href="../../index.html">正法眼蔵読解</a>
        <button type="button" class="nav-toggle" aria-expanded="false" aria-controls="site-nav">メニュー</button>
        <nav id="site-nav" class="site-nav" aria-label="主要ナビゲーション">
          <a href="../../guide/index.html">学習ガイド</a>
          <a href="../index.html">巻一覧</a>
          <a href="../../themes/index.html">テーマ</a>
          <a href="../../glossary/index.html">用語</a>
          <a href="../../chat/index.html">問答 Bot</a>
          <a href="../../site/index.html">サイト情報</a>
        </nav>
      </div>
    </header>

    <main>
      <article id="top" class="prose">
        <p><span class="badge">{label}</span> <a href="../index.html{anchor}">巻一覧</a></p>
        <h1>正法眼藏第{num}　{esc_title}</h1>

        <p class="notice">
          {source_note}
          出典: <a href="{gw.SOURCE_URL}">{gw.SOURCE_URL}</a>
        </p>
        {full_notice}

        <h2>この巻の紹介（導入）</h2>
{intro_block}

        <h2>語彙の足場</h2>
        <ul>
          {vocab_ul}
        </ul>

        <h2>原文（要点の抜粋）</h2>
        <p class="notice">
          当巻の<strong>冒頭付近からの短い抜粋</strong>です。長い引用は載せていません。全文は<strong>全文ページ</strong>を参照してください。出典はリポジトリ内 <code>doc/正法眼蔵.txt</code> です。原文の参照元: <a href="{gw.SOURCE_URL}">{gw.SOURCE_URL}</a>
        </p>
        {excerpt_block}
{manga}

        <h2>深掘り（読解の手掛かり）</h2>
        <ul>
          {deep_ul}
        </ul>

        <h2>確認（形成評価）</h2>
        <p class="notice" style="font-size:0.88rem">各設問の下の「採点」で正誤を表示します（ブラウザ内のみ。ログは送りません）。</p>
{quiz1}
{quiz2}

        <p>{prev_next}</p>
      </article>
    </main>

    <footer class="site-footer">
      <p><a href="../../index.html">ホーム</a> · 正法眼蔵読解</p>
    </footer>
    <script src="../../js/nav.js" defer></script>
  </body>
</html>
"""


def _fieldset_quiz(slug: str, qid: str, legend: str, options: list[str], correct_index: int) -> str:
    labels = []
    for i, opt in enumerate(options):
        esc = html_module.escape(opt)
        labels.append(f'<label><input type="radio" name="{slug}-{qid}" value="{i}" /> {esc}</label>')
    inner = "\n          ".join(labels)
    leg = html_module.escape(legend)
    return f"""        <fieldset class="quiz" data-correct-index="{correct_index}">
          <legend>{leg}</legend>
          {inner}
        </fieldset>"""


def _normalize_quiz(raw: dict, *, n_options: int, slug: str, qname: str) -> dict | None:
    if not isinstance(raw, dict):
        return None
    q = raw.get("question")
    opts = raw.get("options")
    ci = raw.get("correct_index")
    if not isinstance(q, str) or not q.strip():
        return None
    if not isinstance(opts, list):
        return None
    opts2 = [str(x).strip() for x in opts if str(x).strip()]
    if len(opts2) < n_options:
        return None
    opts2 = opts2[:n_options]
    try:
        ci_int = int(ci)
    except (TypeError, ValueError):
        return None
    if ci_int < 0 or ci_int >= len(opts2):
        print(f"  WARN {slug} {qname}: correct_index out of range, clamping", file=sys.stderr)
        ci_int = max(0, min(ci_int, len(opts2) - 1))
    return {"question": q.strip(), "options": opts2, "correct_index": ci_int}


def _call_openai_volume_block(
    *,
    slug: str,
    title: str,
    opening: str,
    model: str | None,
) -> dict:
    from openai_chat import openai_chat_json, with_retries

    body = opening[:4800]
    if not body.strip():
        body = "（冒頭テキストが空です。巻境界設定を確認してください。）"

    schema_hint = """次の JSON オブジェクトのみを返すこと（前後に説明文を付けない）:
{
  "intro_paragraphs": ["段落1", "段落2"],
  "vocab_items": [{"term": "語", "gloss": "50〜160字程度の説明"}],
  "deep_bullets": ["箇条書き1", "箇条書き2", "箇条書き3"],
  "quiz1": {"question": "設問文", "options": ["選択肢A","選択肢B","選択肢C"], "correct_index": 0},
  "quiz2": {"question": "設問文", "options": ["A","B","C","D"], "correct_index": 0}
}
intro_paragraphs は 1〜2 要素。vocab_items は 4〜6 要素。deep_bullets は 3〜4 要素。
quiz の選択肢はいずれも**与えられた冒頭原文の内容に即した**学習用のものとし、
根拠のない歴史事実や他経典の断片を捏造しないこと。"""

    user = (
        f"巻識別子: {slug}\n巻題: {title}\n\n"
        "以下は『正法眼蔵』当該巻の冒頭原文（リポジトリからの抜粋。長さ上限あり）です。\n"
        "語彙・クイズはこの範囲に根拠があるものに限定してください。\n\n"
        f"【冒頭原文】\n{body}\n\n{schema_hint}"
    )

    def _once() -> dict:
        return openai_chat_json(
            [
                {
                    "role": "system",
                    "content": (
                        "あなたは道元『正法眼蔵』の学習支援をする編集アシスタントです。"
                        "与えられた原文抜粋の範囲でしか主張せず、推測は推測と明示するか避けてください。"
                        "JSON 以外は出力しないでください。"
                    ),
                },
                {"role": "user", "content": user},
            ],
            model=model,
            temperature=0.35,
        )

    return with_retries(_once, attempts=4)


def _build_blocks_from_ai(data: dict, slug: str) -> tuple[str, str, str, str, str]:
    ips = data.get("intro_paragraphs")
    if not isinstance(ips, list) or not ips:
        ips = ["（導入文の生成に失敗しました。再実行してください。）"]
    intro_block = "\n".join(
        f"        <p>{html_module.escape(str(p).strip())}</p>" for p in ips if str(p).strip()
    )

    vocab_items = data.get("vocab_items")
    lis: list[str] = []
    if isinstance(vocab_items, list):
        for it in vocab_items[:8]:
            if not isinstance(it, dict):
                continue
            term, gloss = it.get("term"), it.get("gloss")
            if isinstance(term, str) and isinstance(gloss, str) and term.strip() and gloss.strip():
                lis.append(
                    f"<li><strong>{html_module.escape(term.strip())}</strong>："
                    f"{html_module.escape(gloss.strip())}</li>"
                )
    if len(lis) < 2:
        lis.append("<li><strong>巻題</strong>：原文中の用例で意味を確かめてください。</li>")
    vocab_ul = "\n          ".join(lis)

    dbs = data.get("deep_bullets")
    bullets: list[str] = []
    if isinstance(dbs, list):
        for b in dbs[:6]:
            if isinstance(b, str) and b.strip():
                bullets.append(f"<li>{html_module.escape(b.strip())}</li>")
    if len(bullets) < 2:
        bullets.append("<li>否定と肯定の往復を、巻全体の流れで捉え直してください。</li>")
    deep_ul = "\n          ".join(bullets)

    q1 = _normalize_quiz(data.get("quiz1") or {}, n_options=3, slug=slug, qname="quiz1")
    q2 = _normalize_quiz(data.get("quiz2") or {}, n_options=4, slug=slug, qname="quiz2")
    if not q1:
        q1 = {
            "question": "この巻の読み方として、まず避けたいのはどれか。",
            "options": [
                "原文を読まず要約だけで満足する",
                "語の照応を丁寧に追う",
                "分からない箇所に印を付ける",
            ],
            "correct_index": 0,
        }
    if not q2:
        q2 = {
            "question": "出典として優先すべきなのはどれか。",
            "options": [
                "権利処理済みの訳文テキストと自分の読解",
                "検索上位の無名要約のみ",
                "推測のみで穴埋めする読み",
                "巻題だけを断定的に解釈する",
            ],
            "correct_index": 0,
        }
    quiz1_html = _fieldset_quiz(slug, "q1", q1["question"], q1["options"], q1["correct_index"])
    quiz2_html = _fieldset_quiz(slug, "q2", q2["question"], q2["options"], q2["correct_index"])
    return intro_block, vocab_ul, deep_ul, quiz1_html, quiz2_html


def _process_volume_ai(
    kind: str,
    idx: int,
    title: str,
    lines: list[str],
    body_starts: list[int],
    dry_run: bool,
    generate_full: bool,
    model: str | None,
) -> str | None:
    from openai_chat import try_load_local_openai_key

    try_load_local_openai_key()
    slug = f"{kind}-{idx:02d}"
    s1 = body_starts[idx - 1]
    s2 = body_starts[idx]
    opening = _opening_for_slug(kind, idx, lines, body_starts)
    excerpt = gw.excerpt_paragraphs(lines, s1, s2)

    if dry_run:
        return str(VOL / slug / "index.html")

    data = _call_openai_volume_block(slug=slug, title=title, opening=opening, model=model)
    intro_b, vocab_ul, deep_ul, q1h, q2h = _build_blocks_from_ai(data, slug)
    note = (
        "本ページは各巻の<strong>紹介ページ</strong>です。導入・語彙・深掘り・クイズは <code>tools/regen_volume_intro_from_corpus.py</code> が "
        "OpenAI API で生成したものです（入力は当巻の原文からの<strong>短い抜粋</strong>のみ）。"
        "内容はモデル出力のため、重要箇所は必ず原文・教本と照合してください。"
    )
    page = _volume_page_html(
        kind,
        idx,
        title,
        excerpt,
        gw.nav_link_prev_next(kind, idx),
        intro_b,
        vocab_ul,
        deep_ul,
        q1h,
        q2h,
        slug,
        generate_full,
        source_note=note,
    )
    (VOL / slug / "index.html").write_text(page, encoding="utf-8")
    return str(VOL / slug / "index.html")


def _process_volume_offline(
    kind: str,
    idx: int,
    title: str,
    lines: list[str],
    body_starts: list[int],
    _titles: list[str],
    dry_run: bool,
    generate_full: bool,
) -> str | None:
    slug = f"{kind}-{idx:02d}"
    s1 = body_starts[idx - 1]
    s2 = body_starts[idx]
    opening = _opening_for_slug(kind, idx, lines, body_starts)
    counts = _term_counts_offline(opening)
    excerpt = gw.excerpt_paragraphs(lines, s1, s2)

    def _top_terms(counts: Counter[str], lim: int = 5) -> list[str]:
        return [t for t, _ in counts.most_common(lim)] or ["諸法", "萬法"]

    top = _top_terms(counts)
    esc_title = gw.html.escape(title)
    intro_block = f"""        <p>
          「{esc_title}」の紹介（オフライン簡易版）。冒頭に {html_module.escape("、".join(top[:3]))} などが見えます。
          詳細は API 有効時に本スクリプトを再実行してください。
        </p>"""
    lis = [f"<li><strong>巻題</strong>：「{esc_title}」</li>"]
    for t in top[:4]:
        lis.append(f"<li><strong>{html_module.escape(t)}</strong>：原文冒頭の用例で確認。</li>")
    vocab_ul = "\n          ".join(lis)
    deep_ul = (
        f"<li>巻題「{esc_title}」を目印に、引用と道元の按配を追ってください。</li>"
        "<li>括弧内の漢文は外の和文と対で読んでください。</li>"
    )
    q1 = _fieldset_quiz(
        slug,
        "q1",
        "オフライン簡易: 学ぶ姿勢としてまず避けたいのは？",
        ["原文を読まず要約だけで満足する", "語の照応を追う", "印を付けて後で問う"],
        0,
    )
    q2 = _fieldset_quiz(
        slug,
        "q2",
        "オフライン簡易: 出典として優先すべきなのは？",
        [
            "権利処理済みの訳文テキストと自分の読解",
            "無名ブログ要約のみ",
            "推測のみ",
            "巻題の字面だけ",
        ],
        0,
    )
    note = (
        "本ページは各巻の<strong>紹介ページ</strong>の簡易出力です（<code>tools/regen_volume_intro_from_corpus.py --offline</code>）。"
    )
    page = _volume_page_html(
        kind,
        idx,
        title,
        excerpt,
        gw.nav_link_prev_next(kind, idx),
        intro_block,
        vocab_ul,
        deep_ul,
        q1,
        q2,
        slug,
        generate_full,
        source_note=note,
    )
    out = VOL / slug / "index.html"
    if dry_run:
        return str(out)
    out.write_text(page, encoding="utf-8")
    return str(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--offline", action="store_true", help="OpenAI を使わず簡易テンプレのみ")
    ap.add_argument("--slug", type=str, default="", help="例: 75-06 のみ処理")
    ap.add_argument("--model", type=str, default="", help="上書きモデル ID（既定: DOGEN_AI_TOOLS_MODEL または gpt-4o-mini）")
    args = ap.parse_args()

    lines = gw.load_doc_lines()
    generate_full = os.environ.get("DOGEN_GENERATE_FULLTEXT", "1").strip() != "0"
    model = args.model.strip() or None

    if len(gw.BODY_75_STARTS_1BASED) != len(gw.TITLES_75) + 1:
        print("BODY_75_STARTS_1BASED length mismatch", file=sys.stderr)
        return 1
    if len(gw.BODY_12_STARTS_1BASED) != len(gw.TITLES_12) + 1:
        print("BODY_12_STARTS_1BASED length mismatch", file=sys.stderr)
        return 1

    if not args.offline:
        from openai_chat import try_load_local_openai_key

        try_load_local_openai_key()
        if not (os.environ.get("OPENAI_API_KEY") or "").strip():
            print("ERROR: OPENAI_API_KEY が未設定です。--offline を付けるか .env を設定してください。", file=sys.stderr)
            return 1

    written: list[str] = []
    slug_filter = (args.slug or "").strip()

    def want(slug: str) -> bool:
        return not slug_filter or slug == slug_filter

    for i, title in enumerate(gw.TITLES_75, start=1):
        slug = f"75-{i:02d}"
        if slug in SKIP_SLUGS or not want(slug):
            continue
        if args.offline:
            path = _process_volume_offline(
                "75", i, title, lines, gw.BODY_75_STARTS_1BASED, gw.TITLES_75, args.dry_run, generate_full
            )
        else:
            path = _process_volume_ai("75", i, title, lines, gw.BODY_75_STARTS_1BASED, args.dry_run, generate_full, model)
            if not args.dry_run:
                time.sleep(0.4)
        if path:
            written.append(path)

    for i, title in enumerate(gw.TITLES_12, start=1):
        slug = f"12-{i:02d}"
        if not want(slug):
            continue
        if args.offline:
            path = _process_volume_offline(
                "12", i, title, lines, gw.BODY_12_STARTS_1BASED, gw.TITLES_12, args.dry_run, generate_full
            )
        else:
            path = _process_volume_ai("12", i, title, lines, gw.BODY_12_STARTS_1BASED, args.dry_run, generate_full, model)
            if not args.dry_run:
                time.sleep(0.4)
        if path:
            written.append(path)

    mode = "Would write" if args.dry_run else "Wrote"
    print(mode, len(written), "pages; skipped HAND_SLUGS:", ", ".join(sorted(SKIP_SLUGS)))
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "tools"))
    raise SystemExit(main())
