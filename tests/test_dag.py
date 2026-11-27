"""Dependency DAG and makespan lower bounds.

The core invariant here is a mathematical property, not specific numbers:
`lower_bound` must be a TRUE lower bound. If it ever exceeds an achievable
makespan, every scheduling diagnostic ("N cycles recoverable; beyond that is
the machine limit") loses credibility. We therefore verify it against actual
schedules across all built-in scenarios and random graphs.
"""

from __future__ import annotations

import unittest

from vliw.core.baseline import GreedyListScheduler
from vliw.core.dag import (
    SCENARIOS,
    DagBuilder,
    compute_metrics,
    get_scenario,
    random_dag,
)
from vliw.core.model import E2K_V6_MEASURED as M


class TestDagBasics(unittest.TestCase):
    def test_ids_are_sequential(self):
        b = DagBuilder("k", "t")
        self.assertEqual(b.op("ADD", "a"), 0)
        self.assertEqual(b.op("MUL", "m", 0), 1)
        d = b.build()
        self.assertEqual([i.id for i in d], [0, 1])
        self.assertEqual(len(d), 2)

    def test_preds_must_come_earlier(self):
        """Acyclicity is enforced by topological IDs; violations must fail immediately."""
        from vliw.core.dag import DAG, Instr
        with self.assertRaises(AssertionError):
            DAG("k", "t", "", [Instr(0, "n0", "ADD", (1,), "n0"),
                               Instr(1, "n1", "ADD", (), "n1")])

    def test_succs_mirror_preds(self):
        d = get_scenario("simple4")
        for ins in d:
            for p in ins.preds:
                self.assertIn(ins.id, d.succs[p])

    def test_op_counts(self):
        d = get_scenario("divpressure")
        self.assertEqual(d.op_counts()["DIV"], 4)


class TestMetrics(unittest.TestCase):
    def test_asap_respects_latency(self):
        b = DagBuilder("k", "t")
        m = b.op("MUL", "m")          # latency 4
        b.op("ADD", "a", m)
        met = compute_metrics(b.build(), M)
        self.assertEqual(met.asap, (0, 4))

    def test_height_is_remaining_critical_path(self):
        b = DagBuilder("k", "t")
        m = b.op("MUL", "m")
        b.op("ADD", "a", m)
        met = compute_metrics(b.build(), M)
        self.assertEqual(met.height, (5, 1))
        self.assertEqual(met.critical_path_bound, 5)

    def test_resource_bound_sees_the_divider(self):
        """Eight divisions on a single exclusive FU with 2-cycle occupancy are resource-bound."""
        b = DagBuilder("k", "t")
        for i in range(8):
            b.op("DIV", f"d{i}")
        met = compute_metrics(b.build(), M)
        self.assertEqual(met.binding, "resources")
        self.assertGreater(met.resource_bound, met.critical_path_bound)

    def test_lower_bound_is_really_a_lower_bound(self):
        """Across every scenario: lower_bound <= actual scheduled makespan."""
        for key, d in SCENARIOS.items():
            with self.subTest(scenario=key):
                met = compute_metrics(d, M)
                res = GreedyListScheduler().schedule(d, M)
                self.assertEqual(res.schedule.validate(), [])
                self.assertLessEqual(met.lower_bound, res.schedule.makespan)

    def test_lower_bound_holds_on_random_graphs(self):
        for seed in range(12):
            with self.subTest(seed=seed):
                d = random_dag(seed, n=18)
                met = compute_metrics(d, M)
                res = GreedyListScheduler().schedule(d, M)
                self.assertEqual(res.schedule.validate(), [])
                self.assertLessEqual(met.lower_bound, res.schedule.makespan)

    def test_binding_names_the_bigger_bound(self):
        for key, d in SCENARIOS.items():
            met = compute_metrics(d, M)
            with self.subTest(scenario=key):
                if met.critical_path_bound > met.resource_bound:
                    self.assertEqual(met.binding, "critical path")
                elif met.resource_bound > met.critical_path_bound:
                    self.assertEqual(met.binding, "resources")
                else:
                    self.assertEqual(met.binding, "both")


class TestScenarios(unittest.TestCase):
    def test_all_scenarios_schedulable_and_valid(self):
        for key, d in SCENARIOS.items():
            with self.subTest(scenario=key):
                res = GreedyListScheduler().schedule(d, M)
                self.assertTrue(res.schedule.complete)
                self.assertEqual(res.schedule.validate(), [])

    def test_scenarios_have_teaching_metadata(self):
        """Every built-in scenario must carry title, lesson, and family metadata."""
        for key, d in SCENARIOS.items():
            with self.subTest(scenario=key):
                self.assertTrue(d.title.strip())
                self.assertTrue(d.lesson.strip())
                self.assertTrue(d.family.strip())

    def test_unknown_scenario_exits_with_list(self):
        with self.assertRaises(SystemExit) as cm:
            get_scenario("no-such-scenario")
        self.assertIn("simple4", str(cm.exception))

    def test_randN_shortcut(self):
        self.assertEqual(len(get_scenario("rand5")), len(random_dag(5)))


