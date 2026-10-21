# -*- coding: utf-8 -*-
"""Зазоры «производитель → потребитель» у классов с латентностью-допущением.

Пара — запись dst и более позднее чтение того же регистра внутри одного
прямолинейного куска функции. Кусок обрывается на границе цикла: тело
loop_mode и обратная ветвь (rbranch/ibranch на более раннюю метку) — отдельные
куски, через границу последняя запись не переносится. Внутри такта записи
ещё не видны читателям (так устроен разбор широкой команды).

Правило: настоящая латентность не больше минимального зазора, поэтому
допущение больше минимума — опровергнутое допущение. Пар меньше 3 — «мало данных».
Минимум строго больше допущения — «сомнительно»: компилятор ни разу не сжал
расписание до этого числа, допущение может быть занижено, но не опровергнуто.
"""

from __future__ import annotations

import re
from pathlib import Path

from vliw.core.asm_parser import parse_file
from vliw.core.model import ASSUMED, E2K_V6_MEASURED

from .данные import ASM

# Раздел 6.1 руководства МЦСТ, выпуск 1.2 от 2024-02-28, CC BY 4.0.
# http://mcst.ru/doc/elbrus_prog/html/chapter6.html
# Документ про Е4С/Е8С, не про e2k-v6. Глава 12 — задержки пар
# (байпас внутри кластера, регистровый файл между кластерами), не одно число
# класса; в колонку её не сводим. Классов, которых в 6.1 нет, здесь нет.
ПО_РУКОВОДСТВУ = {
    "AND": "1 (Int, Bitwise)",
    "SHL": "1 (Int, Bitwise)",
    "PRED": "0.5–3 (logic→logic 0.5, Cmp→logic 1, →qual 2, →ct 3)",
    "COMBO": "2 (Int_combined)",
}

_МЕТКА = re.compile(r"^(\.L\d+):$")
_НАЗАД = re.compile(r"\b(?:rbranch|ibranch)\s+(\.L\d+)\b")
_ФУНКЦИЯ = re.compile(r"^([A-Za-z_][\w.]*):$")


def вердикт(допущение: float, мин_зазор, пар: int) -> str:
    if пар < 3 or мин_зазор is None:
        return "мало данных"
    if допущение > мин_зазор:
        return "опровергнуто"
    if мин_зазор > допущение:
        return "сомнительно"
    return "согласуется"


def _циклы(lines: list[str]) -> list[tuple[int, int]]:
    """Объединённые отрезки строк циклов: тела loop_mode и обратные ветви."""
    n = len(lines)
    i = 0
    bundles = []
    while i < n:
        if lines[i].strip().startswith("{"):
            j = i
            while j < n and not lines[j].strip().startswith("}"):
                j += 1
            body = "\n".join(lines[i:j + 1])
            bundles.append((i + 1, min(j + 1, n), "loop_mode" in body))
            i = j + 1
        else:
            i += 1
    loops: list[list[int]] = []
    cur = None
    for a, b, loop in bundles:
        if loop:
            if cur is None:
                cur = [a, b]
            else:
                cur[1] = b
        elif cur is not None:
            loops.append(cur)
            cur = None
    if cur is not None:
        loops.append(cur)
    метки = {}
    for idx, raw in enumerate(lines, 1):
        m = _МЕТКА.match(raw.strip())
        if m:
            метки[m.group(1)] = idx
    for idx, raw in enumerate(lines, 1):
        m = _НАЗАД.search(raw)
        if m and метки.get(m.group(1), 10**9) < idx:
            loops.append([метки[m.group(1)], idx])
    return _слить(loops)


