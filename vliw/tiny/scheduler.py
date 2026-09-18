"""Крошки как планировщик: контракт Scheduler, инференс stdlib.

Портфель (всегда, по построению — хуже baseline не бывает):
  greedy      — жадный baseline, идет ПЕРВЫМ: ничьи отдаем ему, а не модели
                (правило честности из CAB: не приписывать алгоритму чужое)
  prio        — крошка-1: порядок из скоров MLP
  prio_defer  — крошка-2: тот же порядок + такты как defer_until («не раньше»)
  prio_hold   — то же, но держки другой головы (цель hold: длительность
                держки после asap, а не абсолютный такт). Другое мнение —
                другой член портфеля: min по супермножеству не бывает хуже.
  beam_d*     — веер по держкам (джиттер holds): ранним contention-держкам
                вида «держи три такта», которые сеть даёт как одну.
  rule_hold   — ручное правило монопольного порта (без ML): не занимать
                узкий канал некритичной операцией, если скоро придёт более
                критичный конкурент за тот же канал. Дырки, которые prio
                выразить не может, а defer-сеть не выучила. Ближний вариант
                (окно от asap).
  rule_hold_far — то же, дальний вариант (окно от выдачи жадного): дальние
                разрывы до конкурента, хвост вместо первой держки.
  beam_h_*/beam_t_* — крошка-3 веер: детерминированный джиттер порядка
                вокруг двух центров (нормированный height и скоры крошки-1,
                K=16 каждый), точный выбор по makespan. Не модель, а поиск:
                проверить несколько вариантов и взять оптимум.

Выбор — минимум makespan среди законных. Без файлов весов — чистый
fallback на baseline, чтобы CLI/TUI не падали до обучения.
"""

from __future__ import annotations

import random
from pathlib import Path

from ..core.api import SchedulingResult
from ..core.baseline import GreedyListScheduler, list_schedule
from ..core.dag import DAG, compute_metrics
from ..core.model import MachineModel
from .features import featurize
from .model import TinyPriority

_DEFAULT_WEIGHTS = Path(__file__).resolve().parent / "weights.json"
_DEFAULT_DEFER = Path(__file__).resolve().parent / "weights_defer.json"
_DEFAULT_HOLD = Path(__file__).resolve().parent / "weights_hold.json"


