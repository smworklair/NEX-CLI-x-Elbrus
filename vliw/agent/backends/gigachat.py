"""Sber GigaChat: OAuth via ngw + OpenAI-compatible chat/completions.

Authentication differs from other providers: instead of a static API key,
a client_id/client_secret pair is exchanged for a short-lived token
(`POST {auth_url}/api/v2/oauth`, `scope=GIGACHAT_API_PERS` by default).
The token is cached until `expires_at` and refreshed automatically.

Environment variables (see `.env.example`):
  GIGACHAT_CLIENT_ID / GIGACHAT_CLIENT_SECRET — required
    (or NEX_API_KEY in "id:secret" form for single-field entry)
  GIGACHAT_SCOPE — defaults to GIGACHAT_API_PERS
  GIGACHAT_BASE_URL — defaults to https://api.giga.chat/v1 (target endpoint
    from 07.2026; legacy gigachat.devices.sberbank.ru is being phased out)
  GIGACHAT_AUTH_URL — defaults to https://ngw.devices.sberbank.ru:9443
  GIGACHAT_MODEL — defaults to GigaChat
  GIGACHAT_INSECURE=1 — skip TLS certificate verification (fallback when
    root CAs are missing in the environment; verification is on by default)
"""

from __future__ import annotations

import base64
import json
import os
import ssl
import time
import urllib.parse
import urllib.request

from .base import (Backend, LLMError, MAX_TOKENS, TIMEOUT, content_str,
                   post_json_retry, post_sse)


class GigaChatBackend(Backend):
    name = "gigachat"

    def __init__(self, client_id: str = "", client_secret: str = "",
                 scope: str = "", base_url: str = "", auth_url: str = "",
                 model: str = "", timeout: float = TIMEOUT,
                 use_env: bool = True):
        env = os.environ if use_env else {}
        cid = client_id or env.get("GIGACHAT_CLIENT_ID", "")
        sec = client_secret or env.get("GIGACHAT_SECRET", "") \
            or env.get("GIGACHAT_CLIENT_SECRET", "")
        if not cid and ":" in env.get("NEX_API_KEY", ""):
            cid, _, sec = env.get("NEX_API_KEY", "").partition(":")
            cid, sec = cid.strip(), sec.strip()
        if not cid or not sec:
            raise LLMError('GigaChat: set GIGACHAT_CLIENT_ID and GIGACHAT_SECRET '
                           '(or NEX_API_KEY as "id:secret")')
        self._cid = cid.strip()
        self._sec = sec.strip()
        self._scope = scope or env.get("GIGACHAT_SCOPE", "") or "GIGACHAT_API_PERS"
        self._base = (base_url or env.get("GIGACHAT_BASE_URL", "")
                      or "https://api.giga.chat/v1").rstrip("/")
        self._auth = (auth_url or env.get("GIGACHAT_AUTH_URL", "")
                      or "https://ngw.devices.sberbank.ru:9443").rstrip("/")
        self._model = model or env.get("GIGACHAT_MODEL", "") \
            or env.get("NEX_MODEL", "") or "GigaChat"
        self._timeout = timeout
        self._insecure = env.get("GIGACHAT_INSECURE", "") == "1"
        self._token = ""
        self._token_until = 0.0

    # --- token ---

    def _ctx(self) -> ssl.SSLContext | None:
        if self._insecure:
            return ssl._create_unverified_context()
        return None

    def _token_headers(self) -> dict:
        basic = base64.b64encode(f"{self._cid}:{self._sec}".encode()).decode()
        import uuid

        return {"Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
                "RqUID": str(uuid.uuid4()),
                "Authorization": f"Basic {basic}"}

    def _fetch_token(self) -> str:
        import uuid

        # RqUID must be fresh for every token request.
        headers = self._token_headers()
        headers["RqUID"] = str(uuid.uuid4())
        body = urllib.parse.urlencode({"scope": self._scope}).encode()
        req = urllib.request.Request(f"{self._auth}/api/v2/oauth",
                                     data=body, headers=headers, method="POST")
        try:
            ctx = self._ctx()
            with (urllib.request.urlopen(req, timeout=self._timeout, context=ctx)
                  if ctx else urllib.request.urlopen(req, timeout=self._timeout)) as resp:
                data = json.load(resp)
        except Exception as e:  # noqa: BLE001
            raise LLMError(f"GigaChat OAuth: {type(e).__name__}: {e}") from None
        tok = data.get("access_token", "")
        if not tok:
            raise LLMError("GigaChat OAuth: no access_token in response")
        # Sber's `expires_at` is an absolute Unix timestamp (30 min), not a TTL:
        # adding it to now() would cache the token for decades. Distinguish by
        # magnitude and refresh one minute before expiry.
        try:
            exp = int(data.get("expires_at", 0) or 0)
        except (TypeError, ValueError):
            exp = 0
        if exp > 1_000_000_000:
            self._token_until = exp - 60
        elif exp > 0:
            self._token_until = time.time() + exp - 60
        else:
            self._token_until = time.time() + 1800 - 60
        self._token = tok
        return tok

    def _auth_token(self) -> str:
        if self._token and time.time() < self._token_until:
            return self._token
        return self._fetch_token()

    # --- generation ---

    def _headers(self, stream: bool = False) -> dict:
        return {"Content-Type": "application/json",
                "Accept": "text/event-stream" if stream else "application/json",
                "Authorization": f"Bearer {self._auth_token()}"}

    def _body(self, system, question, history, temperature, schema, stream):
        msgs = [{"role": "system", "content": system}]
        for role, text in history or []:
            msgs.append({"role": "user" if role == "user" else "assistant",
                         "content": text})
        msgs.append({"role": "user", "content": question})
        body: dict = {"model": self._model, "messages": msgs,
                      "temperature": temperature, "max_tokens": MAX_TOKENS}
        if stream:
            body["stream"] = True
            body["update_interval"] = 0
        if schema:
            body["response_format"] = {"type": "json_object"}
        return body

    def _text_of(self, data: dict) -> tuple[str, int]:
        choices = data.get("choices") or []
        if not choices:
            raise LLMError("model returned no response")
        text = content_str(choices[0].get("message", {}).get("content")).strip()
        used = int(data.get("usage", {}).get("completion_tokens", 0) or 0)
        if not text:
            raise LLMError(f"empty response (finish={choices[0].get('finish_reason')})")
        return text, used

    def complete(self, system, question, history=None, temperature=0.3) -> str:
        data = post_json_retry(
            f"{self._base}/chat/completions",
            self._body(system, question, history, temperature, None, False),
            self._headers(), self._timeout)
        return self._text_of(data)[0]

    def structured(self, system, question, schema, temperature=0.1):
        data = post_json_retry(
            f"{self._base}/chat/completions",
            self._body(system, question, [], temperature, schema, False),
            self._headers(), self._timeout)
        return self._text_of(data)

    def stream(self, system, question, history=None, temperature=0.3):
        for chunk in post_sse(
                f"{self._base}/chat/completions",
                self._body(system, question, history, temperature, None, True),
                self._headers(stream=True), self._timeout):
            for ch in chunk.get("choices", []):
                piece = content_str(ch.get("delta", {}).get("content"))
                if piece:
                    yield piece
