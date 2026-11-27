"""Exact oracle: iterative-deepening branch-and-bound + portfolio fallback.

Computes the proven-optimal makespan lower/upper ceiling for a DAG and
machine model. Uses deadline pruning, earliest-start propagation, dominance,
symmetry breaking, and memoization, falling back to a randomized priority
portfolio if the time budget expires.
"""

from __future__ import annotations

import itertools
import random
import time
from dataclasses import dataclass

from .api import Candidate, DecisionStep, SchedulingResult
from .baseline import GreedyListScheduler, list_schedule
from .dag import DAG, compute_metrics
from .model import MachineModel
from .schedule import Schedule


@dataclass(frozen=True)
class Hint:
    """External search hint (upper-bound schedule and/or priority vectors).

    Cannot affect optimality proofs — only speeds up convergence or narrows
    the proven interval within budget.
    """

    schedule: Schedule | None = None
    priority: tuple[float, ...] | None = None
    defer: dict[int, int] | None = None
    source: str = "hint"
    """Provenance label included in report notes."""


class _Timeout(Exception):
    pass


@dataclass
class _Ctx:
    dag: DAG
    model: MachineModel
    lat: list[int]
    occ: list[int]
    capable: list[tuple[int, ...]]
    height: tuple[int, ...]
    chan_class: tuple[int, ...]
    deadline_wall: float
    nodes: int = 0

    def tick(self) -> None:
        self.nodes += 1
        if self.nodes % 512 == 0 and time.monotonic() > self.deadline_wall:
            raise _Timeout


def _channel_classes(model: MachineModel) -> tuple[int, ...]:
    """Group channels with identical capability sets into equivalence classes."""
    sig: dict[tuple[bool, ...], int] = {}
    out = []
    for ch in range(model.width):
        key = tuple(ch in model.channels_for(op) for op in sorted(model.ops))
        out.append(sig.setdefault(key, len(sig)))
    return tuple(out)


# --------------------------------------------------------------------------
# Assign selected ops to channels via Kuhn bipartite matching
# --------------------------------------------------------------------------


class _Matcher:
    """Incremental op -> channel bipartite matching."""

    def __init__(self, free: set[int]):
        self.free = free
        self.owner: dict[int, int] = {}  # channel -> op
        self.allowed: dict[int, tuple[int, ...]] = {}

    def copy(self) -> "_Matcher":
        m = _Matcher(self.free)
        m.owner = dict(self.owner)
        m.allowed = dict(self.allowed)
        return m

    def add(self, op: int, allowed: tuple[int, ...]) -> bool:
        self.allowed[op] = allowed
        if self._augment(op, set()):
            return True
        del self.allowed[op]
        return False

    def _augment(self, op: int, seen: set[int]) -> bool:
        for ch in self.allowed[op]:
            if ch not in self.free or ch in seen:
                continue
            seen.add(ch)
            holder = self.owner.get(ch)
            if holder is None or self._augment(holder, seen):
                self.owner[ch] = op
                return True
        return False

    def assignment(self) -> dict[int, int]:
        return {op: ch for ch, op in self.owner.items()}


# --------------------------------------------------------------------------
# Exact branch-and-bound search
# --------------------------------------------------------------------------


def _earliest_starts(
    ctx: _Ctx,
    unscheduled: frozenset[int],
    ready_time: tuple[int, ...],
    free_at: tuple[int, ...],
    t: int,
) -> list[int] | None:
    """Earliest feasible start cycle for each unscheduled instruction."""
    est = [0] * len(ctx.dag)
    for i in sorted(unscheduled):
        e = max(t, ready_time[i])
        for p in ctx.dag[i].preds:
            if p in unscheduled:
                e = max(e, est[p] + ctx.lat[p])
        chans = ctx.capable[i]
        if not chans:
            return None
        e = max(e, min(free_at[c] for c in chans))
        est[i] = e
    return est


def _group_interchangeable(
    ctx: _Ctx, ids: list[int], ready_time: tuple[int, ...]
) -> list[list[int]]:
    """Group instructions that are interchangeable in the current cycle."""
    buckets: dict[tuple, list[int]] = {}
    for i in ids:
        key = (
            ctx.dag[i].op,
            ctx.capable[i],
            ctx.height[i],
            ready_time[i],
            ctx.dag.succs[i],
        )
        buckets.setdefault(key, []).append(i)
    return [sorted(v) for v in buckets.values()]


