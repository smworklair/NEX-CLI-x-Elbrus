"""YandexGPT (Yandex Cloud): `foundationModels/v1/completion`.

Two authentication modes (either suffices):
  * API key:   YANDEX_API_KEY (header `Authorization: Api-Key ...`);
  * IAM token: YANDEX_IAM_TOKEN (header `Authorization: Bearer ...`).

Both require a folder ID:
  YANDEX_FOLDER_ID — Yandex Cloud folder identifier.

Environment variables (see `.env.example`):
  YANDEX_API_KEY / YANDEX_IAM_TOKEN / YANDEX_FOLDER_ID
  YANDEX_MODEL — defaults to yandexgpt (or yandexgpt-lite)
  NEX_MODEL — overrides YANDEX_MODEL if set
"""

from __future__ import annotations

import os

from .base import Backend, LLMError, MAX_TOKENS, TIMEOUT, post_json_retry

_API = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"


class YandexBackend(Backend):
    name = "yandexgpt"

    def __init__(self, api_key: str = "", iam_token: str = "", folder_id: str = "",
                 model: str = "", timeout: float = TIMEOUT,
                 use_env: bool = True):
        env = os.environ if use_env else {}
        key = api_key or env.get("YANDEX_API_KEY", "") or env.get("NEX_API_KEY", "")
        iam = iam_token or env.get("YANDEX_IAM_TOKEN", "")
        folder = folder_id or env.get("YANDEX_FOLDER_ID", "")
        # NEX_API_KEY of form "iam:..."/"key:..." for single-field input.
        if not iam and key.startswith("iam:"):
            iam, key = key[4:], ""
        if iam and not folder and ":" in iam:
            iam, _, folder = iam.partition(":")
        if key.startswith("folder:"):
            folder = folder or key[len("folder:"):]
            key = ""
        if not (key or iam):
            raise LLMError("YandexGPT: set YANDEX_API_KEY or YANDEX_IAM_TOKEN")
        if not folder:
            raise LLMError("YandexGPT: set YANDEX_FOLDER_ID (Yandex Cloud folder ID)")
        self._key = key.strip()
        self._iam = iam.strip()
        self._folder = folder.strip()
        self._model = model or env.get("YANDEX_MODEL", "") \
            or env.get("NEX_MODEL", "") or "yandexgpt"
        self._timeout = timeout

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self._iam:
            h["Authorization"] = f"Bearer {self._iam}"
            # Duplicate folder ID in header per official docs:
            # modelUri already includes it, and the extra header is harmless.
            h["x-folder-id"] = self._folder
        else:
            h["Authorization"] = f"Api-Key {self._key}"
        return h

    def _body(self, system, question, history, temperature, schema, stream):
        msgs = [{"role": "system", "text": system}]
        for role, text in history or []:
            msgs.append({"role": "user" if role == "user" else "assistant",
                         "text": text})
        msgs.append({"role": "user", "text": question})
        body: dict = {
            "modelUri": f"gpt://{self._folder}/{self._model}/latest",
            "completionOptions": {"stream": bool(stream),
                                  "temperature": temperature,
                                  "maxTokens": MAX_TOKENS},
            "messages": msgs,
        }
        if schema:
            # Yandex has no response_format — request JSON via system instruction.
            msgs.append({"role": "system",
                         "text": "Respond STRICTLY with valid JSON and no extra "
                                 "commentary, matching the requested schema."})
        return body

    def _text_of(self, data: dict) -> tuple[str, int]:
        alts = (data.get("result") or {}).get("alternatives") or []
        if not alts:
            raise LLMError("model returned no response")
        text = ((alts[0].get("message") or {}).get("text") or "").strip()
        used = int((data.get("result") or {}).get("usage", {})
                   .get("completionTokens", 0) or 0)
        if not text:
            raise LLMError("empty model response")
        return text, used

    def complete(self, system, question, history=None, temperature=0.3) -> str:
        data = post_json_retry(
            _API, self._body(system, question, history, temperature, None, False),
            self._headers(), self._timeout)
        return self._text_of(data)[0]

    def structured(self, system, question, schema, temperature=0.1):
        data = post_json_retry(
            _API, self._body(system, question, [], temperature, schema, False),
            self._headers(), self._timeout)
        return self._text_of(data)

    def stream(self, system, question, history=None, temperature=0.3):
        # Yandex supports SSE with stream=true, but emits full completion objects
        # incrementally; yielding the full completion in one chunk is simpler and
        # more reliable (the UI only skips character-by-character animation).
        yield self.complete(system, question, history, temperature)
