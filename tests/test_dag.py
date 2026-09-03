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
class TestMeasuredClassScenarios(unittest.TestCase):
    """Сценарии на классы, измеренные 30.08.2026.

    До них модель знала плавающую точку, предикаты и упакованные операции,
    но показать их было нечем: одиннадцать классов из девятнадцати не
    встречались ни в одном сценарии. Увидеть их можно было только загрузив
    настоящий `.s`.
    """

    NEW = ("twodividers", "packnarrow", "predchain")

    def test_they_exist_and_are_schedulable(self):
        from vliw.core import SCENARIOS, get_profile, get_scenario
        from vliw.core.baseline import GreedyListScheduler

        model = get_profile("e2k-v6-measured")
        for key in self.NEW:
            with self.subTest(сценарий=key):
                self.assertIn(key, SCENARIOS)
                dag = get_scenario(key)
                res = GreedyListScheduler().schedule(dag, model)
                self.assertEqual(res.schedule.validate(), [],
                                 "сценарий не раскладывается законно")

    def test_new_classes_are_actually_exercised(self):
        """Смысл сценариев — покрыть классы, которых раньше не было нигде."""
        from vliw.core import SCENARIOS, get_scenario

        covered = set()
        for key in SCENARIOS:
            covered |= {i.op for i in get_scenario(key).instrs}
        for op in ("FDIV", "FADD", "FMUL", "PACK", "PACKLOG", "PRED",
                   "MERGE", "INSF", "COMBO"):
            with self.subTest(класс=op):
                self.assertIn(op, covered, "класс не встречается ни в одном "
                                           "сценарии — показать его нечем")

    def test_every_class_used_in_a_scenario_can_be_written(self):
        """Класс, встречающийся в сценарии, должен иметь знак для записи.

        Без него `DagBuilder.op()` падает KeyError при первой же попытке
        собрать граф — именно так и обнаружилось при добавлении FDIV.
        Проверяются классы, реально используемые в сценариях: LOAD и STORE
        знака не имеют и не должны — они пишутся не как «a = b ⊕ c», а
        отдельной формой, и в _SYMBOL их не было никогда.
        """
        from vliw.core import SCENARIOS, get_scenario
        from vliw.core.dag import _SYMBOL

        used = set()
        for key in SCENARIOS:
            used |= {i.op for i in get_scenario(key).instrs}
        for op in sorted(used - {"LOAD", "STORE"}):
            with self.subTest(класс=op):
                self.assertIn(op, _SYMBOL)


class TestIntervalLowerBound(unittest.TestCase):
    """Интервальная нижняя граница: главное — она не имеет права соврать вверх.

    Граница используется точным поиском как точка старта углубления. Если она
    хоть раз превысит истинный оптимум, оракул объявит недостижимым то, что
    достижимо, — и соврёт с самым уверенным лицом, потому что «доказано».
    Поэтому здесь свойство проверяется перебором на случайных графах, а не
    на паре заготовленных примеров.

    Второе, что стережётся, — что она реально сильнее прежней. Прежняя
    (суммарная занятость / число каналов) не выигрывала у критического пути
    ни на одном из 300 графов трудного эвала, то есть была мёртвым кодом.
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
                continue          # оптимум не доказан — сравнивать не с чем
            checked += 1
            lb = compute_metrics(dag, self.machine).lower_bound
            self.assertLessEqual(
                lb, res.schedule.makespan,
                f"граница {lb} выше доказанного оптимума {res.schedule.makespan}")
        self.assertGreater(checked, 20, "фикстура: оптимум доказан слишком редко")

    def test_sees_contention_that_plain_division_misses(self):
        """Граф, где делители конфликтуют во времени, а не просто «их много».

        Четыре деления, все готовы сразу, все обязаны пройти через
        единственный канал `,5` с занятием 2 такта. Деление в столбик даёт
        4*2/1 = 8; интервальная граница обязана учесть ещё и латентность
        деления, стоящую после последнего из них.
        """
        from vliw.core.dag import DAG, Instr, compute_metrics

        instrs = [Instr(i, f"d{i}", "DIV", (), f"d{i}") for i in range(4)]
        dag = DAG("divs", "", "", instrs)
        m = compute_metrics(dag, self.machine)
        # Четыре деления на одном канале: последнее выдаётся не раньше такта 6,
        # плюс его латентность 11 — расписание не короче 17 тактов.
        self.assertGreaterEqual(m.resource_bound, 17)
        self.assertGreaterEqual(m.lower_bound, 17)

    def test_degenerate_graphs_do_not_crash(self):
        from vliw.core.dag import DAG, Instr, compute_metrics

        self.assertEqual(compute_metrics(DAG("e", "", "", []), self.machine).lower_bound, 0)
        one = DAG("o", "", "", [Instr(0, "a", "ADD", (), "a")])
        self.assertEqual(compute_metrics(one, self.machine).lower_bound, 1)


if __name__ == "__main__":
    unittest.main()
