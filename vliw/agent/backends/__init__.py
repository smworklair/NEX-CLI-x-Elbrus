"""Agent backends: one interface, one file per provider.

Same design as `Backend.generate(prompt) -> str` in Nex-pilot
(`nexpilot/backends/base.py`): upper layers (`agent.py`, `analyst.py`)
don't know which API handles the request — Mistral, Gemini, GigaChat,
YandexGPT, or any OpenAI-compatible server. Adding a new provider means
adding one file here and one entry in `llm.py`, without touching the agent.

Intentional constraints (same as legacy `llm.py`):
  * standard library only (`urllib`, `json`) — zero extra dependencies,
    so the project stays runnable on bare Python;
  * secrets come only from env / `.env` / `~/.config/nex/key` (see `llm.py`),
    never hardcoded in source or committed to git (`.env` is in `.gitignore`).
"""

from .base import Backend, LLMError

__all__ = ["Backend", "LLMError"]
