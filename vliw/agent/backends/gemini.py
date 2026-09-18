"""Google Gemini (AI Studio): `generateContent` / `streamGenerateContent`."""

from __future__ import annotations

from .base import Backend, LLMError, MAX_TOKENS, TIMEOUT, post_json_retry, post_sse

_DEFAULT_MODEL = "gemini-2.5-flash"


def _schema_for_gemini(schema: dict) -> dict:
    """Gemini ждёт типы заглавными (OBJECT/STRING/ARRAY/INTEGER)."""
    out = {}
    for k, v in schema.items():
        if k == "type" and isinstance(v, str):
            out[k] = v.upper()
        elif k == "properties" and isinstance(v, dict):
            out[k] = {pk: _schema_for_gemini(pv) for pk, pv in v.items()}
        elif k == "items" and isinstance(v, dict):
            out[k] = _schema_for_gemini(v)
        else:
            out[k] = v
    return out


def _text_of(data: dict) -> tuple[str, int]:
    cands = data.get("candidates") or []
    if not cands:
        raise LLMError("модель не вернула ответ")
    parts = cands[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts).strip()
    used = int(data.get("usageMetadata", {}).get("candidatesTokenCount", 0) or 0)
    if not text:
        raise LLMError(f"пустой ответ (finishReason={cands[0].get('finishReason')})")
    return text, used


class GeminiBackend(Backend):
    name = "gemini"

    def __init__(self, api_key: str, model: str | None = None,
                 timeout: float = TIMEOUT):
        if not api_key:
            raise LLMError("ключ не задан для gemini: задайте GEMINI_API_KEY, "
                           "NEX_API_KEY или ~/.config/nex/key")
        self._key = api_key
        self._model = model or _DEFAULT_MODEL
        self._timeout = timeout

    def _url(self, stream: bool) -> str:
        path = "streamGenerateContent" if stream else "generateContent"
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{self._model}:{path}?key={self._key}")
        if stream:
            url += "&alt=sse"
        return url

    def _body(self, system, question, history, temperature, schema):
        contents = []
        for role, text in history or []:
            contents.append({"role": "user" if role == "user" else "model",
                             "parts": [{"text": text}]})
        contents.append({"role": "user", "parts": [{"text": question}]})
        cfg: dict = {"temperature": temperature, "maxOutputTokens": MAX_TOKENS}
        if schema:
            cfg["responseMimeType"] = "application/json"
            cfg["responseSchema"] = _schema_for_gemini(schema)
        return {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": contents,
            "generationConfig": cfg,
        }

    def complete(self, system, question, history=None, temperature=0.3) -> str:
        data = post_json_retry(
            self._url(False),
            self._body(system, question, history, temperature, None),
            {"Content-Type": "application/json"}, self._timeout)
        return _text_of(data)[0]

    def structured(self, system, question, schema, temperature=0.1):
        data = post_json_retry(
            self._url(False),
            self._body(system, question, [], temperature, schema),
            {"Content-Type": "application/json"}, self._timeout)
        return _text_of(data)

    def stream(self, system, question, history=None, temperature=0.3):
        for chunk in post_sse(
                self._url(True),
                self._body(system, question, history, temperature, None),
                {"Content-Type": "application/json"}, self._timeout):
            for cand in chunk.get("candidates", []):
                for part in cand.get("content", {}).get("parts", []):
                    piece = part.get("text")
                    if piece:
                        yield piece
