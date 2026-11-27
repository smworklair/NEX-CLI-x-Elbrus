"""Fast greedy list-scheduling engine: bit-exact parity with `list_schedule`.

Produces the exact same (cycle, channel) and issue order for every instruction
using remaining-predecessor counters, pre-sorted channels, idle-cycle skipping,
and lazy `Schedule` construction. Does not collect decision traces.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .baseline import channel_costs
from .dag import DAG
from .model import MachineModel
from .schedule import Placement, Schedule

_GUARD = 100000  # matches list_schedule

# Per-machine table: op -> (latency, occupancy, cost-sorted channels).
# Bounded cache keyed by model id with identity check.
#
#
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
    """DAG-invariant precomputation reused across priority/defer runs."""

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
        """Single pass. Higher `priority` first; `defer_until` sets earliest issue cycle."""
        n = self.n
        if n == 0:
            return RawSchedule([], [], [], 0)
        neg = [-p for p in priority]
        order = sorted(range(n), key=neg.__getitem__)  # stable: ties break by instruction ID
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
                raise RuntimeError("scheduler stuck in loop")
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
                        break  # all channels full: nothing more can issue this cycle
                if did:
                    pool = [i for i in pool if cyc[i] < 0]
                    if newly:
                        pool += newly
                    cycle += 1
                    continue
            # Nothing issued this cycle: jump to earliest cycle where some op
            # becomes ready, passes defer_until, and has a free channel.
            #
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
                raise RuntimeError("scheduler stuck in loop")
            cycle = wake if wake > cycle else cycle + 1

        ms = 0
        for i in range(n):
            v = cyc[i] + lat[i]
            if v > ms:
                ms = v
        return RawSchedule(cyc, chn, placed, ms)

    def to_schedule(self, raw: "RawSchedule") -> Schedule:
        """Materialize a `Schedule` (insertion order matches issue order)."""
        s = Schedule(self.dag, self.model)
        pl = s.placements
        cyc, chn = raw.cycle, raw.channel
        for i in raw.order:
            pl[i] = Placement(i, cyc[i], chn[i])
        return s


@dataclass(slots=True)
class RawSchedule:
    """Lightweight schedule result: cycle and channel arrays indexed by instruction ID."""

    cycle: list[int]
    channel: list[int]
    order: list[int]  # instructions in issue order
    makespan: int


def list_schedule_fast(dag: DAG, model: MachineModel, priority: Sequence[float],
                       *, defer_until: Mapping[int, int] | None = None,
                       height: Sequence[int] | None = None) -> tuple[Schedule, list]:
    """Drop-in replacement for `baseline.list_schedule(..., collect_trace=False)`."""
    plan = ListPlan(dag, model)
    return plan.to_schedule(plan.run(priority, defer_until)), []
