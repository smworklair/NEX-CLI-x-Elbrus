"""Language model client: factory over `backends/` (Nex-pilot pattern).

A provider is a backend implementing `backends/base.py:Backend`: upper layers
(`agent.py`, `analyst.py`) do not care which API handles the request. Adding a
new API means adding one file in `backends/` and one entry in the registry below.

Supported providers (selected via `NEX_PROVIDER`):
  * `mistral` — Le Chat / Mistral AI (default);
  * `gemini`  — Google AI Studio;
  * `openai` / `deepseek` / `qwen` / `kimi` / `grok` (xAI) / `glm` (Z.ai) —
    presets over the OpenAI-compatible API (`backends/openai_compat.py`);
  * `anthropic` — Claude API (`backends/anthropic.py`);
  * `muse` — Muse Spark, Meta Model API (`backends/muse.py`);
  * `openrouter` — OpenRouter aggregator (`OPENROUTER_API_KEY`);
  * `vercel` — Vercel AI Gateway;
  * `local-server` — Local loopback server (Ollama / LM Studio / llama.cpp,
    via `NEX_LOCAL_URL` only);
  * `custom` — legacy: any other OpenAI-compatible server (`NEX_BASE_URL` +
    `NEX_MODEL`, hidden from the live catalog);
  * `gigachat` — Sber GigaChat (OAuth client_id/secret);
  * `yandex` (`yandexgpt`) — Yandex Cloud (API key or IAM + folder_id);
  * `local` — in-process local model (llama-server, see `local.py`).

Key resolution (none of these are committed to git):
  1. `NEX_API_KEY` in environment (generic; for GigaChat, "id:secret");
  2. `~/.config/nex/key` (same format, outside the repo);
  3. `.env` at the project root: provider-specific variable first
     (`MISTRAL_API_KEY=...`, etc.), then generic `NEX_API_KEY`
     (gitignored; see `.env.example`).
Non-key settings (`NEX_PROVIDER`, `NEX_MODEL`, URLs, folder) check env first,
then `.env` (see `setting()`), so changes made via `/ai` persist across restarts.

Without a key, no network requests are made: the agent reports honestly that
the model is unavailable and answers offline from computed facts.
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

# Canonical provider names accepted by NEX_PROVIDER.
PROVIDERS = ("mistral", "gemini", "openai", "deepseek", "qwen", "kimi",
             "vercel", "custom", "gigachat", "yandex", "local",
             "grok", "anthropic", "glm", "muse", "openrouter", "local-server")

# Default provider when nothing is configured and no key is recognized.
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
    """Path to `.env` at the project root (gitignored)."""
    return _PROJECT_ROOT / ".env"


def _dotenv_values() -> dict[str, str]:
    """Parse `.env` at the project root using stdlib only."""
    return envfile.load(project_env_path())


def setting(name: str, default: str = "") -> str:
    """Non-key setting: environment overrides `.env`, then falls back to default.

    Keys are intentionally excluded here (they follow `_key_for`). Read on
    every call so `/ai` changes take effect immediately and survive restarts.
    """
    got = os.environ.get(name, "").strip()
    if got:
        return got
    return _dotenv_values().get(name, "").strip() or default


def _embedded_key(prov: str) -> str:
    """Provider key from `.env` if present."""
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
    "local": "phi-4-mini-instruct (4-bit, llama-server)",
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
    "local": "local",
}

TIMEOUT = 60
# Reasoning models spend part of the budget on thinking — keep a generous cap.
MAX_TOKENS = 4000

RETRIES = 3
RETRY_PAUSE = 2.0


# --------------------------------------------------------------------------
# Provider, key, and model selection
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

#: Environment variable where `/key` stores single-key provider secrets.
#: GigaChat (id+secret) and Yandex (key+folder) are handled by `key_updates()`.
KEY_VAR = {"mistral": "MISTRAL_API_KEY", "gemini": "GEMINI_API_KEY",
           "openai": "OPENAI_API_KEY", "deepseek": "DEEPSEEK_API_KEY",
           "qwen": "QWEN_API_KEY", "kimi": "KIMI_API_KEY",
           "vercel": "VERCEL_API_KEY",
           "custom": "NEX_API_KEY", "yandex": "YANDEX_API_KEY",
           "grok": "XAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY",
           "glm": "ZAI_API_KEY", "muse": "META_API_KEY",
           "openrouter": "OPENROUTER_API_KEY", "local-server": "NEX_LOCAL_KEY"}

#: Where to obtain an API key: (url, short note) shown in `/key` and `/ai` hints.
KEY_SOURCE = {
    "mistral": ("https://console.mistral.ai/api-keys", "free tier available"),
    "gemini": ("https://aistudio.google.com/apikey", "free tier"),
    "openai": ("https://platform.openai.com/api-keys", "paid"),
    "deepseek": ("https://platform.deepseek.com/api_keys", "low cost"),
    "qwen": ("https://bailian.console.aliyun.com/", "Alibaba Model Studio"),
    "kimi": ("https://platform.moonshot.ai/console/api-keys", "paid"),
    "vercel": ("https://vercel.com/docs/ai-gateway", "one key for hundreds of models"),
    "grok": ("https://docs.x.ai", "xAI API"),
    "anthropic": ("https://platform.claude.com", "Anthropic API"),
    "glm": ("https://docs.z.ai", "Z.ai API"),
    "muse": ("https://ai.developer.meta.com/docs/models", "Muse Spark"),
    "openrouter": ("https://openrouter.ai", "OpenRouter API"),
    "local-server": ("", "Local: loopback server, NEX_LOCAL_URL/MODEL/KEY"),
    "custom": ("", "URL and key of your server "
                   "(Ollama: url=http://localhost:11434/v1, any key)"),
    "gigachat": ("https://developers.sber.ru/portal/products/gigachat",
                 "Sber OAuth pair"),
    "yandex": ("https://yandex.cloud/ru/docs/foundation-models/operations/api-key/get",
               "also requires folder: /ai yandex folder=..."),
}


def key_source_hint(prov: str) -> str:
    """One-line hint showing where to get an API key."""
    url, note = KEY_SOURCE.get(prov, ("", ""))
    if url:
        return f"get one: {url} ({note})"
    return f"get one: {note}" if note else ""


def key_updates(prov: str, parts: list[str]) -> dict[str, str]:
    """Build env-var updates for `/key` or `/ai ... key=...` (pure function)."""
    if prov == "gigachat":
        if len(parts) == 2:
            return {"GIGACHAT_CLIENT_ID": parts[0], "GIGACHAT_SECRET": parts[1]}
        if len(parts) == 1 and ":" in parts[0]:
            cid, _, sec = parts[0].partition(":")
            if cid.strip() and sec.strip():
                return {"GIGACHAT_CLIENT_ID": cid.strip(),
                        "GIGACHAT_SECRET": sec.strip()}
        raise LLMError("GigaChat requires an OAuth pair: /key <client_id> <client_secret> "
                       "or /ai gigachat key=<id>:<secret>")
    if len(parts) != 1 or not parts[0].strip():
        raise LLMError(f"usage: /key <key>  (provider {_label(prov)})")
    return {KEY_VAR.get(prov, "NEX_API_KEY"): parts[0].strip()}


def repair_pasted_key(part: str) -> tuple[str, list[str]]:
    """Repair common clipboard glitches: doubled paste, leading junk, trailing tail.

    Returns (cleaned_key, repair_notes). Empty notes list means clean paste.
    """
    notes: list[str] = []
    s = "".join(part.split())
    if len(s) % 2 == 0 and len(s) >= 40 and s[:len(s) // 2] == s[len(s) // 2:]:
        s = s[:len(s) // 2]
        notes.append("doubled paste detected — kept one copy")
    i = s.find("sk-or-v1-")
    if i > 0:
        s = s[i:]
        notes.append("stripped leading garbage")
    if s.startswith("sk-or-v1-") and len(s) > 73:
        s = s[:73]
        notes.append("trimmed trailing chars to 73")
    return s, notes


def looks_like_key_text(line: str) -> bool:
    """Return True if user input looks like an API key rather than a question."""
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
    """Detect provider from a pasted key and store it in process memory only.

    Returns (provider_label, masked_key, repair_notes). Nothing is written to
    disk: closing the terminal clears the key.
    """
    s = " ".join((text or "").split())
    if not s:
        raise LLMError("empty — paste your key on a single line")
    parts = s.split(" ")
    repaired_notes: list[str] = []
    if len(parts) == 1:
        # Repair before provider detection so doubled/prefixed keys still match.
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
        repaired_notes = repaired_notes + ["decoded Sber base64 key into id:secret pair"]
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
    """Whether an API key is loaded in THIS session's memory (not just `.env`)."""
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
    """Validate and build env-var updates for switching providers (`/ai ...`)."""
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
    # Clear stale NEX_MODEL when switching providers so one API's model name
    # does not leak into another API.
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
            raise LLMError("server URL required: /ai custom url=... model=... key=... "
                           "(e.g. url=https://openrouter.ai/api/v1)")
        updates["NEX_BASE_URL"] = url
    elif prov == "gigachat":
        cid = kv.get("id") or setting("GIGACHAT_CLIENT_ID", "")
        sec = kv.get("secret") or setting("GIGACHAT_SECRET", "") \
            or setting("GIGACHAT_CLIENT_SECRET", "")
        if kv.get("key"):
            pair = key_updates("gigachat", [kv["key"]])
            cid, sec = pair["GIGACHAT_CLIENT_ID"], pair["GIGACHAT_SECRET"]
        if not cid or not sec:
            raise LLMError("OAuth pair required: /ai gigachat key=<id>:<secret> "
                           "(or id=... secret=... — or simply: /key <id> <secret>)")
        updates["GIGACHAT_CLIENT_ID"] = cid
        updates["GIGACHAT_SECRET"] = sec
        if kv.get("scope"):
            updates["GIGACHAT_SCOPE"] = kv["scope"]
    elif prov == "yandex":
        folder = kv.get("folder") or setting("YANDEX_FOLDER_ID", "")
        if not folder:
            raise LLMError("folder ID required: /ai yandex folder=... key=...")
        updates["YANDEX_FOLDER_ID"] = folder

    if kv.get("key") and prov != "gigachat":
        updates.update(key_updates(prov, [kv["key"]]))
    return updates


