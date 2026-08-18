"""Замер обученной модели на файле эвала — локально, без Kaggle.

Зачем в инструменте, а не отдельным скриптом: до сих пор единственный способ
измерить модель был `training/validate_kaggle.py`, а он рассчитан на Kaggle
(грузит torch, ждёт GPU, печатает свою сводку). Пока замер живёт только там,
любая проверка гипотезы упирается в квоту GPU — 30 часов в неделю.

Здесь тот же замер на локальном движке. Классификатор намеренно совпадает по
смыслу с `validate_kaggle.classify()`: «валидно» / «хвост» (законный префикс,
но модель не остановилась) / «ресурс» (операция на канал, который её не
исполняет) / «прочее». Разделение хвоста и брака — не придирка: именно на нём
пойман EOS-баг, см. docs/EOS_INCIDENT.md.

Разбивка идёт по НАЛИЧИЮ STORE в графе, а не только по размеру. Причина в
docs/ROADMAP.md: в обучающих данных прогона 1 не было ни одной операции STORE,
и по корзинам размера эта причина размазывается, а по STORE — видна сразу.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class BenchRow:
    n: int
    kind: str
    has_store: bool
    gap: int | None = None
    first_error: str = ""


@dataclass
class BenchResult:
    rows: list[BenchRow] = field(default_factory=list)
    seconds: float = 0.0

    @property
    def valid(self) -> int:
        return sum(1 for r in self.rows if r.kind == "валидно")

    def pct(self, n: int) -> float:
        return 100.0 * n / len(self.rows) if self.rows else 0.0

    def by_kind(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for r in self.rows:
            out[r.kind] = out.get(r.kind, 0) + 1
        return out

    def split_store(self) -> dict[bool, tuple[int, int]]:
        """{есть ли STORE: (валидных, всего)} — главный разрез диагноза."""
        out: dict[bool, list[int]] = {True: [0, 0], False: [0, 0]}
        for r in self.rows:
            out[r.has_store][1] += 1
            if r.kind == "валидно":
                out[r.has_store][0] += 1
        return {k: (v[0], v[1]) for k, v in out.items()}


def _parse_graph(prompt: str):
    from ..core.dag import Instr

    instrs = []
    for line in prompt.split("\n")[2:]:
        line = line.strip()
        if line == "расписание:" or not line:
            continue
        head, _, preds_s = line.partition(" <- ")
        idx_s, _, op = head.partition(" ")
        preds = tuple(int(p) for p in preds_s.split()) if preds_s else ()
        i = int(idx_s)
        instrs.append(Instr(i, f"n{i}", op, preds, f"n{i}"))
    return instrs


def run_bench(dataset: Path, limit: int, scheduler, model,
              on_row=None) -> BenchResult:
    """Прогнать `limit` примеров. `on_row` зовётся после каждого — для прогресса."""
    from ..core.dag import DAG

    res = BenchResult()
    t0 = time.monotonic()
    with dataset.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            if len(res.rows) >= limit:
                break
            row = json.loads(line)
            instrs = _parse_graph(row["prompt"])
            dag = DAG("bench", "bench", "", instrs)
            has_store = any(i.op == "STORE" for i in instrs)

            r = scheduler.schedule(dag, model)
            st = r.search_stats
            if st["valid"]:
                kind = "валидно"
                gap = r.schedule.makespan - row.get("meta", {}).get("makespan", 0)
            elif not st["errors"] and not st["missing"]:
                kind, gap = "хвост", None
            elif any("не исполняет" in e for e in st["errors"]):
                kind, gap = "ресурс", None
            else:
                kind, gap = "прочее", None

            br = BenchRow(n=len(instrs), kind=kind, has_store=has_store, gap=gap,
                          first_error=(st["errors"][0] if st["errors"] else ""))
            res.rows.append(br)
            if on_row:
                on_row(len(res.rows), br)
    res.seconds = time.monotonic() - t0
    return res
