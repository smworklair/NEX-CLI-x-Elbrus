# -*- coding: utf-8 -*-
"""Мнемоники MNEMONICS, их следы в 25 файлах lcc и блоки leave-mnemonic-out.

Строка обучения — одна мнемоника, не одна операция. Метку (класс) в токены
не кладём. Классы с одной мнемоникой в проверку не попадают.
"""

from __future__ import annotations

import random
from collections import defaultdict
from pathlib import Path

from vliw.core.asm_parser import MNEMONICS, parse_file

from .язык import токены_имени, токены_употребления
from . import ядра as Я

КОРЕНЬ = Path(__file__).resolve().parents[1]
ASM = КОРЕНЬ / "real_candidates_100_400" / "asm"


def _файлы():
    return sorted(ASM.glob("*.s"))


def собрать() -> dict:
    """Разбор 25 файлов один раз. Возвращает известные строки, незнакомые и сырьё операций."""
    по_мн: dict[str, list[dict]] = defaultdict(list)
    соседи: dict[str, list[list[dict]]] = defaultdict(list)
    операции = []
    for path in _файлы():
        parsed = parse_file(str(path))
        по_бандлу: dict[int, list] = defaultdict(list)
        for o in parsed.ops:
            по_бандлу[o.bundle].append(o)
        for o in parsed.ops:
            rec = {"mnemonic": o.mnemonic, "op": o.op, "channel": o.channel, "dst": o.dst,
                   "srcs": o.srcs, "flags": o.flags, "text": o.text, "cycle": o.cycle,
                   "line": o.line, "bundle": o.bundle, "file": path.name, "known": o.known}
            операции.append(rec)
            по_мн[o.mnemonic].append(rec)
        for o in parsed.ops:
            mates = [{"mnemonic": m.mnemonic, "channel": m.channel}
                     for m in по_бандлу[o.bundle] if m.index != o.index]
            соседи[o.mnemonic].append(mates)

    известные = []
    for mn, cls in sorted(MNEMONICS.items()):
        встр = по_мн.get(mn, [])
        известные.append({
            "мнемоника": mn, "класс": cls, "встреч": len(встр),
            "токены_имени": токены_имени(mn),
            "токены_употребления": токены_употребления(встр, соседи.get(mn, [])),
        })
    незнакомые = []
    for mn in sorted(set(по_мн) - set(MNEMONICS)):
        встр = по_мн[mn]
        незнакомые.append({
            "мнемоника": mn, "встреч": len(встр),
            "токены_имени": токены_имени(mn),
            "токены_употребления": токены_употребления(встр, соседи.get(mn, [])),
        })
    return {"известные": известные, "незнакомые": незнакомые, "операции": операции,
            "файлы": [p.name for p in _файлы()]}


def фолды(известные: list[dict], k: int = 5, зерно: int = 1):
    """5 блоков, стратификация по классу. Класс с одной мнемоникой — только обучение.

    Возвращает (список из k списков проверки, одиночные, имена одиночных классов).
    """
    rnd = random.Random(зерно)
    по: dict[str, list] = defaultdict(list)
    for r in известные:
        по[r["класс"]].append(r)
    блоки = [[] for _ in range(k)]
    одиночные = []
    классы_одиночные = []
    for cls, rows in sorted(по.items()):
        rows = rows[:]
        rnd.shuffle(rows)
        if len(rows) == 1:
            одиночные.append(rows[0])
            классы_одиночные.append(cls)
            continue
        for i, r in enumerate(rows):
            блоки[i % k].append(r)
    return блоки, одиночные, классы_одиночные


def обучение_и_dev(train: list[dict], зерно: int):
    """Dev только из классов, где в обучении ≥ 4 мнемоник, иначе ранняя остановка съедает класс."""
    rnd = random.Random(зерно)
    по: dict[str, list] = defaultdict(list)
    for r in train:
        по[r["класс"]].append(r)
    tr, dv = [], []
    for cls, rows in sorted(по.items()):
        rows = rows[:]
        rnd.shuffle(rows)
        if len(rows) >= 4:
            n = max(1, len(rows) // 5)
            dv += rows[:n]
            tr += rows[n:]
        else:
            tr += rows
    if not dv:
        dv = tr[:1]
        tr = tr[1:] or tr[:1]
    rnd.shuffle(tr)
    rnd.shuffle(dv)
    return tr, dv


def строки_ядра(ядро: str, rows: list[dict]) -> list[dict]:
    """Формат обучающего кода NNL. Токены — имя или употребление, метка одна."""
    ключ = "токены_имени" if ядро == "имя" else "токены_употребления"
    области = [b["область"] for b in Я.описание_блоков(ядро)]
    out = []
    for r in rows:
        обл = Я.область_класса(ядро, r["класс"])
        понятия = {a: (1.0 if a == обл else 0.0) for a in области}
        out.append({
            "токены": r[ключ],
            "понятия": понятия,
            "ответы": [Я.ответ_id(обл, r["класс"])],
            "группа": r["класс"],
            "мнемоника": r["мнемоника"],
        })
    return out


def понятия_языка(ядро: str) -> list[str]:
    return [b["область"] for b in Я.описание_блоков(ядро)]
