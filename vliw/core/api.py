"""Common scheduler contract (extension point for learned models).

Baseline heuristic, exact oracle, and learned schedulers all implement the
same `Scheduler` protocol (`schedule(dag, model) -> SchedulingResult`), so
validation, metrics, explanations, CLI, and UI work unchanged.

Minimal implementation:

    class LearnedScheduler:
        name = "AI scheduler (learned model)"
        kind = "learned"
        short = "learned"

        def schedule(self, dag, model):
            ...
            return SchedulingResult(schedule=sched, trace=steps, notes=[])

`trace` is optional and used only for step-by-step explanations.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from .dag import DAG
from .model import MachineModel
from .schedule import Placement, Schedule


@dataclass
class Candidate:
    """One candidate instruction in a single cycle decision."""

    instr: int
    ready_at: int
    """Earliest cycle when operands are ready."""
    height: int
    """Remaining critical-path length (baseline heuristic priority)."""
    chosen: bool = False
    channel: int | None = None
    reason: str = ""
    """Human-readable reason why this instruction was picked or skipped."""


@dataclass
class DecisionStep:
    """Snapshot of scheduler decisions in one cycle."""

    cycle: int
    free_channels: tuple[int, ...]
    candidates: list[Candidate] = field(default_factory=list)
    blocked: list[tuple[int, int]] = field(default_factory=list)
    """(instruction, busy_until_cycle) for channels held exclusively."""
    rule: str = ""
    """Description of the rule applied in this cycle."""
    comment: str = ""
    """Optional cycle commentary."""

    @property
    def issued(self) -> list[int]:
        return [c.instr for c in self.candidates if c.chosen]


@dataclass
class SchedulingResult:
    schedule: Schedule
    trace: list[DecisionStep] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    """Report notes: what the scheduler did, proved, or timed out on."""
    optimal: bool | None = None
    """True if proven optimal, False if proven suboptimal, None if unknown."""
    search_stats: dict[str, object] = field(default_factory=dict)


@runtime_checkable
class Scheduler(Protocol):
    name: str
    kind: str
    short: str

    def schedule(self, dag: DAG, model: MachineModel) -> SchedulingResult: ...


# --------------------------------------------------------------------------
# Scheduler event stream
# --------------------------------------------------------------------------
#
# WHY THIS EXISTS: the synchronous contract above works for millisecond
# baseline/oracle runs, whereas learned models take 30-60 s and stream
# partial results. An event stream lets any UI render live progress,
#
# grid fills, and cancellation cleanly while keeping the `Scheduler`
# protocol backwards-compatible via `stream()`.
#
#
#
#
#
#
#
#
#
#
#
#
#
#


@dataclass(frozen=True)
class Started:
    """Scheduler identification. Always the first event in the stream."""

    who: str
    note: str = ""


@dataclass(frozen=True)
class Note:
    """Human-readable status line (`level` is a semantic role; coloring lives in `vliw.ui`)."""

    text: str
    level: str = "dim"


@dataclass(frozen=True)
class Token:
    """Raw model text chunk (emitted only by text-generating schedulers)."""

    text: str


@dataclass(frozen=True)
class Step:
    """Single cycle decision (`live=False` indicates replay of a completed trace)."""

    step: DecisionStep
    live: bool = True


@dataclass(frozen=True)
class Placed:
    """An instruction was placed at (cycle, channel); drives live grid updates."""

    placement: Placement
    live: bool = True


@dataclass(frozen=True)
class Repaired:
    """Channel reassigned by repair (cycle unchanged, channel made valid)."""

    instr: int
    frm: int
    to: int


@dataclass(frozen=True)
class Progress:
    """Progress update (`done` of `total`; `total=0` when unknown)."""

    done: int
    total: int = 0
    note: str = ""


@dataclass(frozen=True)
class Done:
    """Terminal event: scheduling succeeded."""

    result: SchedulingResult


@dataclass(frozen=True)
class Failed:
    """Terminal event: expected failure (missing weights, timeout, missing binary).

    Internal scheduler bugs still raise exceptions rather than emitting Failed.
    """

    error: str


SchedulerEvent = (Started | Note | Token | Step | Placed | Repaired
                  | Progress | Done | Failed)

TERMINAL = (Done, Failed)
"""Every stream terminates with exactly one of these events."""


def _replay(res: SchedulingResult) -> Iterator[SchedulerEvent]:
    """Replay a completed SchedulingResult as cycle-ordered events."""
    seen: set[int] = set()
    for st in res.trace:
        yield Step(st, live=False)
        for i in st.issued:
            p = res.schedule.placements.get(i)
            if p is not None and i not in seen:
                seen.add(i)
                yield Placed(p, live=False)
    # `trace` is optional: placements must still reach the grid without it.
    #
    for i, p in sorted(res.schedule.placements.items()):
        if i not in seen:
            yield Placed(p, live=False)


def stream(scheduler, dag: DAG, model: MachineModel) -> Iterator[SchedulerEvent]:
    """Unified UI entry point: stream events from any Scheduler.

    Schedulers with `schedule_events()` stream directly; legacy schedulers
    with only `schedule()` are replayed via `replay()`. Closing the generator
    triggers `GeneratorExit` for cleanup; `schedule_events()` implementations
    must open `try:` BEFORE their first `yield`.
    """
    fn = getattr(scheduler, "schedule_events", None)
    if fn is not None:
        yield from fn(dag, model)
        return

    yield Started(getattr(scheduler, "short", "?"),
                  getattr(scheduler, "name", ""))
    res = scheduler.schedule(dag, model)
    yield from _replay(res)
    yield Done(res)
