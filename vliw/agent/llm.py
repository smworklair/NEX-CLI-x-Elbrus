"""Клиент языковой модели: фабрика поверх `backends/` (концепт Nex-pilot).

Провайдер — это backend с единым интерфейсом (`backends/base.py:Backend`):
верхние слои (`agent.py`, `analyst.py`) не знают, куда ушёл запрос.
Добавление нового API — новый файл в `backends/` + строка в реестре ниже.

Поддерживаются (выбор — `NEX_PROVIDER`):
  * `mistral` — Le Chat / Mistral AI — по умолчанию;
  * `gemini`  — Google AI Studio;
  * `openai` / `deepseek` / `qwen` / `kimi` / `grok` (xAI) / `glm` (Z.ai) —
    готовые пресеты поверх OpenAI-совместимого API
    (`backends/openai_compat.py`);
  * `anthropic` — Claude API (`backends/anthropic.py`);
  * `muse` — Muse Spark, Meta Model API (`backends/muse.py`);
  * `openrouter` — агрегатор OpenRouter (свой ключ `OPENROUTER_API_KEY`);
  * `vercel` — агрегатор Vercel AI Gateway;
  * `local-server` — Local: свой сервер на loopback
    (Ollama / LM Studio / llama.cpp, только `NEX_LOCAL_URL`);
  * `custom` — legacy: любой другой OpenAI-совместимый сервер
    (`NEX_BASE_URL` + `NEX_MODEL`, в каталоге скрыт);
  * `gigachat` — Сбер GigaChat (OAuth по client_id/secret);
  * `yandex` (`yandexgpt`) — Yandex Cloud (API-ключ или IAM + folder_id);
  * `local` — внутренний режим машины (llama-server, см. `local.py`;
    в каталоге скрыт, Local настраивается отдельно).

Ключ берётся так (ничего из этого не идёт в git):
  1. `NEX_API_KEY` в окружении (общий; для GigaChat — вид "id:secret");
  2. `~/.config/nex/key` (тот же формат, вне репозитория);
  3. `.env` в корне проекта: сначала переменная провайдера
     (`MISTRAL_API_KEY=...` и т.д.), потом общий `NEX_API_KEY`
     (файл в `.gitignore`, формат — в `.env.example`).
Неключевые настройки (`NEX_PROVIDER`, `NEX_MODEL`, адреса, folder) —
окружение поверх `.env` (см. `setting()`), поэтому смена через `/ai`
переживает перезапуск.

Без ключа в сеть не ходим: агент честно сообщает, что модель недоступна, и
отвечает офлайн по уже посчитанным числам.

БЫЛО (до 17.08.2026): здесь лежали два настоящих ключа текстом — `EMBEDDED_KEYS
= {"mistral": "...", "gemini": "..."}`, «одноразовые аккаунты, чтобы демо
работало сразу после клонирования». Оба закоммичены и найдены при разборе
`git log --all -p`. Ключи отозваны у провайдера, из кода убраны. См.
`.env.example` — теперь то же удобство даёт файл вне git, а не строка в коде.
"""

from __future__ import annotations

import os
from pathlib import Path

from . import local
from . import envfile
from .backends.anthropic import AnthropicBackend
from .backends.base import Backend, LLMError
from .backends.gemini import GeminiBackend
from .backends.gigachat import GigaChatBackend
from .backends.mistral import MistralBackend
from .backends.muse import MuseBackend
from .backends.openai_compat import OpenAICompatBackend
from .backends.yandex import YandexBackend

__all__ = ["LLMError", "DEFAULT_PROVIDER", "PROVIDERS", "KEY_VAR", "provider",
           "normalize_provider", "provider_updates", "key_updates",
           "key_source_hint", "setting",
           "looks_like_key_text", "adopt_pasted_key", "has_session_key",
           "api_key", "model_name",
           "available", "describe", "is_local", "complete", "structured",
           "stream", "check", "project_env_path", "configured_backend"]

# Все провайдеры, которых понимает NEX_PROVIDER (каноничные имена).
PROVIDERS = ("mistral", "gemini", "openai", "deepseek", "qwen", "kimi",
             "vercel", "custom", "gigachat", "yandex", "local",
             "grok", "anthropic", "glm", "muse", "openrouter", "local-server")

# Провайдер по умолчанию, если ничего не задано и ключ не опознан.
DEFAULT_PROVIDER = "mistral"

_ENV_VAR = {"mistral": "MISTRAL_API_KEY", "gemini": "GEMINI_API_KEY",
            "openai": "OPENAI_API_KEY", "deepseek": "DEEPSEEK_API_KEY",
            "qwen": "QWEN_API_KEY", "kimi": "KIMI_API_KEY",
            "vercel": "VERCEL_API_KEY",
            "grok": "XAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY",
            "glm": "ZAI_API_KEY", "muse": "META_API_KEY",
            "openrouter": "OPENROUTER_API_KEY", "local-server": "NEX_LOCAL_KEY",
            "custom": "NEX_API_KEY"}
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def project_env_path() -> Path:
    """Путь к `.env` в корне проекта (файл в `.gitignore`, не коммитится)."""
    return _PROJECT_ROOT / ".env"


