"""Mistral (Le Chat API): OpenAI-compatible `/v1/chat/completions`."""

from __future__ import annotations

from .base import (Backend, LLMError, MAX_TOKENS, TIMEOUT, _code_of,
                   content_str, post_json_retry, post_sse)

_API = "https://api.mistral.ai/v1/chat/completions"
_DEFAULT_MODEL = "mistral-small-latest"


def _messages(system, history, question):
    msgs = [{"role": "system", "content": system}]
    for role, text in history or []:
        msgs.append({"role": "user" if role == "user" else "assistant",
                     "content": text})
    msgs.append({"role": "user", "content": question})
    return msgs


def _text_of(data: dict) -> tuple[str, int]:
    choices = data.get("choices") or []
    if not choices:
        raise LLMError("model returned no response")
    text = content_str(choices[0].get("message", {}).get("content")).strip()
    used = int(data.get("usage", {}).get("completion_tokens", 0) or 0)
    if not text:
        raise LLMError(f"empty response (finish={choices[0].get('finish_reason')})")
    return text, used


class MistralBackend(Backend):
    name = "mistral"

    def __init__(self, api_key: str, model: str | None = None,
                 timeout: float = TIMEOUT):
        if not api_key:
            raise LLMError("API key not set for Mistral: set MISTRAL_API_KEY, "
                           "NEX_API_KEY, or ~/.config/nex/key")
        self._key = api_key
        self._model = model or _DEFAULT_MODEL
        self._timeout = timeout

    def _headers(self, stream: bool = False) -> dict:
        return {"Content-Type": "application/json",
                "Accept": "text/event-stream" if stream else "application/json",
                "Authorization": f"Bearer {self._key}"}

    def _body(self, system, question, history, temperature, schema, stream,
              model: str | None = None, loose_schema: bool = False):
        body = {
            "model": model or self._model,
            "messages": _messages(system, history, question),
            "temperature": temperature,
            "max_tokens": MAX_TOKENS,
        }
        if stream:
            body["stream"] = True
        if schema:
            # Strict json_schema requires additionalProperties: false and rejects
            # loose schemas with 400/422 — retry with plain json_object (see
            # structured); the caller validates the parsed JSON anyway.
            body["response_format"] = {"type": "json_object"} if loose_schema else {
                "type": "json_schema",
                "json_schema": {"name": "analysis", "schema": schema, "strict": True},
            }
        return body

    def complete(self, system, question, history=None, temperature=0.3) -> str:
        data = post_json_retry(
            _API, self._body(system, question, history, temperature, None, False),
            self._headers(), self._timeout)
        return _text_of(data)[0]

    def structured(self, system, question, schema, temperature=0.1):
        try:
            data = post_json_retry(
                _API, self._body(system, question, [], temperature, schema, False),
                self._headers(), self._timeout)
        except LLMError as e:
            if _code_of(str(e)) not in (400, 422):
                raise
            data = post_json_retry(
                _API, self._body(system, question, [], temperature, schema, False,
                                 loose_schema=True),
                self._headers(), self._timeout)
        return _text_of(data)

    def stream(self, system, question, history=None, temperature=0.3):
        for chunk in post_sse(
                _API, self._body(system, question, history, temperature, None, True),
                self._headers(stream=True), self._timeout):
            for ch in chunk.get("choices", []):
                piece = content_str(ch.get("delta", {}).get("content"))
                if piece:
                    yield piece
