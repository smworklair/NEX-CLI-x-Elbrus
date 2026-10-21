"""Быстрые крошки: то же качество, меньше времени. Новый файл, старый код не тронут.

Что здесь и почему (замеры — docs/TINY_FAST.md):

  1. ГРАНИЦА. У графа есть нижняя граница makespan (`DagMetrics.lower_bound`):
     быстрее неё расписания не бывает. Если жадный уже на границе — оптимум
     доказан, искать нечего. Если какой-то член портфеля дошёл до границы —
     остальные ничего не улучшат. Останавливаемся. Потери качества нет по
     построению: итоговый makespan тот же, что у полного `TinyScheduler`.
     На 3800 графах граница ни разу не оказалась выше найденного оптимума.

  2. ПОРЯДОК. Группы портфеля идут не как исторически добавлялись, а по
     «дёшево и результативно»: bh, rule, bt, prio, hold, defer. Порядок не
     влияет на итоговый makespan при полном проходе, только на то, как рано
     мы упрёмся в границу.

  3. БЫСТРЫЙ ВЫВОД. `FastNet` считает ровно те же числа, что
     `TinyPriority.scores`, в том же порядке сложений (проверено на ==, не на
     «почти»), но по строкам весов; с numpy — ещё в разы быстрее. Метрики и
     фичи графа считаются один раз на график, а не по разу на каждую сеть.

  4. РЕЖИМ "asm". Без групп hold и defer. На 1514 настоящих графах из ваших
     .s эти две группы не дали ничего (после остальных), на eval_hard — 6 из
     300. Это уже НЕ гарантия, а замер: режим выбирает вызывающий.

Гарантии класса `TinyFastScheduler(mode="exact")`:
  * makespan равен makespan `TinyScheduler` на любом графе (при корректной
    нижней границе); не хуже жадного (жадный идёт первым, как и раньше);
  * каждое принятое расписание прошло `validate()` и `complete`;
  * `optimal=True` в результате ставится только когда makespan == границе,
    то есть оптимум доказан.
"""

from __future__ import annotations

import os
import threading

from ..core.api import SchedulingResult
from ..core.baseline import GreedyListScheduler, list_schedule
from ..core.dag import DAG, compute_metrics
from ..core.fastlist import ListPlan
from ..core.model import MachineModel
from .features import featurize, transitive_succs
from .scheduler import TinyScheduler

try:  # numpy только ускоряет; без него тот же результат чистым Python
    if os.environ.get("VLIW_NO_NUMPY"):
        raise ImportError
    import numpy as _np
except Exception:  # noqa: BLE001
    _np = None

#: Порядок групп: дешёвые и результативные первыми (см. docs/TINY_FAST.md).
DEFAULT_ORDER: tuple[str, ...] = ("bh", "rule", "bt", "prio", "hold", "defer")
#: Режим "asm": без дорогих групп, не давших ничего на настоящем коде.
ASM_ORDER: tuple[str, ...] = ("bh", "rule", "bt", "prio")
_NEEDS_PRIO = frozenset({"prio", "defer", "hold", "rule", "bt"})


# --------------------------------------------------------------------------
# Быстрый прямой проход
# --------------------------------------------------------------------------


