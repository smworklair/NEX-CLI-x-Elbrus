"""Общий интерфейс backend'а и HTTP-помощники на стандартной библиотеке.

Тот же приём, что `Backend` в Nex-pilot и `Scheduler` в `vliw.core`:
верхний слой зависит от контракта, а не от конкретного API.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

TIMEOUT = 60
MAX_TOKENS = 4000
# Модели с «размышлением» тратят часть бюджета на него — лимит с запасом,
# иначе ответ обрывается на полуслове.
RETRIES = 3
RETRY_PAUSE = 2.0
_RETRY_CODES = {429, 500, 502, 503, 504}


class LLMError(RuntimeError):
    pass


def _code_of(msg: str) -> int | None:
    if msg.startswith("HTTP "):
        try:
            return int(msg.split()[1].rstrip(":"))
        except (IndexError, ValueError):
            return None
    return None


def _is_exhausted(msg: str) -> bool:
    """Квота кончилась — повторять тот же запрос бессмысленно, надо сменить бэкенд."""
    low = msg.lower()
    return any(s in low for s in ("quota", "billing", "exceeded your current",
                                  "rate limit", "capacity"))


def _extract_error(raw: str) -> str:
    """Вытащить человеческое сообщение из тела ошибки любого провайдера."""
    try:
        err = json.loads(raw)
    except ValueError:
        return raw
    if isinstance(err, dict):
        # Google: {"error": {"message": ...}}, остальные: {"message": ...}
        sub = err.get("error")
        if isinstance(sub, dict):
            return str(sub.get("message") or raw)
        if isinstance(sub, str):
            return sub
        if err.get("message"):
            return str(err["message"])
    return raw


def post_json(url: str, body: dict, headers: dict,
              timeout: float = TIMEOUT) -> dict:
    """Один POST, вернуть распарсенный JSON. Ошибки — как LLMError."""
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"), headers=headers,
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        raise LLMError(f"HTTP {e.code}: {_extract_error(raw).strip()[:200]}") from None
    except Exception as e:  # noqa: BLE001 — сеть даёт что угодно, заворачиваем в LLMError
        raise LLMError(f"{type(e).__name__}: {e}") from None


def post_json_retry(url: str, body: dict, headers: dict,
                    timeout: float = TIMEOUT) -> dict:
    """POST с повторами: бесплатные тарифы регулярно отдают 429/503."""
    last = ""
    for attempt in range(RETRIES):
        if attempt:
            time.sleep(RETRY_PAUSE * attempt)
        try:
            return post_json(url, body, headers, timeout)
        except LLMError as e:
            last = str(e)
            if _is_exhausted(last):
                raise
            code = _code_of(last)
            if code is not None and code not in _RETRY_CODES:
                raise
    raise LLMError(last)


def post_sse(url: str, body: dict, headers: dict,
             timeout: float = TIMEOUT):
    """POST, отдавать распарсенные SSE-события (`data: {...}`) по мере прихода."""
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"), headers=headers,
        method="POST")
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        raise LLMError(f"HTTP {e.code}: {_extract_error(raw).strip()[:200]}") from None
    except Exception as e:  # noqa: BLE001
        raise LLMError(f"{type(e).__name__}: {e}") from None
    with resp:
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if not payload or payload == "[DONE]":
                continue
            try:
                yield json.loads(payload)
            except ValueError:
                continue


def content_str(content) -> str:
    """Текст из `content`, который бывает и строкой, и списком чанков.

    Новые версии Chat API отдают content списком
    (`[{'type': 'text', 'text': ...}]`) вместо строки — прямое `.strip()`
    там падает AttributeError мимо LLMError, наружу летит сырой traceback.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for ch in content:
            if isinstance(ch, dict):
                t = ch.get("text")
                if isinstance(t, str):
                    parts.append(t)
            elif isinstance(ch, str):
                parts.append(ch)
        return "".join(parts)
    return ""


class Backend:
    """Контракт backend'а генерации. Синхронный: агент вызывает из потоков."""

    name = "?"

    def __setattr__(self, name, value):
        if getattr(self, "_frozen", False) and name not in ("_token", "_token_until"):
            raise AttributeError("backend configuration is immutable")
        object.__setattr__(self, name, value)

    def __delattr__(self, name):
        if getattr(self, "_frozen", False):
            raise AttributeError("backend configuration is immutable")
        object.__delattr__(self, name)

    def complete(self, system: str, question: str,
                 history: list[tuple[str, str]] | None = None,
                 temperature: float = 0.3) -> str:
        raise NotImplementedError

    def stream(self, system: str, question: str,
               history: list[tuple[str, str]] | None = None,
               temperature: float = 0.3):
        """Куски текста по мере генерации (генератор строк)."""
        raise NotImplementedError

    def structured(self, system: str, question: str, schema: dict,
                   temperature: float = 0.1) -> tuple[str, int]:
        """Ответ строго по JSON-схеме. Возвращает (JSON-строка, токены ответа)."""
        raise NotImplementedError
