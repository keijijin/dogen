#!/usr/bin/env python3
"""Pre-generate modern Japanese translations for volume full pages.

This script calls dogen-api (/api/v1/chat) and stores translated HTML blocks in:
  doc/modern_translations.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import sys
from pathlib import Path

import gen_web_volumes as gv
from dogen_chat_client import call_chat


ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = ROOT / "doc" / "modern_translations.json"


def build_targets() -> list[tuple[str, str, int, int]]:
    items: list[tuple[str, str, int, int]] = []
    for i, title in enumerate(gv.TITLES_75, start=1):
        slug = f"75-{i:02d}"
        s1 = gv.BODY_75_STARTS_1BASED[i - 1]
        s2 = gv.BODY_75_STARTS_1BASED[i]
        items.append((slug, title, s1, s2))
    for i, title in enumerate(gv.TITLES_12, start=1):
        slug = f"12-{i:02d}"
        s1 = gv.BODY_12_STARTS_1BASED[i - 1]
        s2 = gv.BODY_12_STARTS_1BASED[i]
        items.append((slug, title, s1, s2))
    items.append(("bendowa", "辨道話", gv.BENDOWA_BODY_START_1BASED, gv.BENDOWA_BODY_NEXT_1BASED))
    return items


def paragraphs_from_source(lines: list[str], start_1b: int, next_1b: int) -> list[str]:
    paras = gv.extract_volume_paragraphs(lines, start_1b, next_1b)
    out: list[str] = []
    for p in paras:
        out.append("\n".join(p))
    return out


def split_chunks(paragraphs: list[str], max_chars: int) -> list[str]:
    chunks: list[str] = []
    cur: list[str] = []
    size = 0
    for para in paragraphs:
        p = para.strip()
        if not p:
            continue
        need = len(p) + (2 if cur else 0)
        if cur and size + need > max_chars:
            chunks.append("\n\n".join(cur))
            cur = [p]
            size = len(p)
        else:
            cur.append(p)
            size += need
    if cur:
        chunks.append("\n\n".join(cur))
    return chunks


def to_html_block(text: str) -> str:
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paras:
        return "<p>（現代語訳を生成できませんでした。）</p>"
    rows = []
    for para in paras:
        lines = para.splitlines()
        rows.append("<p>" + "<br />".join(html.escape(x) for x in lines) + "</p>")
    return "\n        ".join(rows)


def load_existing(path: Path) -> dict:
    if not path.is_file():
        return {"volumes": {}}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"volumes": {}}
    if not isinstance(obj, dict):
        return {"volumes": {}}
    if not isinstance(obj.get("volumes"), dict):
        obj["volumes"] = {}
    return obj


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--api-base", default=os.environ.get("DOGEN_CHAT_API_BASE", "http://127.0.0.1:8081"))
    p.add_argument("--bearer", default=os.environ.get("DOGEN_CHAT_BEARER", "Bearer fake"))
    p.add_argument("--model", default=os.environ.get("DOGEN_CHAT_MODEL", ""))
    p.add_argument("--max-chars", type=int, default=1200)
    p.add_argument("--retries", type=int, default=3)
    p.add_argument("--force", action="store_true")
    p.add_argument("--slugs", default="", help="comma separated slugs (e.g. bendowa,75-01)")
    p.add_argument("--output", default=str(OUT_PATH))
    args = p.parse_args()

    wanted = {s.strip() for s in args.slugs.split(",") if s.strip()}
    lines = gv.load_doc_lines()
    targets = build_targets()
    existing = load_existing(Path(args.output))
    vols: dict = existing.get("volumes", {})

    for slug, title, s1, s2 in targets:
        if wanted and slug not in wanted:
            continue
        if (not args.force) and isinstance(vols.get(slug), dict) and vols[slug].get("modern_html"):
            print(f"skip {slug} (cached)")
            continue
        paras = paragraphs_from_source(lines, s1, s2)
        chunks = split_chunks(paras, args.max_chars)
        print(f"translate {slug} ({len(chunks)} chunks)")
        out_chunks: list[str] = []
        for i, ch in enumerate(chunks, start=1):
            prompt = (
                "あなたは道元本人として、自分の原文を現代日本語に言い換える。"
                "意味を落とさず、読みやすくする。"
                "解説・前置き・補足・箇条書きは禁止。"
                "出力は言い換え本文のみ。\n\n"
                f"--- 原文({i}/{len(chunks)}) ---\n{ch}"
            )
            txt = call_chat(args.api_base, args.bearer, prompt, args.model or None, retries=args.retries).strip(
                "`"
            )
            out_chunks.append(txt)
            print(f"  done {i}/{len(chunks)}")
        merged = "\n\n".join(out_chunks)
        vols[slug] = {
            "title": title,
            "chunks": len(chunks),
            "modern_html": to_html_block(merged),
        }
        existing["volumes"] = vols
        existing["generated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        existing["api_base"] = args.api_base
        Path(args.output).write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  checkpoint saved: {slug}")

    existing["volumes"] = vols
    existing["generated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    existing["api_base"] = args.api_base
    Path(args.output).write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