class FastNet:
    """Те же числа, что `TinyPriority.scores`, в том же порядке сложений.

    Оригинал для каждого выхода делает s = b; s += x0*w0; s += x1*w1; ...
    (нулевые входы пропускает). Здесь то же самое, но накопление идёт сразу по
    всем выходам слоя списковым выражением: для каждого выхода последовательность
    сложений та же, поэтому результат совпадает побитово.

    Плюс память по строкам признаков: одинаковый вход даёт одинаковый выход, так
    что повторяющиеся строки (на настоящем коде уникальны 32 % строк внутри
    блока и 12 % среди всех блоков) считаются один раз. Память ограничена
    (`memo_limit` строк; при переполнении очищается целиком); ноль выключает
    запоминание МЕЖДУ вызовами, повторы внутри одного вызова всё равно
    считаются один раз.
    """

    MEMO_LIMIT = 32768

    def __init__(self, net, memo_limit: int | None = None) -> None:
        self.w1 = [list(r) for r in net.w1]
        self.b1 = list(net.b1)
        self.w2 = [list(r) for r in net.w2]
        self.b2 = list(net.b2)
        self.w3 = list(net.w3)
        self.b3 = net.b3
        self.target = getattr(net, "target", None)
        self.memo_limit = self.MEMO_LIMIT if memo_limit is None else memo_limit
        self._memo: dict[tuple, float] = {}

    @property
    def h1(self) -> int:
        return len(self.b1)

    @property
    def h2(self) -> int:
        return len(self.b2)

    def clear_memo(self) -> None:
        self._memo.clear()

    def scores(self, X: list[list[float]]) -> list[float]:
        if not X:
            return []
        keys = [tuple(r) for r in X]
        memo = self._memo if self.memo_limit > 0 else None
        res: dict[tuple, float | None] = {}
        miss: list[tuple] = []
        for k in keys:
            if k in res:
                continue
            v = memo.get(k) if memo is not None else None
            res[k] = v
            if v is None:
                miss.append(k)
        if miss:
            vals = self._forward(miss)
            res.update(zip(miss, vals))
            if memo is not None:
                if len(memo) + len(miss) > self.memo_limit:
                    memo.clear()
                memo.update(zip(miss, vals))
        return [res[k] for k in keys]

    def _forward(self, X) -> list[float]:
        w1, b1, w2, b2, w3, b3 = self.w1, self.b1, self.w2, self.b2, self.w3, self.b3
        out: list[float] = []
        for row in X:
            acc = b1
            for i, v in enumerate(row):
                if v:
                    acc = [a + v * w for a, w in zip(acc, w1[i])]
            acc2 = b2
            for k, a in enumerate(acc):
                if a > 0.0:
                    acc2 = [x + a * w for x, w in zip(acc2, w2[k])]
            s = b3
            for k, x in enumerate(acc2):
                if x > 0.0:
                    s += x * w3[k]
            out.append(s)
        return out


class FastNetNp(FastNet):
    """То же, но слоями на numpy: сложения по k идут последовательно (как в
    оригинале), отдельными операциями умножения и сложения, без FMA и без
    попарного суммирования, поэтому и здесь совпадение побитовое."""

    def __init__(self, net, memo_limit: int | None = None) -> None:
        super().__init__(net, memo_limit)
        self._w1 = _np.asarray(self.w1, dtype=_np.float64)
        self._b1 = _np.asarray(self.b1, dtype=_np.float64)
        self._w2 = _np.asarray(self.w2, dtype=_np.float64)
        self._b2 = _np.asarray(self.b2, dtype=_np.float64)
        self._w3 = _np.asarray(self.w3, dtype=_np.float64)

    def _forward(self, X) -> list[float]:
        A = _np.asarray(X, dtype=_np.float64)
        n = A.shape[0]
        acc = _np.tile(self._b1, (n, 1))
        for i in range(A.shape[1]):
            col = A[:, i:i + 1]
            if col.any():
                acc += col * self._w1[i]
        a1 = _np.maximum(acc, 0.0)
        acc2 = _np.tile(self._b2, (n, 1))
        for k in range(a1.shape[1]):
            col = a1[:, k:k + 1]
            if col.any():
                acc2 += col * self._w2[k]
        a2 = _np.maximum(acc2, 0.0)
        s = _np.full(n, float(self.b3))
        for k in range(a2.shape[1]):
            s += a2[:, k] * self._w3[k]
        return s.tolist()


def make_fast(net, use_numpy: bool | None = None, memo_limit: int | None = None):
    """Быстрая копия сети (или None). numpy — если есть и не отключён."""
    if net is None:
        return None
    if use_numpy is None:
        use_numpy = _np is not None
    if use_numpy and _np is not None:
        return FastNetNp(net, memo_limit)
    return FastNet(net, memo_limit)


# --------------------------------------------------------------------------
# Планировщик
# --------------------------------------------------------------------------


class _Ctx:
    """Всё, что считается один раз на график."""

    __slots__ = ("dag", "model", "metrics", "X", "prio", "rule_common", "base_cycles")

    def __init__(self, dag: DAG, model: MachineModel) -> None:
        self.dag = dag
        self.model = model
        self.metrics = compute_metrics(dag, model)
        self.X = None
        self.prio = None
        self.rule_common = None
        self.base_cycles = None  # такт выдачи каждой инструкции у жадного


