"""CAB (Candidate-And-Best): portfolio of legal VLIW schedules from a single model response.

Two core invariants are guarded here:
1. Legal-by-construction: even if the model places operations on unsupported
   issue ports, the portfolio must still produce a 100% legal schedule.
2. Honest attribution: on a tie in makespan, the model's own response must win
   over algorithmic variants so reports never credit the portfolio when the
   model already matched that makespan.
"""

from __future__ import annotations

import unittest

from training.encode import encode_completion
from vliw.core import GreedyListScheduler, get_profile, get_scenario
from vliw.core.dag import compute_metrics
from vliw.core.schedule import Schedule
from vliw.learned import portfolio as P
from vliw.learned.runtime import ScriptedBackend
from vliw.learned.scheduler import LearnedScheduler


def _fixture(scenario: str = "slotclash"):
    dag = get_scenario(scenario)
    machine = get_profile("e2k-v6-measured")
    return dag, machine


def _as_answer(dag, machine, placements) -> str:
    """Convert placements dict into the training completion text format."""
    sched = Schedule(dag, machine)
    for i, (c, ch) in sorted(placements.items()):
        sched.place(i, c, ch)
    return encode_completion(sched)


def _all_on_channel_zero(dag, machine):
    """Model response with reasonable cycles but every op forced onto port ,0.

    Reproduces the most common failure mode from early fine-tuning runs
    (e.g., STORE placed on port ,0, which cannot execute stores).
    """
    good = GreedyListScheduler().schedule(dag, machine).schedule
    return {p.instr: (p.cycle, 0) for p in good.placements.values()}


class TestOrderFromModel(unittest.TestCase):
    def test_placed_ops_keep_model_order(self):
        """Priority order follows the model's (cycle, port), not instruction IDs."""
        placements = {0: (5, 0), 1: (0, 3), 2: (0, 1)}
        prio = P.order_from_model(placements, 3, height=[0, 0, 0])
        # Earlier (cycle, port) gets higher priority: op 2 (0,1) > op 1 (0,3) > op 0 (5,0).
        self.assertGreater(prio[2], prio[1])
        self.assertGreater(prio[1], prio[0])

    def test_unplaced_go_last_by_height(self):
        """Ops omitted by the model fall to the tail, ordered by baseline critical-path height."""
        placements = {1: (0, 0)}
        prio = P.order_from_model(placements, 3, height=[7, 0, 2])
        self.assertGreater(prio[1], prio[0], "placed op must precede unplaced ops")
        self.assertGreater(prio[0], prio[2], "unplaced tail ordered by descending height")

    def test_empty_answer_degrades_to_height(self):
        """An empty model answer must degrade cleanly to baseline height ordering."""
        dag, machine = _fixture()
        height = compute_metrics(dag, machine).height
        prio = P.order_from_model({}, len(dag), height)
        by_prio = sorted(range(len(dag)), key=lambda i: -prio[i])
        by_height = sorted(range(len(dag)), key=lambda i: (-int(height[i]), i))
        self.assertEqual(by_prio, by_height)


class TestFloorFromModel(unittest.TestCase):
    def test_hallucinated_cycle_is_dropped(self):
        """Out-of-range cycles (e.g. 900) are format glitches and must be discarded."""
        floor = P.floor_from_model({0: (3, 0), 1: (900, 0)}, limit=25)
        self.assertEqual(floor, {0: 3})

    def test_zero_cycle_needs_no_floor(self):
        """A defer_until floor of cycle 0 is vacuous and should be omitted."""
        self.assertEqual(P.floor_from_model({0: (0, 0)}, limit=25), {})


class TestVariantsAreLegalByConstruction(unittest.TestCase):
    def test_broken_answer_still_yields_legal_schedules(self):
        dag, machine = _fixture()
        broken = _all_on_channel_zero(dag, machine)

        raw = Schedule(dag, machine)
        for i, (c, ch) in broken.items():
            raw.place(i, c, ch)
        self.assertTrue(raw.validate(), "fixture must be illegal")

        cands = P.variants(dag, machine, broken)
        self.assertTrue(cands)
        for c in cands:
            with self.subTest(variant=c.name):
                self.assertTrue(c.legal, f"{c.name}: {c.errors}")
                self.assertTrue(c.schedule.complete)

    def test_winner_never_worse_than_greedy(self):
        """The portfolio must never be worse than greedy list scheduling, which is included in it."""
        dag, machine = _fixture()
        broken = _all_on_channel_zero(dag, machine)
        cands = P.variants(dag, machine, broken)
        greedy = next(c for c in cands if c.name == "greedy")
        self.assertLessEqual(P.choose(cands).makespan, greedy.makespan)


