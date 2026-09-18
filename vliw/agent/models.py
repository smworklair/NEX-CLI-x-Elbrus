"""Живой каталог моделей: что доступно именно этому ключу.

Правило окна МОДЕЛЬ: без ключа списка нет. Каталог грузится только после
вставки ключа (или URL у Local) — живых данных, которым можно верить, иначе
не бывает. Выдуманных «проверенных списков» здесь нет: неверное имя модели —
это 404 за деньги пользователя, а угаданный список именно к этому и ведёт.

Контракт `catalog(provider, api_key="", base_url="", folder="")`:
  * `("live", rows)` — сервер отдал список, клик применяется сразу;
  * `("locked", [])` — нужен ключ/URL/folder, в сеть не ходили;
  * `("unsupported", [])` — списка у провайдера нет: ручной ввод ID
    с платной проверкой через API (yandex);
  * `("text", [])` — провайдер скрыт из каталога (`custom`, `local`).
Ошибки сети и неверный ключ — исключением `LLMError` с готовым русским
текстом (без секретов внутри): окно показывает его как есть.

Только стандартная библиотека. Кэш — в памяти процесса, ключом
(провайдер, ключ, адрес): смена ключа даёт свежий список, перезапуск
всё забывает — как и сами ключи.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass

from .backends._loopback import local_base_url
from .backends.base import LLMError

__all__ = ["ModelRow", "catalog", "local_base_url", "reset_cache"]

_TIMEOUT = 10.0

_CACHE: dict[tuple[str, str, str, str], list] = {}


@dataclass(frozen=True)
class ModelRow:
    id: str
    label: str
    free: bool | None


def reset_cache() -> None:
    _CACHE.clear()


def _fetch_json(url: str, headers: dict | None = None,
                timeout: float = _TIMEOUT) -> dict:
    import urllib.error

    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        try:
            raw = e.read().decode("utf-8", "replace")
        except Exception:
            raw = ""
        msg = _short_message(raw) or f"HTTP {e.code}"
        if e.code in (401, 403):
            raise LLMError(f"ключ отклонён (HTTP {e.code}): вставь заново"
                           + (f" — {msg}" if msg else "")) from None
        if e.code == 404:
            raise LLMError("сервер не знает такого списка "
                           f"(HTTP 404): {msg}") from None
        raise LLMError(f"сервер не отдал каталог (HTTP {e.code}): "
                       f"{msg}") from None
    except LLMError:
        raise
    except Exception as e:  # noqa: BLE001 — сеть даёт что угодно
        raise LLMError(f"нет сети: {type(e).__name__} — проверь соединение "
                       "и повтори") from None


def _short_message(raw: str) -> str:
    try:
        err = json.loads(raw)
    except ValueError:
        return raw.strip()[:160]
    if isinstance(err, dict):
        sub = err.get("error")
        if isinstance(sub, dict) and sub.get("message"):
            return str(sub["message"])[:160]
        if isinstance(sub, str):
            return sub[:160]
        if err.get("message"):
            return str(err["message"])[:160]
    return ""


def _openai_rows(data: dict) -> list[ModelRow]:
    items = data.get("data") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise LLMError("сервер вернул странный каталог: нет списка data")
    rows = []
    for m in items:
        if not isinstance(m, dict) or not m.get("id"):
            continue
        mid = str(m["id"])
        rows.append(ModelRow(id=mid, label=str(m.get("name") or mid),
                             free=None))
    rows.sort(key=lambda r: r.id)
    return rows


def _mistral_rows(key: str) -> list[ModelRow]:
    data = _fetch_json("https://api.mistral.ai/v1/models",
                       {"Authorization": f"Bearer {key}"})
    return _openai_rows(data)


def _gemini_rows(key: str) -> list[ModelRow]:
    url = ("https://generativelanguage.googleapis.com/v1beta/models"
           "?pageSize=1000")
    data = _fetch_json(url, {"x-goog-api-key": key})
    items = data.get("models") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise LLMError("сервер вернул странный каталог: нет списка models")
    rows = []
    for m in items:
        if not isinstance(m, dict):
            continue
        name = str(m.get("name", ""))
        mid = name.split("/", 1)[1] if "/" in name else name
        if not mid:
            continue
        methods = m.get("supportedGenerationMethods") or []
        if methods and "generateContent" not in methods:
            continue
        rows.append(ModelRow(id=mid,
                             label=str(m.get("displayName") or mid),
                             free=None))
    rows.sort(key=lambda r: r.id)
    return rows


def _anthropic_rows(key: str) -> list[ModelRow]:
    data = _fetch_json("https://api.anthropic.com/v1/models?limit=1000",
                       {"x-api-key": key,
                        "anthropic-version": "2023-06-01"})
    items = data.get("data") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise LLMError("сервер вернул странный каталог: нет списка data")
    rows = [ModelRow(id=str(m["id"]),
                     label=str(m.get("display_name") or m["id"]), free=None)
            for m in items
            if isinstance(m, dict) and m.get("id")]
    rows.sort(key=lambda r: r.id)
    return rows


def _openrouter_rows(key: str) -> list[ModelRow]:
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    data = _fetch_json("https://openrouter.ai/api/v1/models", headers)
    items = data.get("data") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise LLMError("сервер вернул странный каталог: нет списка data")
    rows = [ModelRow(id=str(m["id"]), label=str(m.get("name") or m["id"]),
                     free=str(m.get("id", "")).endswith(":free"))
            for m in items
            if isinstance(m, dict) and m.get("id")]
    rows.sort(key=lambda r: (not r.free, r.id))
    return rows


def _compat_rows(base_url: str, key: str) -> list[ModelRow]:
    url = base_url.rstrip("/") + "/models"
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    return _openai_rows(_fetch_json(url, headers))


def _gigachat_rows(pair: str) -> list[ModelRow]:
    import base64
    import uuid

    if ":" in pair:
        cid, _, sec = pair.partition(":")
    else:
        try:
            raw = base64.b64decode(pair.strip(), validate=True).decode("ascii")
        except Exception:
            raise LLMError("GigaChat: нужна пара id:secret") from None
        if raw.count(":") != 1:
            raise LLMError("GigaChat: нужна пара id:secret") from None
        cid, _, sec = raw.partition(":")
    cid, sec = cid.strip(), sec.strip()
    if not cid or not sec:
        raise LLMError("GigaChat: нужна пара id:secret")
    basic = base64.b64encode(f"{cid}:{sec}".encode()).decode()
    body = urllib.parse.urlencode({"scope": "GIGACHAT_API_PERS"}).encode()
    req = urllib.request.Request(
        "https://ngw.devices.sberbank.ru:9443/api/v2/oauth", data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded",
                 "Accept": "application/json", "RqUID": str(uuid.uuid4()),
                 "Authorization": f"Basic {basic}"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            tok = json.load(resp)
    except Exception as e:  # noqa: BLE001
        raise LLMError(f"GigaChat OAuth не дал токен: {type(e).__name__}") from None
    access = tok.get("access_token", "") if isinstance(tok, dict) else ""
    if not access:
        raise LLMError("GigaChat OAuth: нет access_token в ответе")
    data = _fetch_json("https://api.giga.chat/v1/models",
                       {"Authorization": f"Bearer {access}"})
    items = data.get("data") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise LLMError("сервер вернул странный каталог: нет списка data")
    rows = []
    for m in items:
        if not isinstance(m, dict):
            continue
        mid = str(m.get("id") or m.get("id_") or m.get("name") or "")
        if mid:
            rows.append(ModelRow(id=mid, label=mid, free=None))
    rows.sort(key=lambda r: r.id)
    return rows


_COMPAT_BASE = {
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com",
    "qwen": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    "kimi": "https://api.moonshot.ai/v1",
    "vercel": "https://ai-gateway.vercel.sh/v1",
    "grok": "https://api.x.ai/v1",
    "glm": "https://api.z.ai/api/paas/v4",
    "muse": "https://api.meta.ai/v1",
}


def catalog(provider: str, api_key: str = "",
            base_url: str = "", folder: str = "") -> tuple[list[ModelRow], str]:
    if provider in ("custom", "local"):
        return [], "text"
    if provider == "local-server":
        try:
            url = local_base_url(base_url or "http://localhost:11434/v1")
        except ValueError as e:
            raise LLMError(str(e)) from None
        key = (api_key or "").strip()
        cache_key = (provider, key, url, "")
        if cache_key in _CACHE:
            return list(_CACHE[cache_key]), "live"
        rows = _compat_rows(url, key if key != "local" else "")
        _CACHE[cache_key] = rows
        return list(rows), "live"
    if provider == "yandex":
        return [], "unsupported"
    if provider not in _COMPAT_BASE and provider not in (
            "mistral", "gemini", "anthropic", "openrouter", "gigachat"):
        return [], "text"
    key = (api_key or "").strip()
    if provider == "gigachat":
        if not key:
            return [], "locked"
    elif not key:
        return [], "locked"
    cache_key = (provider, key, base_url.strip(), "")
    if cache_key in _CACHE:
        return list(_CACHE[cache_key]), "live"
    if provider == "mistral":
        rows = _mistral_rows(key)
    elif provider == "gemini":
        rows = _gemini_rows(key)
    elif provider == "anthropic":
        rows = _anthropic_rows(key)
    elif provider == "openrouter":
        rows = _openrouter_rows(key)
    elif provider == "gigachat":
        rows = _gigachat_rows(key)
    elif provider == "deepseek":
        rows = _compat_rows("https://api.deepseek.com", key)
    else:
        rows = _compat_rows(base_url.strip() or _COMPAT_BASE[provider], key)
    _CACHE[cache_key] = rows
    return list(rows), "live"
