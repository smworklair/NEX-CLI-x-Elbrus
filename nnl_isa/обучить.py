# -*- coding: utf-8 -*-
"""Обучение одного ядра NNL тем же кодом, что nnl_vliw (обучение/сеть.py), без правок.

Пишет <выход>/<блок>/{паспорт.json, веса.npz}. Чисел на ядро не больше ~30 тысяч.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from nnl_vliw.обучение import сеть as С

from . import данные as Д
from . import ядра as Я
from .язык import ЯзыкИмени, ЯзыкУпотребления

НАСТРОЙКИ = {"эпох": 25, "терпение": 5, "пакет": 16, "lr": 0.02, "λ": 1.0, "p_выходной": 0.15}
ГРАНИЦА, СВЁРТКА, МАСШТАБ = 8.0, "корень", 8.0


def sha256_файла(путь) -> str:
    h = hashlib.sha256()
    with open(путь, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def собрать_блоки(ядро: str, зерно: int):
    опис = Я.описание_блоков(ядро)
    блоки = []
    for i, о in enumerate(опис):
        блоки.append(С.БлокУч(
            о["имя"], о["ответы"], о["пишет"], о["читает"],
            корзины=о["корзины"], размер=о["размер"], граница=ГРАНИЦА, соль=о["соль"],
            seed=зерно * 100 + i, область=о["область"],
            роль=f"класс мнемоники, область «{о['область']}»",
            свёртка=СВЁРТКА, масштаб_чтения=МАСШТАБ,
        ))
    чисел = sum(b.чисел() for b in блоки)
    if чисел > Я.ПОТОЛОК_ЧИСЕЛ:
        raise RuntimeError(f"ядро {ядро}: {чисел} чисел, потолок {Я.ПОТОЛОК_ЧИСЕЛ}")
    return блоки, опис, чисел


def обучить_ядро(ядро: str, tr_rows, dv_rows, зерно: int, выход: Path | None, сведения: dict,
                 журнал: str | None = None) -> tuple[list, dict]:
    блоки, опис, чисел = собрать_блоки(ядро, зерно)
    понятия = Д.понятия_языка(ядро)
    tr = С.Набор(Д.строки_ядра(ядро, tr_rows), блоки, понятия)
    dv = С.Набор(Д.строки_ядра(ядро, dv_rows), блоки, понятия)
    сеть = С.Сеть(блоки, проходов=2, смешивание="среднее", градиент_через_шину=False, шум_шины=0.0)
    cfg = НАСТРОЙКИ
    итог = С.обучить(
        сеть, tr, dv, эпох=cfg["эпох"], терпение=cfg["терпение"], пакет=cfg["пакет"],
        lr=cfg["lr"], λ=cfg["λ"], p_выходной=cfg["p_выходной"], seed=зерно,
        журнал=журнал, имя=f"{ядро}",
    )
    итог["чисел"] = чисел
    if выход is not None:
        язык = (ЯзыкИмени() if ядро == "имя" else ЯзыкУпотребления()).паспорт_языка()
        выход.mkdir(parents=True, exist_ok=True)
        for b, о in zip(блоки, опис):
            bd = выход / b.имя
            bd.mkdir(parents=True, exist_ok=True)
            w = bd / "веса.npz"
            b.сохранить(str(w))
            паспорт = {
                "имя": b.имя, "версия": 1,
                "роль": b.роль, "область": о["область"], "архитектура": "мешок_шина",
                "настройки": {"корзины": b.B, "размер": b.d, "граница": b.L, "соль": b.соль,
                              "свёртка": b.свёртка, "масштаб_чтения": b.масштаб},
                "веса": {"файл": "веса.npz", "sha256": sha256_файла(w), "чисел": b.чисел()},
                "язык": язык, "пишет": b.пишет, "читает": b.читает, "ответы": b.ответы,
                "классы": о["классы"],
                "проекции": {a: {о["область"]: 16.0} for a in b.ответы},
                "обучение": {"скрипт": "nnl_isa/обучить.py", "ядро": ядро, "зерно": зерно,
                             "когда": datetime.now().isoformat(timespec="seconds"),
                             "данные": сведения, "эпох": итог["эпох"], "лучший_dev": итог["лучший_dev"],
                             "настройки": cfg, "вместе_с": [x.имя for x in блоки if x is not b]},
            }
            (bd / "паспорт.json").write_text(json.dumps(паспорт, ensure_ascii=False, indent=1), encoding="utf-8")
        (выход / "ход_обучения.json").write_text(
            json.dumps({k: v for k, v in итог.items() if k != "ход"} | {"ход": итог["ход"]},
                       ensure_ascii=False, indent=1), encoding="utf-8")
    return блоки, итог


def вероятности_сети(сеть: С.Сеть, токены: list[str]) -> dict:
    """Тот же softmax, что у обучения: «ничего» = 0, затем ответы блоков после двух тактов."""
    import math
    запись: dict[str, list] = {}
    for b in сеть.блоки:
        h = _h_уч(b, токены)
        if b.пишет:
            c = b.L * __import__("numpy").tanh((h @ b.P["A"] + b.P["a"]) / b.L)
            for k, v in zip(b.пишет, c):
                запись.setdefault(str(k), []).append(float(v))
    шина = {k: sum(v) / len(v) for k, v in запись.items()}
    логиты = {"ничего": 0.0}
    for b in сеть.блоки:
        h = _h_уч(b, токены)
        s = h @ b.P["U"] + b.P["b"]
        if b.читает:
            import numpy as np
            x = np.zeros(2 * len(b.читает), np.float64)
            for j, k in enumerate(b.читает):
                if k in шина:
                    x[j] = шина[k] / b.масштаб
                    x[len(b.читает) + j] = 1.0
            s = s + x @ b.P["V"]
        for a, v in zip(b.ответы, s):
            логиты[a] = float(v)
    return _softmax(логиты)


def _h_уч(b, токены):
    import numpy as np
    if not токены:
        return np.zeros(b.d, np.float64)
    idx = b.индексы(токены)
    s = b.P["E"][idx].astype(np.float64).sum(0)
    return s / (np.sqrt(len(idx)) if b.свёртка == "корень" else len(idx))


def _softmax(логиты: dict) -> dict:
    import math
    m = max(логиты.values())
    e = {k: math.exp(v - m) for k, v in логиты.items()}
    z = sum(e.values())
    return {k: v / z for k, v in e.items()}


def решение(p: dict):
    """(класс или None, имя ответа, вероятность). Ничья остаётся за «ничего»."""
    лучший, pv = "ничего", p["ничего"]
    for k, v in p.items():
        if k == "ничего":
            continue
        if v > pv:
            лучший, pv = k, v
    if лучший == "ничего":
        return None, "ничего", pv
    return Я.класс_из_ответа(лучший), лучший, pv