def normalize_provider(name: str) -> str | None:
    """Resolve a free-form provider alias to its canonical name."""
    key = (name or "").strip().lower()
    if not key:
        return None
    got = _ALIASES.get(key)
    return got if got in PROVIDERS else None


def _looks_google(key: str) -> bool:
    return key.startswith("AIza") or key.startswith("AQ.")


def try_decode_gigachat_key(token: str) -> tuple[str, str] | None:
    """Decode Sber's combined base64(client_id:client_secret) authorization key."""
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
    """Return active provider (explicit NEX_PROVIDER, local if ready, or default)."""
    name = normalize_provider(setting("NEX_PROVIDER", ""))
    if name:
        return name
    raw = setting("NEX_PROVIDER", "")
    if raw:
        return raw  # unknown name — will raise a clear error in _make_backend
    if not _raw_key() and local.ready():
        return "local"
    return DEFAULT_PROVIDER


def _raw_key() -> str:
    """User-supplied generic key (env or ~/.config/nex/key)."""
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
        emb = _embedded_key(prov)
        if emb:
            return emb
        gen = _dotenv_values().get("NEX_API_KEY", "")
        return gen.strip().strip('"').strip("'")
    if prov in ("gigachat", "yandex"):
        # Multi-field auth checked by the backend itself; return sentinel for `available()`.
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
    """Quota exhausted — retrying the same backend won't help."""
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
        return f"{local.model_label()} (4-bit, local)"
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
    """Short UI label: active provider and model."""
    return f"{_PROVIDER_LABEL.get(provider(), provider())} · {model_name()}"


