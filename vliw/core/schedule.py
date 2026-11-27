"""Schedule: instruction placements by (cycle, channel), validation, and metrics."""

from __future__ import annotations

from dataclasses import dataclass, field

from .dag import DAG
from .model import MachineModel


@dataclass(frozen=True)
class Placement:
    instr: int
    cycle: int
    channel: int


@dataclass
class Schedule:
    dag: DAG
    model: MachineModel
    placements: dict[int, Placement] = field(default_factory=dict)

    # --- construction -----------------------------------------------------

    def place(self, instr: int, cycle: int, channel: int) -> None:
        self.placements[instr] = Placement(instr, cycle, channel)

    def cycle_of(self, instr: int) -> int:
        return self.placements[instr].cycle

    def ready_at(self, instr: int) -> int:
        """Earliest cycle when the instruction's result is available to consumers."""
        p = self.placements[instr]
        return p.cycle + self.model.latency(self.dag[instr].op)

    # --- metrics ----------------------------------------------------------

    @property
    def complete(self) -> bool:
        return len(self.placements) == len(self.dag)

    @property
    def makespan(self) -> int:
        """Cycles until ALL block results are ready (accounts for tail latencies)."""
        if not self.placements:
            return 0
        return max(self.ready_at(i) for i in self.placements)

    @property
    def bundle_count(self) -> int:
        """Number of non-empty wide instructions issued."""
        return len({p.cycle for p in self.placements.values()})

    @property
    def span_cycles(self) -> int:
        """Span from first to last issue cycle inclusive."""
        if not self.placements:
            return 0
        return max(p.cycle for p in self.placements.values()) + 1

    @property
    def slot_utilization(self) -> float:
        """Fraction of wide-instruction slots utilized across the issue span."""
        total = self.span_cycles * self.model.width
        return len(self.placements) / total if total else 0.0

    def busy_map(self) -> dict[tuple[int, int], tuple[int, bool]]:
        """Map (cycle, channel) -> (instruction_id, is_issue_cycle).

        Multi-cycle occupancy ops (e.g. DIV) mark subsequent busy cycles as continuations.
        """
        out: dict[tuple[int, int], tuple[int, bool]] = {}
        for p in self.placements.values():
            occ = self.model.occupancy(self.dag[p.instr].op)
            for k in range(occ):
                out[(p.cycle + k, p.channel)] = (p.instr, k == 0)
        return out

    # --- validation -------------------------------------------------------

    def validate(self) -> list[str]:
        """Full validity check. Empty list means the schedule is valid."""
        errs: list[str] = []
        if not self.complete:
            missing = sorted(set(range(len(self.dag))) - set(self.placements))
            errs.append(f"unplaced instructions: {missing}")
            return errs

        # 1. Dependencies.
        for ins in self.dag:
            for p in ins.preds:
                need = self.ready_at(p)
                got = self.cycle_of(ins.id)
                if got < need:
                    errs.append(
                        f"{ins.name} issued in cycle {got}, but operand "
                        f"{self.dag[p].name} is not ready until cycle {need}"
                    )

        # 2. Channel capabilities.
        for p in self.placements.values():
            op = self.dag[p.instr].op
            if p.channel not in self.model.channels_for(op):
                errs.append(
                    f"{self.dag[p.instr].name} ({op}) placed on channel "
                    f"{p.channel}, which does not execute it"
                )

        # 3. Channel conflicts (including multi-cycle exclusive occupancy).
        seen: dict[tuple[int, int], int] = {}
        for p in sorted(self.placements.values(), key=lambda x: (x.cycle, x.channel)):
            occ = self.model.occupancy(self.dag[p.instr].op)
            for k in range(occ):
                cell = (p.cycle + k, p.channel)
                if cell in seen:
                    errs.append(
                        f"channel {p.channel} conflict in cycle {p.cycle + k}: "
                        f"{self.dag[seen[cell]].name} and {self.dag[p.instr].name}"
                    )
                seen[cell] = p.instr

        # 4. Wide instruction width.
        per_cycle: dict[int, int] = {}
        for p in self.placements.values():
            per_cycle[p.cycle] = per_cycle.get(p.cycle, 0) + 1
        for c, k in sorted(per_cycle.items()):
            if k > self.model.width:
                errs.append(f"cycle {c}: {k} operations exceeds width {self.model.width}")

        return errs


# --------------------------------------------------------------------------
# Machine resource state during scheduling (shared across schedulers)
# --------------------------------------------------------------------------


class ChannelState:
    """Cycle until which each channel is occupied."""

    def __init__(self, width: int):
        self.free_at = [0] * width

    def copy(self) -> "ChannelState":
        c = ChannelState(len(self.free_at))
        c.free_at = list(self.free_at)
        return c

    def free_channels(self, cycle: int, capable: tuple[int, ...]) -> list[int]:
        return [c for c in capable if self.free_at[c] <= cycle]

    def occupy(self, channel: int, cycle: int, occupancy: int) -> None:
        self.free_at[channel] = cycle + occupancy
