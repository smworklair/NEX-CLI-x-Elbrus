"""Агентный режим: разговор о планировании на обычном языке.

  backends/   провайдеры API с единым интерфейсом (концепт Nex-pilot:
              mistral, gemini, openai-совместимые, gigachat, yandex)
  llm.py      фабрика поверх backends/ (выбор по NEX_PROVIDER, ключи только
              из окружения/.env/~/.config/nex/key — никогда в git)
  context.py   сборка ФАКТЫ из ядра — то, чем заземляется модель
  agent.py     ход диалога: действие → факты → ответ, с офлайновым запасным

Числа всегда считает `vliw.core`; языковая модель только объясняет. Поэтому
любой ответ проверяется командой (`/doctor`, `/compare`) и не «плывёт».
"""

from .agent import Agent, Turn, status

__all__ = ["Agent", "Turn", "status"]