def _count_vectors(sizes: list[int], total: int):
    """Enumerate distributions of `total` items across bounded groups."""
    def rec(k: int, left: int, acc: list[int]):
        if k == len(sizes):
            if left == 0:
                yield tuple(acc)
            return
        rest = sum(sizes[k + 1 :])
        lo = max(0, left - rest)
        for c in range(min(sizes[k], left), lo - 1, -1):
            acc.append(c)
            yield from rec(k + 1, left - c, acc)
            acc.pop()

    yield from rec(0, total, [])


def _candidate_subsets(
    ctx: _Ctx,
    ready: list[int],
    free: set[int],
    ready_time: tuple[int, ...],
) -> list[tuple[int, ...]]:
    """Enumerate dominant subsets of ready instructions to issue in this cycle."""
    blocking = [i for i in ready if ctx.occ[i] > 1]
    nonblk = [i for i in ready if ctx.occ[i] == 1]
    groups = _group_interchangeable(ctx, nonblk, ready_time)
    sizes = [len(g) for g in groups]

    out: list[tuple[int, ...]] = []
    seen: set[tuple[int, ...]] = set()

    for r in range(len(blocking), -1, -1):
        for bs in itertools.combinations(blocking, r):
            ctx.tick()
            base = _Matcher(free)
            if not all(base.add(i, ctx.capable[i]) for i in bs):
                continue
            probe = base.copy()
            extra = sum(1 for i in nonblk if probe.add(i, ctx.capable[i]))
            for counts in _count_vectors(sizes, extra):
                # Check time budget inside vector enumeration so large real DAGs
                # respect the deadline and fall back cleanly to the portfolio.
                #
                #
                #
                ctx.tick()
                sub = list(bs)
                for g, c in zip(groups, counts):
                    sub.extend(g[:c])
                m = base.copy()
                if all(m.add(i, ctx.capable[i]) for i in sub[len(bs) :]):
                    key = tuple(sorted(sub))
                    if key not in seen:
                        seen.add(key)
                        out.append(key)

    out.sort(key=lambda s: -sum(ctx.height[i] for i in s))
    return out


def _search(
    ctx: _Ctx,
    target: int,
    t: int,
    unscheduled: frozenset[int],
    ready_time: tuple[int, ...],
    free_at: tuple[int, ...],
    placed: list[tuple[int, int, int]],
    failed: set,
) -> list[tuple[int, int, int]] | None:
    if not unscheduled:
        return list(placed)

    ctx.tick()

    est = _earliest_starts(ctx, unscheduled, ready_time, free_at, t)
    if est is None:
        return None
    for i in unscheduled:
        if est[i] + ctx.height[i] > target:
            return None

    by_class: dict[int, list[int]] = {}
    for ch, cls in enumerate(ctx.chan_class):
        by_class.setdefault(cls, []).append(max(0, free_at[ch] - t))
    key = (
        unscheduled,
        tuple(sorted((cls, tuple(sorted(v))) for cls, v in by_class.items())),
        tuple(max(0, ready_time[i] - t) for i in sorted(unscheduled)),
    )
    if key in failed:
        return None

    free = {c for c in range(ctx.model.width) if free_at[c] <= t}
    ready = [
        i
        for i in unscheduled
        if ready_time[i] <= t and all(p not in unscheduled for p in ctx.dag[i].preds)
    ]

    for sub in _candidate_subsets(ctx, ready, free, ready_time):
        m = _Matcher(free)
        for i in sub:
            m.add(i, ctx.capable[i])
        assign = m.assignment()
        new_free = list(free_at)
        new_ready = list(ready_time)
        for i in sub:
            ch = assign[i]
            new_free[ch] = t + ctx.occ[i]
            avail = t + ctx.lat[i]
            for s in ctx.dag.succs[i]:
                new_ready[s] = max(new_ready[s], avail)
        for i in sub:
            placed.append((i, t, assign[i]))

        res = _search(
            ctx,
            target,
            t + 1,
            unscheduled - frozenset(sub),
            tuple(new_ready),
            tuple(new_free),
            placed,
            failed,
        )
        if sub:
            del placed[len(placed) - len(sub) :]
        if res is not None:
            return res

    failed.add(key)
    return None


# --------------------------------------------------------------------------
# Portfolio search (fallback engine)
# --------------------------------------------------------------------------


