"""Common backend interface and stdlib HTTP helpers.

Same pattern as `Backend` in Nex-pilot and `Scheduler` in `vliw.core`:
upper layers depend on the contract, not on a specific provider API.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

TIMEOUT = 60
MAX_TOKENS = 4000
# Reasoning models spend part of the budget on internal thinking — keep a generous
# limit so responses aren't cut off mid-sentence.
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
    """Quota exhausted — retrying the same request is pointless; switch backends."""
    low = msg.lower()
    return any(s in low for s in ("quota", "billing", "exceeded your current",
                                  "rate limit", "capacity"))


def _extract_error(raw: str) -> str:
    """Extract a human-readable error message from any provider's error body."""
    try:
        err = json.loads(raw)
    except ValueError:
        return raw
    if isinstance(err, dict):
        # Google: {"error": {"message": ...}}, others: {"message": ...}
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
    """Single POST returning parsed JSON. Errors are raised as LLMError."""
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"), headers=headers,
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        raise LLMError(f"HTTP {e.code}: {_extract_error(raw).strip()[:200]}") from None
    except Exception as e:  # noqa: BLE001 — wrap any network error as LLMError
        raise LLMError(f"{type(e).__name__}: {e}") from None


def post_json_retry(url: str, body: dict, headers: dict,
                    timeout: float = TIMEOUT) -> dict:
    """POST with retries: free tiers routinely return 429/503."""
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
    """POST yielding parsed SSE events (`data: {...}`) as they arrive."""
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
    """Extract text from `content`, which may be a string or a list of chunks.

    Newer Chat API versions return content as a list
    (`[{'type': 'text', 'text': ...}]`) instead of a string — calling `.strip()`
    directly would raise AttributeError outside LLMError and leak a raw traceback.
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
    """Generation backend contract. Synchronous: the agent invokes it from worker threads."""

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
        """Yield text chunks as they are generated."""
        raise NotImplementedError

    def structured(self, system: str, question: str, schema: dict,
                   temperature: float = 0.1) -> tuple[str, int]:
        """Return output conforming to a JSON schema as (json_str, output_tokens)."""
        raise NotImplementedError