def _слить(spans: list[list[int]]) -> list[tuple[int, int]]:
    if not spans:
        return []
    spans = sorted(spans)
    out = [tuple(spans[0])]
    for a, b in spans[1:]:
        if a <= out[-1][1] + 1:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def _функции(lines: list[str]) -> list[tuple[str, int, int]]:
    spans = []
    cur = None
    in_text = False
    for i, raw in enumerate(lines, 1):
        s = raw.strip()
        if s.startswith(".text"):
            in_text = True
        if s.startswith(".section") or s.startswith(".data") or s.startswith(".bss"):
            if cur is not None and not s.startswith(".text"):
                spans.append((cur[0], cur[1], i - 1))
                cur = None
            in_text = s.startswith(".text")
        if s.startswith(".size") and cur is not None:
            spans.append((cur[0], cur[1], i))
            cur = None
            continue
        m = _ФУНКЦИЯ.match(s)
        if m and in_text:
            if cur is not None:
                spans.append((cur[0], cur[1], i - 1))
            cur = (m.group(1), i)
    if cur is not None:
        spans.append((cur[0], cur[1], len(lines)))
    return spans


def _куски(func: tuple[int, int], loops: list[tuple[int, int]]) -> list[tuple[int, int]]:
    a, b = func
    inside = []
    for s, e in loops:
        if e < a or s > b:
            continue
        inside.append((max(s, a), min(e, b)))
    inside = _слить([list(x) for x in inside])
    out = []
    cur = a
    for s, e in inside:
        if cur <= s - 1:
            out.append((cur, s - 1))
        out.append((s, e))
        cur = e + 1
    if cur <= b:
        out.append((cur, b))
    return out


def _пары_куска(ops: list) -> list[tuple]:
    """ops уже одного куска, в порядке файла. Возвращает (prod, cons, gap)."""
    ops = sorted(ops, key=lambda o: (o.cycle, o.index))
    last: dict[str, object] = {}
    pairs = []
    i = 0
    while i < len(ops):
        j = i
        while j < len(ops) and ops[j].cycle == ops[i].cycle:
            j += 1
        for o in ops[i:j]:
            for src in o.srcs:
                w = last.get(src)
                if w is None:
                    continue
                gap = o.cycle - w.cycle
                if gap > 0:
                    pairs.append((w, o, gap))
        for o in ops[i:j]:
            if o.dst:
                last[o.dst] = o
        i = j
    return pairs


def зазоры() -> list[dict]:
    """По одному ряду на класс с допущением, который встречается в файлах."""
    model = E2K_V6_MEASURED
    предполагаемые = {name for name, op in model.ops.items()
                      if op.latency_source == ASSUMED and name != "UNKNOWN"}
    лучший: dict[str, dict] = {}
    счёт: dict[str, int] = {}
    встреч: dict[str, int] = {}
    for path in sorted(ASM.glob("*.s")):
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
        parsed = parse_file(str(path))
        loops = _циклы(lines)
        funcs = _функции(lines)
        if not funcs:
            funcs = [("", 1, len(lines))]
        куски = []
        for _name, a, b in funcs:
            куски.extend(_куски((a, b), loops))
        for o in parsed.ops:
            if o.op in предполагаемые:
                встреч[o.op] = встреч.get(o.op, 0) + 1
        по_кускам: dict[int, list] = {i: [] for i in range(len(куски))}
        for o in parsed.ops:
            for i, (a, b) in enumerate(куски):
                if a <= o.line <= b:
                    по_кускам[i].append(o)
                    break
        for ops in по_кускам.values():
            for w, o, gap in _пары_куска(ops):
                if w.op not in предполагаемые:
                    continue
                счёт[w.op] = счёт.get(w.op, 0) + 1
                rec = {"зазор": gap, "файл": path.name, "производитель": w.mnemonic,
                       "строка_пр": w.line, "потребитель": o.mnemonic, "строка_пт": o.line,
                       "такт_пр": w.cycle, "такт_пт": o.cycle}
                if w.op not in лучший or gap < лучший[w.op]["зазор"]:
                    лучший[w.op] = rec
    ряды = []
    for name in sorted(встреч):
        lat = model.ops[name].latency
        пар = счёт.get(name, 0)
        мин = лучший[name]["зазор"] if name in лучший else None
        ряды.append({
            "класс": name,
            "допущение": lat,
            "встреч": встреч[name],
            "пар": пар,
            "мин_зазор": мин,
            "вердикт": вердикт(lat, мин, пар),
            "пример": лучший.get(name),
            "по_руководству": ПО_РУКОВОДСТВУ.get(name, ""),
            "руководство": "Е4С/Е8С, выпуск 1.2, не e2k-v6",
        })
    return ряды
