"""YandexGPT (Yandex Cloud): `foundationModels/v1/completion`.

Два способа аутентификации (хватит одного):
  * API-ключ:  YANDEX_API_KEY (заголовок `Authorization: Api-Key ...`);
  * IAM-токен: YANDEX_IAM_TOKEN (заголовок `Authorization: Bearer ...`).

В обоих случаях нужен каталог:
  YANDEX_FOLDER_ID — идентификатор каталога в Yandex Cloud.

Переменные окружения (см. `.env.example`):
  YANDEX_API_KEY / YANDEX_IAM_TOKEN / YANDEX_FOLDER_ID
  YANDEX_MODEL — по умолчанию yandexgpt (можно yandexgpt-lite)
  NEX_MODEL — перебивает YANDEX_MODEL, если задан
"""

from __future__ import annotations

import os

from .base import Backend, LLMError, MAX_TOKENS, TIMEOUT, post_json_retry

_API = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"


class YandexBackend(Backend):
    name = "yandexgpt"

    def __init__(self, api_key: str = "", iam_token: str = "", folder_id: str = "",
                 model: str = "", timeout: float = TIMEOUT,
                 use_env: bool = True):
        env = os.environ if use_env else {}
        key = api_key or env.get("YANDEX_API_KEY", "") or env.get("NEX_API_KEY", "")
        iam = iam_token or env.get("YANDEX_IAM_TOKEN", "")
        folder = folder_id or env.get("YANDEX_FOLDER_ID", "")
        # NEX_API_KEY вида "iam:..."/"key:..." — на случай одного поля ввода.
        if not iam and key.startswith("iam:"):
            iam, key = key[4:], ""
        if iam and not folder and ":" in iam:
            iam, _, folder = iam.partition(":")
        if key.startswith("folder:"):
            folder = folder or key[len("folder:"):]
            key = ""
        if not (key or iam):
            raise LLMError("YandexGPT: задайте YANDEX_API_KEY или YANDEX_IAM_TOKEN")
        if not folder:
            raise LLMError("YandexGPT: задайте YANDEX_FOLDER_ID (каталог в Yandex Cloud)")
        self._key = key.strip()
        self._iam = iam.strip()
        self._folder = folder.strip()
        self._model = model or env.get("YANDEX_MODEL", "") \
            or env.get("NEX_MODEL", "") or "yandexgpt"
        self._timeout = timeout

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self._iam:
            h["Authorization"] = f"Bearer {self._iam}"
            # Каталог дублируем заголовком, как в примерах из документации:
            # modelUri его уже содержит, но лишний заголовок не вредит.
            h["x-folder-id"] = self._folder
        else:
            h["Authorization"] = f"Api-Key {self._key}"
        return h

    def _body(self, system, question, history, temperature, schema, stream):
        msgs = [{"role": "system", "text": system}]
        for role, text in history or []:
            msgs.append({"role": "user" if role == "user" else "assistant",
                         "text": text})
        msgs.append({"role": "user", "text": question})
        body: dict = {
            "modelUri": f"gpt://{self._folder}/{self._model}/latest",
            "completionOptions": {"stream": bool(stream),
                                  "temperature": temperature,
                                  "maxTokens": MAX_TOKENS},
            "messages": msgs,
        }
        if schema:
            # У Yandex нет response_format — просим JSON текстом инструкции.
            msgs.append({"role": "system",
                         "text": "Отвечай СТРОГО валидным JSON без пояснений, "
                                 "ровно по схеме из задачи."})
        return body

    def _text_of(self, data: dict) -> tuple[str, int]:
        alts = (data.get("result") or {}).get("alternatives") or []
        if not alts:
            raise LLMError("модель не вернула ответ")
        text = ((alts[0].get("message") or {}).get("text") or "").strip()
        used = int((data.get("result") or {}).get("usage", {})
                   .get("completionTokens", 0) or 0)
        if not text:
            raise LLMError("пустой ответ модели")
        return text, used

    def complete(self, system, question, history=None, temperature=0.3) -> str:
        data = post_json_retry(
            _API, self._body(system, question, history, temperature, None, False),
            self._headers(), self._timeout)
        return self._text_of(data)[0]

    def structured(self, system, question, schema, temperature=0.1):
        data = post_json_retry(
            _API, self._body(system, question, [], temperature, schema, False),
            self._headers(), self._timeout)
        return self._text_of(data)

    def stream(self, system, question, history=None, temperature=0.3):
        # Yandex умеет SSE при stream=true, но формат тот же completion-объект
        # кусками; проще и надёжнее отдать полный ответ одним куском —
        # интерфейс разницы не заметит, кроме отсутствия побуквенной анимации.
        yield self.complete(system, question, history, temperature)