def is_local() -> bool:
    """Whether the active model runs locally on this machine."""
    return provider() == "local"


# --------------------------------------------------------------------------
# Backend factory
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
        raise LLMError(f"unknown or unsupported snapshot provider {prov!r}")
    backend._frozen = True
    return backend


def _make_backend(prov: str):
    """Instantiate backend by provider name using env over `.env`."""
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
            key = _raw_key()
        return OpenAICompatBackend(key, provider=prov,
                                   base_url=setting("NEX_BASE_URL", "") if prov == "custom" else "",
                                   model=setting("NEX_MODEL", ""))
    if prov == "local":
        raise LLMError("local model weights are not present on disk (see docs/WINDOWS.md): "
                       "install them via tools/setup_local_llm.sh or choose a cloud NEX_PROVIDER")
    raise LLMError(f"unknown provider {prov!r}: NEX_PROVIDER=mistral|gemini|"
                   "openai|deepseek|qwen|kimi|custom|gigachat|yandex|local")


# --------------------------------------------------------------------------
# Public API
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
    """Schema-constrained response returning (json_str, output_tokens)."""
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
    """Stream response chunks as they arrive.

    `nudge` applies only to the local provider (see `agent.local`): False for
    small-talk turns so the small model doesn't inject FACTS numbers into a
    greeting. Cloud models ignore it.
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
    """Detect when a pasted key clearly belongs to a different provider."""
    if not raw:
        return ""
    if "sk-or-v1-" in raw and prov != "openrouter":
        return ("looks like an OpenRouter key (sk-or-v1-…) — use: "
                "/ai openrouter key=... (exact key, no prefix)")
    if try_decode_gigachat_key(raw) is not None and prov != "gigachat":
        return ("looks like a Sber GigaChat key (base64 id:secret) — use: "
                "/ai gigachat (or paste directly in AGENT)")
    if raw.startswith("vck_") and prov != "vercel":
        return ("looks like a Vercel key (vck_…) — use: "
                "/ai vercel key=... (or paste directly in AGENT)")
    if _looks_google(raw) and prov == "mistral":
        return "looks like a Gemini key (AIza…) — switch with: /ai gemini"
    if prov == "gemini" and not _looks_google(raw) and len(raw) > 12:
        return "does not look like a Gemini key — for Le Chat use: /ai mistral"
    if ":" in raw and "/" not in raw and prov != "gigachat":
        return ("looks like a GigaChat pair (id:secret) — switch with: "
                "/ai gigachat key=<id>:<secret>")
    return ""


def _server_message(msg: str) -> str:
    """Extract the upstream server error text (for custom/openrouter)."""
    import re

    m = re.search(r'"message"\s*:\s*"([^"]{1,160})"', msg)
    if m:
        return m.group(1)
    m = re.search(r"HTTP \d{3}:\s*(.{1,160})", msg)
    return m.group(1).strip() if m else ""


def _human_error(prov: str, msg: str, key: str = "") -> str:
    """Turn a raw network/API error into an actionable message for `/ai`."""
    label = _label(prov)
    low = msg.lower()
    if "api key not set" in low:
        hint = key_source_hint(prov)
        tail = f" — {hint}" if hint else ""
        return f"API key not set ({label}) — set via: /key <key>{tail}"
    if ("http 401" in low or "http 403" in low or "invalid api" in low
            or "incorrect api" in low or "unauthorized" in low
            or "invalid auth" in low or "rejected" in low):
        detail = _server_message(msg) if prov in ("custom", "openrouter") else ""
        tail = f' Server says: "{detail}".' if detail else ""
        if prov in ("custom", "openrouter") and key and len(key) > 100:
            tail += (f" Key length is {len(key)} (expected ~73) — it may have "
                     f"been pasted twice or with extra text; paste it once exactly.")
        return f"key rejected ({label}) — paste again: /key <key>.{tail}"
    if _is_exhausted(msg):
        return f"quota exhausted ({label}) — switch provider: /ai <other>"
    if "http 404" in low or "not found" in low or "no such model" in low:
        return (f"model not found ({label}) — check the name: "
                f"/ai {prov} model=...")
    return f"{label}: {msg.strip()[:160]}"


def check() -> tuple[bool, str]:
    """Quick connectivity check for `/ai`."""
    if provider() == "local":
        return local.check()
    try:
        txt = complete("Reply with one word only.", 'Say "ready".', temperature=0.0)
        return True, f"{describe()}: {txt.strip()[:40]}"
    except LLMError as e:
        key = api_key()
        base = _human_error(provider(), str(e), key)
        extra = _misfit_hint(provider(), key)
        return False, base + (". " + extra if extra else "")
