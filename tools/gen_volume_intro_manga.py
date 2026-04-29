#!/usr/bin/env python3
"""各巻紹介用の「冒頭イメージ」4コマ画像を OpenAI Images API (DALL-E 3) で生成する。

出力: ``web/img/{slug}-manga-4panel.png``（例: ``75-06-manga-4panel.png``）。その後
``python3 tools/gen_web_volumes.py`` を実行すると、自動生成の ``index.html`` に
``gen_web_volumes.intro_manga_block`` 経由で埋め込まれる。

前提:
  - 環境変数 ``OPENAI_API_KEY``（または ``deploy/local/.env`` に同項。値はリポジトリに含めない）
  - 画像生成は課金・レート制限がある。失敗した巻はログに残して続行する（``--fail-fast`` で中止）

除外: 既に手元イラスト等がある巻（以下のスラッグはスキップ）::

    75-01, 75-02, 75-03, 75-04, 75-05, 75-20, 75-25, 75-46

権利: プロンプトに載せる原文抜粋は短く抑える。公開・再配布は利用許諾と OpenAI ポリシーに従うこと。
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


def plain_snippet(lines: list[str], start_1b: int, next_1b: int, max_chars: int = 320) -> str:
    paras = gv.extract_volume_paragraphs(lines, start_1b, next_1b)
    parts: list[str] = []
    for p in paras[:4]:
        parts.append(" ".join(p))
    t = " ".join(parts).replace("\n", " ").strip()
    return t[:max_chars]


def build_image_prompt(slug: str, title: str, snippet: str) -> str:
    # 長い漢文の丸写しは避け、短い抜粋＋巻題でテーマ化（モデレーションと権利配慮）
    sn = snippet.replace("\r", "")
    title_e = title[:120]
    return (
        "A single wide image divided into four equal horizontal comic panels, "
        "black and white Japanese ink (sumi-e) illustration, educational tone, "
        "no legible Japanese or Chinese characters inside the artwork "
        "(use abstract shapes, landscapes, zazen silhouettes, mountains, rivers, "
        "temple motifs only). "
        f"Topic: introductory themes for a Zen text fascicle titled 「{title_e}」 "
        f"(Dōgen, Shōbogenzo series, slug {slug}). "
        "Metaphorical motifs only (do not depict readable scripture): "
        f"{sn[:280]}"
    )[:3900]


def build_image_prompt_safe(slug: str, title: str) -> str:
    """安全フィルタで落ちたときの再試行用（本文抜粋なし・抽象のみ）。"""
    return (
        "A single wide image divided into four equal horizontal comic panels, "
        "black and white Japanese ink illustration, calm educational tone, "
        "no readable text in the image. Abstract Zen motifs: mountains, mist, "
        "empty zafu, subtle temple rooflines, river, pine. "
        f"Series chapter code {slug}. Do not depict identifiable persons. "
        "No religious caricature."
    )[:2000]


def openai_dalle3_png(prompt: str, api_key: str) -> bytes:
    body = {
        "model": "dall-e-3",
        "prompt": prompt,
        "n": 1,
        "size": "1792x1024",
        "response_format": "b64_json",
        "quality": "standard",
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
            print(f"would process {slug} — {title}")
        print(f"total {len(jobs)}")
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
            print(f"skip existing {out.name}")
            continue
        snippet = plain_snippet(lines, s1, s2)
        prompt = build_image_prompt(slug, title, snippet)
        print(f"generating {slug} ({title}) …")
        try:
            png = openai_dalle3_png(prompt, api_key)
        except Exception as e:
            err_s = str(e)
            print(f"WARN {slug}: {e}", file=sys.stderr)
            if "content_policy" in err_s.lower() or "safety system" in err_s.lower():
                print(f"  retry {slug} with abstract title-only prompt …")
                try:
                    png = openai_dalle3_png(build_image_prompt_safe(slug, title), api_key)
                except Exception as e2:
                    print(f"ERROR {slug} (retry failed): {e2}", file=sys.stderr)
                    if args.fail_fast:
                        sys.exit(1)
                    continue
            else:
                if args.fail_fast:
                    sys.exit(1)
                continue
        IMG_DIR.mkdir(parents=True, exist_ok=True)
        out.write_bytes(png)
        print(f"  wrote {out} ({len(png)} bytes)")
        done += 1
        time.sleep(args.sleep + random.uniform(0, 0.8))

    patch_bendowa_index()


if __name__ == "__main__":
    main()
