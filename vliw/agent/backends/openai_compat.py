"""Универсальный OpenAI-совместимый backend.

Одним кодом закрывает: OpenAI, DeepSeek, Qwen (DashScope compat-mode),
Kimi/Moonshot, OpenRouter, локальные Ollama/vLLM/LM Studio и любой другой
сервер с `POST {base_url}/chat/completions`.

Выбор — переменными окружения (см. `llm.PROVIDER_DEFAULTS` и `.env.example`):
  NEX_PROVIDER=openai|deepseek|qwen|kimi|custom
  NEX_API_KEY — ключ (для ollama/vllm можно любой непустой)
  NEX_BASE_URL — обязательно для custom, опционально для остальных
  NEX_MODEL — обязательно для custom, опционально для остальных
"""

from __future__ import annotations

from .base import (Backend, LLMError, MAX_TOKENS, TIMEOUT, _code_of,
                   content_str, post_json_retry, post_sse)
from ._loopback import local_base_url as _loopback_validator

DEFAULTS = {
    # provider -> (base_url, model)
    "openai": ("https://api.openai.com/v1", "gpt-4o-mini"),
    "deepseek": ("https://api.deepseek.com/v1", "deepseek-chat"),
    "qwen": ("https://dashscope-intl.aliyuncs.com/compatible-mode/v1", "qwen-plus"),
    "kimi": ("https://api.moonshot.ai/v1", "moonshot-v1-8k"),
    "vercel": ("https://ai-gateway.vercel.sh/v1", "openai/gpt-5.4"),
    "grok": ("https://api.x.ai/v1", "grok-4.6"),
    "glm": ("https://api.z.ai/api/paas/v4", "glm-5.3"),
    "openrouter": ("https://openrouter.ai/api/v1", "deepseek/deepseek-chat"),
    "muse": ("https://api.meta.ai/v1", "muse-spark-1.3"),
    "local-server": ("http://localhost:11434/v1", ""),
    "custom": ("", ""),
}


def _is_loopback_url(url: str) -> str:
    """Local-сервер — только замкнутая петля: http://localhost|127.0.0.1|[::1].

    Remote URL в `local-server` означал бы, что «локальный» провайдер шлёт
    данные чужому серверу. Валидатор вернёт нормализованный адрес (без
    хвостового слэша) или бросит ValueError.
    """
    import ipaddress
    import urllib.parse

    raw = (url or "").strip()
    if not raw:
        raise ValueError("Local: адрес сервера не задан")
    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme != "http":
        raise ValueError("Local: нужен http:// адрес на loopback "
                         "(https к локальному серверу не ходит)")
    host = (parsed.hostname or "").lower()
    if host in ("localhost", "::1"):
        ok = True
    else:
        try:
            ok = ipaddress.ip_address(host).is_loopback
        except ValueError:
            ok = False
    if not ok:
        raise ValueError("Local: только loopback-адреса "
                         "(localhost / 127.0.0.0/8 / ::1)")
    if parsed.query or parsed.fragment:
        raise ValueError("Local: лишние query/fragment в адресе сервера")
    port = f":{parsed.port}" if parsed.port else ""
    path = parsed.path.rstrip("/")
    return f"http://{parsed.hostname}{port}{path}"


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
        raise LLMError("модель не вернула ответ")
    text = content_str(choices[0].get("message", {}).get("content")).strip()
    used = int(data.get("usage", {}).get("completion_tokens", 0) or 0)
    if not text:
        raise LLMError(f"пустой ответ (finish={choices[0].get('finish_reason')})")
    return text, used


class OpenAICompatBackend(Backend):
    name = "openai-compat"

    def __init__(self, api_key: str, base_url: str = "", model: str = "",
                 provider: str = "custom", timeout: float = TIMEOUT):
        dflt_url, dflt_model = DEFAULTS.get(provider, DEFAULTS["custom"])
        if provider == "local-server":
            from .. import models

            validator = getattr(models, "local_base_url", None)
            if validator is None:
                validator = _loopback_validator
            try:
                base_url = validator(base_url or dflt_url)
            except ValueError as e:
                raise LLMError(str(e)) from None
            if not base_url:
                raise LLMError("Local requires a loopback HTTP URL")
            api_key = api_key or "local"
        else:
            base_url = base_url or dflt_url
        if not api_key:
            raise LLMError(
                "ключ не задан: задайте NEX_API_KEY (или ключ провайдера) "
                "либо ~/.config/nex/key")
        self._base_url = (base_url or dflt_url).rstrip("/")
        self._model = model or dflt_model
        if not self._base_url:
            raise LLMError("не задан адрес API: NEX_BASE_URL "
                           "(например, https://openrouter.ai/api/v1)")
        if not self._model:
            raise LLMError("не задана модель: NEX_MODEL (например, deepseek/deepseek-chat)")
        self.name = provider
        self._key = api_key
        self._timeout = timeout

    def _url(self) -> str:
        return f"{self._base_url}/chat/completions"

    def _headers(self, stream: bool = False) -> dict:
        return {"Content-Type": "application/json",
                "Accept": "text/event-stream" if stream else "application/json",
                "Authorization": f"Bearer {self._key}"}

    def _body(self, system, question, history, temperature, schema, stream,
              loose_schema: bool = False):
        body = {
            "model": self._model,
            "messages": _messages(system, history, question),
            "temperature": temperature,
            "max_tokens": MAX_TOKENS,
        }
        if stream:
            body["stream"] = True
        if schema:
            # Строгий json_schema понимают не все серверы (и не все модели):
            # при 400/422 второй попыткой идёт plain json_object, дальше
            # JSON проверяет вызывающий разбором (см. structured).
            body["response_format"] = {"type": "json_object"} if loose_schema else {
                "type": "json_schema",
                "json_schema": {"name": "analysis", "schema": schema, "strict": True},
            }
        return body

    def complete(self, system, question, history=None, temperature=0.3) -> str:
        data = post_json_retry(
            self._url(), self._body(system, question, history, temperature, None, False),
            self._headers(), self._timeout)
        return _text_of(data)[0]

    def structured(self, system, question, schema, temperature=0.1):
        try:
            data = post_json_retry(
                self._url(), self._body(system, question, [], temperature, schema, False),
                self._headers(), self._timeout)
        except LLMError as e:
            if _code_of(str(e)) not in (400, 422):
                raise
            data = post_json_retry(
                self._url(), self._body(system, question, [], temperature, schema, False,
                                        loose_schema=True),
                self._headers(), self._timeout)
        return _text_of(data)

    def stream(self, system, question, history=None, temperature=0.3):
        for chunk in post_sse(
                self._url(), self._body(system, question, history, temperature, None, True),
                self._headers(stream=True), self._timeout):
            for ch in chunk.get("choices", []):
                piece = content_str(ch.get("delta", {}).get("content"))
                if piece:
                    yield piece