class TestChooseIsHonest(unittest.TestCase):
    def test_tie_goes_to_the_earlier_candidate(self):
        """On equal makespan, the earlier candidate wins (model sits first)."""
        dag, machine = _fixture("simple4")
        good = GreedyListScheduler().schedule(dag, machine).schedule
        mine = P.Variant("model", "raw response", good, ())
        clone = P.Variant("order", "model ordering", good, ())
        self.assertEqual(P.choose([mine, clone]).name, "model")
        self.assertEqual(P.choose([clone, mine]).name, "order")

    def test_illegal_never_wins_over_legal(self):
        dag, machine = _fixture("simple4")
        good = GreedyListScheduler().schedule(dag, machine).schedule
        short = Schedule(dag, machine)
        for p in good.placements.values():
            short.place(p.instr, 0, 0)          # all ops crammed onto port 0 in cycle 0
        cands = [P.Variant("model", "raw", short, tuple(short.validate())),
                 P.Variant("greedy", "baseline", good, ())]
        self.assertEqual(P.choose(cands).name, "greedy")


class TestWiredIntoScheduler(unittest.TestCase):
    def test_cab_off_by_default_keeps_model_answer(self):
        """With cab=False (default), raw model output is preserved unchanged."""
        dag, machine = _fixture()
        broken = _all_on_channel_zero(dag, machine)
        text = _as_answer(dag, machine, broken)
        res = LearnedScheduler(backend=ScriptedBackend(text)).schedule(dag, machine)
        self.assertFalse(res.search_stats["valid"])
        self.assertIsNone(res.search_stats.get("cab_winner"))

    def test_cab_on_makes_the_result_legal(self):
        dag, machine = _fixture()
        broken = _all_on_channel_zero(dag, machine)
        text = _as_answer(dag, machine, broken)
        res = LearnedScheduler(backend=ScriptedBackend(text),
                               cab=True).schedule(dag, machine)
        self.assertEqual(res.schedule.validate(), [])
        self.assertTrue(res.schedule.complete)
        self.assertIsNotNone(res.search_stats["cab_winner"])
        rows = res.search_stats["cab"]
        self.assertTrue(any(r["won"] for r in rows))
        self.assertTrue(any("order" in r["name"] for r in rows))


class TestMetricsFollowTheFinalSchedule(unittest.TestCase):
    """Ensure `valid` reflects the final CAB-repaired schedule, not missing ops in the raw reply."""

    def test_valid_is_about_the_result_not_the_raw_answer(self):
        dag, machine = _fixture()
        placements = _all_on_channel_zero(dag, machine)
        del placements[max(placements)]          # model truncated before final op
        res = LearnedScheduler(backend=ScriptedBackend(
            _as_answer(dag, machine, placements)), cab=True).schedule(dag, machine)

        self.assertTrue(res.search_stats["missing"], "fixture: final line must be missing")
        self.assertTrue(res.schedule.complete)
        self.assertTrue(res.search_stats["valid"])


class TestTieIsNotAWin(unittest.TestCase):
    """Tying the greedy baseline must not be reported as beating it."""

    def test_matching_the_heuristic_is_not_beating_it(self):
        dag, machine = _fixture()
        greedy = GreedyListScheduler().schedule(dag, machine).schedule
        answer = {p.instr: (p.cycle, p.channel) for p in greedy.placements.values()}
        res = LearnedScheduler(backend=ScriptedBackend(
            _as_answer(dag, machine, answer)), cab=True).schedule(dag, machine)

        self.assertEqual(res.search_stats["cab_winner"], "model")
        self.assertFalse(res.search_stats["cab_beat_greedy"],
                         "tying greedy baseline must not count as beating it")

    def test_strictly_shorter_counts_as_a_win(self):
        """On `slotclash`, oracle beats greedy; CAB recovers the optimal makespan even with broken ports."""
        from vliw.core.oracle import OracleScheduler

        dag, machine = _fixture()
        orc = OracleScheduler().schedule(dag, machine)
        # Optimal cycles, intentionally broken ports (all on port ,0).
        answer = {p.instr: (p.cycle, 0) for p in orc.schedule.placements.values()}
        res = LearnedScheduler(backend=ScriptedBackend(
            _as_answer(dag, machine, answer)), cab=True).schedule(dag, machine)

        self.assertEqual(res.schedule.validate(), [])
        self.assertEqual(res.schedule.makespan, orc.schedule.makespan)
        self.assertTrue(res.search_stats["cab_beat_greedy"])
        self.assertNotEqual(res.search_stats["cab_winner"], "greedy")


if __name__ == "__main__":
    unittest.main()