class TinyFastScheduler(TinyScheduler):
    name = "Крошки быстрые (граница + порядок групп, без потерь)"
    kind = "learned"
    short = "tiny-fast"

    def __init__(self, weights: str | None = None,
                 defer_weights: str | None = None,
                 hold_weights: str | None = None,
                 beam: int = 16,
                 mode: str = "exact",
                 order: tuple[str, ...] | None = None,
                 stop_at_bound: bool = True,
                 use_numpy: bool | None = None,
                 with_trace: bool = True,
                 memo_limit: int | None = None) -> None:
        super().__init__(weights, defer_weights, hold_weights, beam)
        if mode not in ("exact", "asm"):
            raise ValueError(f"mode: 'exact' или 'asm', получено {mode!r}")
        self.mode = mode
        self.order = tuple(order) if order else (ASM_ORDER if mode == "asm" else DEFAULT_ORDER)
        unknown = set(self.order) - {"bh", "rule", "bt", "prio", "hold", "defer"}
        if unknown:
            raise ValueError(f"неизвестные группы: {sorted(unknown)}")
        self.stop_at_bound = stop_at_bound
        # Трасса решений нужна экрану разбора и объяснениям; при компиляции она
        # не нужна. True — как у TinyScheduler (один дополнительный прогон с
        # трассой, только для победителя); False — пустая трасса, быстрее.
        self.with_trace = with_trace
        # быстрые копии: те же веса, те же числа на выходе
        self.tiny = make_fast(self.tiny, use_numpy, memo_limit)
        self.defer = make_fast(self.defer, use_numpy, memo_limit)
        self.hold = make_fast(self.hold, use_numpy, memo_limit)
        self._tl = threading.local()

    # -- кэш на один вызов schedule(); вне его всё работает как у родителя ----

    def _ctx(self, dag: DAG, model: MachineModel) -> _Ctx | None:
        c = getattr(self._tl, "ctx", None)
        return c if (c is not None and c.dag is dag and c.model is model) else None

    @staticmethod
    def _features(c: _Ctx):
        if c.X is None:
            c.X = featurize(c.dag, c.model)
        return c.X

    def priority(self, dag: DAG, model: MachineModel) -> list[float]:
        c = self._ctx(dag, model)
        if c is None:
            return super().priority(dag, model)
        if c.prio is None:
            if self.tiny is None:
                c.prio = [float(h) for h in c.metrics.height]
            else:
                c.prio = self.tiny.scores(self._features(c))
        return c.prio

    def _holds_of(self, net, dag: DAG, model: MachineModel, limit: int) -> dict[int, int]:
        c = self._ctx(dag, model)
        if c is None or net is None:
            return super()._holds_of(net, dag, model, limit)
        preds = net.scores(self._features(c))
        if getattr(net, "target", None) == "hold":
            asap = c.metrics.asap
            return {i: t for i, v in enumerate(preds)
                    for t in (asap[i] + int(round(v)),)
                    if 0 < t <= limit}
        return {i: t for i, v in enumerate(preds)
                for t in (int(round(v)),)
                if 0 < t <= limit}

    def _rule_common(self, dag: DAG, model: MachineModel):
        c = self._ctx(dag, model)
        if c is None:
            return super()._rule_common(dag, model)
        if c.rule_common is None:
            n = len(dag)
            m = c.metrics
            chans = [frozenset(model.channels_for(ins.op)) for ins in dag]
            occs = [model.occupancy(ins.op) for ins in dag]
            reach = transitive_succs(dag.succs, n)
            if c.base_cycles is not None:
                gt = dict(enumerate(c.base_cycles))
            else:
                gt = {p.instr: p.cycle for p in GreedyListScheduler().schedule(dag, model)
                      .schedule.placements.values()}
            c.rule_common = (n, m.height, m.asap, chans, occs, reach, gt)
        return c.rule_common

    # -- основной вызов -------------------------------------------------------

    def schedule(self, dag: DAG, model: MachineModel) -> SchedulingResult:
        ctx = _Ctx(dag, model)
        self._tl.ctx = ctx
        try:
            return self._schedule(dag, model, ctx)
        finally:
            self._tl.ctx = None

    def _schedule(self, dag: DAG, model: MachineModel, ctx: _Ctx) -> SchedulingResult:
        metrics = ctx.metrics
        lb = metrics.lower_bound
        n = len(dag)
        plan = ListPlan(dag, model)
        prio_g = [float(h) for h in metrics.height]
        raw0 = plan.run(prio_g)                      # жадный baseline, без трассы
        ctx.base_cycles = raw0.cycle
        g_ms = raw0.makespan
        # лучшее на сейчас; recipe — как воспроизвести трассу победителя
        # (None = трасса жадного, как у TinyScheduler для жадного и вееров)
        best = {"raw": raw0, "ms": g_ms, "sched": None, "tag": "greedy", "recipe": None}
        ran: list[str] = []
        skipped: list[str] = []
        hit: list[str | None] = [None]     # где впервые достигнута граница
        cur = ["greedy"]                   # какая группа сейчас работает

        def at_bound() -> bool:
            return best["ms"] <= lb

        def consider(raw, tag: str, recipe) -> bool:
            """Принять расписание, если оно ЗАКОННО и строго короче. Порядок
            проверок другой, чем в TinyScheduler (там validate() идёт первым,
            на каждом варианте), но принимается ровно то же множество:
            «короче И полно И законно» не зависит от порядка проверок."""
            ms = raw.makespan
            if ms < best["ms"]:
                sched = plan.to_schedule(raw)
                if sched.complete and not sched.validate():
                    best.update(raw=raw, ms=ms, sched=sched, tag=tag, recipe=recipe)
                    if hit[0] is None and at_bound():
                        hit[0] = cur[0]
            return self.stop_at_bound and at_bound()

        if at_bound():
            hit[0] = "greedy"

        if n:
            mh = max(metrics.height)
            height_c = [float(h) / mh for h in metrics.height]
            have_net = self.tiny is not None

            def applicable(g: str) -> bool:
                return not (g in _NEEDS_PRIO and not have_net)

            for k, grp in enumerate(self.order):
                if self.stop_at_bound and at_bound():
                    skipped = [g for g in self.order[k:] if applicable(g)]
                    break
                if not applicable(grp):
                    continue  # как у родителя: группы на крошке-1 без весов не идут
                ran.append(grp)
                cur[0] = grp
                if grp == "bh":
                    for j, bp in enumerate(self._beam_orders(height_c, self.beam, 1000)):
                        if consider(plan.run(bp), f"beam_h{j}", None):
                            break
                    continue
                prio = self.priority(dag, model)
                if grp == "prio":
                    consider(plan.run(prio), "prio", (prio, None))
                elif grp == "defer":
                    d = self.defer_until(dag, model, g_ms)
                    if d:
                        consider(plan.run(prio, d), "prio_defer", (prio, d))
                elif grp == "hold":
                    h = self.hold_until(dag, model, g_ms)
                    if h:
                        if not consider(plan.run(prio, h), "prio_hold", (prio, h)):
                            for j, hd in enumerate(self._beam_holds(h, n, self.beam, 3000, g_ms)):
                                if consider(plan.run(prio, hd), f"beam_d{j}", None):
                                    break
                elif grp == "rule":
                    for tag, fn in (("rule_hold", self.rule_holds),
                                    ("rule_hold_far", self.rule_holds_far)):
                        holds = fn(dag, model, g_ms)
                        if not holds:
                            continue
                        if consider(plan.run(prio, holds), tag, (prio, holds)):
                            break
                elif grp == "bt":
                    for j, bp in enumerate(self._beam_orders(prio, self.beam, 2000)):
                        if consider(plan.run(bp), f"beam_t{j}", None):
                            break

        sched = best["sched"] if best["sched"] is not None else plan.to_schedule(best["raw"])
        trace: list = []
        if self.with_trace:
            if best["recipe"] is None:
                trace = list_schedule(dag, model, priority=prio_g, collect_trace=True,
                                      height=metrics.height)[1]
            else:
                pr, df = best["recipe"]
                trace = list_schedule(dag, model, priority=pr, defer_until=df,
                                      height=metrics.height, collect_trace=True)[1]
        proved = sched.makespan <= lb
        notes = [f"tiny-fast[{self.mode}]: greedy={g_ms} -> best={sched.makespan} "
                 f"({best['tag']}); граница={lb}"
                 + (" — оптимум доказан границей" if proved else ""),
                 "группы: " + (",".join(ran) if ran else "не запускались")
                 + (f"; пропущены по границе: {','.join(skipped)}" if skipped else "")]
        if self.tiny is None:
            notes.append("веса priority не загружены — группы на крошке-1 выключены; "
                         + (self.load_error or ""))
        if self.defer is None and "defer" in self.order:
            notes.append("веса defer не загружены — вариант prio_defer выключен; "
                         + (self.defer_error or ""))
        if self.hold is None and "hold" in self.order:
            notes.append("веса hold не загружены — вариант prio_hold выключен; "
                         + (self.hold_error or ""))
        return SchedulingResult(
            schedule=sched, trace=trace, optimal=True if proved else None, notes=notes,
            search_stats={"tiny": True, "tiny_fast": True, "tiny_winner": best["tag"],
                          "baseline_makespan": g_ms, "lower_bound": lb,
                          "proved_by_bound": proved, "bound_hit_at": hit[0],
                          "groups_run": ran, "groups_skipped": skipped,
                          "mode": self.mode, "order": list(self.order),
                          "weights": self.weights_path, "defer_weights": self.defer_path,
                          "hold_weights": self.hold_path, "beam": self.beam},
        )
