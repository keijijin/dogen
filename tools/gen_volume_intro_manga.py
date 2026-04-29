#!/usr/bin/env python3
"""各巻紹介用の4コマ漫画画像を OpenAI Images API (DALL-E 3) で生成する。

各巻の ``doc/正法眼蔵.txt`` から**冒頭の原文（長めの抜粋）**を取り、画像生成 API の
プロンプトに埋め込み、「添付の内容をわかりやすく4コマで」と同趣旨の依頼を日本語で
与える（Chat への添付と同様に、モデルはプロンプト内の原文を読んで構成する）。

出力: ``web/img/{slug}-manga-4panel.png``。その後 ``python3 tools/gen_web_volumes.py`` で
自動生成 ``index.html`` に ``intro_manga_block`` が差し込まれる。

前提:
  - 環境変数 ``OPENAI_API_KEY``（または ``deploy/local/.env``）。リポジトリに含めない。
  - 課金・レート制限あり。``--fail-fast`` で中止。

除外（手元イラスト等あり）::

    75-01, 75-02, 75-03, 75-04, 75-05, 75-20, 75-25, 75-46

権利: 抜粋は巻の冒頭に限定。公開・再配布は利用許諾と OpenAI ポリシーに従うこと。
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import gen_web_volumes as gv

ROOT = Path(__file__).resolve().parents[1]
IMG_DIR = ROOT / "web" / "img"

# ユーザー指定: 既に紹介用ビジュアルがある巻
SKIP_SLUGS: frozenset[str] = frozenset(
    {
        "75-01",
        "75-02",
        "75-03",
        "75-04",
        "75-05",
        "75-20",
        "75-25",
        "75-46",
    }
)

MANGA_SUFFIX = gv.MANGA_4PANEL_SUFFIX

# DALL-E 3 のプロンプト上限に合わせる（公式は約 4000 文字）
DALLE3_PROMPT_MAX = 3900


def try_load_local_openai_key() -> None:
    envp = ROOT / "deploy" / "local" / ".env"
    if not envp.is_file():
        return
    for raw in envp.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("OPENAI_API_KEY="):
            v = line.split("=", 1)[1].strip().strip('"').strip("'")
            if v and "OPENAI_API_KEY" not in os.environ:
                os.environ["OPENAI_API_KEY"] = v
            break


def volume_source_excerpt(lines: list[str], start_1b: int, next_1b: int, max_chars: int) -> str:
    """巻本文の冒頭を段落のまま連結し、max_chars まで取る（画像プロンプトに渡す原文）。"""
    paras = gv.extract_volume_paragraphs(lines, start_1b, next_1b)
    parts: list[str] = []
    total = 0
    for p in paras:
        block = "\n".join(s.strip() for s in p if s.strip())
        if not block:
            continue
        sep = 2 if parts else 0
        if total + sep + len(block) <= max_chars:
            parts.append(block)
            total += sep + len(block)
            continue
        remain = max_chars - total - sep - 1
        if remain >= 120:
            parts.append(block[:remain].rstrip() + "…")
        break
    return "\n\n".join(parts).strip()[:max_chars]


def _instruction_block(title: str, slug: str) -> str:
    return (
        "【依頼】次に示す『正法眼蔵』一巻の冒頭原文の内容を、学習者に伝わるよう、"
        "わかりやすく4コマ漫画で表現してください。\n"
        "・横長（ランドスケープ）の1枚の画像の中に、左から右へ4つのコマを**幅がほぼ等しい**縦長の区画として並べること。\n"
        "・白黒の日本の学習漫画または墨絵調。各コマで話・比喩が順に進むこと。\n"
        "・吹き出しや短いキャプションは**日本語**でよい（原文の長文を画像内に写し取らないこと。要約・解説レベルの短い文のみ）。\n"
        "・写実的な特定人物の肖像は避け、比喩・山水・道場の情景・象徴的な人物の後ろ姿などで表現すること。\n\n"
        f"【巻題】{title.strip()[:200]}\n"
        f"【識別子】{slug}\n\n"
        "【原文（冒頭・抜粋。これに基づいて構成すること）】\n"
    )


def build_image_prompt(slug: str, title: str, excerpt: str, max_total: int = DALLE3_PROMPT_MAX) -> str:
    """原文抜粋を含む日本語中心プロンプト（DALL-E 3 文字数上限内に収める）。"""
    head = _instruction_block(title, slug)
    body = excerpt.replace("\r", "").strip()
    room = max_total - len(head)
    if room < 400:
        body = body[: max(200, room)]
    else:
        body = body[:room]
    return (head + body)[:max_total]


def build_image_prompt_safe(slug: str, title: str) -> str:
    """安全フィルタで落ちたときの最終リトライ（原文なし・巻題も出さない英語短プロンプト）。"""
    # title は引数互換のため残すがプロンプトには含めない（フィルタ誤検知を避ける）
    _ = title
    return (
        "Single wide landscape image: exactly four equally wide vertical comic panels, left to right. "
        "Black and white, calm educational ink-wash or gentle manga. Motifs: mist, mountains, pine, river, "
        "small distant rooflines, meditation hall interior without identifiable people. "
        "Very short Japanese text in speech bubbles is OK; no long passages. No caricature. "
        f"Internal episode id (subtle only if needed): {slug}."
    )[:1200]


def openai_dalle3_png(prompt: str, api_key: str, quality: str) -> bytes:
    body = {
        "model": "dall-e-3",
        "prompt": prompt,
        "n": 1,
        "size": "1792x1024",
        "response_format": "b64_json",
        "quality": quality,
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        "https://api.openai.com/v1/images/generations",
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {err}") from e
    b64 = payload["data"][0].get("b64_json")
    if not b64:
        raise RuntimeError("missing b64_json in response")
    return base64.standard_b64decode(b64)


def openai_dalle3_png_retry(
    prompt: str, api_key: str, quality: str, transient_retries: int = 3
) -> bytes:
    """502/503 などの一時障害で数回まで再試行する。"""
    last: Exception | None = None
    for attempt in range(transient_retries):
        try:
            return openai_dalle3_png(prompt, api_key, quality)
        except RuntimeError as e:
            last = e
            msg = str(e)
            if ("HTTP 502" in msg or "HTTP 503" in msg) and attempt + 1 < transient_retries:
                wait = 8.0 + attempt * 6.0
                print(f"  transient API error, sleep {wait:.0f}s and retry ({attempt + 2}/{transient_retries}) …", flush=True)
                time.sleep(wait)
                continue
            raise
    assert last is not None
    raise last


def iter_volume_jobs(lines: list[str]) -> list[tuple[str, str, int, int]]:
    jobs: list[tuple[str, str, int, int]] = []
    for i, title in enumerate(gv.TITLES_75, start=1):
        slug = f"75-{i:02d}"
        if slug in SKIP_SLUGS:
            continue
        s1 = gv.BODY_75_STARTS_1BASED[i - 1]
        s2 = gv.BODY_75_STARTS_1BASED[i]
        jobs.append((slug, title, s1, s2))
    for i, title in enumerate(gv.TITLES_12, start=1):
        slug = f"12-{i:02d}"
        s1 = gv.BODY_12_STARTS_1BASED[i - 1]
        s2 = gv.BODY_12_STARTS_1BASED[i]
        jobs.append((slug, title, s1, s2))
    jobs.append(
        (
            "bendowa",
            "辨道話",
            gv.BENDOWA_BODY_START_1BASED,
            gv.BENDOWA_BODY_NEXT_1BASED,
        )
    )
    return jobs


def patch_bendowa_index() -> None:
    p = ROOT / "web" / "volumes" / "bendowa" / "index.html"
    img = ROOT / "web" / "img" / f"bendowa{MANGA_SUFFIX}"
    if not img.is_file():
        return
    text = p.read_text(encoding="utf-8")
    if "bendowa-manga-4panel.png" in text:
        return
    insert = """        <h2>図解（4コマ・AI生成）</h2>
        <p class="notice" style="font-size:0.88rem">教義の根拠は本文・出典に従い、漫画は比喩の補助に留めてください。</p>
        <div style="overflow-x:auto;margin:1rem 0">
          <img src="../../img/bendowa-manga-4panel.png" width="1792" height="1024" alt="辨道話: 冒頭をテーマにした4コマ（学習用・AI生成）" loading="lazy" style="width:min(100%,1792px);height:auto;display:block;margin:0 auto" />
        </div>

