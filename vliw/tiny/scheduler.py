"""Крошки как планировщик: контракт Scheduler, инференс stdlib.

Портфель (всегда, по построению — хуже baseline не бывает):
  greedy      — жадный baseline, идет ПЕРВЫМ: ничьи отдаем ему, а не модели
                (правило честности из CAB: не приписывать алгоритму чужое)
  prio        — крошка-1: порядок из скоров MLP
  prio_defer  — крошка-2: тот же порядок + такты как defer_until («не раньше»)
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


class TinyScheduler:
    name = "Крошки (tiny priority+defer+beam, без LLM)"
    kind = "learned"
    short = "tiny"

    def __init__(self, weights: str | None = None,
                 defer_weights: str | None = None,
                 beam: int = 8) -> None:
        from .features import N_FEATURES

        p = Path(weights) if weights else _DEFAULT_WEIGHTS
        self.weights_path = str(p)
        self.tiny: TinyPriority | None = None
        self.load_error: str = ""
        if p.exists():
            try:
                self.tiny = TinyPriority.load(str(p))
                # Веса от другого набора фич (старые, до давления на порт)
                # дали бы IndexError в прямом проходе — честный fallback
                # на baseline вместо падения, как с битыми весами.
                if len(self.tiny.w1) != N_FEATURES:
                    self.load_error = (
                        f"веса на {len(self.tiny.w1)} фич, нужно "
                        f"{N_FEATURES} — переобучи (vliw/tiny/train.py)")
                    self.tiny = None
            except Exception as e:  # битые веса — не валим планировщик
                self.load_error = str(e)
                self.tiny = None
        dp = Path(defer_weights) if defer_weights else _DEFAULT_DEFER
        self.defer_path = str(dp)
        self.defer: TinyPriority | None = None
        self.defer_error: str = ""
        if dp.exists():
            try:
                self.defer = TinyPriority.load(str(dp))
                if len(self.defer.w1) != N_FEATURES:
                    self.defer_error = (
                        f"веса на {len(self.defer.w1)} фич, нужно "
                        f"{N_FEATURES} — переобучи (vliw/tiny/train.py)")
                    self.defer = None
            except Exception as e:  # noqa: BLE001
                self.defer_error = str(e)
                self.defer = None
        self.beam = beam

    def priority(self, dag: DAG, model: MachineModel) -> list[float]:
        metrics = compute_metrics(dag, model)
        if self.tiny is None:
            return [float(h) for h in metrics.height]
        return self.tiny.scores(featurize(dag, model))

    def defer_until(self, dag: DAG, model: MachineModel, limit: int) -> dict[int, int]:
        """Такты крошки-2 как запрет «не раньше». Клип по жадному makespan —
        тот же прием, что floor_from_model в CAB: такт выше потолка это сбой
        формата, а не мнение (иначе один выброс растянет расписание)."""
        if self.defer is None:
            return {}
        preds = self.defer.scores(featurize(dag, model))
        return {i: c for i, v in enumerate(preds)
                for c in (int(round(v)),) if 0 < c <= limit}

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
        return SchedulingResult(
            schedule=best, trace=best_trace, optimal=None, notes=notes,
            search_stats={"tiny": True, "tiny_winner": winner,
                          "baseline_makespan": base.schedule.makespan,
                          "weights": self.weights_path,
                          "defer_weights": self.defer_path,
                          "beam": self.beam},
        )
