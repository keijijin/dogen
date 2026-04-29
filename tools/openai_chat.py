"""OpenAI Chat Completions（JSON モード可）と Responses API 経由の画像生成の薄いラッパー。"""
from __future__ import annotations

import base64
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


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


def _base_url() -> str:
    u = (os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").strip().rstrip("/")
    return u or "https://api.openai.com/v1"


def openai_chat_completion(
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    temperature: float = 0.35,
    json_mode: bool = False,
    timeout_s: int = 120,
) -> str:
    """アシスタントのテキスト（JSON モード時は JSON 文字列）を返す。"""
    api_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set (export or deploy/local/.env)")
    m = model or (os.environ.get("DOGEN_AI_TOOLS_MODEL") or "gpt-4o-mini").strip()
    body: dict = {
        "model": m,
        "messages": messages,
        "temperature": temperature,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{_base_url()}/chat/completions",
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI HTTP {e.code}: {err}") from e
    choices = payload.get("choices") or []
    if not choices:
        raise RuntimeError("OpenAI: no choices in response: " + repr(payload)[:500])
    msg = choices[0].get("message") or {}
    content = msg.get("content")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("OpenAI: empty assistant content")
    return content.strip()


def extract_first_json_object_string(text: str) -> str | None:
    """先頭から最初の `{` から括弧バランスが取れるまでを切り出す（前後の説明文・不完全フェンスに対応）。"""
    t = text.strip()
    start = t.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(t)):
        ch = t[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return t[start : i + 1]
    return None


def parse_json_object(raw: str) -> dict:
    """フェンス付き JSON や前後のゴミを多少許容して dict にする。

    Llama Stack 等が返す「説明 + JSON」や、文字列内のスマートクォートで壊れた JSON にも再試行する。
    """
    t = raw.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t, flags=re.I)
        t = re.sub(r"\s*```\s*$", "", t)
    t = t.strip()
    # よくある壊れ方（列位置がずれる原因になりやすい）
    t = t.replace("\u201c", '"').replace("\u201d", '"').replace("\u2018", "'").replace("\u2019", "'")

    candidates: list[str] = []
    for cand in (t, extract_first_json_object_string(t) or ""):
        if cand and cand not in candidates:
            candidates.append(cand)

    last: Exception | None = None
    for cand in candidates:
        try:
            obj = json.loads(cand)
            if isinstance(obj, dict):
                return obj
            last = ValueError("JSON root must be an object")
        except json.JSONDecodeError as e:
            last = e
            continue
    if last is not None:
        raise ValueError(f"invalid JSON after recovery attempts: {last}") from last
    raise ValueError("empty JSON candidate")


def openai_chat_json(
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    temperature: float = 0.35,
    timeout_s: int = 120,
) -> dict:
    raw = openai_chat_completion(
        messages, model=model, temperature=temperature, json_mode=True, timeout_s=timeout_s
    )
    return parse_json_object(raw)


def with_retries(fn, *, attempts: int = 4, base_sleep: float = 2.0):
    last: Exception | None = None
    for i in range(attempts):
        try:
            return fn()
        except (RuntimeError, json.JSONDecodeError, ValueError, urllib.error.URLError) as e:
            last = e
            msg = str(e)
            transient = "HTTP 429" in msg or "HTTP 502" in msg or "HTTP 503" in msg or "timeout" in msg.lower()
            if i + 1 < attempts and transient:
                time.sleep(base_sleep * (i + 1))
                continue
            if i + 1 < attempts and isinstance(e, (json.JSONDecodeError, ValueError)):
                time.sleep(base_sleep)
                continue
            raise
    assert last is not None
    raise last


def _map_dalle_quality(quality: str) -> str:
    q = (quality or "high").strip().lower()
    if q in ("hd", "high"):
        return "high"
    if q in ("standard", "medium"):
        return "medium"
    if q == "low":
        return "low"
    return "high"


def _walk_image_generation_b64(obj: object, depth: int = 0) -> str | None:
    if depth > 20:
        return None
    if isinstance(obj, dict):
        if obj.get("type") == "image_generation_call":
            r = obj.get("result")
            if isinstance(r, str) and len(r) > 64:
                return r
        for v in obj.values():
            found = _walk_image_generation_b64(v, depth + 1)
            if found:
                return found
    elif isinstance(obj, list):
        for x in obj:
            found = _walk_image_generation_b64(x, depth + 1)
            if found:
                return found
    return None


def openai_image_png_via_responses(
    prompt: str,
    *,
    api_key: str | None = None,
    model: str | None = None,
    quality: str = "high",
    timeout_s: int = 300,
) -> bytes:
    """Responses API の ``image_generation`` ツールで PNG を得る。

    ``model`` は会話の主モデル（例: ``gpt-4.1-mini``）。実際のラスタ生成は OpenAI 側の
    GPT Image 系モデルが担当する（API 仕様）。

    ``quality`` は従来の ``hd`` / ``standard`` も受け付け、``high`` / ``medium`` に写す。
    """
    key = (api_key or os.environ.get("OPENAI_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    m = (model or os.environ.get("DOGEN_IMAGE_RESPONSE_MODEL") or "gpt-4.1-mini").strip()
    q = _map_dalle_quality(quality)

    def _post(body: dict) -> dict:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            f"{_base_url()}/responses",
            data=data,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenAI HTTP {e.code}: {err}") from e

    # まず横長に近い size を試し、拒否されたらツール最小形へフォールバック
    bodies: list[dict] = [
        {
            "model": m,
            "input": prompt,
            "tools": [{"type": "image_generation", "quality": q, "size": "1536x1024"}],
            "tool_choice": {"type": "image_generation"},
        },
        {
            "model": m,
            "input": prompt,
            "tools": [{"type": "image_generation", "quality": q}],
            "tool_choice": {"type": "image_generation"},
        },
        {
            "model": m,
            "input": prompt,
            "tools": [{"type": "image_generation"}],
            "tool_choice": {"type": "image_generation"},
        },
    ]
    last_err: str = ""
    for body in bodies:
        try:
            payload = _post(body)
        except RuntimeError as e:
            last_err = str(e)
            if "HTTP 400" in last_err:
                continue
            raise
        b64 = _walk_image_generation_b64(payload)
        if b64:
            return base64.standard_b64decode(b64)
        last_err = "no image_generation_call.result in response: " + repr(payload)[:600]
    raise RuntimeError(last_err or "image generation failed")
