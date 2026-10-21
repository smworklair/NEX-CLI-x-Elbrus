"""Быстрый движок списочного планирования == baseline.list_schedule, поразрядно.

Сравнивается всё расписание целиком: для каждой инструкции тот же такт и канал,
тот же порядок выдачи и тот же makespan. Приоритеты берутся с множеством ничьих
(они проверяют разрешение ничьих по номеру), держки — случайные, машины —
все профили, разной ширины и с искажёнными латентностями.
"""

import random
import unittest
from dataclasses import replace

from vliw.core.baseline import list_schedule
from vliw.core.dag import DAG, DagBuilder, SCENARIOS, compute_metrics, random_dag
from vliw.core.fastlist import ListPlan, list_schedule_fast
from vliw.core.model import PROFILES, Port, get_profile


def _tweaked(model, kind):
    ops = dict(model.ops)
    for name, oc in list(ops.items()):
        if kind == "lat0" and oc.latency == 1:
            ops[name] = replace(oc, latency=0)
        elif kind == "occ" and (oc.occupancy > 1 or oc.latency >= 4):
            ops[name] = replace(oc, occupancy=max(oc.occupancy, 5))
        elif kind == "mixed":
            ops[name] = replace(oc, latency=(oc.latency * 3) % 7,
                                occupancy=1 + (oc.latency % 3))
    return replace(model, ops=ops, name=f"{model.name}/{kind}")


def _priorities(dag, model, rnd):
    n = len(dag)
    h = [float(v) for v in compute_metrics(dag, model).height]
    yield h
    yield [float(rnd.randint(0, 3)) for _ in range(n)]      # много ничьих
    yield [1.0] * n                                          # одни ничьи
    yield [rnd.random() for _ in range(n)]
    yield [float(-i) for i in range(n)]


def _defers(dag, ms, rnd):
    n = len(dag)
    yield None
    if n:
        yield {rnd.randrange(n): rnd.randint(1, max(2, ms)) for _ in range(max(1, n // 5))}
        yield {i: rnd.randint(0, max(2, ms)) for i in range(n) if rnd.random() < 0.5}
        yield {rnd.randrange(n): ms + rnd.randint(1, 40)}      # далёкая держка: прыжок по тактам


class TestFastList(unittest.TestCase):
    def assertSame(self, dag, model, prio, defer, plan=None):
        ref, _ = list_schedule(dag, model, priority=prio, defer_until=defer)
        plan = plan or ListPlan(dag, model)
        raw = plan.run(prio, defer)
        new = plan.to_schedule(raw)
        self.assertEqual(ref.placements, new.placements)
        self.assertEqual(list(ref.placements), list(new.placements), "порядок выдачи")
        self.assertEqual(ref.makespan, raw.makespan)
        self.assertEqual(new.makespan, raw.makespan)

    def check_graph(self, dag, model, rnd):
        plan = ListPlan(dag, model)
        ms = max(1, compute_metrics(dag, model).lower_bound * 2)
        for prio in _priorities(dag, model, rnd):
            for defer in _defers(dag, ms, rnd):
                self.assertSame(dag, model, prio, defer, plan)

    def test_scenarios_all_profiles(self):
        rnd = random.Random(1)
        for pname in PROFILES:
            model = get_profile(pname)
            for key, dag in SCENARIOS.items():
                with self.subTest(profile=pname, scenario=key):
                    self.check_graph(dag, model, rnd)

    def test_random_graphs_various_widths(self):
        rnd = random.Random(2)
        base = get_profile("e2k-v6-measured")
        for seed in range(25):
            dag = random_dag(seed, n=5 + seed * 3, max_preds=1 + seed % 3, reach=4 + seed % 9)
            for w in (1, 2, 3, 4, 8):
                with self.subTest(seed=seed, width=w):
                    self.check_graph(dag, base.with_width(w), rnd)

    def test_distorted_machines(self):
        rnd = random.Random(3)
        for kind in ("lat0", "occ", "mixed"):
            for base in (get_profile("e2k-v6-measured"), get_profile("naive_homogeneous")):
                model = _tweaked(base, kind)
                for seed in (3, 11, 17):
                    with self.subTest(kind=kind, base=base.name, seed=seed):
                        self.check_graph(random_dag(seed, n=40), model, rnd)

    def test_alternating_models_do_not_mix_cached_tables(self):
        """Таблица каналов кэшируется по модели: чередование моделей не должно
        подсовывать чужую таблицу."""
        rnd = random.Random(4)
        dag = random_dag(5, n=30)
        models = [get_profile("e2k-v6-measured"), get_profile("naive_homogeneous"),
                  get_profile("e2k-v6-measured").with_width(2)]
        for _ in range(3):
            for m in models:
                self.check_graph(dag, m, rnd)

    def test_empty_and_single(self):
        model = get_profile("e2k-v6-measured")
        empty = DAG("empty", "e", "", [])
        raw = ListPlan(empty, model).run([])
        self.assertEqual((raw.cycle, raw.order, raw.makespan), ([], [], 0))
        b = DagBuilder("one", "one")
        b.op("DIV", "d")
        one = b.build()
        self.assertSame(one, model, [1.0], None)
        self.assertSame(one, model, [1.0], {0: 7})

    def test_duplicate_predecessor(self):
        """Операнд читается дважды (preds=(a, a)) — счётчик готовности не ломается."""
        model = get_profile("e2k-v6-measured")
        b = DagBuilder("dup", "dup")
        a = b.op("LOAD", "a")
        c = b.op("ADD", "c", a, a)
        b.op("STORE", "s", c)
        dag = b.build()
        self.assertSame(dag, model, [3.0, 2.0, 1.0], None)

    def test_schedule_is_legal(self):
        model = get_profile("e2k-v6-measured")
        rnd = random.Random(5)
        for seed in range(10):
            dag = random_dag(seed, n=60)
            plan = ListPlan(dag, model)
            for prio in _priorities(dag, model, rnd):
                s = plan.to_schedule(plan.run(prio))
                self.assertTrue(s.complete)
                self.assertEqual(s.validate(), [])

    def test_unexecutable_op_raises_like_reference(self):
        """Операция без исполнимого порта: как и у оригинала — RuntimeError, а не
        зависание. (Оригинал доходит до этого после 100000 пустых тактов, здесь
        — сразу.)"""
        model = get_profile("e2k-v6-measured")
        ports = tuple(Port(p.index, p.label, p.ops - {"DIV"}) for p in model.ports)
        broken = replace(model, ports=ports, name="no-div")
        b = DagBuilder("nd", "nd")
        b.op("DIV", "d")
        dag = b.build()
        with self.assertRaises(RuntimeError):
            ListPlan(dag, broken).run([1.0])

    def test_drop_in_wrapper(self):
        model = get_profile("e2k-v6-measured")
        dag = random_dag(7, n=30)
        prio = [float(v) for v in compute_metrics(dag, model).height]
        ref, _ = list_schedule(dag, model, priority=prio)
        new, trace = list_schedule_fast(dag, model, prio)
        self.assertEqual(ref.placements, new.placements)
        self.assertEqual(trace, [])


if __name__ == "__main__":
    unittest.main()
