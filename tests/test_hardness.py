"""Трудность графа: есть ли что выигрывать у жадной эвристики.

Зачем этот тест существует. Замер `docs/CAB.md` показал, что на обеих
выборках проекта baseline стоит в доказанном оптимуме почти везде — то есть
данные, на которых сравнивалась обученная модель, не содержали задачи. Чтобы
это больше не проходило незамеченным, «есть ли зазор» стало измеримым
свойством, и здесь стережётся его смысл.

Главное, что тут закреплено, — осторожность в одну сторону: граф, на котором
оптимум НЕ доказан за бюджет, трудным не считается. Иначе в обучающую
выборку попадёт эталон, который сам может быть хуже оптимального, и вся
метрика «разрыв до оптимума» перестанет что-либо означать.
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
        """Сценарий-ловушка: монопольный порт занят менее срочной операцией."""
        h = measure(get_scenario("slotclash"), self.machine)
        self.assertTrue(h.proven)
        self.assertEqual(h.gap, 1)
        self.assertTrue(h.hard)

    def test_easy_scenario_has_none(self):
        """На простом графе эвристика уже оптимальна — учить нечему."""
        h = measure(get_scenario("simple4"), self.machine)
        self.assertTrue(h.proven)
        self.assertEqual(h.gap, 0)
        self.assertFalse(h.hard)

    def test_schedule_is_the_optimum_and_is_legal(self):
        """Расписание из `measure` — готовый эталон, а не черновик."""
        dag = get_scenario("slotclash")
        h = measure(dag, self.machine)
        self.assertEqual(h.schedule.validate(), [])
        self.assertTrue(h.schedule.complete)
        self.assertEqual(h.schedule.makespan, h.optimum)


class TestUnprovenIsNotHard(unittest.TestCase):
    def test_gap_without_proof_does_not_count(self):
        """Зазор при недоказанном оптимуме — догадка, а не задача.

        Без этого правила в выборку попадёт эталон, который сам может быть
        хуже оптимального, и «разрыв до оптимума» перестанет что-то значить.
        """
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
        """Смесь передаётся аргументом и не течёт в модульное состояние.

        Раньше веса жили только модульной переменной; подмешать свои можно
        было лишь присваиванием в чужой модуль — то есть оставив состояние
        жить после вызова.
        """
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
        self.assertEqual(OP_WEIGHTS["DIV"], 3, "модульные веса не тронуты")


if __name__ == "__main__":
    unittest.main()


class TestHarvestWorker(unittest.TestCase):
    """Сборщик трудных примеров: то, что он вернул, обязано быть эталоном.

    Проверяется не «работает ли функция», а свойство её выхода: расписание
    законно, полно, равно записанному в `meta` оптимуму и СТРОГО короче
    жадного. Пример, у которого это не так, отравляет обучение молча —
    метрика «разрыв до оптимума» станет считаться от неверного эталона.
    """

    def test_returned_rows_are_valid_hard_examples(self):
        from training.encode import build_schedule, decode_completion
        from vliw.core.baseline import GreedyListScheduler
        from vliw.core.dag import DAG
        from vliw.core.hardness import harvest_one
        from vliw.learned.bench import _parse_graph

        machine = get_profile("e2k-v6-measured")
        rows = [harvest_one((seed, 16, 22, "e2k-v6-measured")) for seed in range(30)]
        found = [r for r in rows if r is not None]
        self.assertTrue(found, "на 30 семенах не нашлось ни одного трудного графа")

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
                                   "трудный пример обязан быть короче жадного")

    def test_same_seed_gives_the_same_example(self):
        """Иначе выборку нельзя воспроизвести, а `meta.seed` — украшение."""
        from vliw.core.hardness import harvest_one
        a = harvest_one((12, 16, 22, "e2k-v6-measured"))
        b = harvest_one((12, 16, 22, "e2k-v6-measured"))
        self.assertEqual(a, b)


class TestBenchDataFlag(unittest.TestCase):
    def test_data_flag_selects_the_eval_file(self):
        """`--bench` умеет считать не только по `eval_wide.jsonl`.

        Пока файл был зашит в код, замер шёл по выборке, где жадная
        эвристика оптимальна на 298 графах из 300 — то есть сравнивать было
        не с чем (docs/CAB.md).
        """
        from vliw.cli import _parse_learned
        self.assertEqual(_parse_learned([]).data, "eval_wide.jsonl")
        a = _parse_learned("--bench 30 --data eval_hard.jsonl".split())
        self.assertEqual(a.data, "eval_hard.jsonl")
        self.assertEqual(a.bench, 30)
        self.assertIsNone(a.name, "имя файла не должно уехать в имя адаптера")
