#!/usr/bin/env python3
"""既存の巻紹介 index.html の用語を統一し、機械生成巻の原文ブロックを短い抜粋に差し替える。

- 手編集巻 ``gen_web_volumes.HAND_SLUGS`` は blockquote のみ触らない（見出し・注記の文言置換のみ）。
- ``bendowa/index.html`` は blockquote を触らず見出し・注記のみ。
- 七十五巻・十二巻のその他は ``excerpt_paragraphs``（既定行数）で blockquote を置換。

``tools/gen_web_volumes.py`` のテンプレ更新後に一度実行して整合を取る用途。
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VOL = ROOT / "web" / "volumes"


def _load_gw():
    path = ROOT / "tools" / "gen_web_volumes.py"
    spec = importlib.util.spec_from_file_location("gen_web_volumes", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _slug_body_range(gw, slug: str) -> tuple[int, int] | None:
    if slug == "bendowa":
        return gw.BENDOWA_BODY_START_1BASED, gw.BENDOWA_BODY_NEXT_1BASED
    if slug.startswith("75-"):
        n = int(slug.split("-")[1])
        if n < 1 or n > len(gw.TITLES_75):
            return None
        return gw.BODY_75_STARTS_1BASED[n - 1], gw.BODY_75_STARTS_1BASED[n]
    if slug.startswith("12-"):
        n = int(slug.split("-")[1])
        if n < 1 or n > len(gw.TITLES_12):
            return None
        return gw.BODY_12_STARTS_1BASED[n - 1], gw.BODY_12_STARTS_1BASED[n]
    return None


def _normalize_excerpt_heading_indent(html: str) -> str:
    return re.sub(r"\n\s+<h2>原文（要点の抜粋）</h2>", "\n        <h2>原文（要点の抜粋）</h2>", html)


def _apply_text_replacements(html: str) -> str:
    pairs = [
        (
            "（ローカル生成の全文: <a href=\"full.html\">全文ページ</a>）",
            "<strong>原文・現代語訳の全文</strong>は <a href=\"full.html\">全文ページ</a>を参照してください。",
        ),
        (
            "（ローカル生成の全文：<a href=\"full.html\">全文ページ</a>）",
            "<strong>原文・現代語訳の全文</strong>は <a href=\"full.html\">全文ページ</a>を参照してください。",
        ),
        ("本文（冒頭・抜粋）", "原文（要点の抜粋）"),
        ("本文（冒頭・自動抜粋）", "原文（要点の抜粋）"),
        ("この巻の位置（導入）", "この巻の紹介（導入）"),
        ("この巻の位置づけ（学習メモ）", "この巻の紹介（概要）"),
        ("語彙・冒頭本文・クイズ（", "紹介ページ（語彙・原文の要点抜粋・クイズ（"),
        ("語彙・冒頭本文・形成評価", "紹介ページ（語彙・原文の要点抜粋・形成評価"),
        ("紹介ページ。紹介ページ（", "紹介ページ（"),
        ("入力は当巻冒頭原文の抜粋）。", "入力は当巻の原文からの<strong>短い抜粋</strong>のみ）。"),
        ("入力は当巻冒頭原文の抜粋）", "入力は当巻の原文からの<strong>短い抜粋</strong>のみ）"),
        ("本ページの導入・語彙", "本紹介ページの導入・語彙"),
        ("深掘り（短い手がかり）", "深掘り（読解の手掛かり）"),
        ("本文を読まず", "原文を読まず"),
        ("教義の根拠は本文・出典に従い", "教義の根拠は原文・出典に従い"),
        ("抜粋ページへ戻る", "紹介ページへ戻る"),
        ("冒頭をテーマにした4コマ", "抜粋をテーマにした4コマ"),
        ("<h2>冒頭（抜粋）</h2>", "<h2>原文（要点の抜粋）</h2>"),
    ]
    for a, b in pairs:
        html = html.replace(a, b)
    return html


_EXCERPT_SECTION = re.compile(
    r"<h2>原文（要点の抜粋）</h2>\s*"
    r"(?:<p class=\"notice\">.*?</p>\s*)?"
    r"<blockquote>.*?</blockquote>",
    re.DOTALL,
)


def _canonical_excerpt_notice(gw) -> str:
    u = gw.SOURCE_URL
    return (
        "        <h2>原文（要点の抜粋）</h2>\n"
        "        <p class=\"notice\">\n"
        "          当巻の<strong>冒頭付近からの短い抜粋</strong>です。長い引用は載せていません。"
        " 全文は<strong>全文ページ</strong>を参照してください。出典はリポジトリ内 <code>doc/正法眼蔵.txt</code> です。"
        f'原文の参照元: <a href="{u}">{u}</a>\n'
        "        </p>\n"
    )


def main() -> int:
    gw = _load_gw()
    lines = gw.load_doc_lines()
    hand = gw.HAND_SLUGS
    n_changed = 0
    for path in sorted(VOL.rglob("index.html")):
        rel_parent = path.parent.relative_to(VOL)
        slug = str(rel_parent).replace("\\", "/")
        if slug == ".":
            continue
        text = path.read_text(encoding="utf-8")
        orig = text
        text = _apply_text_replacements(text)

        excerpt_replace = (
            (slug.startswith("75-") or slug.startswith("12-"))
            and slug not in hand
            and slug != "bendowa"
        )
        if excerpt_replace:
            span = _slug_body_range(gw, slug)
            if span:
                s1, s2 = span
                new_inner = gw.excerpt_paragraphs(lines, s1, s2)
                block = _canonical_excerpt_notice(gw) + new_inner + "\n"
                text2, n = _EXCERPT_SECTION.subn(block, text, count=1)
                if n:
                    text = text2
                    # 図解見出し直前の空行が増殖するのを防ぐ
                    text = re.sub(r"(</blockquote>)\n{3,}", r"\1\n\n", text)

        text = _normalize_excerpt_heading_indent(text)
        if text != orig:
            path.write_text(text, encoding="utf-8")
            n_changed += 1
            print(path.relative_to(ROOT))

    # 全文ページの戻りリンク
    for path in sorted(VOL.rglob("full.html")):
        t = path.read_text(encoding="utf-8")
        nt = _apply_text_replacements(t)
        if nt != t:
            path.write_text(nt, encoding="utf-8")
            n_changed += 1
            print(path.relative_to(ROOT))

    print(f"patched_files={n_changed}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
