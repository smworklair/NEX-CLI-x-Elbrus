"""Клиент языковой модели на голой стандартной библиотеке, со сменой провайдера.

Зависимостей не добавляет: HTTP через `urllib`, JSON через `json`. Проект
остаётся запускаемым без `pip install`.

Поддерживаются два провайдера с одинаковым интерфейсом:

  * `mistral` — Le Chat / Mistral AI (`api.mistral.ai`) — по умолчанию;
  * `gemini`  — Google AI Studio (`generativelanguage.googleapis.com`).

Провайдер выбирается так:
  1. переменная `NEX_PROVIDER` (`mistral` | `lechat` | `gemini`);
  2. иначе угадывается по виду ключа (ключи Google начинаются на `AIza` или
     `AQ.`, ключи Mistral — просто длинная строка без этих префиксов);
  3. иначе — провайдер по умолчанию ниже.

Ключ берётся так:
  1. `NEX_API_KEY` (любой провайдер, определяется по виду);
  2. `~/.config/nex/key` (тот же формат, вне репозитория — безопасно хранить);
  3. `.env` в корне проекта: `MISTRAL_API_KEY=...` / `GEMINI_API_KEY=...`
     (файл в `.gitignore`, см. `.env.example`).

Без ключа в сеть не ходим: агент честно сообщает, что модель недоступна, и
отвечает офлайн по уже посчитанным числам.

БЫЛО (до 17.08.2026): здесь лежали два настоящих ключа текстом — `EMBEDDED_KEYS
= {"mistral": "...", "gemini": "..."}`, «одноразовые аккаунты, чтобы демо
работало сразу после клонирования». Оба закоммичены и найдены при разборе
`git log --all -p`. Удобство неудобно чужой безопасностью: секрет в файле,
который попадает в `git init`, — уже утечка независимо от того, пушился ли
репозиторий куда-то. Ключи отозваны у провайдера, из кода убраны. См.
`.env.example` — теперь то же самое удобство «работает сразу после клонирования»
даёт файл вне git, а не строка в исходнике.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

# Провайдер по умолчанию, если ничего не задано и ключ не опознан.
DEFAULT_PROVIDER = "mistral"

_ENV_VAR = {"mistral": "MISTRAL_API_KEY", "gemini": "GEMINI_API_KEY"}
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _dotenv_values() -> dict[str, str]:
    """Разбор `.env` в корне проекта: `ИМЯ=значение`, `#` — комментарий.

    Без внешних зависимостей (python-dotenv сюда не тащим — весь клиент и так
    держится на голой stdlib, см. шапку файла). Кэш на уровне процесса: файл
    не меняется на лету, а агент дёргает ключ на каждый запрос.
    """
    path = _PROJECT_ROOT / ".env"
    out: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _embedded_key(prov: str) -> str:
    """Ключ из `.env` (если он там есть) — единственный оставшийся «встроенный» слой."""
    return _dotenv_values().get(_ENV_VAR.get(prov, ""), "")

DEFAULT_MODELS = {
    "mistral": "mistral-small-latest",
    "gemini": "gemini-flash-latest",
}

_PROVIDER_LABEL = {
    "mistral": "le chat",
    "gemini": "gemini",
}

TIMEOUT = 60
# Модели с «размышлением» тратят часть бюджета на него, поэтому лимит с запасом:
# иначе ответ обрывается на полуслове.
MAX_TOKENS = 4000

RETRIES = 3
RETRY_PAUSE = 2.0
_RETRY_CODES = {429, 500, 502, 503, 504}


class LLMError(RuntimeError):
    pass


# --------------------------------------------------------------------------
# Выбор провайдера, ключа и модели
# --------------------------------------------------------------------------


def _looks_google(key: str) -> bool:
    return key.startswith("AIza") or key.startswith("AQ.")


def provider() -> str:
    """Провайдер меняется только явно: NEX_PROVIDER. Иначе — Le Chat.

    Раньше ключ Gemini в NEX_API_KEY / ~/.config/nex/key молча переключал
    агента на Google — и «привет» уходил в исчерпанную квоту.
    """
    name = os.environ.get("NEX_PROVIDER", "").strip().lower()
    if name in ("mistral", "lechat", "le-chat"):
        return "mistral"
    if name in ("gemini", "google"):
        return "gemini"
    return DEFAULT_PROVIDER


def _raw_key() -> str:
    """Ключ, заданный пользователем (без встроенных значений)."""
    key = os.environ.get("NEX_API_KEY", "").strip()
    if key:
        return key
    try:
        k = (Path.home() / ".config" / "nex" / "key").read_text(encoding="utf-8").strip()
        if k:
            return k
    except OSError:
        pass
    return ""


def _key_fits(key: str, prov: str) -> bool:
    google = _looks_google(key)
    return google if prov == "gemini" else not google


def _key_for(prov: str) -> str:
    raw = _raw_key()
    if raw and _key_fits(raw, prov):
        return raw
    return _embedded_key(prov)


def api_key() -> str:
    return _key_for(provider())


def _label(prov: str) -> str:
    return _PROVIDER_LABEL.get(prov, prov)


def _provider_order() -> list[str]:
    primary = provider()
    other = "gemini" if primary == "mistral" else "mistral"
    order = [primary]
    if _key_for(other):
        order.append(other)
    return order


def _is_exhausted(msg: str) -> bool:
    """Квота кончилась — повторять тот же запрос бессмысленно, надо сменить бэкенд."""
    low = msg.lower()
    return any(s in low for s in ("quota", "billing", "exceeded your current",
                                  "rate limit", "capacity"))


def model_name() -> str:
    name = os.environ.get("NEX_MODEL", "").strip()
    return name or DEFAULT_MODELS.get(provider(), "")


def available() -> bool:
    return bool(api_key())


def describe() -> str:
    """Строка для интерфейса: кто отвечает и какой моделью."""
    return f"{_PROVIDER_LABEL.get(provider(), provider())} · {model_name()}"


# --------------------------------------------------------------------------
# Сеть
# --------------------------------------------------------------------------


def _open(url: str, body: dict, headers: dict):
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"), headers=headers)
    try:
        return urllib.request.urlopen(req, timeout=TIMEOUT)
    except urllib.error.HTTPError as e:
        # Читаем тело ЦЕЛИКОМ: раньше обрезали до 1200 байт, JSON рвался
        # посередине, разбор падал — и в интерфейс лез сырой текст.
        raw = e.read().decode("utf-8", "replace")
        msg = raw
        try:
            err = json.loads(raw)
            # У Google — {"error":{"message":…}}, у Mistral — {"message":…}
            msg = (err.get("error", {}).get("message")
                   if isinstance(err.get("error"), dict) else None) \
                or err.get("message") or raw
        except ValueError:
            pass
        raise LLMError(f"HTTP {e.code}: {str(msg).strip()[:200]}") from None
    except Exception as e:
        raise LLMError(f"{type(e).__name__}: {e}") from None


def _code_of(msg: str) -> int | None:
    if msg.startswith("HTTP "):
        try:
            return int(msg.split()[1].rstrip(":"))
        except (IndexError, ValueError):
            return None
    return None


def _request_raw(url: str, body: dict, headers: dict):
    """Запрос с повторами: бесплатные тарифы регулярно отдают 429/503."""
    last = ""
    for attempt in range(RETRIES):
        if attempt:
            time.sleep(RETRY_PAUSE * attempt)
        try:
            return _open(url, body, headers)
        except LLMError as e:
            last = str(e)
            if _is_exhausted(last):
                raise
            code = _code_of(last)
            if code is not None and code not in _RETRY_CODES:
                raise
    raise LLMError(last)


# --------------------------------------------------------------------------
# Схема ответа: описываем один раз, подгоняем под провайдера
# --------------------------------------------------------------------------


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


# --------------------------------------------------------------------------
# Тела запросов по провайдерам
# --------------------------------------------------------------------------


def _mistral_body(system, history, question, temperature, schema, stream,
                  model: str | None = None):
    msgs = [{"role": "system", "content": system}]
    for role, text in history:
        msgs.append({"role": "user" if role == "user" else "assistant",
                     "content": text})
    msgs.append({"role": "user", "content": question})
    body = {
        "model": model or _model_for("mistral"),
        "messages": msgs,
        "temperature": temperature,
        "max_tokens": MAX_TOKENS,
    }
    if stream:
        body["stream"] = True
    if schema:
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "analysis", "schema": schema, "strict": True},
        }
    return body


def _gemini_body(system, history, question, temperature, schema, stream):
    contents = []
    for role, text in history:
        contents.append({"role": "user" if role == "user" else "model",
                         "parts": [{"text": text}]})
    contents.append({"role": "user", "parts": [{"text": question}]})
    cfg = {"temperature": temperature, "maxOutputTokens": MAX_TOKENS}
    if schema:
        cfg["responseMimeType"] = "application/json"
        cfg["responseSchema"] = _schema_for_gemini(schema)
    return {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": contents,
        "generationConfig": cfg,
    }


def _model_for(prov: str) -> str:
    name = os.environ.get("NEX_MODEL", "").strip()
    if name and prov == provider():
        return name
    return DEFAULT_MODELS.get(prov, "")


def _endpoint(stream: bool, prov: str) -> tuple[str, dict]:
    key = _key_for(prov)
    if not key:
        raise LLMError(f"ключ не задан для {_label(prov)}: "
                       f"задайте NEX_API_KEY или ~/.config/nex/key")
    if prov == "mistral":
        return ("https://api.mistral.ai/v1/chat/completions",
                {"Content-Type": "application/json",
                 "Accept": "text/event-stream" if stream else "application/json",
                 "Authorization": f"Bearer {key}"})
    path = "streamGenerateContent" if stream else "generateContent"
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{_model_for(prov)}:{path}?key={key}")
    if stream:
        url += "&alt=sse"
    return url, {"Content-Type": "application/json"}


def _build_body(prov, system, history, question, temperature, schema, stream):
    model = _model_for(prov)
    if prov == "mistral":
        return _mistral_body(system, history, question, temperature,
                             schema, stream, model=model)
    return _gemini_body(system, history, question, temperature, schema, stream)


def _call(system, question, history, temperature, schema=None, stream=False):
    """Возвращает (ответ, провайдер). При квоте пробует второй бэкенд."""
    errors: list[str] = []
    candidates = [p for p in _provider_order() if _key_for(p)]
    if not candidates:
        raise LLMError("ключ не задан: задайте NEX_API_KEY или ~/.config/nex/key")
    for i, prov in enumerate(candidates):
        try:
            url, headers = _endpoint(stream, prov)
            body = _build_body(prov, system, history or [], question,
                               temperature, schema, stream)
            return _request_raw(url, body, headers), prov
        except LLMError as e:
            tagged = f"{_label(prov)}: {e}"
            errors.append(tagged)
            more = i + 1 < len(candidates)
            if more and (_is_exhausted(str(e)) or _code_of(str(e)) in _RETRY_CODES):
                continue
            raise LLMError(tagged) from None
    raise LLMError(" / ".join(errors))


# --------------------------------------------------------------------------
# Разбор ответов
# --------------------------------------------------------------------------


def _text_of(data: dict, prov: str) -> tuple[str, int]:
    """(текст, потрачено токенов) — из ответа любого провайдера."""
    if prov == "mistral":
        choices = data.get("choices") or []
        if not choices:
            raise LLMError("модель не вернула ответ")
        text = (choices[0].get("message", {}).get("content") or "").strip()
        used = int(data.get("usage", {}).get("completion_tokens", 0) or 0)
        if not text:
            raise LLMError(f"пустой ответ (finish={choices[0].get('finish_reason')})")
        return text, used
    cands = data.get("candidates") or []
    if not cands:
        raise LLMError("модель не вернула ответ")
    parts = cands[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts).strip()
    used = int(data.get("usageMetadata", {}).get("candidatesTokenCount", 0) or 0)
    if not text:
        raise LLMError(f"пустой ответ (finishReason={cands[0].get('finishReason')})")
    return text, used


def _delta_of(chunk: dict, prov: str):
    """Кусок текста из потокового события."""
    if prov == "mistral":
        for ch in chunk.get("choices", []):
            piece = ch.get("delta", {}).get("content")
            if piece:
                yield piece
        return
    for cand in chunk.get("candidates", []):
        for part in cand.get("content", {}).get("parts", []):
            piece = part.get("text")
            if piece:
                yield piece


# --------------------------------------------------------------------------
# Публичный интерфейс
# --------------------------------------------------------------------------


def complete(system: str, question: str,
             history: list[tuple[str, str]] | None = None,
             temperature: float = 0.3) -> str:
    resp, prov = _call(system, question, history, temperature)
    with resp:
        data = json.load(resp)
    return _text_of(data, prov)[0]


def structured(system: str, question: str, schema: dict,
               temperature: float = 0.1) -> tuple[str, int]:
    """Ответ строго по схеме. Возвращает (JSON-строка, потрачено токенов)."""
    resp, prov = _call(system, question, [], temperature, schema=schema)
    with resp:
        data = json.load(resp)
    return _text_of(data, prov)


def stream(system: str, question: str,
           history: list[tuple[str, str]] | None = None,
           temperature: float = 0.3):
    """Ответ по частям: текст появляется по мере генерации.

    Ожидание в 5–10 секунд без признаков жизни выглядит как зависание, поэтому
    в диалоге используется именно потоковый режим.
    """
    resp, prov = _call(system, question, history, temperature, stream=True)
    with resp:
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if not payload or payload == "[DONE]":
                continue
            try:
                chunk = json.loads(payload)
            except ValueError:
                continue
            yield from _delta_of(chunk, prov)


def check() -> tuple[bool, str]:
    """Быстрая проверка доступности — для команды /ai."""
    try:
        txt = complete("Отвечай одним словом.", "Скажи «готово».", temperature=0.0)
        return True, f"{describe()}: {txt.strip()[:40]}"
    except LLMError as e:
        return False, str(e)
