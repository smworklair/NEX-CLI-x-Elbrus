"""Backend'ы агента: один интерфейс, по файлу на провайдер.

Концепт — как `Backend.generate(prompt) -> str` в Nex-pilot
(`nexpilot/backends/base.py`): верхние слои (`agent.py`, `analyst.py`)
не знают, в какой именно API ушёл запрос — Mistral, Gemini, GigaChat,
YandexGPT или любой OpenAI-совместимый. Добавление нового провайдера —
новый файл здесь + одна строка в реестре `llm.py`, без правок агента.

Ограничения намеренные, как и в старом `llm.py`:
  * только стандартная библиотека (`urllib`, `json`) — без новых
    зависимостей, проект остаётся запускаемым голым Python;
  * секреты только из окружения/`.env`/`~/.config/nex/key` (см. `llm.py`),
    никогда строкой в коде и никогда в git (`.env` в `.gitignore`).
"""

from .base import Backend, LLMError

__all__ = ["Backend", "LLMError"]
