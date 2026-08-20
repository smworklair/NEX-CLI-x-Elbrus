"""Агент на модели с этой машины: тот же llama-server, что и у планировщика.

ЗАЧЕМ. Раньше у агента был единственный путь — чужой сервер по HTTP (Le Chat
или Gemini). Значит: нужен ключ, нужна сеть, чужая квота может кончиться, и
вопрос про твой код уезжает наружу. При этом в инструменте УЖЕ крутится
языковая модель — та, что планирует расписание. Странно спрашивать интернет,
когда модель стоит рядом.

ЧТО ИМЕННО ОТВЕЧАЕТ. Голая база Qwen2.5-3B-Instruct, БЕЗ обученного адаптера.
Адаптер учит модель ровно одному — писать строки `0: такт=0 канал=1`; спроси
его «почему медленно», и получишь расписание вместо ответа. Поэтому разговор
идёт на базе, планирование — на адаптере, а процесс один и тот же: режимы
переключаются шкалами LoRA за один HTTP-запрос вместо перезапуска с чтением
2.1 ГБ (см. `LlamaServer.using`).

ЧЕСТНО ПРО КАЧЕСТВО. 3B в 4 битах формулирует заметно беднее, чем облачная
модель, и рассуждает мельче. Это терпимо ровно потому, что агент устроен так,
как устроен: файлы грузит парсер, расписание считает точный поиск, потери
находит `core.doctor`, — а языковая модель отвечает только за формулировку
поверх готовых чисел (см. шапку `agent.py`). Числа от смены модели не меняются.
Если нужен разбор получше — `NEX_PROVIDER=mistral` и ключ.
"""

from __future__ import annotations

import json

# Сколько ждём ответа в разговоре. Не как у планировщика (там минуты на граф):
# в диалоге человек сидит и смотрит, и молчание дольше полуминуты — это уже
# «повисло», а не «думает».
CHAT_TIMEOUT_S = 180
CHAT_MAX_TOKENS = 700


# Состояние прогрева. Первый вопрос в сессии дорогой не из-за генерации, а
# из-за двух разовых вещей: поднять сервер (~7 с) и посчитать системный
# промпт агента — 1451 токен на CPU. Обе делаются ОДИН раз и обе можно
# сделать заранее, пока человек читает экран и набирает вопрос.
_WARM = {"state": "cold", "note": ""}
"""cold | warming | ready | failed — что показывать в интерфейсе."""


def warm_state() -> tuple[str, str]:
    """(состояние, пояснение) — для честной подписи в интерфейсе."""
    return _WARM["state"], _WARM["note"]


def warmup(system: str | None = None) -> None:
    """Поднять сервер и, если дан промпт, набить им кэш.

    Вызывается в фоновом потоке при входе в режим. Ничего не возвращает:
    если не получилось, первый вопрос просто пойдёт обычным путём и покажет
    настоящую ошибку — прятать её здесь нельзя.

    Промпт прогревается запросом на ОДИН токен: считать надо префикс, а не
    ответ. Дальше `cache_prompt` переиспользует посчитанное, и настоящий
    вопрос платит только за свои несколько слов.
    """
    if _WARM["state"] in ("warming", "ready"):
        return
    _WARM["state"], _WARM["note"] = "warming", "поднимаю модель"
    try:
        from ..learned import runtime

        server = runtime.shared_server()
        if system is not None:
            _WARM["note"] = "грею контекст"
            list(server.chat([{"role": "system", "content": system + SMALL_MODEL_NUDGE},
                              {"role": "user", "content": "."}],
                             temperature=0, max_tokens=1, timeout=CHAT_TIMEOUT_S))
        _WARM["state"], _WARM["note"] = "ready", ""
    except Exception as e:                # прогрев не имеет права ронять интерфейс
        _WARM["state"] = "failed"
        _WARM["note"] = str(e)[:120]


def ready() -> bool:
    """Есть ли на машине всё для локального ответа: бинарник и база."""
    try:
        from ..learned import runtime
    except Exception:
        return False
    return (runtime.find_llama_server() is not None
            and runtime.find_gguf_base() is not None)


def model_label() -> str:
    from ..learned import runtime

    base = runtime.find_gguf_base()
    return base.name if base is not None else "qwen2.5-3b-instruct"


