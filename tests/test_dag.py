"""Граф зависимостей и нижние границы makespan.

Главное здесь — свойство, а не конкретные числа: `lower_bound` обязана быть
НАСТОЯЩЕЙ нижней границей. Если она хоть раз окажется выше достижимого
makespan, все выводы демо («столько-то тактов можно отыграть, дальше предел
машины») перестанут значить что-либо. Поэтому граница проверяется против
реально построенного расписания на всех встроенных сценариях.
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
        """Ацикличность держится нумерацией; нарушение обязано падать сразу."""
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
        m = b.op("MUL", "m")          # латентность 4
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
        """Восемь делений на один порт с темпом 2 такта — упор в ресурс."""
        b = DagBuilder("k", "t")
        for i in range(8):
            b.op("DIV", f"d{i}")
        met = compute_metrics(b.build(), M)
        self.assertEqual(met.binding, "ресурсы")
        self.assertGreater(met.resource_bound, met.critical_path_bound)

    def test_lower_bound_is_really_a_lower_bound(self):
        """На каждом сценарии: граница <= то, что реально построено."""
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
                    self.assertEqual(met.binding, "критический путь")
                elif met.resource_bound > met.critical_path_bound:
                    self.assertEqual(met.binding, "ресурсы")
                else:
                    self.assertEqual(met.binding, "и то, и другое")


class TestScenarios(unittest.TestCase):
    def test_all_scenarios_schedulable_and_valid(self):
        for key, d in SCENARIOS.items():
            with self.subTest(scenario=key):
                res = GreedyListScheduler().schedule(d, M)
                self.assertTrue(res.schedule.complete)
                self.assertEqual(res.schedule.validate(), [])

    def test_scenarios_have_teaching_metadata(self):
        """Сценарий без урока — просто граф; в этом демо он бесполезен."""
        for key, d in SCENARIOS.items():
            with self.subTest(scenario=key):
                self.assertTrue(d.title.strip())
                self.assertTrue(d.lesson.strip())
                self.assertTrue(d.family.strip())

    def test_unknown_scenario_exits_with_list(self):
        with self.assertRaises(SystemExit) as cm:
            get_scenario("нет-такого")
        self.assertIn("simple4", str(cm.exception))

    def test_randN_shortcut(self):
        self.assertEqual(len(get_scenario("rand5")), len(random_dag(5)))


if __name__ == "__main__":
    unittest.main()
