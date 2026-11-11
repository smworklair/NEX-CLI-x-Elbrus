"""NNL-блок помощи: вопрос обычными словами → тема ответа.

Сам блок лежит в `nnl_vliw/блоки_помощь/Помощь_ассистент/` — паспорт и
`веса.npz`, как у остальных блоков NNL. Архитектура — та же `мешок_шина`:
вопрос переводится в мешок токенов, вектор — среднее строк таблицы E по
корзинам crc32, счёты тем — линейный слой `h·U + b`.

Почему две копии весов:
  · `веса.npz` — канонический блок NNL (numpy, как весь `nnl_vliw`);
  · `vliw/help_weights.json` — те же числа для чистого Python.
Экран установки показывается как раз на машине, где numpy может быть ещё
не установлен, поэтому помощник обязан работать без единой библиотеки.
Числа в обеих копиях одинаковые — это проверяет тест.
"""

from __future__ import annotations

import json
import math
import re
import zlib
from pathlib import Path

КОРЕНЬ = Path(__file__).resolve().parent.parent
БЛОК = КОРЕНЬ / "nnl_vliw" / "блоки_помощь" / "Помощь_ассистент"
ЛЁГКИЕ = Path(__file__).resolve().parent / "help_weights.json"

СЛОВО = re.compile(r"[a-zа-я0-9]+")
НЕ_ТЕМА = "не_тема"   # класс «вопрос не про NEX CLI», ему блок тоже обучен
БЕСЕДА = "беседа"     # приветствия и благодарности
ПОРОГ = 0.35          # ниже — «не понял вопрос»
ЗАЗОР = 0.08          # разница между первой и второй темой

# Однозначные слова и названия команд. Блок обучен на живых формулировках, но
# точные имена (`textual`, `venv`, `slotclash`, …) надёжнее узнавать по ним:
# одна опечатка в остальном вопросе не должна уводить ответ в соседнюю тему.
# Сильные подсказки перебивают блок, слабые — только если блок не уверен.
_СИЛЬНЫЕ: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("удаление", ("удал", "снести", "деинстал", "uninstall", "стереть установку")),
    ("обновление", ("обнов", "upgrade", "git pull", "новая версия", "свежую версию")),
    ("nnl", ("nnl", "нейросет", "нейрон", "обучил", "обучал", "обучен",
             "трениров", "мешок слов", "мешок токенов", "понимает контекст")),
    ("textual", ("textual", "rich", "текстуал", "рич", "панели")),
    ("venv", ("venv", "виртуал", "ensurepip", "pip не найден", "нет pip")),
    ("агент", ("агент", "api", "ключ", "llm", "openai", "anthropic",
               "ollama", "провайдер")),
    ("данные", ("slotclash", "сценар", "датасет", "eval_real", "eval real", "граф")),
    ("проверка", ("doctor", "selfcheck", "unittest", "тест")),
    ("система", ("windows", "linux", "ubuntu", "debian", "fedora", "macos", "мак",
                 "винде", "powershell", "cmd", "microsoft store")),
    ("требования", ("требован", "памят", "gpu", "видеокарт", "версия python",
                    "версия питона", "какой python", "диска", "интернет")),
)

_СЛАБЫЕ: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("проблема", ("не работает", "не запускается", "не открывается", "ошибк",
                  "падает", "traceback", "черный экран", "зависает",
                  "не найдена", "не найден")),
    ("запуск", ("запуст", "старт", "python -m vliw", "открыть программу",
                "открыть интерфейс", "открыть меню")),
    ("установка", ("установ", "поставить", "pip install", "скачать")),
    ("проверка", ("провер",)),
    ("зачем", ("зачем", "для чего", "что такое", "что это", "чем полез",
               "польза", "назначение")),
)

_ПРИВЕТ = {"привет", "приветик", "прив", "здравствуйте", "здравствуй", "добрый день",
           "добрый вечер", "доброе утро", "доброго дня", "доброго времени суток",
           "как дела", "как ты", "ты кто", "кто ты", "кто ты такой",
           "что ты умеешь", "чем можешь помочь", "помоги мне", "мне нужна помощь",
           "ты бот", "ты человек", "как тебя зовут", "что нового",
           # Разговорные приветствия: люди пишут и так, и это не оффтоп.
           "йоу", "йо", "хай", "хеллоу", "ку", "здарова", "здорово", "салют",
           "hello", "hi", "hey"}
_ПОКА = {"пока", "до свидания", "до встречи", "хорошего дня"}

_кэш: dict = {}


def токены(текст: str) -> list[str]:
    """Слова и символьные n-граммы: русская морфология без стеммера.

    «установить», «установка», «установил» дают общие куски «уст», «ста»,
    «тан» — линейная модель уверенно переносит вопрос на ту же тему.
    """
    low = (текст or "").lower().replace("ё", "е")
    out: list[str] = []
    for word in СЛОВО.findall(low):
        if len(word) < 2:
            continue
        out.append("w:" + word)
        padded = "^" + word + "$"
        for n in (3, 4):
            for i in range(len(padded) - n + 1):
                out.append(f"{n}:" + padded[i:i + n])
    return out or ["w:пусто"]


