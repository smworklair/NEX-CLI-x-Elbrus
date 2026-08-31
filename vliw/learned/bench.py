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
class SampleOutcome:
    """Итог одного сэмпла внутри best-of: ровно то, по чему идёт выбор.

    `gap` — только у валидного сэмпла: сравнивать makespan битых ответов
    с оптимумом бессмысленно.
    """

    valid: bool
    errors: int
    missing: int
    makespan: int
    gap: int | None = None


@dataclass(frozen=True)
class BestOf:
    """N сэмплов на граф при temperature>0, лучший по validate().

    Зачем: repair() чинит ТОЛЬКО канал (см. его докстринг) — нарушения
    зависимости и занятости порта во времени он сознательно не трогает.
    А вот другой сэмпл может их просто не совершить: при температуре модель
    каждый раз пишет расписание чуть иначе, и среди N попыток законное
    встречается чаще, чем в одной. Это и измеряется здесь.

    `seed` — база: сэмпл k получает seed+k. Пришпилён не для красоты:
    без него повторный прогон замера давал бы другие числа, а одинаковый
    seed на все k — N одинаковых ответов и вырожденный best-of.
    """

    n: int = 1
    temperature: float = 0.0
    seed: int = 1

    def sample_seed(self, k: int) -> int:
        return self.seed + k


@dataclass
class BenchRow:
    n: int
    kind: str
    has_store: bool
    gap: int | None = None
    first_error: str = ""
    samples: list[SampleOutcome] | None = None
    """Сэмплы best-of по порядку k=0..N-1. None — обычный прогон без сэмплинга.

    Хранить их все, а не только итог, нужно ради таблицы: best-of-2 и
    best-of-4 — это те же сэмплы, усечённые до первых 2 и 4. Один прогон
    с N=8 отвечает сразу на все k ≤ 8, без отдельных забегов на каждый N.
    """

    cab_improved: bool = False
    """Победитель портфеля строго короче жадного кандидата, а не вничью."""

    cab_winner: str | None = None
    """Кто выиграл портфель CAB на этом графе. None — портфель выключен.

    Без этого замер отвечает «сколько тактов», но не «чья это работа»: на
    трудном эвале жадный кандидат лежит в портфеле и не даёт результату
    стать хуже baseline, поэтому по одному среднему нельзя понять, добавила
    модель что-нибудь или просто не помешала.
    """

    @property
    def valid_samples(self) -> int:
        return sum(1 for s in self.samples or () if s.valid)


@dataclass
class BenchResult:
    rows: list[BenchRow] = field(default_factory=list)
    seconds: float = 0.0
    best_of: BestOf | None = None

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

    def cab_winners(self) -> dict[str, tuple[int, int]]:
        """{кандидат: (побед, из них строго лучше жадного)}.

        Второе число и есть вклад: победа вничью означает, что кандидат
        совпал с эвристикой, а не обыграл её.
        """
        out: dict[str, list[int]] = {}
        for r in self.rows:
            if r.cab_winner:
                slot = out.setdefault(r.cab_winner, [0, 0])
                slot[0] += 1
                slot[1] += 1 if r.cab_improved else 0
        return {k: (v[0], v[1]) for k, v in out.items()}

    def split_store(self) -> dict[bool, tuple[int, int]]:
        """{есть ли STORE: (валидных, всего)} — главный разрез диагноза."""
        out: dict[bool, list[int]] = {True: [0, 0], False: [0, 0]}
        for r in self.rows:
            out[r.has_store][1] += 1
            if r.kind == "валидно":
                out[r.has_store][0] += 1
        return {k: (v[0], v[1]) for k, v in out.items()}

    def best_of_valid(self, k: int) -> tuple[int, int]:
        """(валидных среди первых k сэмплов, строк с сэмплами).

        «Валиден best-of-k» = ХОТЯ БЫ один из первых k сэмплов валиден —
        выбор идёт по минимуму нарушений, а валидный сэмпл нарушений не
        имеет и выигрывает у любого битого.
        """
        rows = [r for r in self.rows if r.samples]
        return (sum(1 for r in rows if any(s.valid for s in r.samples[:k])),
                len(rows))


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


def _candidate_key(res):
    """Порядок кандидатов best-of: меньше нарушений → меньше makespan.

    Ошибки validate() и неразмещённые инструкции считаются НАРАВНЕ: и то и
    другое — провал графа, а не частичная заслуга. makespan — только
    тай-брейк: сравнивать его между битыми ответами смысла нет, а вот между
    двумя валидными — это и есть качество плана.
    """
    st = res.search_stats
    unplaced = 0 if res.schedule.complete else len(st["missing"])
    return (len(st["errors"]) + unplaced, res.schedule.makespan)


def _sample_outcome(res, meta_makespan: int) -> SampleOutcome:
    st = res.search_stats
    return SampleOutcome(
        valid=st["valid"],
        errors=len(st["errors"]),
        missing=0 if res.schedule.complete else len(st["missing"]),
        makespan=res.schedule.makespan,
        gap=res.schedule.makespan - meta_makespan if st["valid"] else None,
    )


def _candidates(scheduler, dag, model, best_of: BestOf | None):
    """Все ответы модели на один граф. Без best_of — один, прежним путём."""
    if best_of is None:
        return [scheduler.schedule(dag, model)]

    # Атрибуты, а не аргументы schedule(): протокол Scheduler фиксирован,
    # и bench меняет сэмплинг между попытками. Нет атрибутов — перед нами не
    # обученный планировщик, и best-of к нему неприменим.
    if not hasattr(scheduler, "temperature"):
        raise TypeError(
            "best-of требует обученный планировщик с сэмплингом "
            "(vliw.learned.LearnedScheduler)")

    out = []
    for k in range(max(1, best_of.n)):
        scheduler.temperature = best_of.temperature
        scheduler.seed = best_of.sample_seed(k)
        out.append(scheduler.schedule(dag, model))
    return out


def run_bench(dataset: Path, limit: int, scheduler, model,
              on_row=None, best_of: BestOf | None = None) -> BenchResult:
    """Прогнать `limit` примеров. `on_row` зовётся после каждого — для прогресса.

    `best_of` включает выбор из N сэмплов при temperature>0: каждый сэмпл
    идёт через тот же конвейер (включая repair() планировщика), побеждает
    кандидат с меньшим числом нарушений, при равенстве — с меньшим makespan.
    None — прежний путь: один жадный ответ, как на всех замерах.
    """
    from ..core.dag import DAG

    res = BenchResult(best_of=best_of)
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
            meta_makespan = row.get("meta", {}).get("makespan", 0)

            cands = _candidates(scheduler, dag, model, best_of)
            r = min(cands, key=_candidate_key) if len(cands) > 1 else cands[0]

            st = r.search_stats
            if st["valid"]:
                kind = "валидно"
                gap = r.schedule.makespan - meta_makespan
            elif not st["errors"] and not st["missing"]:
                kind, gap = "хвост", None
            elif any("не исполняет" in e for e in st["errors"]):
                kind, gap = "ресурс", None
            else:
                kind, gap = "прочее", None

            br = BenchRow(n=len(instrs), kind=kind, has_store=has_store, gap=gap,
                          cab_winner=st.get("cab_winner"),
                          cab_improved=bool(st.get("cab_beat_greedy")),
                          first_error=(st["errors"][0] if st["errors"] else ""),
                          samples=([_sample_outcome(c, meta_makespan)
                                    for c in cands] if best_of is not None else None))
            res.rows.append(br)
            if on_row:
                on_row(len(res.rows), br)
    res.seconds = time.monotonic() - t0
    return res
