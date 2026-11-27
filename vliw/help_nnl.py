"""NNL help block: natural-language question -> answer topic.

The canonical block lives in `nnl_vliw/блоки_помощь/Помощь_ассистент/` —
a passport JSON and `веса.npz`, just like other NNL blocks. Architecture:
`мешок_шина` (bag-of-tokens): the question is split into words and character
n-grams, hashed via crc32 into rows of embedding table E, averaged into h,
and scored by a linear layer `h·U + b`.

Why two copies of the weights exist:
  · `веса.npz` — canonical NNL block (numpy, matching the rest of `nnl_vliw`);
  · `vliw/help_weights.json` — identical numbers for pure Python.
The setup screen runs on machines where numpy may not be installed yet, so the
assistant must work with zero external dependencies.

Because `help_weights.json` was trained on Russian phrasings, this module also
includes an English keyword/stem fallback matcher so English questions route
accurately to the corresponding topics in `vliw/help_answers.py`.
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
_CYRILLIC = re.compile(r"[а-яё]")
НЕ_ТЕМА = "не_тема"   # class "off-topic / not about NEX CLI", also trained
БЕСЕДА = "беседа"     # greetings and thanks
ПОРОГ = 0.35          # below this -> "didn't understand"
ЗАЗОР = 0.08          # minimum margin between 1st and 2nd topic

# Unambiguous keywords and command names. The NNL block is trained on natural
# Russian phrasings, while exact names (`textual`, `venv`, `slotclash`, ...)
# and English stems are matched deterministically so a single typo doesn't
# misroute the answer. Strong hints override the NNL block; weak hints apply
# when the block is unsure (or for pure-English queries where Russian weights
# do not apply).
_СИЛЬНЫЕ: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("удаление", (
        "удал", "снести", "деинстал", "стереть установку",
        "uninstall", "remove nex", "delete nex", "remove package", "clean up",
    )),
    ("обновление", (
        "обнов", "новая версия", "свежую версию",
        "upgrade", "update", "git pull", "new version", "latest version",
    )),
    ("nnl", (
        "nnl", "нейросет", "нейрон", "обучил", "обучал", "обучен",
        "трениров", "мешок слов", "мешок токенов", "понимает контекст",
        "neural", "bag of words", "classifier", "weights", "how do you understand",
    )),
    ("textual", (
        "textual", "rich", "текстуал", "рич", "панели",
        "fullscreen", "full screen", "full-screen", "tui",
    )),
    ("venv", (
        "venv", "виртуал", "ensurepip", "pip не найден", "нет pip",
        "virtual env", "virtualenv", "pip not found", "no pip",
    )),
    ("агент", (
        "агент", "api", "ключ", "llm", "openai", "anthropic",
        "ollama", "провайдер",
        "agent", "api key", "gemini", "mistral", "yandex", "provider", "vllm",
    )),
    ("данные", (
        "slotclash", "сценар", "датасет", "eval_real", "eval real", "граф",
        "scenario", "dataset", "benchmark", "examples", "probe.s", "sample",
    )),
    ("проверка", (
        "doctor", "selfcheck", "unittest", "тест",
        "verify", "test suite", "run tests", "diagnostics",
    )),
    ("система", (
        "windows", "linux", "ubuntu", "debian", "fedora", "macos", "мак",
        "винде", "powershell", "cmd", "microsoft store",
        "mac os", "osx", "arch", "chcp", "executionpolicy",
    )),
    ("требования", (
        "требован", "памят", "gpu", "видеокарт", "версия python",
        "версия питона", "какой python", "диска", "интернет",
        "require", "system req", "python version", "which python",
        "disk space", "cuda", "hardware", "offline", "internet",
    )),
)

_СЛАБЫЕ: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("проблема", (
        "не работает", "не запускается", "не открывается", "ошибк",
        "падает", "traceback", "черный экран", "зависает",
        "не найдена", "не найден",
        "not working", "doesn t work", "doesnt work", "won t start", "wont start",
        "won t open", "wont open", "won t it open", "won t it start",
        "doesn t open", "doesnt open", "can t open", "cant open", "can t start",
        "error", "crash", "fail", "broken", "problem", "issue", "troubleshoot",
        "black screen", "freeze", "hang", "not found", "missing", "bug",
    )),
    ("запуск", (
        "запуст", "старт", "python -m vliw", "открыть программу",
        "открыть интерфейс", "открыть меню",
        "launch", "start", "run nex", "run vliw", "how to run", "open ui",
        "plain mode", "cli mode",
    )),
    ("установка", (
        "установ", "поставить", "pip install", "скачать",
        "install", "setup", "set up", "download", "getting started",
    )),
    ("проверка", (
        "провер", "check", "test", "tty", "isatty",
    )),
    ("удаление", (
        "remove", "delete",
    )),
    ("зачем", (
        "зачем", "для чего", "что такое", "что это", "чем полез",
        "польза", "назначение",
        "what is nex", "what is this", "what is vliw", "what is the scheduler",
        "what does nex", "what does it do", "what does this", "why use",
        "why do i need", "purpose", "about nex", "overview", "explain nex",
        "elbrus", "vliw", "scheduler",
    )),
)

_ПРИВЕТ = {
    "привет", "приветик", "прив", "здравствуйте", "здравствуй", "добрый день",
    "добрый вечер", "доброе утро", "доброго дня", "доброго времени суток",
    "как дела", "как ты", "ты кто", "кто ты", "кто ты такой",
    "что ты умеешь", "чем можешь помочь", "помоги мне", "мне нужна помощь",
    "ты бот", "ты человек", "как тебя зовут", "что нового",
    # Informal greetings
    "йоу", "йо", "хай", "хеллоу", "ку", "здарова", "здорово", "салют",
    "hello", "hello there", "hi", "hi there", "hey", "hey there",
    "good morning", "good afternoon", "good evening",
    "how are you", "who are you", "what can you do", "help", "help me",
    "i need help", "are you a bot", "what is your name", "whats up",
}
_ПОКА = {
    "пока", "до свидания", "до встречи", "хорошего дня",
    "bye", "goodbye", "see you", "have a nice day",
}

_кэш: dict = {}


def токены(текст: str) -> list[str]:
    """Words and character n-grams: handles inflection without a stemmer.

    Related inflections share 3- and 4-character substrings so the linear model
    generalizes across word forms.
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
    """Canonical block weights via numpy; missing numpy is handled gracefully."""
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
    """Topics the assistant can answer (internal off-topic class is hidden)."""
    w = _из_json() or _из_npz()
    return [a for a in w["ответы"] if a != НЕ_ТЕМА] if w else []


def сведения() -> str:
    """Status line for the greeting banner describing the loaded help block."""
    w = _из_json() or _из_npz()
    if not w:
        return "help block not found"
    return (f"NNL block 'Help_assistant' · {w['корзины']} buckets · "
            f"{w['размер']} features · {len(темы())} topics")


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
    """Raw topic scores (logits before softmax)."""
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
    """Return (topic, is_strong) from deterministic keyword/stem matching."""
    ч = _чисто(вопрос)
    if not ч:
        return None
    if (ч in _ПРИВЕТ or ч in _ПОКА
            or ч.startswith(("спасибо", "благодар", "thank", "thx"))):
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
    """Return (topic, confidence), or None if the question is off-topic."""
    подсказка = _подсказка(вопрос)
    if подсказка is not None and подсказка[1]:
        return подсказка[0], 1.0
    # For pure-English queries (no Cyrillic), trust the English keyword/stem
    # matcher directly because help_weights.json was trained on Russian tokens.
    ч = _чисто(вопрос)
    if ч and not _CYRILLIC.search(ч):
        if подсказка is not None:
            return подсказка[0], 0.85
        return None
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
