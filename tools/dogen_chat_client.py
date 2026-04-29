"""dogen-api（OpenShift / ローカル）の ``POST /api/v1/chat`` を呼ぶ薄いクライアント。

環境変数（任意・既定はローカル開発向け）:

- ``DOGEN_CHAT_API_BASE`` … API のオリジン（例: ``https://dogen-api.apps.example.com``）
- ``DOGEN_CHAT_BEARER`` … ``Authorization`` ヘッダ全文（例: ``Bearer eyJ...``）。Compose の匿名時は ``Bearer fake`` 等。

``tools/gen_ai_modern_translations.py`` / ``gen_glossary_from_corpus.py`` から利用する。
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request


def call_chat_messages(
    api_base: str,
    bearer: str,
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    volume_scope: str | None = None,
    retries: int = 3,
    timeout_s: int = 180,
) -> str:
    """Chat Completions 互換の ``messages`` を送り、アシスタント本文を返す。"""
    body: dict[str, object] = {"messages": messages}
    if model:
        body["model"] = model
    if volume_scope:
        body["volumeScope"] = volume_scope
    url = api_base.rstrip("/") + "/api/v1/chat"
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        method="POST",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": bearer,
        },
    )
    last_err: Exception | None = None
    for n in range(1, retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            content = (((payload or {}).get("choices") or [{}])[0].get("message") or {}).get("content")
            if not isinstance(content, str) or not content.strip():
                raise RuntimeError("empty assistant content from dogen-api")
            return content.strip()
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            last_err = RuntimeError(f"HTTP {e.code}: {detail[:800]}")
        except Exception as e:
            last_err = e
        if n < retries:
            time.sleep(min(8.0, 2.0 * n))
    raise RuntimeError(str(last_err))


def call_chat(
    api_base: str,
    bearer: str,
    prompt: str,
    model: str | None = None,
    *,
    retries: int = 3,
    timeout_s: int = 180,
) -> str:
    """単一 user メッセージでチャットする（現代語訳生成など）。"""
    return call_chat_messages(
        api_base,
        bearer,
        [{"role": "user", "content": prompt}],
        model=model,
        retries=retries,
        timeout_s=timeout_s,
    )


def default_api_base() -> str:
    return (os.environ.get("DOGEN_CHAT_API_BASE") or "http://127.0.0.1:8081").strip()


def default_bearer() -> str:
    return (os.environ.get("DOGEN_CHAT_BEARER") or "Bearer fake").strip()