SMALL_MODEL_NUDGE = (
    "\n\nВАЖНО ДЛЯ ЭТОГО ОТВЕТА: сначала напиши 2–4 предложения по существу "
    "вопроса, опираясь на числа из ФАКТОВ. Строку «Дальше:» добавляй ТОЛЬКО "
    "после этих предложений. Ответ, состоящий из одной строки «Дальше:», "
    "недопустим."
)
"""Добавка к системному промпту — только для локальной модели.

Не косметика. Системный промпт агента кончается правилом «если уместно,
заканчивай строкой Дальше: с командой», и модель на 3B хватается за последнюю
конкретную инструкцию вместо ответа. Замерено на одном и том же вопросе
(«почему этот участок медленный?») и одних и тех же фактах:

    без добавки    18 символов:  «Дальше: /explain 22»
    с добавкой    268 символов:  разбор монополии порта ,5 с тактами

Облачной модели добавка не нужна и не достаётся: там правил хватает.
"""


def _messages(system: str, question: str,
              history: list[tuple[str, str]] | None,
              nudge: bool = True) -> list[dict]:
    if nudge:
        system = system + SMALL_MODEL_NUDGE
    msgs = [{"role": "system", "content": system}]
    for asked, answered in (history or []):
        msgs.append({"role": "user", "content": asked})
        msgs.append({"role": "assistant", "content": answered})
    msgs.append({"role": "user", "content": question})
    return msgs


def stream(system: str, question: str,
           history: list[tuple[str, str]] | None = None,
           temperature: float = 0.3, nudge: bool = True):
    """Ответ по частям. Ошибки сервера — как `LLMError`, чтобы агент их ловил.

    `nudge=False` — для реплик не по делу («привет», «спасибо»): добавка
    прямым текстом велит модели тащить числа из ФАКТОВ в любой ответ, а
    ФАКТЫ есть всегда, даже когда расписание ещё не считалось. На 3B это
    значило не «ответь короче», а «сочини технический разбор из ближайших
    похожих слов» — проверено вживую: вопрос «привет» с добавкой дал
    выдуманные «11 тактов» (это была latency DIV, а не длина расписания) и
    перевранный смысл заметки об участке; без добавки — «Привет. Дальше:
    /run» за 1.4 с вместо 58.
    """
    from ..learned import runtime, server as srv

    from .llm import LLMError

    try:
        pump = runtime.shared_server().chat(
            _messages(system, question, history, nudge=nudge),
            temperature=temperature, max_tokens=CHAT_MAX_TOKENS,
            timeout=CHAT_TIMEOUT_S)
        yield from pump
    except srv.ServerError as e:
        raise LLMError(f"локальная модель: {e}") from e
    except OSError as e:
        raise LLMError(f"локальная модель недоступна: {e}") from e


def complete(system: str, question: str,
             history: list[tuple[str, str]] | None = None,
             temperature: float = 0.3, nudge: bool = True) -> str:
    return "".join(stream(system, question, history, temperature, nudge=nudge))


def structured(system: str, question: str, schema: dict,
               temperature: float = 0.1) -> tuple[str, int]:
    """Ответ строго по схеме — через грамматику llama.cpp.

    llama.cpp умеет ограничивать вывод JSON-схемой, поэтому просить модель
    «ответь JSON-ом» и надеяться не приходится: несоответствующий текст она
    физически не сможет сгенерировать.

    Если сервер этого не поддерживает, поднимается `LLMError` — и вызывающий
    (`analyst.py`) честно падает на детерминированный разбор, а не выдаёт
    выдумку за анализ.
    """
    from ..learned import runtime, server as srv

    from .llm import LLMError

    msgs = _messages(system, question, None)
    try:
        server = runtime.shared_server()
        with server.using(None):
            status, body = server._request(
                "POST", "/v1/chat/completions",
                {"messages": msgs, "temperature": temperature,
                 "max_tokens": CHAT_MAX_TOKENS,
                 "response_format": {"type": "json_object", "schema": schema}},
                timeout=CHAT_TIMEOUT_S)
        if status != 200:
            raise LLMError(f"локальная модель, схема: ответ {status}")
        data = json.loads(body)
        text = data["choices"][0]["message"]["content"]
        used = int((data.get("usage") or {}).get("completion_tokens", 0))
        return text, used
    except (srv.ServerError, OSError, KeyError, ValueError) as e:
        raise LLMError(f"локальная модель не дала ответ по схеме: {e}") from e


def check() -> tuple[bool, str]:
    """Быстрая проверка для `/ai`: поднять сервер и получить одно слово."""
    from .llm import LLMError, describe

    try:
        txt = complete("Отвечай одним словом.", "Скажи «готово».",
                       temperature=0.0)
    except LLMError as e:
        return False, str(e)
    return True, f"{describe()}: {txt.strip()[:40]}"
