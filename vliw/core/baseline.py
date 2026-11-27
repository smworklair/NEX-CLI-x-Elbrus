"""Baseline: greedy list scheduler ordered by remaining critical-path height.

Work-conserving and channel-cost aware (assigns flexible ops to least-capable
channels first). Exposed `list_schedule()` is reused by the oracle and learned
portfolios with custom priority vectors and `defer_until` constraints.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from .api import Candidate, DecisionStep, SchedulingResult
from .dag import DAG, compute_metrics
from .model import MachineModel
from .schedule import ChannelState, Schedule


def channel_costs(model: MachineModel) -> list[int]:
    """Channel scarcity = number of op classes supported (cheaper channels assigned first)."""
    return [
        sum(1 for op in model.ops if ch in model.channels_for(op))
        for ch in range(model.width)
    ]


def list_schedule(
    dag: DAG,
    model: MachineModel,
    priority: Sequence[float],
    *,
    defer_until: Mapping[int, int] | None = None,
    collect_trace: bool = False,
    height: Sequence[int] | None = None,
) -> tuple[Schedule, list[DecisionStep]]:
    """Single cycle-by-cycle greedy list-scheduling pass.

    Higher `priority` is considered first; `defer_until` forbids issuing
    before the given cycle.
    """
    n = len(dag)
    if height is None:
        height = compute_metrics(dag, model).height
    costs = channel_costs(model)
    defer = defer_until or {}

    sched = Schedule(dag, model)
    chans = ChannelState(model.width)
    ready_time = [0] * n
    unscheduled = set(range(n))
    trace: list[DecisionStep] = []

    cycle = 0
    guard = 0
    while unscheduled:
        guard += 1
        if guard > 100000:
            raise RuntimeError("scheduler stuck in loop")

        ready = sorted(
            (
                i
                for i in unscheduled
                if all(p not in unscheduled for p in dag[i].preds)
                and ready_time[i] <= cycle
            ),
            key=lambda i: (-priority[i], i),
        )

        step: DecisionStep | None = None
        if collect_trace:
            step = DecisionStep(
                cycle=cycle,
                free_channels=tuple(
                    c for c in range(model.width) if chans.free_at[c] <= cycle
                ),
                blocked=[
                    (p.instr, chans.free_at[p.channel])
                    for p in sched.placements.values()
                    if model.occupancy(dag[p.instr].op) > 1
                    and chans.free_at[p.channel] > cycle
                ],
                rule="priority = descending remaining critical path (height); "
                "tie-breaker = lower instruction ID",
            )

        issued_any = False
        for i in ready:
            op = dag[i].op
            capable = model.channels_for(op)
            free = chans.free_channels(cycle, capable)
            cand = Candidate(instr=i, ready_at=ready_time[i], height=int(height[i]))

            if defer.get(i, 0) > cycle:
                cand.reason = f"deferred by search until cycle {defer[i]}"
                if step:
                    step.candidates.append(cand)
                continue
            if not free:
                if not chans.free_channels(cycle, tuple(range(model.width))):
                    cand.reason = "all channels occupied in this cycle"
                else:
                    cand.reason = (
                        f"free channels do not execute {op} "
                        f"(requires one of {','.join(map(str, capable))})"
                    )
                if step:
                    step.candidates.append(cand)
                continue

            ch = min(free, key=lambda c: (costs[c], c))
            occ = model.occupancy(op)
            sched.place(i, cycle, ch)
            chans.occupy(ch, cycle, occ)
            unscheduled.discard(i)
            issued_any = True
            avail = cycle + model.latency(op)
            for s in dag.succs[i]:
                ready_time[s] = max(ready_time[s], avail)

            cand.chosen = True
            cand.channel = ch
            cand.reason = (
                f"highest priority among ready ops (h={int(height[i])}), "
                f"channel {ch} free"
            )
            if occ > 1:
                cand.reason += f"; holds channel exclusively until cycle {cycle + occ}"
            if step:
                step.candidates.append(cand)

        if step is not None:
            if not issued_any:
                step.rule = "stall"
                step.comment = (
                    "nothing to issue: operands not ready or all capable "
                    "channels busy"
                )
            trace.append(step)
        cycle += 1

    return sched, trace


class GreedyListScheduler:
    name = "Baseline: greedy list scheduler (critical path)"
    kind = "heuristic"
    short = "baseline"

    def schedule(self, dag: DAG, model: MachineModel) -> SchedulingResult:
        metrics = compute_metrics(dag, model)
        sched, trace = list_schedule(
            dag,
            model,
            priority=[float(h) for h in metrics.height],
            collect_trace=True,
            height=metrics.height,
        )
        return SchedulingResult(
            schedule=sched,
            trace=trace,
            optimal=None,
            notes=[
                "Decisions consider only the current cycle with no lookahead."
                "",
                "Height priority has no visibility into upcoming channel demand "
                "in future cycles.",
            ],
        )
