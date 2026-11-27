"""Agent mode: natural-language conversation about VLIW instruction scheduling.

  backends/   API providers behind one interface (Nex-pilot pattern:
              mistral, gemini, openai-compatible, gigachat, yandex)
  llm.py      factory over backends/ (selected via NEX_PROVIDER; keys only
              from env / .env / ~/.config/nex/key — never committed to git)
  context.py  assembles FACTS from the core to ground the language model
  agent.py    dialogue loop: action -> facts -> answer, with offline fallback

All numbers are computed by `vliw.core`; the language model only explains them.
Every answer can be verified with a command (`/doctor`, `/compare`) and never drifts.
"""

from .agent import Agent, Turn, status

__all__ = ["Agent", "Turn", "status"]