"""
    anchor = "</blockquote>\n\n        <h2>読み方のヒント</h2>"
    if anchor not in text:
        print("WARN: bendowa/index.html: insert anchor not found; skip bendowa HTML patch", file=sys.stderr)
        return
    p.write_text(text.replace(anchor, "</blockquote>\n\n" + insert + "        <h2>読み方のヒント</h2>", 1), encoding="utf-8")
    print("Patched web/volumes/bendowa/index.html for manga image.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate volume intro 4-panel manga via DALL-E 3.")
    parser.add_argument("--slug", help="Process only this slug (e.g. 75-06 or bendowa)")
    parser.add_argument("--max", type=int, default=0, help="Max volumes to generate (0 = no limit)")
    parser.add_argument("--force", action="store_true", help="Overwrite existing PNG")
    parser.add_argument("--dry-run", action="store_true", help="List targets only; no API calls")
    parser.add_argument("--fail-fast", action="store_true", help="Stop on first API error")
    parser.add_argument("--sleep", type=float, default=2.5, help="Seconds between API calls")
    parser.add_argument(
        "--max-chars",
        type=int,
        default=3000,
        metavar="N",
        help="原文抜粋の最大文字数（プロンプト全体は API 上限で自動トリム）",
    )
    parser.add_argument(
        "--quality",
        choices=("hd", "standard"),
        default="hd",
        help="DALL-E 3 quality (default: hd)",
    )
    args = parser.parse_args()

    try_load_local_openai_key()
    api_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    lines = gv.load_doc_lines()
    jobs = iter_volume_jobs(lines)
    if args.slug:
        want = args.slug.strip()
        jobs = [j for j in jobs if j[0] == want]
        if not jobs:
            print(f"No job for slug {want!r} (skipped or unknown).", file=sys.stderr)
            sys.exit(2)

    if args.dry_run:
        for slug, title, _, _ in jobs:
            print(f"would process {slug} — {title}", flush=True)
        print(f"total {len(jobs)}", flush=True)
        return

    if not api_key:
        print(
            "ERROR: OPENAI_API_KEY is not set. Export it or add to deploy/local/.env",
            file=sys.stderr,
        )
        sys.exit(1)

    done = 0
    for slug, title, s1, s2 in jobs:
        if args.max and done >= args.max:
            break
        out = IMG_DIR / f"{slug}{MANGA_SUFFIX}"
        if out.is_file() and not args.force:
            print(f"skip existing {out.name}", flush=True)
            continue
        excerpt = volume_source_excerpt(lines, s1, s2, args.max_chars)
        prompt = build_image_prompt(slug, title, excerpt)
        print(
            f"generating {slug} ({title}) … (prompt {len(prompt)} chars, quality={args.quality})",
            flush=True,
        )
        png: bytes | None = None
        try:
            png = openai_dalle3_png_retry(prompt, api_key, args.quality)
        except Exception as e:
            err_s = str(e)
            print(f"WARN {slug}: {e}", file=sys.stderr)
            if "content_policy" in err_s.lower() or "safety system" in err_s.lower():
                short_n = max(600, min(args.max_chars // 2, 1500))
                excerpt2 = volume_source_excerpt(lines, s1, s2, short_n)
                prompt2 = build_image_prompt(slug, title, excerpt2)
                print(f"  retry {slug} with shorter excerpt ({len(excerpt2)} chars) …", flush=True)
                try:
                    png = openai_dalle3_png_retry(prompt2, api_key, args.quality)
                except Exception as e2:
                    err2 = str(e2)
                    print(f"WARN {slug} (short excerpt): {e2}", file=sys.stderr)
                    if "content_policy" in err2.lower() or "safety system" in err2.lower():
                        print(f"  retry {slug} with abstract title-only prompt …", flush=True)
                        try:
                            png = openai_dalle3_png_retry(
                                build_image_prompt_safe(slug, title), api_key, args.quality
                            )
                        except Exception as e3:
                            print(f"ERROR {slug} (all retries failed): {e3}", file=sys.stderr)
                            if args.fail_fast:
                                sys.exit(1)
                            continue
                    else:
                        if args.fail_fast:
                            sys.exit(1)
                        continue
            else:
                if args.fail_fast:
                    sys.exit(1)
                continue
        if png is None:
            continue
        IMG_DIR.mkdir(parents=True, exist_ok=True)
        out.write_bytes(png)
        print(f"  wrote {out} ({len(png)} bytes)", flush=True)
        done += 1
        time.sleep(args.sleep + random.uniform(0, 0.8))

    patch_bendowa_index()


if __name__ == "__main__":
    main()