def _индекс(соль: str, токен: str, корзины: int) -> int:
    return zlib.crc32((соль + "\x1f" + токен).encode("utf-8")) % корзины


def _из_json() -> dict | None:
    if "json" in _кэш:
        return _кэш["json"]
    try:
        data = json.loads(ЛЁГКИЕ.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = None
    _кэш["json"] = data
    return data


def _из_npz() -> dict | None:
    """Канонические веса блока через numpy; нет numpy — не страшно."""
    if "npz" in _кэш:
        return _кэш["npz"]
    data = None
    try:
        import numpy as np

        with np.load(БЛОК / "веса.npz", allow_pickle=False) as z:
            data = {
                "E": z["E"].astype(np.float64),
                "U": z["U"].astype(np.float64),
                "b": z["b"].astype(np.float64),
                "ответы": [str(x) for x in z["ответы"]],
                "соль": json.loads((БЛОК / "паспорт.json").read_text(encoding="utf-8"))["настройки"]["соль"],
                "корзины": int(z["E"].shape[0]),
                "размер": int(z["E"].shape[1]),
                "свёртка": "среднее",
            }
    except Exception:
        data = None
    _кэш["npz"] = data
    return data


def доступно() -> bool:
    return _из_json() is not None or _из_npz() is not None


def темы() -> list[str]:
    """Темы, на которые ассистент отвечает (служебный класс «не_тема» скрыт)."""
    w = _из_json() or _из_npz()
    return [a for a in w["ответы"] if a != НЕ_ТЕМА] if w else []


def сведения() -> str:
    """Строка для приветствия: чем именно отвечает блок."""
    w = _из_json() or _из_npz()
    if not w:
        return "блок помощи не найден"
    return (f"блок NNL «Помощь_ассистент» · {w['корзины']} корзин · "
            f"{w['размер']} признаков · {len(темы())} тем")


def _h(ток: list[str], w: dict) -> list[float]:
    d = w["размер"]
    h = [0.0] * d
    for t in ток:
        row = w["E"][_индекс(w["соль"], t, w["корзины"])]
        for j in range(d):
            h[j] += row[j]
    n = len(ток) or 1
    return [v / n for v in h]


def оценки(вопрос: str) -> dict[str, float]:
    """Сырые счёты тем (логарифмы шансов до softmax)."""
    tok = токены(вопрос)
    npz = _из_npz()
    if npz is not None:
        import numpy as np

        idx = np.fromiter(
            (_индекс(npz["соль"], t, npz["корзины"]) for t in tok),
            dtype=np.int64, count=len(tok))
        h = npz["E"][idx].sum(0) / max(1, len(idx))
        s = h @ npz["U"] + npz["b"]
        return {a: float(v) for a, v in zip(npz["ответы"], s)}

    w = _из_json()
    if w is None:
        return {}
    h = _h(tok, w)
    d = w["размер"]
    out: dict[str, float] = {}
    for j, тема in enumerate(w["ответы"]):
        total = w["b"][j]
        for i in range(d):
            total += h[i] * w["U"][i][j]
        out[тема] = total
    return out


def вероятности(вопрос: str) -> dict[str, float]:
    s = оценки(вопрос)
    if not s:
        return {}
    top = max(s.values())
    ex = {k: math.exp(v - top) for k, v in s.items()}
    total = sum(ex.values())
    return {k: v / total for k, v in ex.items()}


def _чисто(текст: str) -> str:
    низ = (текст or "").lower().replace("ё", "е")
    return " ".join(re.sub(r"[^a-zа-я0-9\s]+", " ", низ).split())


def _подсказка(вопрос: str) -> tuple[str, bool] | None:
    """Тема по слову и признак «слово однозначное»."""
    ч = _чисто(вопрос)
    if not ч:
        return None
    if ч in _ПРИВЕТ or ч in _ПОКА or ч.startswith(("спасибо", "благодар")):
        return БЕСЕДА, True
    for тема, слова in _СИЛЬНЫЕ:
        for слово in слова:
            if слово in ч:
                return тема, True
    for тема, слова in _СЛАБЫЕ:
        for слово in слова:
            if слово in ч:
                return тема, False
    return None


def спросить(вопрос: str) -> tuple[str, float] | None:
    """Тема и уверенность. None — вопрос не про установку/работу NEX CLI."""
    подсказка = _подсказка(вопрос)
    if подсказка is not None and подсказка[1]:
        return подсказка[0], 1.0
    p = вероятности(вопрос)
    if p:
        ranked = sorted(p.items(), key=lambda kv: kv[1], reverse=True)
        тема, уверенность = ranked[0]
        второй = ranked[1][1] if len(ranked) > 1 else 0.0
        if (тема != НЕ_ТЕМА and уверенность >= ПОРОГ
                and уверенность - второй >= ЗАЗОР):
            return тема, уверенность
    if подсказка is not None:
        return подсказка[0], 0.5
    return None