def _portfolio(
    dag: DAG,
    model: MachineModel,
    height: tuple[int, ...],
    best: Schedule,
    budget_s: float,
    seed: int = 20260811,
    hint: "Hint | None" = None,
) -> tuple[Schedule, int, bool]:
    """Priority-vector portfolio search; returns `(best_sched, tries, hint_won)`."""
    rnd = random.Random(seed)
    blocking = [i.id for i in dag if model.occupancy(i.op) > 1]
    deadline = time.monotonic() + budget_s
    tries = 0
    hmax = max(height) if height else 1
    hint_won = False
    if hint is not None and hint.priority is not None:
        tries += 1
        cand, _ = list_schedule(dag, model, list(hint.priority),
                                defer_until=dict(hint.defer or {}), height=height)
        if cand.makespan < best.makespan and not cand.validate():
            best, hint_won = cand, True
    while time.monotonic() < deadline and tries < 20000:
        tries += 1
        jitter = rnd.choice((0.0, 0.15, 0.4, 1.0)) * hmax
        prio = [h + rnd.uniform(-jitter, jitter) for h in height]
        defer = {
            i: rnd.randint(1, 5) for i in blocking if rnd.random() < 0.25
        }
        cand, _ = list_schedule(
            dag, model, prio, defer_until=defer, height=height
        )
        if cand.makespan < best.makespan and not cand.validate():
            best, hint_won = cand, False
    return best, tries, hint_won


# --------------------------------------------------------------------------


class OracleScheduler:
    name = "Oracle (exact search: theoretical optimum)"
    kind = "exact"
    short = "oracle"

    def __init__(self, budget_s: float = 20.0, portfolio_s: float = 5.0,
                 hint: Hint | None = None):
        self.budget_s = budget_s
        self.portfolio_s = portfolio_s
        self.hint = hint
        """Optional external `Hint` (never affects optimality guarantees)."""

    def schedule(self, dag: DAG, model: MachineModel) -> SchedulingResult:
        metrics = compute_metrics(dag, model)
        base = GreedyListScheduler().schedule(dag, model)
        best = base.schedule
        ub = best.makespan
        lb = metrics.lower_bound

        # Accept hint schedule as upper bound ONLY if valid, complete,
        # and strictly shorter than baseline.
        #
        #
        hint = self.hint
        hint_ub = False
        if (hint is not None and hint.schedule is not None
                and hint.schedule.complete and not hint.schedule.validate()
                and hint.schedule.makespan < ub):
            best = hint.schedule
            ub = best.makespan
            hint_ub = True

        ctx = _Ctx(
            dag=dag,
            model=model,
            lat=[model.latency(i.op) for i in dag],
            occ=[model.occupancy(i.op) for i in dag],
            capable=[model.channels_for(i.op) for i in dag],
            height=metrics.height,
            chan_class=_channel_classes(model),
            deadline_wall=time.monotonic() + self.budget_s,
        )

        notes = [
            f"Lower bound: {lb} cycles (critical path "
            f"{metrics.critical_path_bound}, resources {metrics.resource_bound}) — "
            f"bound by {metrics.binding}.",
            (f"Initial upper bound ({hint.source}): {ub} cycles "
             f"(baseline: {base.schedule.makespan})." if hint_ub else
             f"Initial upper bound (baseline): {ub} cycles."),
        ]
        proven: bool | None = None
        timed_out = False
        hint_won = False
        engine = "exact"
        t0 = time.monotonic()
        proved_impossible = lb  # everything strictly below this is proven infeasible

        if lb >= ub:
            proven = True
            notes.append(
                (f"Schedule from '{hint.source}' already hits the lower bound: "
                 "optimality proven with zero search nodes." if hint_ub else
                 "Baseline already hits the lower bound: cannot be improved, "
                 "optimality proven without search.")
            )
        else:
            for target in range(lb, ub):
                try:
                    res = _search(
                        ctx,
                        target,
                        0,
                        frozenset(range(len(dag))),
                        tuple([0] * len(dag)),
                        tuple([0] * model.width),
                        [],
                        set(),
                    )
                except _Timeout:
                    timed_out = True
                    break
                if res is not None:
                    s = Schedule(dag, model)
                    for i, c, ch in res:
                        s.place(i, c, ch)
                    errs = s.validate()
                    if errs:
                        raise AssertionError(
                            "exact search produced an invalid schedule: " + "; ".join(errs)
                        )
                    best = s
                    proven = True
                    if target == lb:
                        notes.append(
                            f"Schedule of length {target} cycles found right at "
                            f"the lower bound — optimal by construction."
                        )
                    elif target == lb + 1:
                        notes.append(
                            f"Found {target}-cycle schedule; target {lb} "
                            f"proven infeasible by search."
                        )
                    else:
                        notes.append(
                            f"Found {target}-cycle schedule; all targets "
                            f"from {lb} to {target - 1} proven infeasible."
                        )
                    break
                proved_impossible = target + 1
            else:
                proven = True
                notes.append(
                    f"All targets from {lb} to {ub - 1} proven infeasible — "
                    f"baseline schedule ({ub}) is already optimal."
                )

        portfolio_tries = 0
        if timed_out:
            engine = "portfolio"
            proven = False
            notes.append(
                f"Exact search exceeded {self.budget_s:g} s budget "
                f"({ctx.nodes} nodes explored). Switching to portfolio "
                f"priority search."
            )
            best, portfolio_tries, hint_won = _portfolio(
                dag, model, metrics.height, best, self.portfolio_s, hint=hint
            )
            if hint_won:
                notes.append(
                    f"Best portfolio result came from '{hint.source}' priorities "
                    "rather than random search.")
            notes.append(
                f"Portfolio: {portfolio_tries} greedy runs with varied "
                f"priorities. Best found: {best.makespan} cycles; "
                f"optimum proven in [{proved_impossible}, {best.makespan}]."
            )

        elapsed = time.monotonic() - t0
        return SchedulingResult(
            schedule=best,
            trace=_replay_trace(best, dag, model, metrics.height),
            notes=notes,
            optimal=proven,
            search_stats={
                "engine": engine,
                "nodes": ctx.nodes,
                "portfolio_tries": portfolio_tries,
                "seconds": round(elapsed, 3),
                "lower_bound": lb,
                "proved_impossible_below": proved_impossible,
                "baseline_upper_bound": base.schedule.makespan,
                "hint_source": hint.source if hint is not None else None,
                "hint_gave_upper_bound": hint_ub,
                "hint_won_portfolio": hint_won,
                "result": best.makespan,
                "timed_out": timed_out,
            },
        )


