"""SEED tests: hints to the exact branch-and-bound oracle must never corrupt optimality.

A hint enters the oracle only as a validated upper bound (strictly shorter than
baseline) and as a priority vector for the portfolio. An illegal or incomplete
hint must be rejected so the oracle can never claim a false optimum.
"""

from __future__ import annotations

import unittest

from vliw.core import get_profile, get_scenario
from vliw.core.oracle import Hint, OracleScheduler
from vliw.core.schedule import Schedule
from vliw.learned.seed import hint_from_answer


class TestHintCannotChangeTheAnswer(unittest.TestCase):
    def setUp(self):
        self.machine = get_profile("e2k-v6-measured")

    def test_same_optimum_with_and_without_hint(self):
        for key in ("slotclash", "divpressure", "mixed18"):
            dag = get_scenario(key)
            plain = OracleScheduler().schedule(dag, self.machine)
            answer = {p.instr: (p.cycle, 0)
                      for p in plain.schedule.placements.values()}
            hinted = OracleScheduler(
                hint=hint_from_answer(dag, self.machine, answer)
            ).schedule(dag, self.machine)
            with self.subTest(scenario=key):
                self.assertEqual(hinted.schedule.makespan, plain.schedule.makespan)
                self.assertEqual(hinted.optimal, plain.optimal)
                self.assertEqual(hinted.schedule.validate(), [])

    def test_illegal_hint_is_ignored(self):
        """An illegal schedule must never be accepted as an upper bound."""
        dag = get_scenario("slotclash")
        bad = Schedule(dag, self.machine)
        for i in range(len(dag)):
            bad.place(i, 0, 0)              # all ops crammed onto port 0 in cycle 0
        self.assertTrue(bad.validate(), "fixture must be illegal")

        plain = OracleScheduler().schedule(dag, self.machine)
        hinted = OracleScheduler(
            hint=Hint(schedule=bad, source="junk")
        ).schedule(dag, self.machine)
        self.assertEqual(hinted.schedule.makespan, plain.schedule.makespan)
        self.assertFalse(hinted.search_stats["hint_gave_upper_bound"])

    def test_incomplete_hint_is_ignored(self):
        """An incomplete schedule has artificially low makespan and must be rejected."""
        dag = get_scenario("slotclash")
        part = Schedule(dag, self.machine)
        part.place(0, 0, 0)
        hinted = OracleScheduler(
            hint=Hint(schedule=part, source="stub")
        ).schedule(dag, self.machine)
        self.assertFalse(hinted.search_stats["hint_gave_upper_bound"])
        self.assertEqual(hinted.schedule.validate(), [])


class TestHintIsCredited(unittest.TestCase):
    def test_upper_bound_from_hint_is_recorded(self):
        """Attribution of a winning hint must be preserved in search_stats and notes."""
        dag = get_scenario("slotclash")
        machine = get_profile("e2k-v6-measured")
        opt = OracleScheduler().schedule(dag, machine).schedule
        answer = {p.instr: (p.cycle, 0) for p in opt.placements.values()}

        res = OracleScheduler(
            hint=hint_from_answer(dag, machine, answer, source="model")
        ).schedule(dag, machine)

        # Recompute baseline dynamically so latency updates in model.py never stale this test.
        from vliw.core.baseline import GreedyListScheduler
        greedy_ms = GreedyListScheduler().schedule(dag, machine).schedule.makespan

        self.assertTrue(res.search_stats["hint_gave_upper_bound"])
        self.assertEqual(res.search_stats["hint_source"], "model")
        self.assertEqual(res.search_stats["baseline_upper_bound"], greedy_ms,
                         "baseline_makespan in stats must remain the unseeded baseline")
        self.assertEqual(res.search_stats["nodes"], 0,
                         "a hint meeting the lower bound proves optimality with zero branch-and-bound search")
        self.assertTrue(any("model" in n for n in res.notes))


if __name__ == "__main__":
    unittest.main()
