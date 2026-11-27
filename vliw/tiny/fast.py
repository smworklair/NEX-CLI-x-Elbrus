"""Fast Tiny scheduler: same quality, less time. New file; legacy code untouched.

What is here and why (measurements in docs/archive/TINY_FAST.md):

  1. LOWER BOUND. Every graph has a makespan lower bound (`DagMetrics.lower_bound`):
     no schedule can be shorter. If greedy already hits the lower bound, optimality
     is proven and there is nothing to search. If any portfolio member hits the lower
     bound, no remaining member can improve on it — we stop immediately. Zero quality
     loss by construction: final makespan matches full `TinyScheduler`.
     Across 3800 graphs, the lower bound never exceeded the found optimum.

  2. ORDERING. Portfolio groups run not in historical order, but cheapest-and-most-
     effective first: bh, rule, bt, prio, hold, defer. Ordering does not affect final
     makespan on a full pass, only how early we hit the lower bound.

  3. FAST INFERENCE. `FastNet` computes the exact same numbers as `TinyPriority.scores`,
     in the exact same addition order (verified with ==, not "almost"), row-wise over
     weights; with numpy, several times faster. Graph metrics and features are computed
     once per DAG instead of once per network.

  4. "asm" MODE. Drops hold and defer groups. Across 1514 real graphs from .s files,
     those two groups added nothing after the rest; on eval_hard, 6 of 300. This is
     an empirical measurement, not a guarantee — the caller chooses the mode.

Guarantees of `TinyFlashScheduler(mode="exact")`:
  * makespan equals `TinyScheduler` makespan on any graph (given a valid lower bound),
    and is never worse than greedy (greedy runs first, as before);
  * every accepted schedule passed `validate()` and `complete`;
  * `optimal=True` is set only when makespan == lower bound (proven optimal).
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

try:  # numpy only speeds this up; without it pure Python gives the exact same result
    if os.environ.get("VLIW_NO_NUMPY"):
        raise ImportError
    import numpy as _np
except Exception:  # noqa: BLE001
    _np = None

#: Group order: cheap and effective first (see docs/archive/TINY_FAST.md).
DEFAULT_ORDER: tuple[str, ...] = ("bh", "rule", "bt", "prio", "hold", "defer")
#: "asm" mode: skips expensive groups that added no wins on real assembly.
ASM_ORDER: tuple[str, ...] = ("bh", "rule", "bt", "prio")
_NEEDS_PRIO = frozenset({"prio", "defer", "hold", "rule", "bt"})


# --------------------------------------------------------------------------
# Fast forward pass
# --------------------------------------------------------------------------


class FastNet:
    """Same numbers as `TinyPriority.scores`, in the exact same addition order.

    The original computes s = b; s += x0*w0; s += x1*w1; ... per output
    (skipping zero inputs). Here we accumulate across all layer outputs at once
    via a list comprehension: each output sees the exact same addition sequence,
    so results match bit-for-bit.

    Also memoizes by feature row: identical inputs yield identical outputs, so
    duplicate rows (on real code, only 32% of rows are unique within a block and
    12% across all blocks) are evaluated once. Memory is bounded (`memo_limit`
    rows; cleared on overflow); zero disables cross-call memoization while
    in-call duplicates are still evaluated once.
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
    """Same, using numpy per layer: additions over k run sequentially (as in the
    original) with separate multiply and add ops, no FMA and no pairwise
    summation, preserving bit-exact parity."""

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
    """Fast copy of the network (or None). Uses numpy if available and enabled."""
    if net is None:
        return None
    if use_numpy is None:
        use_numpy = _np is not None
    if use_numpy and _np is not None:
        return FastNetNp(net, memo_limit)
    return FastNet(net, memo_limit)


# --------------------------------------------------------------------------
# Scheduler
# --------------------------------------------------------------------------


class _Ctx:
    """Everything computed once per DAG."""

    __slots__ = ("dag", "model", "metrics", "X", "prio", "rule_common", "base_cycles")

    def __init__(self, dag: DAG, model: MachineModel) -> None:
        self.dag = dag
        self.model = model
        self.metrics = compute_metrics(dag, model)
        self.X = None
        self.prio = None
        self.rule_common = None
        self.base_cycles = None  # greedy issue cycle for each instruction


class TinyFlashScheduler(TinyScheduler):
    name = "Fast Tiny (lower bound + group order, lossless)"
    kind = "learned"
    short = "tiny-flash"

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
            raise ValueError(f"mode must be 'exact' or 'asm', got {mode!r}")
        self.mode = mode
        self.order = tuple(order) if order else (ASM_ORDER if mode == "asm" else DEFAULT_ORDER)
        unknown = set(self.order) - {"bh", "rule", "bt", "prio", "hold", "defer"}
        if unknown:
            raise ValueError(f"unknown groups: {sorted(unknown)}")
        self.stop_at_bound = stop_at_bound
        # Decision trace is needed for inspection/explanations, not during compilation.
        # True matches TinyScheduler (one extra traced run for the winner only);
        # False leaves trace empty for speed.
        self.with_trace = with_trace
        # fast copies: same weights, bit-exact outputs
        self.tiny = make_fast(self.tiny, use_numpy, memo_limit)
        self.defer = make_fast(self.defer, use_numpy, memo_limit)
        self.hold = make_fast(self.hold, use_numpy, memo_limit)
        self._tl = threading.local()

    # -- single-call cache for schedule(); outside it behaves like parent ----

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

    # -- main entry point -----------------------------------------------------

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
        raw0 = plan.run(prio_g)                      # greedy baseline, untraced
        ctx.base_cycles = raw0.cycle
        g_ms = raw0.makespan
        # best so far; recipe describes how to replay the winner trace
        # (None = greedy trace, matching TinyScheduler for greedy and beams)
        best = {"raw": raw0, "ms": g_ms, "sched": None, "tag": "greedy", "recipe": None}
        ran: list[str] = []
        skipped: list[str] = []
        hit: list[str | None] = [None]     # where the lower bound was first hit
        cur = ["greedy"]                   # currently active group

        def at_bound() -> bool:
            return best["ms"] <= lb

        def consider(raw, tag: str, recipe) -> bool:
            """Accept a schedule if it is VALID and strictly shorter. Check order
            differs from TinyScheduler (which calls validate() first on every
            candidate), but the accepted set is identical:
            (shorter AND complete AND valid) is independent of check order."""
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
                    continue  # same as parent: Tiny-1 groups do not run without weights
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
        notes = [f"tiny-flash[{self.mode}]: greedy={g_ms} -> best={sched.makespan} "
                 f"({best['tag']}); lower_bound={lb}"
                 + (" — optimal proven by lower bound" if proved else ""),
                 "groups: " + (",".join(ran) if ran else "none run")
                 + (f"; skipped at lower bound: {','.join(skipped)}" if skipped else "")]
        if self.tiny is None:
            notes.append("priority weights not loaded — Tiny-1 groups disabled; "
                         + (self.load_error or ""))
        if self.defer is None and "defer" in self.order:
            notes.append("defer weights not loaded — prio_defer disabled; "
                         + (self.defer_error or ""))
        if self.hold is None and "hold" in self.order:
            notes.append("hold weights not loaded — prio_hold disabled; "
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


# Previous name kept for backwards compatibility with external imports and scripts.
TinyFastScheduler = TinyFlashScheduler