class TinyScheduler:
    name = "Крошки (tiny priority+defer+beam, без LLM)"
    kind = "learned"
    short = "tiny"

    @staticmethod
    def _load_net(path: Path, kind: str) -> tuple[TinyPriority | None, str]:
        """Веса или честный fallback: битые, чужие (другое число фич),
        отсутствующие — всё это не валит планировщик, а гасит вариант."""
        from .features import N_FEATURES

        if not path.exists():
            return None, ""
        try:
            net = TinyPriority.load(str(path))
        except Exception as e:  # битые веса — не валим планировщик
            return None, str(e)
        if len(net.w1) != N_FEATURES:
            return None, (f"веса {kind} на {len(net.w1)} фич, нужно "
                           f"{N_FEATURES} — переобучи (vliw/tiny/train.py)")
        return net, ""

    def __init__(self, weights: str | None = None,
                 defer_weights: str | None = None,
                 hold_weights: str | None = None,
                 beam: int = 16) -> None:
        p = Path(weights) if weights else _DEFAULT_WEIGHTS
        self.weights_path = str(p)
        self.tiny, self.load_error = self._load_net(p, "priority")
        dp = Path(defer_weights) if defer_weights else _DEFAULT_DEFER
        self.defer_path = str(dp)
        self.defer, self.defer_error = self._load_net(dp, "defer")
        hp = Path(hold_weights) if hold_weights else _DEFAULT_HOLD
        self.hold_path = str(hp)
        self.hold, self.hold_error = self._load_net(hp, "hold")
        self.beam = beam

    def priority(self, dag: DAG, model: MachineModel) -> list[float]:
        metrics = compute_metrics(dag, model)
        if self.tiny is None:
            return [float(h) for h in metrics.height]
        return self.tiny.scores(featurize(dag, model))

    def _holds_of(self, net: TinyPriority | None, dag: DAG,
                  model: MachineModel, limit: int) -> dict[int, int]:
        """Запреты «не раньше» из головы сети. Трактовка выхода — по маркеру
        весов: "hold" значит длительность держки после раннего старта
        (asap + hold), отсутствие маркера — legacy "cycle" (абсолютный
        такт)."""
        if net is None:
            return {}
        preds = net.scores(featurize(dag, model))
        if getattr(net, "target", None) == "hold":
            asap = compute_metrics(dag, model).asap
            return {i: c for i, v in enumerate(preds)
                    for c in (asap[i] + int(round(v)),)
                    if 0 < c <= limit}
        return {i: c for i, v in enumerate(preds)
                for c in (int(round(v)),) if 0 < c <= limit}

    def defer_until(self, dag: DAG, model: MachineModel, limit: int) -> dict[int, int]:
        """Такты крошки-2 как запрет «не раньше». Клип по жадному makespan —
        тот же прием, что floor_from_model в CAB: такт выше потолка это сбой
        формата, а не мнение (иначе один выброс растянет расписание)."""
        return self._holds_of(self.defer, dag, model, limit)

    def hold_until(self, dag: DAG, model: MachineModel, limit: int) -> dict[int, int]:
        """То же другой головой (цель hold). Отдельный член портфеля."""
        return self._holds_of(self.hold, dag, model, limit)

    def _rule_common(self, dag: DAG, model: MachineModel):
        """Общее для ручных правил: метрики, каналы, достижимость, выдача жадного."""
        from .features import transitive_succs

        n = len(dag)
        metrics = compute_metrics(dag, model)
        chans = [frozenset(model.channels_for(ins.op)) for ins in dag]
        occs = [model.occupancy(ins.op) for ins in dag]
        reach = transitive_succs(dag.succs, n)
        gt = {p.instr: p.cycle
              for p in GreedyListScheduler().schedule(dag, model)
              .schedule.placements.values()}
        return n, metrics.height, metrics.asap, chans, occs, reach, gt

    @staticmethod
    def _contenders(i: int, chans, reach, n: int) -> list[int]:
        """Конкуренты за тот же монопольный канал, не связанные с X."""
        return [j for j in range(n)
                if j != i and chans[j] == chans[i]
                and i not in reach[j] and j not in reach[i]]

    def rule_holds(self, dag: DAG, model: MachineModel, limit: int) -> dict[int, int]:
        """Ручное правило монопольного порта, ближний вариант: держка без ML.

        Случай из разбора (граф 7 eval_hard): в t.0 готовы ADD и DIV 11,
        порт ,5 свободен — жадный забивает его некритичным DIV 11, а
        критичный DIV 1 приходит в t.1 и ждёт лишний такт (occupancy 2).
        Оракул оставляет дырку. Статический порядок дырку выразить не
        может, defer-сеть её не выучила, поэтому правило явное: X держим
        до asap[Y]+1 первого более критичного конкурента в окне occupancy.
        Малые точные держки; дальних разрывов не видит (для них —
        rule_holds_far ниже).
        """
        n, height, asap, chans, occs, reach, _gt = self._rule_common(dag, model)
        if n == 0:
            return {}
        out: dict[int, int] = {}
        for i in range(n):
            if len(chans[i]) != 1:
                continue
            for j in self._contenders(i, chans, reach, n):
                if not asap[i] < asap[j] <= asap[i] + occs[i]:
                    continue
                if not height[j] > height[i]:
                    continue
                c = asap[j] + 1
                if c < out.get(i, limit + 1):
                    out[i] = c
        return {i: c for i, c in out.items() if 0 < c <= limit}

    def rule_holds_far(self, dag: DAG, model: MachineModel, limit: int) -> dict[int, int]:
        """То же, дальний вариант (граф 23): разрыв до конкурента бывает не
        1–2 такта, а 11 — окно от asap слепо (у всех лёгких DIV нули).
        Окно считаем от времени выдачи жадным gt[X]: держим X, только если
        жадный ставит его за occ(X) тактов до прихода первого более
        критичного конкурента (12/15/21 уходят в ранние дырки — их не
        трогаем; 22 встанет за такт до тяжёлых — его держим). Значение —
        хвост конкурентов: max(asap[Y] + occ(Y)) + 1. Агрессивно само по
        себе, но живёт отдельным членом портфеля: min забирает лучшее
        с обеих сторон, пере-держки гасит слак или min-защита.
        """
        n, height, asap, chans, occs, reach, gt = self._rule_common(dag, model)
        if n == 0:
            return {}
        out: dict[int, int] = {}
        for i in range(n):
            if len(chans[i]) != 1 or i not in gt:
                continue
            first, tail = 0, 0
            for j in self._contenders(i, chans, reach, n):
                if not asap[j] > gt[i]:
                    continue
                if not height[j] > height[i]:
                    continue
                first = asap[j] if not first else min(first, asap[j])
                tail = max(tail, asap[j] + occs[j])
            if tail and 0 <= first - gt[i] <= occs[i]:
                out[i] = tail + 1
        return {i: c for i, c in out.items() if 0 < c <= limit}

    def _beam_holds(self, base: dict[int, int], n: int, k: int,
                    seed_base: int, limit: int) -> list[dict[int, int]]:
        """Джиттер держек: та же философия, что у веера порядка, но центр —
        предсказанные держки, а не скоры. Нужен ранним contention-держкам
        («держи DIV 11 три такта», сеть даёт одну): детерминированные
        варианты вокруг предсказания, точный выбор по makespan. Пустые
        (<=0 после округления) и выше потолка отбрасываем — как обычно."""
        if n == 0 or k <= 0 or not base:
            return []
        dense = [float(base.get(i, 0)) for i in range(n)]
        mean = sum(dense) / n
        var = sum((v - mean) ** 2 for v in dense) / n
        amp = (var ** 0.5) / 2.0 or 1.0
        out = []
        for j in range(k):
            rnd = random.Random(seed_base + j)
            d = {i: c for i, v in enumerate(dense)
                 for c in (int(round(v + amp * rnd.gauss(0.0, 1.0))),)
                 if 0 < c <= limit}
            out.append(d)
        return out

    def _beam_orders(self, base_prio: list[float], k: int,
                     seed_base: int) -> list[list[float]]:
        """Детерминированный веер: гауссов джиттер с фикс. сидами.
        Амплитуда = std(скоров)/2: порядок болтается, но не превращается в шум.
        ВАЖНО про масштаб: джиттер осмыслен только если скоры в сравнимом
        диапазоне — поэтому центры нормализуем (height/max, скоры MLP и так
        в ~[0,1]). Сырой height (1..60) джиттером убивается в мусор: проверено,
        height+beam без нормализации дает 0 побед (см. tiny/README)."""
        n = len(base_prio)
        if n == 0 or k <= 0:
            return []
        mean = sum(base_prio) / n
        var = sum((v - mean) ** 2 for v in base_prio) / n
        amp = (var ** 0.5) / 2.0 or 1.0
        out = []
        for j in range(k):
            rnd = random.Random(seed_base + j)
            out.append([v + amp * rnd.gauss(0.0, 1.0) for v in base_prio])
        return out

    def schedule(self, dag: DAG, model: MachineModel) -> SchedulingResult:
        metrics = compute_metrics(dag, model)
        base = GreedyListScheduler().schedule(dag, model)
        best = base.schedule
        best_trace = base.trace
        winner = "greedy"

        prio = self.priority(dag, model)
        mh = max(metrics.height) if len(dag) else 1
        height_c = [float(h) / mh for h in metrics.height]
        if self.tiny is not None:
            sched, trace = list_schedule(dag, model, priority=prio,
                                         height=metrics.height, collect_trace=True)
            if not sched.validate() and sched.complete \
                    and sched.makespan < best.makespan:
                best, best_trace, winner = sched, trace, "prio"

            defer = self.defer_until(dag, model, base.schedule.makespan)
            if defer:
                sched2, trace2 = list_schedule(
                    dag, model, priority=prio, defer_until=defer,
                    height=metrics.height, collect_trace=True)
                if not sched2.validate() and sched2.complete \
                        and sched2.makespan < best.makespan:
                    best, best_trace, winner = sched2, trace2, "prio_defer"

            hold = self.hold_until(dag, model, base.schedule.makespan)
            if hold:
                schedh, traceh = list_schedule(
                    dag, model, priority=prio, defer_until=hold,
                    height=metrics.height, collect_trace=True)
                if not schedh.validate() and schedh.complete \
                        and schedh.makespan < best.makespan:
                    best, best_trace, winner = schedh, traceh, "prio_hold"

                for j, hd in enumerate(self._beam_holds(
                        hold, len(dag), self.beam, 3000,
                        base.schedule.makespan)):
                    schedd, _ = list_schedule(
                        dag, model, priority=prio, defer_until=hd,
                        height=metrics.height)
                    if not schedd.validate() and schedd.complete \
                            and schedd.makespan < best.makespan:
                        best, best_trace, winner = \
                            schedd, base.trace, f"beam_d{j}"

            for tag, holds in (
                    ("rule_hold",
                     self.rule_holds(dag, model, base.schedule.makespan)),
                    ("rule_hold_far",
                     self.rule_holds_far(dag, model, base.schedule.makespan))):
                if not holds:
                    continue
                schedr, tracer = list_schedule(
                    dag, model, priority=prio, defer_until=holds,
                    height=metrics.height, collect_trace=True)
                if not schedr.validate() and schedr.complete \
                        and schedr.makespan < best.makespan:
                    best, best_trace, winner = schedr, tracer, tag

            for j, bp in enumerate(self._beam_orders(prio, self.beam, 2000)):
                schedj, _ = list_schedule(dag, model, priority=bp,
                                          height=metrics.height)
                if not schedj.validate() and schedj.complete \
                        and schedj.makespan < best.makespan:
                    best, best_trace, winner = schedj, base.trace, f"beam_t{j}"

        for j, bp in enumerate(self._beam_orders(height_c, self.beam, 1000)):
            schedj, _ = list_schedule(dag, model, priority=bp,
                                      height=metrics.height)
            if not schedj.validate() and schedj.complete \
                    and schedj.makespan < best.makespan:
                best, best_trace, winner = schedj, base.trace, f"beam_h{j}"

        notes = [f"tiny-портфель: greedy={base.schedule.makespan} "
                 f"-> best={best.makespan} ({winner})"]
        if self.tiny is None:
            notes.append("веса priority не загружены — работа как baseline; "
                         + (self.load_error or ""))
        if self.defer is None:
            notes.append("веса defer не загружены — вариант prio_defer выключен; "
                         + (self.defer_error or ""))
        if self.hold is None:
            notes.append("веса hold не загружены — вариант prio_hold выключен; "
                         + (self.hold_error or ""))
        return SchedulingResult(
            schedule=best, trace=best_trace, optimal=None, notes=notes,
            search_stats={"tiny": True, "tiny_winner": winner,
                          "baseline_makespan": base.schedule.makespan,
                          "weights": self.weights_path,
                          "defer_weights": self.defer_path,
                          "hold_weights": self.hold_path,
                          "beam": self.beam},
        )
