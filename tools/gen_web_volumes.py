#!/usr/bin/env python3
"""Generate web/volumes/index.html and volume pages for 七十五巻・十二巻.

手編集で上書きしないスラッグは HAND_SLUGS。それ以外は doc/正法眼蔵.txt から
冒頭を抜粋した読解ページ（語彙・深掘り・クイズ付き）を再生成する。
"""
from __future__ import annotations

import html
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VOL = ROOT / "web" / "volumes"
DOC = ROOT / "doc" / "正法眼蔵.txt"
SOURCE_URL = "https://shomonji.or.jp/zazen/doc/genzou.html"

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


def excerpt_paragraphs(lines: list[str], start_1b: int, next_start_1b: int, max_lines: int = 72) -> str:
    """start_1b 行から次見出しの直前まで。空行は詰め、先頭の巻見出し行は本文に含めない。"""
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
        if len(out) >= max_lines:
            break
    if not out:
        return "<p>（この巻の冒頭を自動抽出できませんでした。<code>doc/正法眼蔵.txt</code> を直接参照してください。）</p>"
    inner = "</p>\n          <p>".join(out)
    return f"<blockquote>\n          <p>{inner}</p>\n        </blockquote>"


def fulltext_html_block(lines: list[str], start_1b: int, next_start_1b: int) -> str:
    """該当巻の本文全体を HTML にする（空行で段落区切り）。"""
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
        cur.append(html.escape(s))
    if cur:
        paras.append(cur)
    if not paras:
        return "<p>（本文を抽出できませんでした。<code>doc/正法眼蔵.txt</code> を参照してください。）</p>"
    ps = []
    for p in paras:
        ps.append("<p>" + "<br />".join(p) + "</p>")
    return "\n        ".join(ps)


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
    meta = html.escape(f"正法眼蔵第{num}　{title}。語彙・本文冒頭・クイズ（自動生成ページ）。")
    return f"""<!DOCTYPE html>
<html lang="ja">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>第{num}　{esc_title} — 正法眼蔵読解</title>
    <meta name="description" content="{meta}" />
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
          本ページは <code>tools/gen_web_volumes.py</code> が <code>doc/正法眼蔵.txt</code> から冒頭を抜粋して生成しています。図・詳細解説は今後の手編集で拡張できます。
          出典（原文）: <a href="{SOURCE_URL}">{SOURCE_URL}</a>
        </p>
        {f'<p class=\"notice\">（ローカル生成の全文: <a href=\"full.html\">全文ページ</a>）</p>' if fulltext_link else ''}

        <h2>この巻の位置づけ（学習メモ）</h2>
        <p>
          道元『正法眼蔵』{label}の第{num}篇「{esc_title}」です。禅籍・経典への引用や語の行間が重なりやすいので、<strong>一度ですべてを要約に還元しない</strong>読み方を推奨します。問答
          Bot では巻スコープにこの題名を含めると応答が安定しやすいことがあります。
        </p>

        <h2>語彙の足場</h2>
        <ul>
          <li><strong>題名語</strong>：巻題「{esc_title}」は、道元が本章で特に扱う論点の看板です。辞書義だけに固定せず、本文中の<strong>用例</strong>で意味を確かめます。</li>
          <li><strong>引用と典故</strong>：公案・経文の引用は、一字一句の<strong>照応</strong>（何に答えているか）を押さえると全体が見えやすくなります。</li>
          <li><strong>学び方</strong>：冒頭だけでも<strong>音読</strong>し、分からない箇所は印を付けて後から問うとよいです。</li>
        </ul>

        <h2>本文（冒頭・自動抜粋）</h2>
        <p class="notice">
          出典はリポジトリ内 <code>doc/正法眼蔵.txt</code> です。原文の参照元: <a href="{SOURCE_URL}">{SOURCE_URL}</a>
        </p>
        {excerpt_block}

        <h2>深掘り（読解のコツ）</h2>
        <ul>
          <li>道元文は<strong>定義の羅列</strong>に見えても、多くの場合<strong>誤解への遮断</strong>と<strong>正伝の姿勢</strong>が背骨になっています。</li>
          <li>「当体」「現成」「即」などの語が出たら、その巻独自の<strong>差別相</strong>にどう接続しているかをメモしておくとよいです。</li>
        </ul>

        <h2>確認（形成評価）</h2>
        <fieldset class="quiz" data-correct-index="0">
          <legend>1. 道元の文章を学ぶ姿勢として、まず避けたいのはどれか。</legend>
          <label><input type="radio" name="{slug}-q1" value="0" /> 本文を読まずに要約だけで満足する</label>
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
        <p>七十五巻・十二巻・辨道話への導線です。多くの巻はスクリプトが <code>doc/正法眼蔵.txt</code> から冒頭を抜粋したページを生成しています。原文の参照元: <a href="{SOURCE_URL}">{SOURCE_URL}</a></p>
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
    generate_full = os.environ.get("DOGEN_GENERATE_FULLTEXT", "").strip() == "1"
    if len(BODY_75_STARTS_1BASED) != len(TITLES_75) + 1:
        raise SystemExit("BODY_75_STARTS_1BASED must have len(TITLES_75)+1 sentinel")

    VOL.mkdir(parents=True, exist_ok=True)
    (VOL / "index.html").write_text(index_html(), encoding="utf-8")

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
            (d / "full.html").write_text(
                f"""<!DOCTYPE html>
