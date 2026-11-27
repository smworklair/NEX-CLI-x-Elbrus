"""Channel repair for model output: keep its cycles, assign valid channels.

WHY
---
Evaluation showed a clean split: when the model does not pick an invalid
channel, it hits the EXACT optimum (0.00 cycle gap on all valid schedules).
When it errs, it is almost always STORE placed on an unsupported channel
(run-1 training data had zero STOREs, so the model did not know STORE only
executes on `,2` and `,5`).

The model is strong at scheduling across cycles and weak on the hardware
channel matrix, which is known exactly in `vliw/core/model.py`. Leaving cycles
untouched and reassigning only channels preserves makespan (determined purely
by cycles) and fixes channel validity.

HONESTY. A repaired schedule is a hybrid, not pure model output. `repair()`
returns a detailed report of every moved channel so the UI surfaces it.

NON-GOALS. Cycles are never moved. Dependency or multi-cycle port-occupancy
violations cannot be fixed without moving cycles and are left for
`Schedule.validate()` to report.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..core.model import MachineModel
from ..core.schedule import Schedule


@dataclass
class RepairReport:
    """Exact record of channel reassignments."""

    moved: list[tuple[int, int, int]] = field(default_factory=list)
    """(instruction, model_channel, repaired_channel)."""
    impossible: list[int] = field(default_factory=list)
    """Instructions for which no valid channel existed in their cycle."""

    @property
    def touched(self) -> int:
        return len(self.moved)

    @property
    def ok(self) -> bool:
        return not self.impossible


def _assign_cycle(ops: list[tuple[int, tuple[int, ...], int]],
                  width: int) -> dict[int, int] | None:
    """Assign channels to instructions in a single cycle. Returns None if impossible.

    Uses Kuhn bipartite matching (same technique as `vliw/core/oracle.py`).
    Greedy "first free" fails when a flexible op takes the sole port needed by
    a narrow op (e.g. ADD takes `,2`, stranding STORE which only runs on `,2,5`).

    `ops` is (instruction, allowed_channels, model_channel). Preference order
    tries the model channel first so already-valid channels stay unchanged.
    """
    owner: dict[int, int] = {}          # channel -> instruction

    def augment(op: int, allowed: tuple[int, ...], seen: set[int],
                prefer: int) -> bool:
        order = ([prefer] if prefer in allowed else []) + \
                [c for c in allowed if c != prefer]
        for ch in order:
            if ch in seen or ch >= width:
                continue
            seen.add(ch)
            holder = owner.get(ch)
            if holder is None:
                owner[ch] = op
                return True
            h_allowed, h_prefer = holders[holder]
            if augment(holder, h_allowed, seen, h_prefer):
                owner[ch] = op
                return True
        return False

    holders: dict[int, tuple[tuple[int, ...], int]] = {
        i: (allowed, prefer) for i, allowed, prefer in ops
    }
    # Most constrained ops first: starting with flexible ops can starve narrow ones.
    for i, allowed, prefer in sorted(ops, key=lambda t: len(t[1])):
        if not augment(i, allowed, set(), prefer):
            return None
    return {op: ch for ch, op in owner.items()}


def repair(sched: Schedule, model: MachineModel) -> tuple[Schedule, RepairReport]:
    """Return a new schedule with the same cycles and valid channels.

    Does not mutate the input schedule.
    """
    dag = sched.dag
    report = RepairReport()

    by_cycle: dict[int, list[int]] = {}
    for i, p in sched.placements.items():
        by_cycle.setdefault(p.cycle, []).append(i)

    fixed = Schedule(dag, model)
    for cycle in sorted(by_cycle):
        ops = []
        for i in sorted(by_cycle[cycle]):
            allowed = model.channels_for(dag[i].op)
            ops.append((i, allowed, sched.placements[i].channel))

        got = _assign_cycle(ops, model.width)
        if got is None:
            # Cannot assign validly — more ops in this cycle than compatible ports.
            # We never move cycles, so leave as-is for validate() to report.
            for i, _, prefer in ops:
                fixed.place(i, cycle, prefer)
                report.impossible.append(i)
            continue

        for i, _, prefer in ops:
            ch = got[i]
            fixed.place(i, cycle, ch)
            if ch != prefer:
                report.moved.append((i, prefer, ch))

    return fixed, report
