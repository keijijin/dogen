#!/usr/bin/env python3
"""Generate web/volumes/index.html and volume pages for 七十五巻・十二巻.

手編集で上書きしないスラッグは HAND_SLUGS。それ以外は doc/正法眼蔵.txt から
各巻の紹介ページ（原文の要点抜粋・語彙・深掘り・クイズ付き）を再生成する。
"""
from __future__ import annotations

import html
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VOL = ROOT / "web" / "volumes"
DOC = ROOT / "doc" / "正法眼蔵.txt"
SOURCE_URL = "https://shomonji.or.jp/zazen/doc/genzou.html"
MODERN_CACHE_PATH = ROOT / "doc" / "modern_translations.json"

# `tools/gen_volume_intro_manga.py` が出力する AI 4コマ（ファイルが無ければ何も出さない）
MANGA_4PANEL_SUFFIX = "-manga-4panel.png"
# 巻ごとに別名 PNG を使う（手元イラスト等）。値は `web/img/` 直下のファイル名。
MANGA_IMAGE_OVERRIDES: dict[str, str] = {
    "bendowa": "辨道話.png",
    "75-06": "行佛威儀.png",
    "75-07": "一顆明珠.png",
    "75-08": "心不可得.png",
    "75-09": "古佛心.png",
    "75-10": "大悟.png",
    "12-01": "出家功徳.png",
    "12-02": "受戒.png",
    "12-03": "袈裟功徳.png",
    "12-04": "發菩提心.png",
}


def _png_pixel_size(path: Path) -> tuple[int, int] | None:
    """PNG の IHDR から幅・高さを読む（Pillow 不要）。"""
    try:
        data = path.read_bytes()[:32]
    except OSError:
        return None
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    if data[12:16] != b"IHDR":
        return None
    w = int.from_bytes(data[16:20], "big")
    h = int.from_bytes(data[20:24], "big")
    return (w, h) if w > 0 and h > 0 else None


def intro_manga_block(slug: str) -> str:
    """紹介ページ用: `web/img/{slug}-manga-4panel.png`（または MANGA_IMAGE_OVERRIDES）があれば図解ブロックを返す。"""
    fname = MANGA_IMAGE_OVERRIDES.get(slug) or f"{slug}{MANGA_4PANEL_SUFFIX}"
    path = ROOT / "web" / "img" / fname
    if not path.is_file():
        return ""
    dims = _png_pixel_size(path) or (1792, 1024)
    mw, mh = dims
    alt = html.escape(f"{slug}: 抜粋をテーマにした4コマ（学習用・AI生成）")
    return f"""        <h2>図解（4コマ・AI生成）</h2>
        <p class="notice" style="font-size:0.88rem">教義の根拠は原文・出典に従い、漫画は比喩の補助に留めてください。</p>
        <div style="overflow-x:auto;margin:1rem 0">
          <img src="../../img/{html.escape(fname)}" width="{mw}" height="{mh}" alt="{alt}" loading="lazy" style="width:min(100%,{mw}px);height:auto;display:block;margin:0 auto" />
        </div>
"""