def _replay_trace(
    sched: Schedule, dag: DAG, model: MachineModel, height: tuple[int, ...]
) -> list[DecisionStep]:
    """Reconstruct a cycle-by-cycle DecisionStep trace from a completed schedule."""
    n = len(dag)
    if not sched.complete:
        return []
    last = max(p.cycle for p in sched.placements.values())
    by_cycle: dict[int, list[int]] = {}
    for p in sched.placements.values():
        by_cycle.setdefault(p.cycle, []).append(p.instr)

    ready_time = [0] * n
    for ins in dag:
        for p in ins.preds:
            ready_time[ins.id] = max(ready_time[ins.id], sched.ready_at(p))

    trace: list[DecisionStep] = []
    for t in range(last + 1):
        issued = sorted(by_cycle.get(t, []), key=lambda i: sched.placements[i].channel)
        held = [
            p
            for p in sched.placements.values()
            if p.cycle < t < p.cycle + model.occupancy(dag[p.instr].op)
        ]
        busy = {p.channel for p in held}
        used = busy | {sched.placements[i].channel for i in issued}
        step = DecisionStep(
            cycle=t,
            free_channels=tuple(c for c in range(model.width) if c not in busy),
            blocked=[
                (p.instr, p.cycle + model.occupancy(dag[p.instr].op)) for p in held
            ],
            rule="decision made with full lookahead across the remaining DAG "
            "(global schedule optimization, not greedy per-cycle)",
        )
        for i in range(n):
            if sched.cycle_of(i) < t or ready_time[i] > t:
                continue
            cand = Candidate(instr=i, ready_at=ready_time[i], height=height[i])
            if i in issued:
                cand.chosen = True
                cand.channel = sched.placements[i].channel
                cand.reason = f"scheduled in this cycle (h={height[i]})"
                occ = model.occupancy(dag[i].op)
                if occ > 1:
                    cand.reason += f"; holds channel exclusively until cycle {t + occ}"
            elif not (set(model.channels_for(dag[i].op)) - used):
                cand.reason = "all capable channels occupied in this cycle"
            else:
                cand.reason = (
                    f"channel free, but deferred until cycle "
                    f"{sched.cycle_of(i)} — deliberate lookahead choice"
                )
            step.candidates.append(cand)

        # Key insight: where exact search intentionally overrode greedy height.
        chosen_h = [height[i] for i in issued]
        deferred = [c for c in step.candidates if not c.chosen]
        outranked = [c for c in deferred if chosen_h and c.height > max(chosen_h)]
        if outranked:
            names = ", ".join(dag[c.instr].name for c in outranked)
            step.comment = (
                f"issued ops with h={max(chosen_h)}, holding {names} "
                f"with h={max(c.height for c in outranked)}: greedy critical-path "
                f"would have done the opposite"
            )
        if not step.issued:
            step.rule = "pause"
            step.comment = (
                "cycle left empty — all required channels busy with "
                "previously issued operations"
            )
        trace.append(step)
    return trace
