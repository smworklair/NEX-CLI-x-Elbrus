"""Muse Spark (Meta Model API): OpenAI-compatible `/v1/chat/completions`.

Verified against official docs (ai.developer.meta.com, dev.meta.ai):
  * base URL — `https://api.meta.ai/v1`;
  * chat — `POST /v1/chat/completions`, key via `Authorization: Bearer`;
  * model catalog — `GET /v1/models` with the same key (OpenAI shape: `{"data": [...]}`);
  * models — `muse-spark-1.3` (current), `muse-spark-1.2`, `muse-spark-1.1`,
    and `-contributor` variants of the same checkpoints.

Muse Spark is a reasoning model: it thinks before answering, and reasoning
tokens count toward output tokens. There is no separate reasoning toggle in
Chat Completions.
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