<html lang="ja">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>第{i}　{html.escape(title)}（全文）— 正法眼蔵読解</title>
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
      <article class="prose">
        <p class="notice">
          <strong>注意</strong>：全文表示は権利条件に依存します。公開サイトに載せる範囲は利用許諾に従ってください。
          出典: <code>doc/正法眼蔵.txt</code>。原文の参照元: <a href="{SOURCE_URL}">{SOURCE_URL}</a>
        </p>
        <h1>正法眼藏第{i}　{html.escape(title)}（全文）</h1>
        <p><a href="index.html">抜粋ページへ戻る</a> · <a href="../index.html">巻一覧</a> · <a href="../../index.html">ホーム</a></p>
        {full}
      </article>
    </main>
    <footer class="site-footer">
      <p><a href="../../index.html">ホーム</a> · 正法眼蔵読解</p>
    </footer>
    <script src="../../js/nav.js" defer></script>
  </body>
</html>
""",
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
            (d / "full.html").write_text(
                f"""<!DOCTYPE html>
<html lang="ja">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>第{i}　{html.escape(title)}（全文）— 正法眼蔵読解</title>
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
      <article class="prose">
        <p class="notice">
          <strong>注意</strong>：全文表示は権利条件に依存します。公開サイトに載せる範囲は利用許諾に従ってください。
          出典: <code>doc/正法眼蔵.txt</code>。原文の参照元: <a href="{SOURCE_URL}">{SOURCE_URL}</a>
        </p>
        <h1>正法眼藏第{i}　{html.escape(title)}（全文）</h1>
        <p><a href="index.html">抜粋ページへ戻る</a> · <a href="../index.html">巻一覧</a> · <a href="../../index.html">ホーム</a></p>
        {full}
      </article>
    </main>
    <footer class="site-footer">
      <p><a href="../../index.html">ホーム</a> · 正法眼蔵読解</p>
    </footer>
    <script src="../../js/nav.js" defer></script>
  </body>
</html>
""",
                encoding="utf-8",
            )
        n_written += 1

    # 辨道話（手編集 index は別ファイル。全文 HTML はコーパスと同期するため毎回生成）
    bendowa_dir = VOL / "bendowa"
    bendowa_dir.mkdir(parents=True, exist_ok=True)
    full_bw = fulltext_html_block(lines, BENDOWA_BODY_START_1BASED, BENDOWA_BODY_NEXT_1BASED)
    (bendowa_dir / "full.html").write_text(
        f"""<!DOCTYPE html>
<html lang="ja">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>辨道話（全文）— 正法眼蔵読解</title>
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
      <article class="prose">
        <p class="notice">
          <strong>注意</strong>：全文表示は権利条件に依存します。公開サイトに載せる範囲は利用許諾に従ってください。
          出典: <code>doc/正法眼蔵.txt</code>。原文の参照元: <a href="{SOURCE_URL}">{SOURCE_URL}</a>
        </p>
        <h1>辨道話（全文）</h1>
        <p><a href="index.html">抜粋ページへ戻る</a> · <a href="../index.html">巻一覧</a> · <a href="../../index.html">ホーム</a></p>
        {full_bw}
      </article>
    </main>
    <footer class="site-footer">
      <p><a href="../../index.html">ホーム</a> · 正法眼蔵読解</p>
    </footer>
    <script src="../../js/nav.js" defer></script>
  </body>
</html>
""",
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
