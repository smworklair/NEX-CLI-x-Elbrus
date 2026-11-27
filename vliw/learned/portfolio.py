"""CAB: one model response -> multiple valid schedules, selected by exact metric.

WHY
---
Previously the model had to act as bookkeeper: remember the channel matrix,
track occupied ports per cycle, and compute operand readiness. It is poor at
that (`docs/archive/DIAG3.md`: 315 invalid channels, 208 conflicts, 26 unready
operands), yet great at ordering: 97 of 98 valid run-1 answers hit the exact
CP-SAT optimum.

So we split the labor: take bookkeeping away from the model and keep only what
it does well — ORDERING (who to consider first). `list_schedule` from
`core/baseline.py` handles bookkeeping and by construction never issues an op
before its predecessors or puts two ops on one channel. Every schedule from it
is valid by mechanism, not luck.

WHAT WE TAKE FROM THE MODEL

* `order_from_model` — ordering. Ops are sorted by its `(cycle, channel)`;
  channel choice is DISCARDED entirely. That is the point: channel is its
  most frequent error, while ordering is its most valuable signal.
* `floor_from_model` — cycles as "no earlier than" (`defer_until`). The
  scheduler may push an op later, never earlier. Successor to `repair.py`
  without its dead end: always yields a valid schedule.

WHAT IS NOT HERE
----------------
Optimality. `list_schedule` is greedy; it proves nothing and may lose to the
oracle. Only validity and makespan are guaranteed.

Honesty matters too: cycles in "order" and "order+cycles" are placed by the
scheduler, not the model, so those results are labeled as hybrids. Reaching
100% valid after CAB is a property of the mechanism, not model improvement;
compare by gap to oracle instead.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..core.baseline import list_schedule
from ..core.dag import DAG, compute_metrics
from ..core.model import MachineModel
from ..core.schedule import Schedule


@dataclass(frozen=True)
class Variant:
    """One portfolio candidate.

    `name` is a short column label; `how` explains to the user whose work it
    is. Kept separate because tables are tight while footnotes need provenance.
    """

    name: str
    how: str
    schedule: Schedule
    errors: tuple[str, ...] = ()

    @property
    def legal(self) -> bool:
        return not self.errors and self.schedule.complete

    @property
    def makespan(self) -> int:
        return self.schedule.makespan


def order_from_model(placements: dict[int, tuple[int, int]], n: int,
                     height) -> list[float]:
    """Model response -> priority vector for `list_schedule`.

    Higher value means considered earlier. Model-placed ops follow its
    `(cycle, channel)` order; unplaced ops follow by descending critical path
    (the baseline rule).

    Unplaced ops go at the tail rather than interleaved: the model gave no
    opinion on them (truncated/malformed), so a height-ordered tail gives a
    smooth fallback to greedy on the uncovered portion of the graph.
    """
    def key(i: int):
        place = placements.get(i)
        if place is None:
            return (1, -int(height[i]), i)
        cycle, channel = place
        return (0, cycle, channel, i)

    order = sorted(range(n), key=key)
    prio = [0.0] * n
    for rank, i in enumerate(order):
        prio[i] = float(n - rank)
    return prio


def floor_from_model(placements: dict[int, tuple[int, int]],
                     limit: int) -> dict[int, int]:
    """Model cycles as "no earlier than" constraints (`defer_until`).

    `limit` clips hallucinations: a cycle above the ceiling (greedy makespan)
    is a formatting failure, not a scheduling hint, and must not be honored
    (otherwise a single "cycle 900" would legitimately stretch the schedule).
    """
    return {i: c for i, (c, _ch) in placements.items() if 0 < c <= limit}


def variants(dag: DAG, model: MachineModel,
             placements: dict[int, tuple[int, int]],
             *, extra: tuple[Variant, ...] = ()) -> list[Variant]:
    """Build portfolio candidates for one DAG without invoking model generation.

    `extra` holds upstream candidates from the same response (raw model
    schedule and `repair.py` output). They compete on equal footing so
    selection prefers the model's own answer on ties and reporting never
    overstates algorithmic gains.
    """
    metrics = compute_metrics(dag, model)
    n = len(dag)

    greedy, _ = list_schedule(dag, model, priority=[float(h) for h in metrics.height],
                              height=metrics.height)
    out = [
        *extra,
        Variant("greedy", "baseline, model did not participate", greedy,
                tuple(greedy.validate())),
    ]

    prio = order_from_model(placements, n, metrics.height)
    by_order, _ = list_schedule(dag, model, priority=prio, height=metrics.height)
    out.append(Variant(
        "order",
        "model ordering, cycles and channels by scheduler",
        by_order, tuple(by_order.validate())))

    defer = floor_from_model(placements, greedy.makespan)
    if defer:
        by_both, _ = list_schedule(dag, model, priority=prio,
                                   defer_until=defer, height=metrics.height)
        out.append(Variant(
            "order+cycles",
            "model ordering, its cycles as defer_until, channels by scheduler",
            by_both, tuple(by_both.validate())))

    return out


def choose(cands: list[Variant]) -> Variant:
    """Pick the best valid candidate: fewer cycles wins.

    Ties go to the earlier entry, with the model's own response placed first
    so the portfolio never credits the algorithm when the model matched it.

    If no valid candidate exists (empty/degenerate input), returns the first
    so the caller prints diagnostics instead of raising.
    """
    legal = [(i, c) for i, c in enumerate(cands) if c.legal]
    if not legal:
        return cands[0]
    return min(legal, key=lambda p: (p[1].makespan, p[0]))[1]
