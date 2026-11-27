"""Tiny scheduler: Scheduler contract, pure-stdlib inference.

Portfolio (by construction, never worse than baseline):
  greedy      — greedy baseline, runs FIRST: ties go to greedy, not the model
                (CAB honesty rule: never credit the model for ties)
  prio        — Tiny-1: ordering from MLP priority scores
  prio_defer  — Tiny-2: same ordering + predicted cycles as defer_until
  prio_hold   — same, using the hold head (delay after ASAP rather than
                absolute cycle). Another opinion = another portfolio member:
                min over a superset can never be worse.
  beam_d*     — hold beam (jittered holds): helps early contention holds
                like "hold 3 cycles" when the net predicts 1.
  rule_hold   — hand-crafted exclusive-port rule (no ML): do not occupy a
                narrow channel with a non-critical op if a more critical
                competitor arrives soon. Expresses bubbles that prio cannot
                and defer did not learn. Near variant (ASAP window).
  rule_hold_far — far variant (greedy-issue window): longer gaps to a
                competitor, using the competitor tail instead of first hold.
  beam_h_*/beam_t_* — Tiny-3 beam: deterministic ordering jitter around two
                centers (normalized height and Tiny-1 scores, K=16 each),
                exact selection by makespan. Search, not a model: try
                several candidates and take the best.

Selection: minimum makespan among valid schedules. Without weight files,
falls back cleanly to baseline so CLI/TUI never crash before training.
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
    name = "Tiny (priority+defer+beam, no LLM)"
    kind = "learned"
    short = "tiny"

    @staticmethod
    def _load_net(path: Path, kind: str) -> tuple[TinyPriority | None, str]:
        """Load weights or fall back cleanly: corrupt, mismatched feature count,
        or missing files disable the variant instead of crashing."""
        from .features import N_FEATURES

        if not path.exists():
            return None, ""
        try:
            net = TinyPriority.load(str(path))
        except Exception as e:  # corrupt weights — do not crash scheduler
            return None, str(e)
        if len(net.w1) != N_FEATURES:
            return None, (f"{kind} weights have {len(net.w1)} features, expected "
                           f"{N_FEATURES} — retrain (vliw/tiny/train.py)")
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
        """Defer-until constraints from a network head. Output interpretation
        follows the weight marker: "hold" means delay after ASAP
        (asap + hold); missing marker means legacy "cycle" (absolute cycle)."""
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
        """Tiny-2 cycles as defer-until constraints. Clipped to greedy makespan —
        same safeguard as floor_from_model in CAB: a cycle above the ceiling
        is an outlier, not a valid hint (otherwise one outlier stretches the schedule)."""
        return self._holds_of(self.defer, dag, model, limit)

    def hold_until(self, dag: DAG, model: MachineModel, limit: int) -> dict[int, int]:
        """Same using the hold head. Separate portfolio member."""
        return self._holds_of(self.hold, dag, model, limit)

    def _rule_common(self, dag: DAG, model: MachineModel):
        """Shared context for hand-crafted rules: metrics, channels, reachability, greedy cycles."""
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
        """Competitors for the same exclusive channel that have no dependency on X."""
        return [j for j in range(n)
                if j != i and chans[j] == chans[i]
                and i not in reach[j] and j not in reach[i]]

    def rule_holds(self, dag: DAG, model: MachineModel, limit: int) -> dict[int, int]:
        """Hand-crafted exclusive-port rule, near variant: non-ML hold.

        Motivating case (eval_hard graph 7): at t.0 ADD and DIV 11 are ready,
        port ,5 is free — greedy fills it with non-critical DIV 11, while
        critical DIV 1 arrives at t.1 and stalls an extra cycle (occupancy 2).
        The oracle leaves a bubble. Static priority cannot express a bubble
        and the defer net missed it, so the rule is explicit: hold X until
        asap[Y]+1 of the first more-critical competitor within the occupancy
        window. Small exact holds; does not catch long gaps (see
        rule_holds_far below).
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
        """Far variant (graph 23): the gap to a competitor can be 11 cycles
        instead of 1-2, where the ASAP window is blind (all light DIVs have 0).
        Compute the window from greedy issue cycle gt[X]: hold X only if
        greedy places it within occ(X) cycles before the first more-critical
        competitor (12/15/21 fit in early slots — untouched; 22 would land 1
        cycle before heavy ops — held). Target is the competitor tail:
        max(asap[Y] + occ(Y)) + 1. Aggressive on its own, but safe as a
        separate portfolio member: min keeps the best of both worlds.
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
        """Hold jitter: same philosophy as ordering beam, centered on predicted
        holds instead of scores. Helps early contention holds (e.g. "hold
        DIV 11 for 3 cycles" when the net predicts 1): deterministic
        perturbations around the prediction, exact makespan selection.
        Empty (<=0 after rounding) and above-ceiling values are dropped."""
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
        """Deterministic beam: Gaussian jitter with fixed seeds.
        Amplitude = std(scores)/2: perturbs ordering without turning it to noise.
        Scale matters: jitter only makes sense when scores share a comparable
        range, so centers are normalized (height/max; MLP scores are already
        in ~[0,1]). Raw height (1..60) degrades under jitter: unnormalized
        height+beam yields 0 wins (see tiny/README)."""
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

        notes = [f"tiny portfolio: greedy={base.schedule.makespan} "
                 f"-> best={best.makespan} ({winner})"]
        if self.tiny is None:
            notes.append("priority weights not loaded — running as baseline; "
                         + (self.load_error or ""))
        if self.defer is None:
            notes.append("defer weights not loaded — prio_defer disabled; "
                         + (self.defer_error or ""))
        if self.hold is None:
            notes.append("hold weights not loaded — prio_hold disabled; "
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
