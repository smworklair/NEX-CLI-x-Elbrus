"""Muse Spark (Meta Model API): OpenAI-совместимый `/v1/chat/completions`.

Проверено по официальной документации (ai.developer.meta.com, dev.meta.ai):
  * base URL — `https://api.meta.ai/v1`;
  * чат — `POST /v1/chat/completions`, ключ — `Authorization: Bearer`;
  * каталог — `GET /v1/models` тем же ключом (форма OpenAI: `{"data": [...]}`);
  * модели — `muse-spark-1.3` (актуальная), `muse-spark-1.2`, `muse-spark-1.1`
    и `-contributor`-варианты тех же чекпоинтов.

Muse Spark — рассуждающая модель: думает до ответа, токены размышления
считаются выходными. Отдельного тумблера мышления в Chat Completions нет.
"""

from __future__ import annotations

from .openai_compat import OpenAICompatBackend

_BASE_URL = "https://api.meta.ai/v1"
_DEFAULT_MODEL = "muse-spark-1.3"


class MuseBackend(OpenAICompatBackend):
    name = "muse"

    def __init__(self, api_key: str, base_url: str = "", model: str = "",
                 timeout=None):
        from .base import TIMEOUT as _TIMEOUT

        super().__init__(api_key, base_url=base_url or _BASE_URL,
                         model=model or _DEFAULT_MODEL, provider="muse",
                         timeout=_TIMEOUT if timeout is None else timeout)
