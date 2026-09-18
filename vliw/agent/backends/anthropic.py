from __future__ import annotations

import json

from .base import Backend, LLMError, MAX_TOKENS, TIMEOUT, post_json_retry, post_sse

_DEFAULT_MODEL = "claude-sonnet-4-5"


def _text_of(data: dict) -> tuple[str, int]:
    if data.get("type") == "error":
        raise LLMError(str((data.get("error") or {}).get("message", "Anthropic error")))
    text = "".join(block.get("text", "") for block in data.get("content", [])
                   if block.get("type") == "text").strip()
    if not text:
        raise LLMError(f"пустой ответ (stop_reason={data.get('stop_reason')})")
    return text, int((data.get("usage") or {}).get("output_tokens", 0) or 0)


class AnthropicBackend(Backend):
    name = "anthropic"

    def __init__(self, api_key: str, base_url: str = "", model: str = "",
                 timeout: float = TIMEOUT):
        if not api_key:
            raise LLMError("ключ не задан: ANTHROPIC_API_KEY")
        self._key = api_key
        self._base_url = (base_url or "https://api.anthropic.com/v1").rstrip("/")
        self._model = model or _DEFAULT_MODEL
        self._timeout = timeout

    def _headers(self, stream: bool = False) -> dict:
        return {"Content-Type": "application/json",
                "Accept": "text/event-stream" if stream else "application/json",
                "x-api-key": self._key, "anthropic-version": "2023-06-01"}

    def _body(self, system, question, history, temperature, schema=None, stream=False):
        messages = [{"role": "user" if role == "user" else "assistant", "content": text}
                    for role, text in history or []]
        messages.append({"role": "user", "content": question})
        body = {"model": self._model, "system": system, "messages": messages,
                "temperature": temperature, "max_tokens": MAX_TOKENS}
        if stream:
            body["stream"] = True
        if schema is not None:
            body["output_config"] = {"format": {"type": "json_schema", "schema": schema}}
        return body

    def complete(self, system, question, history=None, temperature=0.3) -> str:
        data = post_json_retry(
            f"{self._base_url}/messages", self._body(system, question, history, temperature),
            self._headers(), self._timeout)
        return _text_of(data)[0]

    def structured(self, system, question, schema, temperature=0.1):
        data = post_json_retry(
            f"{self._base_url}/messages", self._body(system, question, [], temperature, schema),
            self._headers(), self._timeout)
        if data.get("stop_reason") in ("max_tokens", "refusal"):
            raise LLMError(f"Anthropic structured output: {data['stop_reason']}")
        text, used = _text_of(data)
        try:
            json.loads(text)
        except ValueError:
            raise LLMError("Anthropic: invalid JSON structured output") from None
        return text, used

    def stream(self, system, question, history=None, temperature=0.3):
        for chunk in post_sse(
                f"{self._base_url}/messages",
                self._body(system, question, history, temperature, stream=True),
                self._headers(stream=True), self._timeout):
            if chunk.get("type") == "error":
                raise LLMError(str((chunk.get("error") or {}).get("message", "Anthropic error")))
            if chunk.get("type") == "content_block_delta":
                delta = chunk.get("delta") or {}
                if delta.get("type") == "text_delta" and delta.get("text"):
                    yield delta["text"]
            elif chunk.get("type") == "message_stop":
                return
