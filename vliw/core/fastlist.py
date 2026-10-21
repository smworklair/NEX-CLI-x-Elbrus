"""Быстрый жадный потактовый движок: ТЕ ЖЕ расписания, что у `list_schedule`.

Зачем. На настоящем коде 95 % времени портфеля крошек уходит не в нейросети, а
в `baseline.list_schedule`: на каждом такте он заново перебирает ВСЕ ещё не
выданные инструкции и для каждой проверяет всех предшественников, а ещё строит
кортежи каналов заново. Для блока в 300 операций это сотни тысяч лишних шагов.

Что делает этот модуль. Выдаёт ровно то же расписание — для КАЖДОЙ инструкции
тот же такт и тот же канал, — но считает иначе:

  * достоверность готовности — счётчиком оставшихся предшественников, а не
    перебором (`remaining[i]`);
  * ключ сортировки считается один раз на запуск: `rank[i]` — место инструкции
    в порядке (−приоритет, номер); дальше на такте сортируются только готовые;
  * каналы инструкции заранее отсортированы по (цена канала, номер) — первый
    свободный и есть `min(free, key=(costs, c))` оригинала;
  * такты, в которые ничего выдать нельзя, пропускаются прыжком к ближайшему
    моменту, когда это станет возможным (в такты без выдачи состояние машины не
    меняется, так что результат тот же);
  * объекты `Schedule`/`Placement` строятся только для тех вариантов, которые
    действительно нужны (лучший на сей момент), а не для каждого запуска.

Что это НЕ делает: трассу решений (`collect_trace`) не ведёт — это остаётся за
`baseline.list_schedule`. Поведение при нестандартных входах то же:
операция без исполнимого канала → «планировщик зациклился» (RuntimeError).

Строгое равенство подтверждается тестами (`tests/test_fastlist.py`): сравнение
`placements` целиком и порядка выдачи с оригиналом на случайных графах,
случайных приоритетах (с множеством ничьих), случайных `defer_until`, на всех
профилях машин и на разной ширине.

Единственное допущение: приоритеты — конечные числа (NaN в ключе сортировки
ломает порядок и у оригинала).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .baseline import channel_costs
from .dag import DAG
from .model import MachineModel
from .schedule import Placement, Schedule

_GUARD = 100000  # как в list_schedule

# Таблица «операция → (латентность, занятость, каналы по цене)» зависит только от
# машины, а считать её дорого (channel_costs зовёт channels_for 150 раз). Модели
# живут долго (PROFILES), поэтому кэш по id с проверкой `is`; размер ограничен,
# чтобы массовый прогон с `with_width` не копил модели.
_TABLES: dict[int, tuple[MachineModel, dict[str, tuple[int, int, tuple[int, ...]]], list[int]]] = {}
_TABLES_MAX = 16


def _model_table(model: MachineModel):
    e = _TABLES.get(id(model))
    if e is not None and e[0] is model:
        return e[1], e[2]
    if len(_TABLES) >= _TABLES_MAX:
        _TABLES.clear()
    costs = channel_costs(model)
    by_op: dict[str, tuple[int, int, tuple[int, ...]]] = {}
    _TABLES[id(model)] = (model, by_op, costs)
    return by_op, costs


class ListPlan:
    """Всё, что не зависит от приоритетов и держек: считается один раз на граф."""

    __slots__ = ("dag", "model", "n", "width", "lat", "occ", "caps",
                 "npreds", "succs", "roots")

    def __init__(self, dag: DAG, model: MachineModel) -> None:
        n = len(dag)
        self.dag = dag
        self.model = model
        self.n = n
        self.width = model.width
        by_op, costs = _model_table(model)
        lat: list[int] = []
        occ: list[int] = []
        caps: list[tuple[int, ...]] = []
        for ins in dag:
            e = by_op.get(ins.op)
            if e is None:
                capable = model.channels_for(ins.op)
                e = (model.latency(ins.op), model.occupancy(ins.op),
                     tuple(sorted(capable, key=lambda c: (costs[c], c))))
                by_op[ins.op] = e
            lat.append(e[0])
            occ.append(e[1])
            caps.append(e[2])
        self.lat = lat
        self.occ = occ
        self.caps = caps
        self.npreds = [len(ins.preds) for ins in dag]
        self.succs = dag.succs
        self.roots = [i for i in range(n) if not self.npreds[i]]

    def run(self, priority: Sequence[float],
            defer_until: Mapping[int, int] | None = None) -> "RawSchedule":
        """Один проход. `priority`: чем больше, тем раньше. `defer_until`:
        «не раньше такта» (как в `list_schedule`)."""
        n = self.n
        if n == 0:
            return RawSchedule([], [], [], 0)
        neg = [-p for p in priority]
        order = sorted(range(n), key=neg.__getitem__)  # устойчиво: ничьи — по номеру
        rank = [0] * n
        for r, i in enumerate(order):
            rank[i] = r

        lat, occ, caps, succs = self.lat, self.occ, self.caps, self.succs
        remaining = self.npreds[:]
        ready_time = [0] * n
        cyc = [-1] * n
        chn = [-1] * n
        free_at = [0] * self.width
        pool = self.roots[:]
        placed: list[int] = []
        left = n
        cycle = 0
        iters = 0
        dget = defer_until.get if defer_until else None
        rank_get = rank.__getitem__

        while left:
            iters += 1
            if iters > _GUARD:
                raise RuntimeError("планировщик зациклился")
            cands = [i for i in pool if ready_time[i] <= cycle]
            if cands:
                if len(cands) > 1:
                    cands.sort(key=rank_get)
                did = False
                newly: list[int] | None = None
                for i in cands:
                    if dget is not None and dget(i, 0) > cycle:
                        continue
                    for c in caps[i]:
                        if free_at[c] <= cycle:
                            break
                    else:
                        continue
                    cyc[i] = cycle
                    chn[i] = c
                    free_at[c] = cycle + occ[i]
                    placed.append(i)
                    left -= 1
                    did = True
                    avail = cycle + lat[i]
                    for s in succs[i]:
                        if ready_time[s] < avail:
                            ready_time[s] = avail
                        r = remaining[s] - 1
                        remaining[s] = r
                        if not r:
                            if newly is None:
                                newly = [s]
                            else:
                                newly.append(s)
                    if min(free_at) > cycle:
                        break  # все каналы заняты: дальше такт ничего не даст
                if did:
                    pool = [i for i in pool if cyc[i] < 0]
                    if newly:
                        pool += newly
                    cycle += 1
                    continue
            # В этот такт ничего не выдано: состояние машины не изменилось и не
            # изменится до ближайшего момента, когда какая-то инструкция из пула
            # станет готова, снимется держка и освободится её канал.
            wake = -1
            for i in pool:
                ci = caps[i]
                if not ci:
                    continue
                t = ready_time[i]
                if dget is not None:
                    d = dget(i, 0)
                    if d > t:
                        t = d
                f = min([free_at[c] for c in ci])
                if f > t:
                    t = f
                if wake < 0 or t < wake:
                    wake = t
            if wake < 0:
                raise RuntimeError("планировщик зациклился")
            cycle = wake if wake > cycle else cycle + 1

        ms = 0
        for i in range(n):
            v = cyc[i] + lat[i]
            if v > ms:
                ms = v
        return RawSchedule(cyc, chn, placed, ms)

    def to_schedule(self, raw: "RawSchedule") -> Schedule:
        """Настоящий `Schedule` (порядок вставки в `placements` — порядок выдачи,
        как у оригинала)."""
        s = Schedule(self.dag, self.model)
        pl = s.placements
        cyc, chn = raw.cycle, raw.channel
        for i in raw.order:
            pl[i] = Placement(i, cyc[i], chn[i])
        return s


@dataclass(slots=True)
class RawSchedule:
    """Расписание без объектов: такт и канал по номеру инструкции."""

    cycle: list[int]
    channel: list[int]
    order: list[int]  # инструкции в порядке выдачи
    makespan: int


def list_schedule_fast(dag: DAG, model: MachineModel, priority: Sequence[float],
                       *, defer_until: Mapping[int, int] | None = None,
                       height: Sequence[int] | None = None) -> tuple[Schedule, list]:
    """Замена `baseline.list_schedule(..., collect_trace=False)` по сигнатуре:
    тот же `Schedule`, пустая трасса. `height` принимается ради совместимости
    (на расписание не влияет)."""
    plan = ListPlan(dag, model)
    return plan.to_schedule(plan.run(priority, defer_until)), []
