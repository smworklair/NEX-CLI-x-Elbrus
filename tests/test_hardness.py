"""Graph hardness tests: measuring whether a DAG has recoverable headroom over greedy list scheduling.

Core invariant: a graph whose optimum was NOT proven within the oracle budget
must never be labeled hard, preventing suboptimal targets from polluting training
and evaluation datasets.
"""

from __future__ import annotations

import unittest

from vliw.core import get_profile, get_scenario
from vliw.core.hardness import Hardness, measure
from vliw.core.schedule import Schedule


class TestMeasure(unittest.TestCase):
    def setUp(self):
        self.machine = get_profile("e2k-v6-measured")

    def test_slotclash_has_a_gap(self):
        """Trap scenario: exclusive divider port occupied by a non-critical op."""
        h = measure(get_scenario("slotclash"), self.machine)
        self.assertTrue(h.proven)
        self.assertEqual(h.gap, 1)
        self.assertTrue(h.hard)

    def test_easy_scenario_has_none(self):
        """On a trivial DAG, greedy is already optimal (gap == 0)."""
        h = measure(get_scenario("simple4"), self.machine)
        self.assertTrue(h.proven)
        self.assertEqual(h.gap, 0)
        self.assertFalse(h.hard)

    def test_schedule_is_the_optimum_and_is_legal(self):
        """The schedule returned by `measure()` is a validated, complete reference."""
        dag = get_scenario("slotclash")
        h = measure(dag, self.machine)
        self.assertEqual(h.schedule.validate(), [])
        self.assertTrue(h.schedule.complete)
        self.assertEqual(h.schedule.makespan, h.optimum)


class TestUnprovenIsNotHard(unittest.TestCase):
    def test_gap_without_proof_does_not_count(self):
        """An unproven gap must not be accepted as a hard training example."""
        dag = get_scenario("simple4")
        machine = get_profile("e2k-v6-measured")
        sched = Schedule(dag, machine)
        guess = Hardness(baseline=20, optimum=18, proven=False, schedule=sched)
        self.assertEqual(guess.gap, 2)
        self.assertFalse(guess.hard)

        proved = Hardness(baseline=20, optimum=18, proven=True, schedule=sched)
        self.assertTrue(proved.hard)


class TestGeneratorWeightsAreParameter(unittest.TestCase):
    def test_pressure_mix_shifts_the_op_distribution(self):
        """Op-weight overrides are passed as arguments without mutating module globals."""
        import random
        from collections import Counter

        from tools.vliw_gen import OP_WEIGHTS, PRESSURE_WEIGHTS, gen_graph

        rnd = random.Random(7)
        plain = Counter(i.op for _ in range(60)
                        for i in gen_graph(rnd, 14, "mixed"))
        loaded = Counter(i.op for _ in range(60)
                         for i in gen_graph(rnd, 14, "mixed", PRESSURE_WEIGHTS))

        self.assertLess(plain["DIV"] / plain.total(), 0.08)
        self.assertGreater(loaded["DIV"] / loaded.total(), 0.12)
        self.assertEqual(OP_WEIGHTS["DIV"], 3, "module-level OP_WEIGHTS must remain untouched")
class TestHarvestWorker(unittest.TestCase):
    """Hard-example collector: every returned record must be legal, optimal, and strictly beat greedy."""

    def test_returned_rows_are_valid_hard_examples(self):
        from training.encode import build_schedule, decode_completion
        from vliw.core.baseline import GreedyListScheduler
        from vliw.core.dag import DAG
        from vliw.core.hardness import harvest_one
        from vliw.learned.bench import _parse_graph

        machine = get_profile("e2k-v6-measured")
        rows = [harvest_one((seed, 16, 22, "e2k-v6-measured")) for seed in range(30)]
        found = [r for r in rows if r is not None]
        self.assertTrue(found, "no hard graph found across 30 seeds")

        for row in found:
            with self.subTest(seed=row["meta"]["seed"]):
                dag = DAG("h", "", "", _parse_graph(row["prompt"]))
                sched = build_schedule(dag, machine,
                                       decode_completion(row["completion"]))
                greedy = GreedyListScheduler().schedule(dag, machine).schedule
                self.assertEqual(sched.validate(), [])
                self.assertTrue(sched.complete)
                self.assertEqual(sched.makespan, row["meta"]["makespan"])
                self.assertEqual(greedy.makespan, row["meta"]["baseline"])
                self.assertGreater(greedy.makespan, sched.makespan,
                                   "hard example must strictly beat greedy baseline")

    def test_same_seed_gives_the_same_example(self):
        """Collection must be deterministic for a fixed seed."""
        from vliw.core.hardness import harvest_one
        a = harvest_one((12, 16, 22, "e2k-v6-measured"))
        b = harvest_one((12, 16, 22, "e2k-v6-measured"))
        self.assertEqual(a, b)


class TestBenchDataFlag(unittest.TestCase):
    def test_data_flag_selects_the_eval_file(self):
        """`--bench` accepts a custom `--eval` dataset path without mistaking it for an adapter name."""
        from vliw.cli import _parse_learned
        self.assertEqual(_parse_learned([]).data, "eval_wide.jsonl")
        a = _parse_learned("--bench 30 --data eval_hard.jsonl".split())
        self.assertEqual(a.data, "eval_hard.jsonl")
        self.assertEqual(a.bench, 30)
        self.assertIsNone(a.name, "eval file path must not be parsed as adapter name")


if __name__ == "__main__":
    unittest.main()