# 手編集サンプル・優先整備済み（再生成で上書きしない）
HAND_SLUGS = frozenset(
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

# 七十五巻本文: 各巻見出し行（1-based 行番号）。末尾は十二巻直前の番兵。
BODY_75_STARTS_1BASED = [
    443,
    504,
    571,
    904,
    973,
    1038,
    1193,
    1274,
    1347,
    1420,
    1499,
    1532,
    1771,
    1844,
    1963,
    2080,
    2744,
    2847,
    2926,
    3167,
    3280,
    3431,
    3464,
    3525,
    3584,
    3753,
    3890,
    3985,
    4140,
    4255,
    4488,
    4581,
    4828,
    4893,
    5088,
    5217,
    5276,
    5423,
    5526,
    5683,
    5822,
    5913,
    6012,
    6171,
    6338,
    6413,
    6566,
    6655,
    6694,
    6747,
    6932,
    7029,
    7164,
    7315,
    7452,
    7529,
    7696,
    7779,
    7908,
    8023,
    8296,
    8379,
    8430,
    8509,
    8570,
    8607,
    8680,
    8715,
    8844,
    8981,
    9106,
    9141,
    9510,
    9643,
    9728,
    9798,
]

# 辨道話本文（1-based）。目次の「辨道話」は除き、本文見出し行から七十五巻直前の重複見出しまで。
BENDOWA_BODY_START_1BASED = 185
BENDOWA_BODY_NEXT_1BASED = 438

# 十二巻本文見出し（1-based）＋ EOF 番兵
BODY_12_STARTS_1BASED = [
    9798,
    10103,
    10234,
    10695,
    10826,
    11237,
    11488,
    11623,
    11822,
    11887,
    12108,
    12355,
    12418,
]

TITLES_75 = [
    "現成公案",
    "摩訶般若波羅蜜",
    "佛性",
    "身心學道",
    "卽心是佛",
    "行佛威儀",
    "一顆明珠",
    "心不可得",
    "古佛心",
    "大悟",
    "坐禪儀",
    "坐禪箴",
    "海印三昧",
    "空華",
    "光明",
    "行持（上・下）",
    "恁麼",
    "觀音",
    "古鏡",
    "有時",
    "授記",
    "全機",
    "都機",
    "畫餅",
    "谿聲山色",
    "佛向上事",
    "夢中説夢",
    "禮拜得髓",
    "山水經",
    "看經",
    "諸惡莫作",
    "傳衣",
    "道得",
    "佛教",
    "神通",
    "阿羅漢",
    "春秋",
    "葛藤",
    "嗣書",
    "栢樹子",
    "三界唯心",
    "説心説性",
    "諸法實相",
    "佛道",
    "密語",
    "無情説法",
    "佛經",
    "法性",
    "陀羅尼",
    "洗面",
    "面授",
    "佛祖",
    "梅花",
    "洗淨",
    "十方",
    "見佛",
    "遍參",
    "眼睛",
    "家常",
    "三十七品菩提分法",
    "龍吟",
    "祖師西來意",
    "發菩提心",
    "優曇華",
    "如來全身",
    "三昧王三昧",
    "轉法輪",
    "大修行",
    "自證三昧",
    "虛空",
    "鉢盂",
    "安居",
    "他心通",
    "王索仙陀婆",
    "出家",
]

TITLES_12 = [
    "出家功徳",
    "受戒",
    "袈裟功徳",
    "發菩提心",
    "供養諸佛",
    "歸依佛法僧寶",
    "深信因果",
    "三時業",
    "四馬",
    "四禪比丘",
    "一百八法明門",
    "八大人覺",
]


def load_doc_lines() -> list[str]:
    if not DOC.is_file():
        raise FileNotFoundError(f"Corpus not found: {DOC}")
    text = DOC.read_text(encoding="utf-8")
    return text.splitlines()


# 紹介ページに載せる原文は短い抜粋に留める（全文は full.html）
INTRO_EXCERPT_MAX_LINES = 12


def excerpt_paragraphs(lines: list[str], start_1b: int, next_start_1b: int, max_lines: int | None = None) -> str:
    """start_1b 行から次見出しの直前まで。空行は詰め、先頭の巻見出し行は除く。紹介ページ用に行数上限あり。"""
    lim = INTRO_EXCERPT_MAX_LINES if max_lines is None else max_lines
    a = start_1b - 1
    b = next_start_1b - 1
    chunk = lines[a:b]
    out: list[str] = []
    for raw in chunk:
        s = raw.strip()
        if not s:
            continue
        if s.startswith("正法眼藏第") and "　" in s and len(s) < 40:
            continue
        out.append(html.escape(s))
        if len(out) >= lim:
            break
    if not out:
        return "<p>（この巻の原文を自動抽出できませんでした。<code>doc/正法眼蔵.txt</code> を直接参照してください。）</p>"
    inner = "</p>\n          <p>".join(out)
    return f"        <blockquote>\n          <p>{inner}</p>\n        </blockquote>"


def extract_volume_paragraphs(lines: list[str], start_1b: int, next_start_1b: int) -> list[list[str]]:
    """該当巻の本文を段落ごとに抽出（空行区切り、巻見出し除外）。"""
    a = start_1b - 1
    b = next_start_1b - 1
    chunk = lines[a:b]
    paras: list[list[str]] = []
    cur: list[str] = []
    for raw in chunk:
        s = raw.strip()
        if not s:
            if cur:
                paras.append(cur)
                cur = []
            continue
        if s.startswith("正法眼藏第") and "　" in s and len(s) < 40:
            # 巻見出し行は除外
            continue
        cur.append(s)
    if cur:
        paras.append(cur)
    return paras


def fulltext_html_block(lines: list[str], start_1b: int, next_start_1b: int) -> str:
    """該当巻の本文全体を HTML にする（空行で段落区切り）。"""
    paras = extract_volume_paragraphs(lines, start_1b, next_start_1b)
    if not paras:
        return "<p>（本文を抽出できませんでした。<code>doc/正法眼蔵.txt</code> を参照してください。）</p>"
    ps = []
    for p in paras:
        escaped = [html.escape(s) for s in p]
        ps.append("<p>" + "<br />".join(escaped) + "</p>")
    return "\n        ".join(ps)


def modernize_japanese_line(src: str) -> str:
    """事前生成向けの平易化（静的表示用）。"""
    out = src
    replacements = [
        ("諸佛", "諸仏"),
        ("佛法", "仏法"),
        ("佛道", "仏道"),
        ("佛性", "仏性"),
        ("佛身", "仏身"),
        ("佛事", "仏事"),
        ("佛國土", "仏国土"),
        ("證", "証"),
        ("參", "参"),
        ("禪", "禅"),
        ("學", "学"),
        ("觀", "観"),
        ("眞", "真"),
        ("實", "実"),
        ("廣", "広"),
        ("爲", "為"),
        ("祖", "祖"),
        ("觸", "触"),
        ("處", "処"),
        ("すなはち", "すなわち"),
        ("いはく", "いわく"),
        ("いふ", "いう"),
        ("いへども", "とはいえ"),
        ("ことば", "言葉"),
        ("こころ", "心"),
        ("なんぢ", "あなた"),
        ("われ", "わたし"),
        ("ゐ", "い"),
    ]
    for old, new in replacements:
        out = out.replace(old, new)
    return out


def modern_fulltext_html_block(lines: list[str], start_1b: int, next_start_1b: int) -> str:
    paras = extract_volume_paragraphs(lines, start_1b, next_start_1b)
    if not paras:
        return "<p>（現代語訳を抽出できませんでした。）</p>"
    ps = []
    for p in paras:
        rendered = [modernize_japanese_line(s) for s in p]
        escaped = [html.escape(s) for s in rendered]
        ps.append("<p>" + "<br />".join(escaped) + "</p>")
    return "\n        ".join(ps)


def load_modern_cache() -> dict[str, str]:
    if not MODERN_CACHE_PATH.is_file():
        return {}
    try:
        raw = json.loads(MODERN_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    vols = raw.get("volumes", {}) if isinstance(raw, dict) else {}
    out: dict[str, str] = {}
    for slug, payload in vols.items():
        if isinstance(payload, dict):
            html_block = payload.get("modern_html")
            if isinstance(html_block, str) and html_block.strip():
                out[str(slug)] = html_block
        elif isinstance(payload, str) and payload.strip():
            out[str(slug)] = payload
    return out


def modern_fulltext_html_block_for_slug(
    slug: str, lines: list[str], start_1b: int, next_start_1b: int, modern_cache: dict[str, str]
) -> str:
    cached = modern_cache.get(slug)
    if cached and cached.strip():
        return cached
    return modern_fulltext_html_block(lines, start_1b, next_start_1b)


def nav_link_prev_next(kind: str, n: int) -> str:
    """相対パス prev, next の HTML 断片。"""
    if kind == "75":
        prev_h = "../bendowa/index.html" if n == 1 else f"../75-{n - 1:02d}/index.html"
        if n >= len(TITLES_75):
            next_h = "../12-01/index.html"
        else:
            next_h = f"../75-{n + 1:02d}/index.html"
    else:
        prev_h = "../75-75/index.html" if n == 1 else f"../12-{n - 1:02d}/index.html"
        if n >= len(TITLES_12):
            next_h = "../../index.html#12"
        else:
            next_h = f"../12-{n + 1:02d}/index.html"
    parts = []
    if prev_h:
        lab = "辨道話" if kind == "75" and n == 1 else f"← 第{n - 1}巻"
        parts.append(f'<a href="{prev_h}">{lab}</a>')
    if next_h:
        if kind == "12" and n == len(TITLES_12):
            parts.append(f'<a href="{next_h}">巻一覧 →</a>')
        else:
            parts.append(f'<a href="{next_h}">第{n + 1}巻 →</a>')
    parts.append('<a href="../index.html">巻一覧</a>')
    parts.append('<a href="../../index.html">ホーム</a>')
    return " · ".join(parts)


def rich_volume_html(
    kind: str,
    num: int,
    title: str,
    excerpt_block: str,
    prev_next: str,
    fulltext_link: str | None = None,
) -> str:
    label = "七十五巻" if kind == "75" else "十二巻"
    anchor = "#75" if kind == "75" else "#12"
    slug = f"{kind}-{num:02d}"
    esc_title = html.escape(title)
    meta = html.escape(
        f"正法眼蔵第{num}　{title}。紹介ページ（語彙・原文の要点抜粋・クイズ・自動生成）。"
    )
    return f"""<!DOCTYPE html>
<html lang="ja">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>第{num}　{esc_title} — 正法眼蔵読解</title>
    <meta name="description" content="{meta}" />
    {head_favicon_links("../../")}
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
          本ページは各巻の<strong>紹介ページ</strong>です。<code>tools/gen_web_volumes.py</code> が <code>doc/正法眼蔵.txt</code> から<strong>要点の短い抜粋</strong>を載せています（全文の引用ではありません）。
          出典（原文）: <a href="{SOURCE_URL}">{SOURCE_URL}</a>
        </p>
        {f'<p class=\"notice\"><strong>原文・現代語訳の全文</strong>は <a href=\"full.html\">全文ページ</a>を参照してください。</p>' if fulltext_link else ''}

        <h2>この巻の紹介（概要）</h2>
        <p>
          道元『正法眼蔵』{label}の第{num}篇「{esc_title}」です。禅籍・経典への引用や語の行間が重なりやすいので、<strong>一度ですべてを要約に還元しない</strong>読み方を推奨します。問答
          Bot では巻スコープにこの題名を含めると応答が安定しやすいことがあります。
        </p>

        <h2>語彙の足場</h2>
        <ul>
          <li><strong>題名語</strong>：巻題「{esc_title}」は、道元が本章で特に扱う論点の看板です。辞書義だけに固定せず、原文中の<strong>用例</strong>で意味を確かめます。</li>
          <li><strong>引用と典故</strong>：公案・経文の引用は、一字一句の<strong>照応</strong>（何に答えているか）を押さえると全体が見えやすくなります。</li>
          <li><strong>学び方</strong>：抜粋だけでも<strong>音読</strong>し、分からない箇所は印を付けて後から問うとよいです。</li>
        </ul>

        <h2>原文（要点の抜粋）</h2>
        <p class="notice">
          当巻の<strong>冒頭付近からの短い抜粋</strong>です。長い引用は載せていません。全文は<strong>全文ページ</strong>を参照してください。出典はリポジトリ内 <code>doc/正法眼蔵.txt</code> です。原文の参照元: <a href="{SOURCE_URL}">{SOURCE_URL}</a>
        </p>
        {excerpt_block}
{intro_manga_block(slug)}

        <h2>深掘り（読解のコツ）</h2>
        <ul>
          <li>道元文は<strong>定義の羅列</strong>に見えても、多くの場合<strong>誤解への遮断</strong>と<strong>正伝の姿勢</strong>が背骨になっています。</li>
          <li>「当体」「現成」「即」などの語が出たら、その巻独自の<strong>差別相</strong>にどう接続しているかをメモしておくとよいです。</li>
        </ul>

        <h2>確認（形成評価）</h2>
        <fieldset class="quiz" data-correct-index="0">
          <legend>1. 道元の文章を学ぶ姿勢として、まず避けたいのはどれか。</legend>
          <label><input type="radio" name="{slug}-q1" value="0" /> 原文を読まずに要約だけで満足する</label>
          <label><input type="radio" name="{slug}-q1" value="1" /> 語の行間と引用の照応を丁寧に追う</label>
          <label><input type="radio" name="{slug}-q1" value="2" /> 分からない箇所に印を付けて後で問う</label>
        </fieldset>
        <fieldset class="quiz" data-correct-index="0">
          <legend>2. 出典として最優先すべきなのはどれか。</legend>
          <label><input type="radio" name="{slug}-q2" value="0" /> 権利処理済みの訳文テキスト（本サイトの正本）と自分の批評</label>
          <label><input type="radio" name="{slug}-q2" value="1" /> 検索上位の無名要約のみ</label>
          <label><input type="radio" name="{slug}-q2" value="2" /> 推測で穴埋めする読み</label>
        </fieldset>

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


def head_favicon_links(web_root_rel: str) -> str:
    """各 HTML から web ルートへの相対パス（例: ../ または ../../）。"""
    return (
        f'    <link rel="icon" type="image/png" sizes="32x32" href="{web_root_rel}img/app-icon-dogen-32.png" />\n'
        f'    <link rel="icon" href="{web_root_rel}favicon.ico" sizes="any" />\n'
        f'    <link rel="apple-touch-icon" href="{web_root_rel}apple-touch-icon.png" />'
    )


def learning_focus_line(title: str) -> str:
    t = title
    tags: list[str] = []
    if t in ("辨道話", "出家", "出家功徳", "行持（上・下）"):
        tags.append("経験の記録")
    if any(k in t for k in ("佛性", "般若", "法", "諸法", "法性", "全機", "都機", "三昧", "道")):
        tags.append("真理の伝達")
    if any(k in t for k in ("坐禪", "安居", "行佛", "行持", "看經", "出家")):
        tags.append("坐禅実践")
    if any(k in t for k in ("現成公案", "有時", "家常", "夢中説夢", "發菩提心", "受戒")):
        tags.append("参加型理解")
    if any(k in t for k in ("山水", "谿聲山色", "無情説法", "梅花", "龍吟", "十方", "虛空")):
        tags.append("一体性の理解")
    if not tags:
        tags = ["真理の伝達", "参加型理解"]
    uniq = []
    for x in tags:
        if x not in uniq:
            uniq.append(x)
    picked = uniq[:2]
    joined = "・".join(picked)
    return f"主軸: {joined}。巻題「{html.escape(t)}」の論点を、該当観点で重点的に読む。"


def learning_map_html() -> str:
    rows = []
    rows.append(
        '<tr><th>序</th><td><a href="bendowa/index.html">辨道話</a></td><td>求法の出発点をつかむ。坐禅の位置づけを先に理解する。</td></tr>'
    )
    for i, title in enumerate(TITLES_75, start=1):
        slug = f"75-{i:02d}"
        rows.append(
            f'<tr><th>{i}</th><td><a href="{slug}/index.html">第{i}巻 {html.escape(title)}</a></td><td>{learning_focus_line(title)}</td></tr>'
        )
    for i, title in enumerate(TITLES_12, start=1):
        slug = f"12-{i:02d}"
        rows.append(
            f'<tr><th>{i}</th><td><a href="{slug}/index.html">十二巻 第{i}巻 {html.escape(title)}</a></td><td>{learning_focus_line(title)}</td></tr>'
        )
    return f"""<!DOCTYPE html>
<html lang="ja">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>学習総覧（5観点）— 正法眼蔵読解</title>
    {head_favicon_links("../")}
    <link rel="stylesheet" href="../css/main.css" />
  </head>
  <body>
    <header class="site-header">
      <div class="site-header__inner">
        <a class="site-logo" href="../index.html">正法眼蔵読解</a>
        <button type="button" class="nav-toggle" aria-expanded="false" aria-controls="site-nav">メニュー</button>
        <nav id="site-nav" class="site-nav" aria-label="主要ナビゲーション">
          <a href="../guide/index.html">学習ガイド</a>
          <a href="index.html">巻一覧</a>
          <a href="../themes/index.html">テーマ</a>
          <a href="../glossary/index.html">用語</a>
          <a href="../chat/index.html">問答 Bot</a>
          <a href="../site/index.html">サイト情報</a>
        </nav>
      </div>
    </header>
    <main>
      <article class="prose">
        <h1>学習総覧（5観点）</h1>
        <p class="notice">
          各巻を「経験の記録」「真理の伝達」「坐禅実践」「参加型理解」「一体性の理解」の5観点で読むための一覧です。
          原文の参照元: <a href="{SOURCE_URL}">{SOURCE_URL}</a>
        </p>
        <h2>5観点の使い方</h2>
        <ol>
          <li><strong>経験の記録</strong>：道元が何を体験として語っているかを拾う。</li>
          <li><strong>真理の伝達</strong>：誰に何を伝えようとしているかを確認する。</li>
          <li><strong>坐禅実践</strong>：実践がどの文脈で強調されるかを追う。</li>
          <li><strong>参加型理解</strong>：自分の生活に引き寄せて問いを立てる。</li>
          <li><strong>一体性の理解</strong>：自己・他者・自然の関係をどう語るかを見る。</li>
        </ol>
        <h2>各巻の学習導線</h2>
        <table class="toc-table" aria-label="各巻の学習導線">
          <tbody>
            {"".join(rows)}
          </tbody>
        </table>
        <p><a href="index.html">巻一覧へ戻る</a> · <a href="../index.html">ホームへ</a></p>
      </article>
    </main>
    <footer class="site-footer">
      <p><a href="../index.html">ホーム</a> · 正法眼蔵読解</p>
    </footer>
    <script src="../js/nav.js" defer></script>
  </body>
</html>"""


def fulltext_page_html(
    page_title: str,
    heading: str,
    back_link: str,
    index_link: str,
    home_link: str,
    original_html: str,
    modern_html: str,
    script_prefix: str,
) -> str:
    return f"""<!DOCTYPE html>
<html lang="ja">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{html.escape(page_title)}</title>
    {head_favicon_links(script_prefix)}
    <link rel="stylesheet" href="{script_prefix}css/main.css" />
  </head>
  <body>
    <header class="site-header">
      <div class="site-header__inner">
        <a class="site-logo" href="{home_link}">正法眼蔵読解</a>
        <button type="button" class="nav-toggle" aria-expanded="false" aria-controls="site-nav">メニュー</button>
        <nav id="site-nav" class="site-nav" aria-label="主要ナビゲーション">
          <a href="{script_prefix}guide/index.html">学習ガイド</a>
          <a href="{index_link}">巻一覧</a>
          <a href="{script_prefix}themes/index.html">テーマ</a>
          <a href="{script_prefix}glossary/index.html">用語</a>
          <a href="{script_prefix}chat/index.html">問答 Bot</a>
          <a href="{script_prefix}site/index.html">サイト情報</a>
        </nav>
      </div>
    </header>
    <main>
      <article class="prose">
        <p class="notice">
          <strong>注意</strong>：全文表示は権利条件に依存します。公開サイトに載せる範囲は利用許諾に従ってください。
          出典: <code>doc/正法眼蔵.txt</code>。原文の参照元: <a href="{SOURCE_URL}">{SOURCE_URL}</a>
        </p>
        <h1>{html.escape(heading)}</h1>
        <p><a href="{back_link}">紹介ページへ戻る</a> · <a href="{index_link}">巻一覧</a> · <a href="{home_link}">ホーム</a></p>
        <div class="reading-toggle" data-reading-toggle>
          <button type="button" class="reading-toggle__btn is-active" data-reading-tab="original" aria-selected="true">原文</button>
          <button type="button" class="reading-toggle__btn" data-reading-tab="modern" aria-selected="false">現代語訳</button>
        </div>
        <section data-reading-panel="original">
        {original_html}
        </section>
        <section data-reading-panel="modern" hidden>
          <p class="notice">
            現代語訳は事前に生成した読解補助版です（閲覧時に通信しません）。
          </p>
        {modern_html}
        </section>
      </article>
    </main>
    <footer class="site-footer">
      <p><a href="{home_link}">ホーム</a> · 正法眼蔵読解</p>
    </footer>
    <script src="{script_prefix}js/nav.js" defer></script>
    <script src="{script_prefix}js/volume-reading.js" defer></script>
  </body>
</html>
"""


def index_html() -> str:
    rows75 = []
    for i, title in enumerate(TITLES_75, start=1):
        slug = f"75-{i:02d}"
        rows75.append(
            f'<tr><th>{i}</th><td><a href="{slug}/index.html">正法眼藏第{i}　{title}</a></td></tr>'
        )
    rows12 = []
    for i, title in enumerate(TITLES_12, start=1):
        slug = f"12-{i:02d}"
        rows12.append(
            f'<tr><th>{i}</th><td><a href="{slug}/index.html">正法眼藏第{i}　{title}</a></td></tr>'
        )
    return f"""<!DOCTYPE html>
<html lang="ja">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>巻一覧 — 正法眼蔵読解</title>
    {head_favicon_links("../")}
    <link rel="stylesheet" href="../css/main.css" />
  </head>
  <body>
    <header class="site-header">
      <div class="site-header__inner">
        <a class="site-logo" href="../index.html">正法眼蔵読解</a>
        <button type="button" class="nav-toggle" aria-expanded="false" aria-controls="site-nav">メニュー</button>
        <nav id="site-nav" class="site-nav" aria-label="主要ナビゲーション">
          <a href="../guide/index.html">学習ガイド</a>
          <a href="index.html">巻一覧</a>
          <a href="../themes/index.html">テーマ</a>
          <a href="../glossary/index.html">用語</a>
          <a href="../chat/index.html">問答 Bot</a>
          <a href="../site/index.html">サイト情報</a>
        </nav>
      </div>
    </header>
    <main>
      <article class="prose">
        <h1>巻一覧</h1>
        <p>七十五巻・十二巻・辨道話への導線です。多くの巻は<strong>紹介ページ</strong>として <code>doc/正法眼蔵.txt</code> から<strong>要点の短い抜粋</strong>を載せています（全文は各巻の全文ページ）。原文の参照元: <a href="{SOURCE_URL}">{SOURCE_URL}</a></p>
        <p class="notice">教育効率の高い学習導線: <a href="learning-map.html">学習総覧（5観点）</a></p>
        <h2 id="bendowa">辨道話</h2>
        <p><a href="bendowa/index.html">辨道話</a>（坐禅辨道の大意）</p>
        <h2 id="75">七十五巻正法眼藏</h2>
        <table class="toc-table" aria-label="七十五巻一覧">
          <tbody>
            {"".join(rows75)}
          </tbody>
        </table>
        <h2 id="12">十二巻正法眼藏</h2>
        <table class="toc-table" aria-label="十二巻一覧">
          <tbody>
            {"".join(rows12)}
          </tbody>
        </table>
        <p><a href="../index.html">ホームへ</a></p>
      </article>
    </main>
    <footer class="site-footer">
      <p><a href="../index.html">ホーム</a> · 正法眼蔵読解</p>
    </footer>
    <script src="../js/nav.js" defer></script>
  </body>
</html>"""


def main() -> None:
    lines = load_doc_lines()
    # 既定で全文ページを生成し、紹介 index に「（ローカル生成の全文: …）」を出す。無効化は DOGEN_GENERATE_FULLTEXT=0
    generate_full = os.environ.get("DOGEN_GENERATE_FULLTEXT", "1").strip() != "0"
    modern_cache = load_modern_cache()
    if len(BODY_75_STARTS_1BASED) != len(TITLES_75) + 1:
        raise SystemExit("BODY_75_STARTS_1BASED must have len(TITLES_75)+1 sentinel")

    VOL.mkdir(parents=True, exist_ok=True)
    (VOL / "index.html").write_text(index_html(), encoding="utf-8")
    (VOL / "learning-map.html").write_text(learning_map_html(), encoding="utf-8")

    n_written = 0
    for i, title in enumerate(TITLES_75, start=1):
        slug = f"75-{i:02d}"
        d = VOL / slug
        d.mkdir(parents=True, exist_ok=True)
        s1 = BODY_75_STARTS_1BASED[i - 1]
        s2 = BODY_75_STARTS_1BASED[i]
        if slug not in HAND_SLUGS:
            excerpt = excerpt_paragraphs(lines, s1, s2)
            pn = nav_link_prev_next("75", i)
            page = rich_volume_html(
                "75",
                i,
                title,
                excerpt,
                pn,
                fulltext_link="full.html" if generate_full else None,
            )
            (d / "index.html").write_text(page, encoding="utf-8")
        if generate_full:
            full = fulltext_html_block(lines, s1, s2)
            modern = modern_fulltext_html_block_for_slug(slug, lines, s1, s2, modern_cache)
            (d / "full.html").write_text(
                fulltext_page_html(
                    page_title=f"第{i}　{title}（全文）— 正法眼蔵読解",
                    heading=f"正法眼藏第{i}　{title}（全文）",
                    back_link="index.html",
                    index_link="../index.html",
                    home_link="../../index.html",
                    original_html=full,
                    modern_html=modern,
                    script_prefix="../../",
                ),
                encoding="utf-8",
            )
        n_written += 1

    if len(BODY_12_STARTS_1BASED) != len(TITLES_12) + 1:
        raise SystemExit("BODY_12_STARTS_1BASED must have len(TITLES_12)+1 sentinel")

    for i, title in enumerate(TITLES_12, start=1):
        slug = f"12-{i:02d}"
        d = VOL / slug
        d.mkdir(parents=True, exist_ok=True)
        s1 = BODY_12_STARTS_1BASED[i - 1]
        s2 = BODY_12_STARTS_1BASED[i]
        excerpt = excerpt_paragraphs(lines, s1, s2)
        pn = nav_link_prev_next("12", i)
        page = rich_volume_html("12", i, title, excerpt, pn, fulltext_link="full.html" if generate_full else None)
        (d / "index.html").write_text(page, encoding="utf-8")
        if generate_full:
            full = fulltext_html_block(lines, s1, s2)
            modern = modern_fulltext_html_block_for_slug(slug, lines, s1, s2, modern_cache)
            (d / "full.html").write_text(
                fulltext_page_html(
                    page_title=f"第{i}　{title}（全文）— 正法眼蔵読解",
                    heading=f"正法眼藏第{i}　{title}（全文）",
                    back_link="index.html",
                    index_link="../index.html",
                    home_link="../../index.html",
                    original_html=full,
                    modern_html=modern,
                    script_prefix="../../",
                ),
                encoding="utf-8",
            )
        n_written += 1

    # 辨道話（手編集 index は別ファイル。全文 HTML はコーパスと同期するため毎回生成）
    bendowa_dir = VOL / "bendowa"
    bendowa_dir.mkdir(parents=True, exist_ok=True)
    full_bw = fulltext_html_block(lines, BENDOWA_BODY_START_1BASED, BENDOWA_BODY_NEXT_1BASED)
    modern_bw = modern_fulltext_html_block_for_slug(
        "bendowa", lines, BENDOWA_BODY_START_1BASED, BENDOWA_BODY_NEXT_1BASED, modern_cache
    )
    (bendowa_dir / "full.html").write_text(
        fulltext_page_html(
            page_title="辨道話（全文）— 正法眼蔵読解",
            heading="辨道話（全文）",
            back_link="index.html",
            index_link="../index.html",
            home_link="../../index.html",
            original_html=full_bw,
            modern_html=modern_bw,
            script_prefix="../../",
        ),
        encoding="utf-8",
    )

    print(
        "Wrote",
        VOL / "index.html",
        "and",
        n_written,
        "volume pages (hand-tuned slugs skipped:",
        ", ".join(sorted(HAND_SLUGS)),
        "); bendowa/full.html",
    )


if __name__ == "__main__":
    main()