class TestMeasuredClassScenarios(unittest.TestCase):
    """Scenarios exercising the e2k operation classes measured on 2026-08-30.

    Previously, floating-point, predication, and packed SIMD classes existed in
    the machine model but appeared in no built-in scenario.
    """

    NEW = ("twodividers", "packnarrow", "predchain")

    def test_they_exist_and_are_schedulable(self):
        from vliw.core import SCENARIOS, get_profile, get_scenario
        from vliw.core.baseline import GreedyListScheduler

        model = get_profile("e2k-v6-measured")
        for key in self.NEW:
            with self.subTest(scenario=key):
                self.assertIn(key, SCENARIOS)
                dag = get_scenario(key)
                res = GreedyListScheduler().schedule(dag, model)
                self.assertEqual(res.schedule.validate(), [],
                                 "scenario failed to schedule legally")

    def test_new_classes_are_actually_exercised(self):
        """Ensure built-in scenarios actually cover the newly measured op classes."""
        from vliw.core import SCENARIOS, get_scenario

        covered = set()
        for key in SCENARIOS:
            covered |= {i.op for i in get_scenario(key).instrs}
        for op in ("FDIV", "FADD", "FMUL", "PACK", "PACKLOG", "PRED",
                   "MERGE", "INSF", "COMBO"):
            with self.subTest(op_class=op):
                self.assertIn(op, covered, "op class does not appear in any scenario")

    def test_every_class_used_in_a_scenario_can_be_written(self):
        """Every non-memory op class used in a scenario must have a symbol in `_SYMBOL`.

        Without an entry in `_SYMBOL`, `DagBuilder.op()` raises KeyError. LOAD
        and STORE use dedicated syntax rather than infix operators.
        """
        from vliw.core import SCENARIOS, get_scenario
        from vliw.core.dag import _SYMBOL

        used = set()
        for key in SCENARIOS:
            used |= {i.op for i in get_scenario(key).instrs}
        for op in sorted(used - {"LOAD", "STORE"}):
            with self.subTest(op_class=op):
                self.assertIn(op, _SYMBOL)


class TestIntervalLowerBound(unittest.TestCase):
    """Interval resource lower bound: must NEVER overestimate the true optimum.

    The exact branch-and-bound oracle uses this lower bound as its iterative
    deepening starting point. Overestimating even once would cause the oracle to
    declare an achievable makespan infeasible and claim false optimality.
    """

    def setUp(self):
        from vliw.core import get_profile
        self.machine = get_profile("e2k-v6-measured")

    def test_never_exceeds_the_true_optimum(self):
        import random

        from vliw.core.dag import DAG, Instr, compute_metrics
        from vliw.core.oracle import OracleScheduler
        from tools.vliw_gen import PRESSURE_WEIGHTS, SHAPES, gen_graph

        rnd = random.Random(20260902)
        checked = 0
        for _ in range(40):
            raw = gen_graph(rnd, rnd.randint(6, 18), rnd.choice(SHAPES),
                            PRESSURE_WEIGHTS)
            dag = DAG("t", "", "", [Instr(x.id, f"n{x.id}", x.op, x.preds, f"n{x.id}")
                                    for x in raw])
            res = OracleScheduler(budget_s=10.0).schedule(dag, self.machine)
            if not res.optimal:
                continue          # optimum not proven — cannot compare
            checked += 1
            lb = compute_metrics(dag, self.machine).lower_bound
            self.assertLessEqual(
                lb, res.schedule.makespan,
                f"lower bound {lb} exceeds proven optimum {res.schedule.makespan}")
        self.assertGreater(checked, 20, "fixture: too few graphs reached proven optimality")

    def test_sees_contention_that_plain_division_misses(self):
        """Four ready DIVs on exclusive port ,5 (occupancy 2): naive total_occ/ports
        gives 8, whereas the interval bound must include the trailing latency of
        the final division (6 + 11 = 17 cycles)."""
        from vliw.core.dag import DAG, Instr, compute_metrics

        instrs = [Instr(i, f"d{i}", "DIV", (), f"d{i}") for i in range(4)]
        dag = DAG("divs", "", "", instrs)
        m = compute_metrics(dag, self.machine)
        # Four DIVs on one port: last issues no earlier than cycle 6, plus 11c latency = 17c.
        self.assertGreaterEqual(m.resource_bound, 17)
        self.assertGreaterEqual(m.lower_bound, 17)

    def test_degenerate_graphs_do_not_crash(self):
        from vliw.core.dag import DAG, Instr, compute_metrics

        self.assertEqual(compute_metrics(DAG("e", "", "", []), self.machine).lower_bound, 0)
        one = DAG("o", "", "", [Instr(0, "a", "ADD", (), "a")])
        self.assertEqual(compute_metrics(one, self.machine).lower_bound, 1)


if __name__ == "__main__":
    unittest.main()