def _dotenv_values() -> dict[str, str]:
    """Разбор `.env` в корне проекта — без внешних зависимостей."""
    return envfile.load(project_env_path())


def setting(name: str, default: str = "") -> str:
    """Неключевая настройка: окружение побеждает `.env`, дальше — умолчание.

    Ключи здесь намеренно НЕ ищутся (у них свой порядок в `_key_for`).
    Читается при каждом вызове — смена через `/ai` действует сразу и
    переживает перезапуск (CLI сохраняет в `.env`).
    """
    got = os.environ.get(name, "").strip()
    if got:
        return got
    return _dotenv_values().get(name, "").strip() or default


def _embedded_key(prov: str) -> str:
    """Ключ из `.env` (если он там есть) — единственный «встроенный» слой."""
    return _dotenv_values().get(_ENV_VAR.get(prov, ""), "")


DEFAULT_MODELS = {
    "mistral": "mistral-small-latest",
    "gemini": "gemini-2.5-flash",
    "openai": "gpt-4o-mini",
    "deepseek": "deepseek-chat",
    "qwen": "qwen-plus",
    "kimi": "moonshot-v1-8k",
    "vercel": "openai/gpt-5.4",
    "custom": "",
    "grok": "grok-4.6",
    "anthropic": "claude-sonnet-4-5",
    "glm": "glm-5.3",
    "muse": "muse-spark-1.3",
    "openrouter": "deepseek/deepseek-chat",
    "local-server": "",
    "gigachat": "GigaChat",
    "yandex": "yandexgpt",
    "local": "phi-4-mini-instruct (4 бита, llama-server)",
}

_PROVIDER_LABEL = {
    "mistral": "le chat",
    "gemini": "gemini",
    "openai": "openai",
    "deepseek": "deepseek",
    "qwen": "qwen",
    "kimi": "kimi",
    "vercel": "vercel",
    "grok": "grok",
    "anthropic": "anthropic",
    "glm": "glm",
    "muse": "muse spark",
    "openrouter": "openrouter",
    "local-server": "Local",
    "custom": "custom",
    "gigachat": "gigachat",
    "yandex": "yandexgpt",
    "local": "локально",
}

TIMEOUT = 60
# Модели с «размышлением» тратят часть бюджета на него, поэтому лимит с запасом:
# иначе ответ обрывается на полуслове.
MAX_TOKENS = 4000

RETRIES = 3
RETRY_PAUSE = 2.0


# --------------------------------------------------------------------------
# Выбор провайдера, ключа и модели
# --------------------------------------------------------------------------

_ALIASES = {
    "lechat": "mistral", "le-chat": "mistral",
    "google": "gemini",
    "openrouter": "openrouter", "ollama": "local-server", "vllm": "local-server",
    "local-server": "local-server", "lmstudio": "local-server",
    "grok": "grok", "xai": "grok", "x.ai": "grok",
    "anthropic": "anthropic", "claude": "anthropic",
    "glm": "glm", "zai": "glm", "z.ai": "glm",
    "muse": "muse", "meta": "muse", "muse-spark": "muse", "muse spark": "muse",
    "openai-compat": "custom", "compat": "custom",
    "yandexgpt": "yandex",
    "giga": "gigachat",
    "local": "local", "локально": "local", "llama": "local", "offline": "local",
    "mistral": "mistral", "gemini": "gemini",
    "openai": "openai", "deepseek": "deepseek", "qwen": "qwen",
    "kimi": "kimi", "vercel": "vercel", "custom": "custom",
    "gigachat": "gigachat", "yandex": "yandex",
}

_OPENAI_COMPAT = {"openai", "deepseek", "qwen", "kimi", "vercel", "custom",
                  "grok", "glm", "openrouter", "local-server"}

#: Куда `/key` кладёт ключ для каждого однопарольного провайдера.
#: У gigachat пара (id+secret), у yandex ключ + отдельно folder — их `/key`
#: разбирает `key_updates()` ниже.
KEY_VAR = {"mistral": "MISTRAL_API_KEY", "gemini": "GEMINI_API_KEY",
           "openai": "OPENAI_API_KEY", "deepseek": "DEEPSEEK_API_KEY",
           "qwen": "QWEN_API_KEY", "kimi": "KIMI_API_KEY",
           "vercel": "VERCEL_API_KEY",
           "custom": "NEX_API_KEY", "yandex": "YANDEX_API_KEY",
           "grok": "XAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY",
           "glm": "ZAI_API_KEY", "muse": "META_API_KEY",
           "openrouter": "OPENROUTER_API_KEY", "local-server": "NEX_LOCAL_KEY"}

