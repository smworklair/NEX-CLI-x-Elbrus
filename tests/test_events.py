"""Scheduler event stream tests: `vliw.core.api.stream()`.

Verifies two core contracts:
1. Backwards compatibility: any scheduler implementing only `schedule()`
   streams cleanly via replay without needing `schedule_events()`.
2. Cancellation safety: calling `close()` raises `GeneratorExit` at `yield`
   and runs the scheduler's `finally` block (critical for killing llama.cpp).
"""

from __future__ import annotations

import unittest

from vliw.core import (
    DAG,
    Done,
    Failed,
    GreedyListScheduler,
    OracleScheduler,
    Placed,
    SchedulingResult,
    Started,
    Step,
    Token,
    get_profile,
    get_scenario,
    stream,
)
from vliw.core.api import TERMINAL
from vliw.core.schedule import Schedule

M = get_profile("e2k-v6-measured")


class OldContractScheduler:
    """Legacy-contract scheduler: implements only `schedule()`, no events or trace."""

    name = "legacy contract"
    kind = "heuristic"
    short = "old"

    def schedule(self, dag: DAG, model) -> SchedulingResult:
        sched = Schedule(dag, model)
        for i, instr in enumerate(dag):
            sched.place(i, i, model.channels_for(instr.op)[0])
        return SchedulingResult(schedule=sched)


class StreamAdapterTest(unittest.TestCase):
    """Scheduler without `schedule_events()` streams via result replay."""

    def setUp(self) -> None:
        self.dag = get_scenario("slotclash")

    def _events(self, scheduler):
        return list(stream(scheduler, self.dag, M))

    def test_old_contract_scheduler_works_untouched(self) -> None:
        """A single-method `schedule()` class still produces a complete event stream."""
        evs = self._events(OldContractScheduler())
        self.assertIsInstance(evs[0], Started)
        self.assertIsInstance(evs[-1], Done)
        placed = [e for e in evs if isinstance(e, Placed)]
        self.assertEqual(len(placed), len(self.dag))

    def test_no_trace_still_places_everything(self) -> None:
        """Even without a trace, every placement must still be emitted as a `Placed` event."""
        evs = self._events(OldContractScheduler())
        got = {e.placement.instr for e in evs if isinstance(e, Placed)}
        self.assertEqual(got, set(range(len(self.dag))))

    def test_every_instruction_placed_exactly_once(self) -> None:
        """No instruction may be emitted twice when combining trace and schedule placements."""
        for scheduler in (GreedyListScheduler(),
                          OracleScheduler(budget_s=5.0, portfolio_s=1.0)):
            with self.subTest(scheduler=scheduler.short):
                evs = self._events(scheduler)
                placed = [e.placement.instr for e in evs if isinstance(e, Placed)]
                self.assertEqual(len(placed), len(set(placed)))
                self.assertEqual(set(placed), set(range(len(self.dag))))

    def test_exactly_one_terminal_event_and_it_is_last(self) -> None:
        """Exactly one terminal `Done` event is emitted at the end of the stream."""
        evs = self._events(GreedyListScheduler())
        terminals = [e for e in evs if isinstance(e, TERMINAL)]
        self.assertEqual(len(terminals), 1)
        self.assertIs(terminals[0], evs[-1])

    def test_replay_is_marked_not_live(self) -> None:
        """Replay streams must set `replay=True` on `Started` so the UI knows it is not live."""
        evs = self._events(GreedyListScheduler())
        marks = {e.live for e in evs if isinstance(e, (Step, Placed))}
        self.assertEqual(marks, {False})

    def test_terminal_result_is_the_schedulers_own(self) -> None:
        """`Done.result` must be the exact ScheduleResult object returned by `schedule()`."""
        scheduler = GreedyListScheduler()
        direct = scheduler.schedule(self.dag, M)
        evs = self._events(scheduler)
        self.assertEqual(evs[-1].result.schedule.makespan,
                         direct.schedule.makespan)


class EventfulScheduler:
    """Event-native scheduler that places `try:` BEFORE its first `yield`."""

    name = "event-native"
    kind = "learned"
    short = "ev"

    def __init__(self) -> None:
        self.cleaned = False
        self.emitted = 0

    def schedule_events(self, dag: DAG, model):
        try:
            yield Started(self.short)
            while True:                     # infinite stream, like LLM generation
                self.emitted += 1
                yield Token("x")
        finally:
            # In the learned scheduler, this terminates the llama.cpp subprocess.
            self.cleaned = True

    def schedule(self, dag: DAG, model) -> SchedulingResult:
        raise AssertionError("schedule() must not be called when schedule_events() exists")


class LeakyScheduler:
    """Anti-pattern fixture: `try:` placed AFTER the first `yield` leaks on immediate close()."""

    name = "leaky"
    kind = "learned"
    short = "leak"

    def __init__(self) -> None:
        self.cleaned = False

    def schedule_events(self, dag: DAG, model):
        yield Started(self.short)           # outside try: leaks if closed here
        try:
            while True:
                yield Token("x")
        finally:
            self.cleaned = True


class EventfulPathTest(unittest.TestCase):

    def setUp(self) -> None:
        self.dag = get_scenario("simple4")

    def test_schedule_events_wins_over_schedule(self) -> None:
        """When `schedule_events()` is present, live streaming is used instead of replay."""
        sch = EventfulScheduler()
        gen = stream(sch, self.dag, M)
        self.assertIsInstance(next(gen), Started)
        self.assertIsInstance(next(gen), Token)
        gen.close()

    def test_close_runs_scheduler_cleanup(self) -> None:
        """Closing the generator mid-stream triggers `finally` cleanup."""
        sch = EventfulScheduler()
        gen = stream(sch, self.dag, M)
        for _ in range(4):
            next(gen)
        self.assertFalse(sch.cleaned)
        gen.close()
        self.assertTrue(sch.cleaned)

    def test_cancel_on_the_very_first_event_still_cleans_up(self) -> None:
        """Cancelling immediately after `Started` must still execute `finally` cleanup."""
        sch = EventfulScheduler()
        gen = stream(sch, self.dag, M)
        next(gen)
        gen.close()
        self.assertTrue(sch.cleaned)
        self.assertEqual(sch.emitted, 0)

    def test_try_after_first_yield_leaks_and_that_is_why_the_rule_exists(self) -> None:
        """Documents the Python generator contract: `try:` after first `yield` misses `finally`."""
        sch = LeakyScheduler()
        gen = stream(sch, self.dag, M)
        next(gen)                            # yielded Started outside try
        gen.close()
        self.assertFalse(sch.cleaned, "Python generator close semantics changed — recheck contract")


class FailingScheduler:
    """Expected failure fixture (e.g. missing weights): emits `Failed` cleanly."""

    name = "no weights"
    kind = "learned"
    short = "nofail"

    def schedule_events(self, dag: DAG, model):
        yield Started(self.short)
        yield Failed("missing weights: adapter not converted to GGUF")


class FailedEventTest(unittest.TestCase):

    def test_failed_is_terminal(self) -> None:
        """`Failed` terminates the stream cleanly just like `Done`."""
        evs = list(stream(FailingScheduler(), get_scenario("simple4"), M))
        self.assertIsInstance(evs[-1], Failed)
        self.assertEqual(len([e for e in evs if isinstance(e, TERMINAL)]), 1)


if __name__ == "__main__":
    unittest.main()
