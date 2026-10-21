# -*- coding: utf-8 -*-
"""Строки для обучения и оценки ядер: метки портфеля (tools/portfolio_labels.py) + токены графа."""

from __future__ import annotations

import json
import random
from pathlib import Path

from .язык import ЯзыкГрафов
from . import ядра as Я


def прочитать_метки(путь) -> list[dict]:
    return [json.loads(x) for x in Path(путь).read_text(encoding="utf-8").splitlines() if x.strip()]


def с_токенами(метки: list[dict], язык: ЯзыкГрафов | None = None) -> list[dict]:
    """Каждой метке добавляет токены и понятия графа (prompt после этого не нужен)."""
    язык = язык or ЯзыкГрафов()
    out = []
    for m in метки:
        t = язык.перевести(m["prompt"])
        out.append({"ключ": m["ключ"], "n": m["n"], "лучший": m["лучший"], "по_группам": m["по_группам"],
                    "дешёвая": m["дешёвая"], "токены": t["токены"], "понятия": t["понятия"]})
    return out


def строки_ядра(ядро: str, база: list[dict]) -> list[dict]:
    """Строки в формате обучающего кода NNL: {токены, понятия, ответы, группа}."""
    out = []
    for r in база:
        обл = Я.область_строки(ядро, r["понятия"])
        out.append({"токены": r["токены"], "понятия": r["понятия"], "группа": r["дешёвая"],
                    "ответы": [Я.ответ_id(обл, r["дешёвая"])], "ключ": r["ключ"]})
    return out


def разбить(база: list[dict], доля_жадных: float = 1.0, доля_dev: float = 0.15, зерно: int = 1):
    """Обучение/dev. В обучение идут все трудные графы (дешёвая группа не greedy) и
    жадных не больше `доля_жадных` от числа трудных (иначе ядро выучит «всегда greedy»).
    Dev берётся из того же набора стратифицированно по группе — по нему ранняя остановка."""
    rnd = random.Random(зерно)
    трудные = [r for r in база if r["дешёвая"] != "greedy"]
    лёгкие = [r for r in база if r["дешёвая"] == "greedy"]
    rnd.shuffle(лёгкие)
    пул = трудные + лёгкие[:int(доля_жадных * len(трудные))]
    по_группам: dict[str, list] = {}
    for r in пул:
        по_группам.setdefault(r["дешёвая"], []).append(r)
    tr, dv = [], []
    for g, rows in sorted(по_группам.items()):
        rnd.shuffle(rows)
        k = max(1, int(доля_dev * len(rows)))
        dv += rows[:k]
        tr += rows[k:]
    rnd.shuffle(tr)
    rnd.shuffle(dv)
    return tr, dv