#: Где брать ключ: (ссылка, короткая пометка). Показывается в подсказках
#: `/key` и `/ai`, чтобы не надо было лезть в доки за ссылкой.
KEY_SOURCE = {
    "mistral": ("https://console.mistral.ai/api-keys", "бесплатный тариф есть"),
    "gemini": ("https://aistudio.google.com/apikey", "бесплатно"),
    "openai": ("https://platform.openai.com/api-keys", "платно"),
    "deepseek": ("https://platform.deepseek.com/api_keys", "дешево"),
    "qwen": ("https://bailian.console.aliyun.com/", "Alibaba Model Studio"),
    "kimi": ("https://platform.moonshot.ai/console/api-keys", "платно"),
    "vercel": ("https://vercel.com/docs/ai-gateway", "один ключ на сотни моделей"),
    "grok": ("https://docs.x.ai", "xAI API"),
    "anthropic": ("https://platform.claude.com", "Anthropic API"),
    "glm": ("https://docs.z.ai", "Z.ai API"),
    "muse": ("https://ai.developer.meta.com/docs/models", "Muse Spark"),
    "openrouter": ("https://openrouter.ai", "OpenRouter API"),
    "local-server": ("", "Local: loopback server, NEX_LOCAL_URL/MODEL/KEY"),
    "custom": ("", "адрес и ключ вашего сервера "
                   "(Ollama: url=http://localhost:11434/v1, ключ любой)"),
    "gigachat": ("https://developers.sber.ru/portal/products/gigachat",
                 "Сбер, OAuth-пара"),
    "yandex": ("https://yandex.cloud/ru/docs/foundation-models/operations/api-key/get",
               "нужен ещё каталог: /ai yandex folder=..."),
}


def key_source_hint(prov: str) -> str:
    """Одна строка «где взять ключ» для подсказок CLI."""
    url, note = KEY_SOURCE.get(prov, ("", ""))
    if url:
        return f"взять: {url} ({note})"
    return f"взять: {note}" if note else ""


def key_updates(prov: str, parts: list[str]) -> dict[str, str]:
    """Переменные окружения для вставки ключа (`/key`, `/ai ... key=...`).

    Чистая функция: ничего не пишет, только решает КУДА. Пишет вызывающий
    (через `envfile.save` + `os.environ`), чтобы было видно и тестируемо.
    """
    if prov == "gigachat":
        if len(parts) == 2:
            return {"GIGACHAT_CLIENT_ID": parts[0], "GIGACHAT_SECRET": parts[1]}
        if len(parts) == 1 and ":" in parts[0]:
            cid, _, sec = parts[0].partition(":")
            if cid.strip() and sec.strip():
                return {"GIGACHAT_CLIENT_ID": cid.strip(),
                        "GIGACHAT_SECRET": sec.strip()}
        raise LLMError("GigaChat — пара OAuth: /key <client_id> <client_secret> "
                       "или /ai gigachat key=<id>:<secret>")
    if len(parts) != 1 or not parts[0].strip():
        raise LLMError(f"форма: /key <ключ>  (провайдер {_label(prov)})")
    return {KEY_VAR.get(prov, "NEX_API_KEY"): parts[0].strip()}


def repair_pasted_key(part: str) -> tuple[str, list[str]]:
    """Починить вставку ключа: склейка, мусор, хвост.

    Живой случай: ключ в буфере уже склеенный (вставили дважды или со
    словом спереди — видели 146 символов при норме 73), и ругаться
    бесполезно: человек вставит то же самое ещё раз. Правила узкие и
    безопасные — чинят только то, что настоящим ключом быть не может:
      * точная склейка из двух одинаковых половин — взять одну;
      * мусор спереди (`misterialsk-or-v1-…`) — резать до `sk-or-v1-`;
      * хвост длиннее 73 у `sk-or-v1-…` (норма OpenRouter) — обрезать.
    Возвращает (чистый_ключ, что_убрано). Пустой список — вставка чистая.
    """
    notes: list[str] = []
    s = "".join(part.split())
    if len(s) % 2 == 0 and len(s) >= 40 and s[:len(s) // 2] == s[len(s) // 2:]:
        s = s[:len(s) // 2]
        notes.append("склейка из двух одинаковых половин — взял одну")
    i = s.find("sk-or-v1-")
    if i > 0:
        s = s[i:]
        notes.append("убран мусор спереди")
    if s.startswith("sk-or-v1-") and len(s) > 73:
        s = s[:73]
        notes.append("хвост обрезан до нормы 73")
    return s, notes


def looks_like_key_text(line: str) -> bool:
    """Похоже ли введённое на ключ, а не на вопрос (для строки ввода АГЕНТА).

    Ошибка в любую сторону стоит дорого: вопрос, съеденный как ключ, —
    потерянный вопрос; ключ, ушедший вопросом в историю, — засвеченный
    секрет. Поэтому правило консервативное: ключ — это один длинный токен
    без пробелов (настоящие ключи — от 20 символов) либо узнаваемый вид
    (sk-or-v1, AIza, пара id:secret), либо пара длинных токенов.
    «Привет» и «почему медленно» под него не подпадают — проверено тестами.
    """
    s = (line or "").strip()
    if not s or s.startswith("/"):
        return False
    parts = s.split()
    if len(parts) == 1:
        p = parts[0]
        return (len(p) >= 20 or "sk-or-v1-" in p
                or p.startswith("AIza") or p.startswith("AQ.")
                or (":" in p and "/" not in p))
    if len(parts) == 2:
        return len(parts[0]) >= 16 and len(parts[1]) >= 16
    return False


def adopt_pasted_key(text: str) -> tuple[str, str, list[str]]:
    """Вставленный ключ → провайдер, сохранение, сводка для ответа.

    Провайдер угадывается по виду ключа (как `_key_fits`, только наоборот):
    sk-or-v1 — OpenRouter (custom + его адрес/модель по умолчанию, если своих
    нет), AIza — Gemini, id:secret — GigaChat, остальное — Mistral (дефолт).
    Возвращает (подпись_провайдера, замаскированный_ключ, что_починили).

    Сохранение — ТОЛЬКО в память процесса (`os.environ`), на диск ничего не
    пишется: вставил на сессию — закрыл терминал — ключа нет. Это требование
    к экрану АГЕНТА (см. `AgentScreen`).
    """
    s = " ".join((text or "").split())
    if not s:
        raise LLMError("пусто — вставь ключ одной строкой")
    parts = s.split(" ")
    repaired_notes: list[str] = []
    if len(parts) == 1:
        # Починка — до угадывания провайдера: иначе склеенный ключ
        # опознаётся неверно, а обрезанный — вообще никак.
        parts[0], repaired_notes = repair_pasted_key(parts[0])
    if len(parts) == 2:
        prov = "gigachat"
        key_parts = parts
    elif len(parts) == 1 and "sk-or-v1-" in parts[0]:
        prov, key_parts = "openrouter", parts
    elif len(parts) == 1 and parts[0].startswith("vck_"):
        prov, key_parts = "vercel", parts
    elif len(parts) == 1 and _looks_google(parts[0]):
        prov, key_parts = "gemini", parts
    elif len(parts) == 1 and ":" in parts[0] and "/" not in parts[0]:
        prov, key_parts = "gigachat", parts
    elif len(parts) == 1 and try_decode_gigachat_key(parts[0]) is not None:
        cid, sec = try_decode_gigachat_key(parts[0])  # type: ignore[misc]
        prov, key_parts = "gigachat", [cid, sec]
        repaired_notes = repaired_notes + ["готовый ключ Сбера разобран на пару"]
    else:
        prov, key_parts = "mistral", parts
    updates: dict[str, str | None] = {"NEX_PROVIDER": prov}
    updates.update(key_updates(prov, key_parts))
    if prov == "custom":
        if not setting("NEX_BASE_URL", ""):
            updates["NEX_BASE_URL"] = "https://openrouter.ai/api/v1"
        if not setting("NEX_MODEL", ""):
            updates["NEX_MODEL"] = "deepseek/deepseek-chat"
    for k, v in updates.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    label = _label(prov)
    shown = envfile.mask(parts[0]) if len(parts) == 1 else (
        f"id {envfile.mask(parts[0])}")
    return label, shown, repaired_notes


def has_session_key() -> bool:
    """Есть ли ключ в ЭТОЙ сессии (память), а не в сохранённых файлах.

    Экран АГЕНТА живёт одну сессию: вставил — работаешь, закрыл терминал —
    ключа нет. Поэтому просьбу вставить показывают именно по этому флагу,
    а не по `available()` (тот видит и `.env`, и `~/.config/nex/key`).
    """
    if provider() == "local":
        return local.ready()
    e = os.environ
    if provider() == "local-server":
        return bool(e.get("NEX_LOCAL_MODEL", "").strip())
    if provider() == "gigachat":
        if e.get("GIGACHAT_CLIENT_ID", "").strip() and (
                e.get("GIGACHAT_SECRET", "").strip()
                or e.get("GIGACHAT_CLIENT_SECRET", "").strip()):
            return True
        return ":" in e.get("NEX_API_KEY", "")
    if provider() == "yandex":
        return bool(e.get("YANDEX_API_KEY", "").strip()
                    or e.get("YANDEX_IAM_TOKEN", "").strip())
    var = KEY_VAR.get(provider(), "NEX_API_KEY")
    return bool(e.get(var, "").strip() or e.get("NEX_API_KEY", "").strip())


def provider_updates(prov: str, kv: dict[str, str]) -> dict[str, str | None]:
    """Настройки смены провайдера (`/ai ...`, окно каталога): проверки + словарь.

    Чистая функция: ничего не пишет, только решает ЧТО. Пишет вызывающий
    (в память сессии — см. `AgentScreen`, `cli._ai_save`), чтобы было видно
    и тестируемо. Ошибки — как LLMError с готовым текстом для вывода.
    """
    if prov == "local-server":
        from . import models

        validator = getattr(models, "local_base_url", None)
        if validator is None:
            raise LLMError("Local URL validator is unavailable")
        try:
            url = validator(kv.get("url") or setting("NEX_LOCAL_URL", "http://localhost:11434/v1"))
        except ValueError as e:
            raise LLMError(str(e)) from None
        if not url:
            raise LLMError("Local requires a loopback HTTP URL")
        updates = {"NEX_PROVIDER": prov, "NEX_LOCAL_URL": url}
        if kv.get("model"):
            updates["NEX_LOCAL_MODEL"] = kv["model"]
        if kv.get("key"):
            updates["NEX_LOCAL_KEY"] = kv["key"]
        return updates
    updates: dict[str, str | None] = {"NEX_PROVIDER": prov}
    # Чужой NEX_MODEL при смене провайдера — утечка через границу: модель
    # одного API уехала бы в другой. Чистим, если модель явно не задана.
    if kv.get("model"):
        if prov == "yandex":
            updates["YANDEX_MODEL"] = kv["model"]
        elif prov == "gigachat":
            updates["GIGACHAT_MODEL"] = kv["model"]
        else:
            updates["NEX_MODEL"] = kv["model"]
    elif prov not in ("yandex", "gigachat"):
        updates["NEX_MODEL"] = None

    if prov == "custom":
        url = kv.get("url") or setting("NEX_BASE_URL", "")
        if not url:
            raise LLMError("нужен адрес сервера: /ai custom url=... model=... key=... "
                           "(например, url=https://openrouter.ai/api/v1)")
        updates["NEX_BASE_URL"] = url
    elif prov == "gigachat":
        cid = kv.get("id") or setting("GIGACHAT_CLIENT_ID", "")
        sec = kv.get("secret") or setting("GIGACHAT_SECRET", "") \
            or setting("GIGACHAT_CLIENT_SECRET", "")
        if kv.get("key"):
            pair = key_updates("gigachat", [kv["key"]])
            cid, sec = pair["GIGACHAT_CLIENT_ID"], pair["GIGACHAT_SECRET"]
        if not cid or not sec:
            raise LLMError("нужна пара OAuth: /ai gigachat key=<id>:<secret> "
                           "(или id=... secret=... — или короче: /key <id> <secret>)")
        updates["GIGACHAT_CLIENT_ID"] = cid
        updates["GIGACHAT_SECRET"] = sec
        if kv.get("scope"):
            updates["GIGACHAT_SCOPE"] = kv["scope"]
    elif prov == "yandex":
        folder = kv.get("folder") or setting("YANDEX_FOLDER_ID", "")
        if not folder:
            raise LLMError("нужен каталог: /ai yandex folder=... key=...")
        updates["YANDEX_FOLDER_ID"] = folder

    if kv.get("key") and prov != "gigachat":
        updates.update(key_updates(prov, [kv["key"]]))
    return updates


def normalize_provider(name: str) -> str | None:
    """Каноничное имя провайдера из вольного написания (алиасы — как в Nex-pilot)."""
    key = (name or "").strip().lower()
    if not key:
        return None
    got = _ALIASES.get(key)
    return got if got in PROVIDERS else None


def _looks_google(key: str) -> bool:
    return key.startswith("AIza") or key.startswith("AQ.")


def try_decode_gigachat_key(token: str) -> tuple[str, str] | None:
    """Готовый ключ авторизации Сбера — это base64(client_id:client_secret).

    В личном кабинете лежит именно готовая строка, а не пара отдельно, и
    человек вставляет её как есть (видели живьём: 100 символов base64).
    Проверка строгая: валидный base64, внутри печатный ASCII, ровно одно
    двоеточие, обе части от 8 символов — случайный чужой ключ сюда попасть
    не может физически.
    """
    import base64
    import string

    s = (token or "").strip()
    if not s or len(s) < 24 or len(s) % 4:
        return None
    if any(c not in string.ascii_letters + string.digits + "+/=" for c in s):
        return None
    try:
        raw = base64.b64decode(s, validate=True).decode("ascii")
    except Exception:
        return None
    if raw.count(":") != 1:
        return None
    cid, _, sec = raw.partition(":")
    if len(cid.strip()) < 8 or len(sec.strip()) < 8:
        return None
    if any(c not in string.printable or c in " \t\r\n" for c in raw):
        return None
    return cid.strip(), sec.strip()


def provider() -> str:
    """Провайдер меняется только явно: NEX_PROVIDER. Иначе — Le Chat.

    Раньше ключ Gemini в NEX_API_KEY / ~/.config/nex/key молча переключал
    агента на Google — и «привет» уходил в исчерпанную квоту.
    Для новых провайдеров (gigachat/yandex/openai-совместимые) автовыбора
    по виду ключа нет — их включают явно через NEX_PROVIDER.
    """
    name = normalize_provider(setting("NEX_PROVIDER", ""))
    if name:
        return name
    raw = setting("NEX_PROVIDER", "")
    if raw:
        return raw  # неизвестное имя — честно упадёт в _make_backend с подсказкой
    # Без ключа и без явного выбора — локальная модель, если она есть. Это не
    # «запасной вариант похуже», а нормальный режим: агент и так строит ответ
    # поверх посчитанных чисел, языковая модель отвечает только за
    # формулировку. Зато без сети, без ключа и без чужой квоты.
    if not _raw_key() and local.ready():
        return "local"
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
    except (OSError, RuntimeError):
        pass
    return ""


def _key_fits(key: str, prov: str) -> bool:
    google = _looks_google(key)
    return google if prov == "gemini" else not google


def _key_for(prov: str) -> str:
    if prov == "local-server":
        return setting("NEX_LOCAL_KEY", "") or "local"
    specific = os.environ.get(KEY_VAR.get(prov, ""), "").strip()
    if specific:
        return specific
    if prov in _OPENAI_COMPAT:
        raw = _raw_key()
        if raw:
            return raw
        # Ключ конкретного совместимого провайдера из `.env` — точнее общего.
        emb = _embedded_key(prov)
        if emb:
            return emb
        gen = _dotenv_values().get("NEX_API_KEY", "")
        return gen.strip().strip('"').strip("'")
    if prov in ("gigachat", "yandex"):
        # У этих провайдеров аутентификация не одним ключом — наличие
        # проверяет сам backend; здесь возвращаем то, что есть, для `available()`.
        return _raw_key() or "configured"
    raw = _raw_key()
    if raw and _key_fits(raw, prov):
        return raw
    emb = _embedded_key(prov)
    if emb:
        return emb
    gen = _dotenv_values().get("NEX_API_KEY", "").strip().strip('"').strip("'")
    if gen and _key_fits(gen, prov):
        return gen
    return ""


def api_key() -> str:
    return _key_for(provider())


def _label(prov: str) -> str:
    return _PROVIDER_LABEL.get(prov, prov)


def _provider_order() -> list[str]:
    primary = provider()
    if primary in ("mistral", "gemini"):
        other = "gemini" if primary == "mistral" else "mistral"
        order = [primary]
        if _key_for(other):
            order.append(other)
        return order
    return [primary]


def _is_exhausted(msg: str) -> bool:
    """Квота кончилась — повторять тот же запрос бессмысленно, надо сменить бэкенд."""
    low = msg.lower()
    return any(s in low for s in ("quota", "billing", "exceeded your current",
                                  "rate limit", "capacity"))


def model_name() -> str:
    if provider() == "local-server":
        return setting("NEX_LOCAL_MODEL", "")
    name = setting("NEX_MODEL", "")
    if name:
        return name
    if provider() == "local":
        return f"{local.model_label()} (4 бита, здесь)"
    if provider() == "custom":
        return setting("NEX_MODEL", "") or "custom"
    if provider() == "yandex":
        return setting("YANDEX_MODEL", "") or DEFAULT_MODELS["yandex"]
    if provider() == "gigachat":
        return setting("GIGACHAT_MODEL", "") or DEFAULT_MODELS["gigachat"]
    return DEFAULT_MODELS.get(provider(), "")


def available() -> bool:
    if provider() == "local":
        return local.ready()
    if provider() in ("gigachat", "yandex", "local-server"):
        try:
            _make_backend(provider())
            return True
        except LLMError:
            return False
    return bool(api_key())


def describe() -> str:
    """Строка для интерфейса: кто отвечает и какой моделью."""
    return f"{_PROVIDER_LABEL.get(provider(), provider())} · {model_name()}"


def is_local() -> bool:
    """Отвечает ли сейчас модель на этой машине, а не чужой сервер."""
    return provider() == "local"


# --------------------------------------------------------------------------
# Фабрика backend'ов
# --------------------------------------------------------------------------


def configured_backend(prov: str, model: str, api_key: str = "",
                       base_url: str = "", folder: str = "") -> Backend:
    prov = normalize_provider(prov) or prov
    if prov == "muse":
        backend = MuseBackend(api_key, base_url=base_url,
                              model=model or setting("NEX_MODEL", ""))
    elif prov == "local-server":
        from . import models

        validator = getattr(models, "local_base_url", None)
        if validator is None:
            from .backends.openai_compat import _is_loopback_url

            validator = _is_loopback_url
        try:
            base_url = validator(base_url or "http://localhost:11434/v1")
        except ValueError as e:
            raise LLMError(str(e)) from None
        backend = OpenAICompatBackend(api_key, base_url=base_url,
                                      model=model, provider=prov)
    elif prov in _OPENAI_COMPAT:
        backend = OpenAICompatBackend(api_key, base_url=base_url, model=model, provider=prov)
    elif prov == "anthropic":
        backend = AnthropicBackend(api_key, base_url=base_url, model=model)
    elif prov == "mistral":
        backend = MistralBackend(api_key, model=model)
    elif prov == "gemini":
        backend = GeminiBackend(api_key, model=model)
    elif prov == "gigachat":
        cid = setting("GIGACHAT_CLIENT_ID", "") if not api_key else ""
        sec = (setting("GIGACHAT_SECRET", "") or setting("GIGACHAT_CLIENT_SECRET", "")) if not api_key else ""
        pair = api_key or (setting("NEX_API_KEY", "") if not (cid and sec) else "")
        if pair:
            decoded = try_decode_gigachat_key(pair)
            if decoded:
                cid, sec = decoded
            elif ":" in pair:
                cid, _, sec = pair.partition(":")
            else:
                raise LLMError("GigaChat requires id:secret or a base64 OAuth pair")
        backend = GigaChatBackend(
            client_id=cid, client_secret=sec, model=model or setting("GIGACHAT_MODEL", ""),
            base_url=base_url or setting("GIGACHAT_BASE_URL", ""),
            auth_url=setting("GIGACHAT_AUTH_URL", ""), scope=setting("GIGACHAT_SCOPE", ""),
            use_env=False)
    elif prov == "yandex":
        backend = YandexBackend(
            api_key=api_key or setting("YANDEX_API_KEY", "") or setting("NEX_API_KEY", ""),
            iam_token="" if api_key else setting("YANDEX_IAM_TOKEN", ""),
            folder_id=folder or setting("YANDEX_FOLDER_ID", ""),
            model=model or setting("YANDEX_MODEL", ""), use_env=False)
    else:
        raise LLMError(f"неизвестный или неподдерживаемый snapshot провайдер {prov!r}")
    backend._frozen = True
    return backend


def _make_backend(prov: str):
    """Backend по имени провайдера. Настройки — env поверх `.env` (см. `setting`)."""
    if prov == "muse":
        return configured_backend(prov, setting("NEX_MODEL", ""), _key_for(prov))
    if prov == "local-server":
        return configured_backend(prov, setting("NEX_LOCAL_MODEL", ""),
                                  setting("NEX_LOCAL_KEY", ""),
                                  setting("NEX_LOCAL_URL", "http://localhost:11434/v1"))
    if prov == "anthropic":
        return configured_backend(prov, setting("NEX_MODEL", ""), _key_for(prov))
    if prov in ("gigachat", "yandex"):
        model_var = "GIGACHAT_MODEL" if prov == "gigachat" else "YANDEX_MODEL"
        return configured_backend(prov, setting(model_var, "") or setting("NEX_MODEL", ""))
    if prov == "mistral":
        return MistralBackend(_key_for("mistral"),
                              model=setting("NEX_MODEL", "") or None)
    if prov == "gemini":
        return GeminiBackend(_key_for("gemini"),
                             model=setting("NEX_MODEL", "") or None)
    if prov in _OPENAI_COMPAT:
        key = _key_for(prov)
        if not key and prov != "custom":
            # Совместимый провайдер без своего ключа — пробуем общий.
            key = _raw_key()
        return OpenAICompatBackend(key, provider=prov,
                                   base_url=setting("NEX_BASE_URL", "") if prov == "custom" else "",
                                   model=setting("NEX_MODEL", ""))
    if prov == "local":
        raise LLMError("локальные веса удалены с диска (см. docs/WINDOWS.md): "
                       "поднимите их через tools/setup_local_llm.sh или "
                       "выберите облачный NEX_PROVIDER")
    raise LLMError(f"неизвестный провайдер {prov!r}: NEX_PROVIDER=mistral|gemini|"
                   "openai|deepseek|qwen|kimi|custom|gigachat|yandex|local")


# --------------------------------------------------------------------------
# Публичный интерфейс
# --------------------------------------------------------------------------


def complete(system: str, question: str,
             history: list[tuple[str, str]] | None = None,
             temperature: float = 0.3, nudge: bool = True) -> str:
    if provider() == "local":
        return local.complete(system, question, history, temperature, nudge=nudge)
    errors: list[str] = []
    for i, prov in enumerate(_provider_order()):
        try:
            return _make_backend(prov).complete(system, question, history, temperature)
        except LLMError as e:
            tagged = f"{_label(prov)}: {e}"
            errors.append(tagged)
            more = i + 1 < len(_provider_order())
            if more and _is_exhausted(str(e)):
                continue
            raise LLMError(tagged) from None
    raise LLMError(" / ".join(errors))


def structured(system: str, question: str, schema: dict,
               temperature: float = 0.1) -> tuple[str, int]:
    """Ответ строго по схеме. Возвращает (JSON-строка, потрачено токенов)."""
    if provider() == "local":
        return local.structured(system, question, schema, temperature)
    errors: list[str] = []
    for i, prov in enumerate(_provider_order()):
        try:
            return _make_backend(prov).structured(system, question, schema, temperature)
        except LLMError as e:
            tagged = f"{_label(prov)}: {e}"
            errors.append(tagged)
            more = i + 1 < len(_provider_order())
            if more and _is_exhausted(str(e)):
                continue
            raise LLMError(tagged) from None
    raise LLMError(" / ".join(errors))


def stream(system: str, question: str,
           history: list[tuple[str, str]] | None = None,
           temperature: float = 0.3, nudge: bool = True):
    """Ответ по частям: текст появляется по мере генерации.

    Ожидание в 5–10 секунд без признаков жизни выглядит как зависание, поэтому
    в диалоге используется именно потоковый режим.

    `nudge` — только для локального провайдера, см. `agent.local`: False для
    реплик не по делу («привет»), иначе модель тащит числа из ФАКТОВ в любой
    ответ. Облачные модели этот параметр игнорируют — им хватает правил
    самого системного промпта.
    """
    if provider() == "local":
        yield from local.stream(system, question, history, temperature,
                               nudge=nudge)
        return
    errors: list[str] = []
    order = _provider_order()
    for i, prov in enumerate(order):
        try:
            yield from _make_backend(prov).stream(system, question, history, temperature)
            return
        except LLMError as e:
            tagged = f"{_label(prov)}: {e}"
            errors.append(tagged)
            more = i + 1 < len(order)
            if more and _is_exhausted(str(e)):
                continue
            raise LLMError(tagged) from None
    raise LLMError(" / ".join(errors))


def _misfit_hint(prov: str, raw: str) -> str:
    """Ключ вставлен, но он явно не от выбранного провайдера — куда с ним.

    Классическая ошибка (видели живьём): в Mistral вставляют ключ OpenRouter
    и получают голый 401. Вид ключа такое палит сразу.
    """
    if not raw:
        return ""
    if "sk-or-v1-" in raw and prov != "openrouter":
        return ("похоже на ключ OpenRouter (sk-or-v1-…) — ему нужен: "
                "/ai openrouter key=... "
                "(ключ — ровно как выдан, без приставок)")
    if try_decode_gigachat_key(raw) is not None and prov != "gigachat":
        return ("похоже на готовый ключ Сбера (id:secret в base64) — ему нужен: "
                "/ai gigachat (или вставь его прямо в АГЕНТЕ)")
    if raw.startswith("vck_") and prov != "vercel":
        return ("похоже на ключ Vercel (vck_…) — ему нужен: "
                "/ai vercel key=... (или вставь его прямо в АГЕНТЕ)")
    if _looks_google(raw) and prov == "mistral":
        return "ключ похож на Gemini (AIza…) — переключите: /ai gemini"
    if prov == "gemini" and not _looks_google(raw) and len(raw) > 12:
        return "ключ не похож на Gemini — для Le Chat: /ai mistral"
    if ":" in raw and "/" not in raw and prov != "gigachat":
        return ("похоже на пару GigaChat (id:secret) — переключите: "
                "/ai gigachat key=<id>:<secret>")
    return ""


def _server_message(msg: str) -> str:
    """Вытащить текст ошибки сервера (для custom).

    Две формы: сырой JSON (`{"error":{"message":"..."}}`) и уже извлечённое
    (`HTTP 401: User not found.`) — HTTP-слой выше обычно уже распарсил тело.
    """
    import re

    m = re.search(r'"message"\s*:\s*"([^"]{1,160})"', msg)
    if m:
        return m.group(1)
    m = re.search(r"HTTP \d{3}:\s*(.{1,160})", msg)
    return m.group(1).strip() if m else ""


def _human_error(prov: str, msg: str, key: str = "") -> str:
    """Сырая ошибка сети → что делать. Показывается в `/ai`, читает человек."""
    label = _label(prov)
    low = msg.lower()
    if "ключ не задан" in msg:
        hint = key_source_hint(prov)
        tail = f" — {hint}" if hint else ""
        return f"ключ не задан ({label}) — вставьте: /key <ключ>{tail}"
    if ("http 401" in low or "http 403" in low or "invalid api" in low
            or "incorrect api" in low or "unauthorized" in low
            or "invalid auth" in low or "не принят" in low):
        # У custom/openrouter за провайдером — чужой сервер со своими
        # причинами («User not found», «insufficient credits»): его текст —
        # главная улика, прятать её за «отклонён» нельзя (проверено живьём).
        detail = _server_message(msg) if prov in ("custom", "openrouter") else ""
        tail = f" Сервер пишет: «{detail}»." if detail else ""
        if prov in ("custom", "openrouter") and key and len(key) > 100:
            tail += (f" Длина ключа {len(key)} при норме ~73 — похоже, "
                     f"вставился дважды или с мусором: вставь ровно один раз, "
                     f"как на сайте.")
        return f"ключ отклонён ({label}) — вставьте заново: /key <ключ>.{tail}"
    if _is_exhausted(msg):
        return f"квота исчерпана ({label}) — смените провайдера: /ai <другой>"
    if "http 404" in low or "not found" in low or "no such model" in low:
        return (f"модель не найдена ({label}) — проверьте имя: "
                f"/ai {prov} model=...")
    return f"{label}: {msg.strip()[:160]}"


def check() -> tuple[bool, str]:
    """Быстрая проверка доступности — для команды /ai."""
    if provider() == "local":
        return local.check()
    try:
        txt = complete("Отвечай одним словом.", "Скажи «готово».", temperature=0.0)
        return True, f"{describe()}: {txt.strip()[:40]}"
    except LLMError as e:
        # Подсказка смотрит на РЕАЛЬНЫЙ ключ (включая `.env`), а не только
        # на окружение: иначе чужой ключ из файла не опознается.
        key = api_key()
        base = _human_error(provider(), str(e), key)
        extra = _misfit_hint(provider(), key)
        return False, base + (". " + extra if extra else "")
