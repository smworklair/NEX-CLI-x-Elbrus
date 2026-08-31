"""SEED: подсказка точному поиску не имеет права менять его ответ.

Главное свойство всей конструкции — модель здесь НЕ МОЖЕТ сделать хуже.
Подсказка входит в поиск двумя способами: верхней границей (только законное
полное расписание строго короче baseline) и вектором приоритетов для
портфельного движка. Ни один вывод «доказанно недостижимо» от неё не
зависит.

Регрессия здесь была бы самой опасной из возможных в проекте: оракул —
источник истины, против которого меряется всё остальное. Если подсказка
сможет подсунуть ему более короткий, но незаконный ответ, испортятся сразу
все метрики, и заметить это будет неоткуда.
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
        """Незаконное расписание верхней границей стать не может.

        Иначе оракул «докажет» недостижимое: объявит оптимумом длину,
        которой не соответствует ни одно исполнимое расписание.
        """
        dag = get_scenario("slotclash")
        bad = Schedule(dag, self.machine)
        for i in range(len(dag)):
            bad.place(i, 0, 0)              # всё в один такт на один канал
        self.assertTrue(bad.validate(), "фикстура обязана быть незаконной")

        plain = OracleScheduler().schedule(dag, self.machine)
        hinted = OracleScheduler(
            hint=Hint(schedule=bad, source="мусор")
        ).schedule(dag, self.machine)
        self.assertEqual(hinted.schedule.makespan, plain.schedule.makespan)
        self.assertFalse(hinted.search_stats["hint_gave_upper_bound"])

    def test_incomplete_hint_is_ignored(self):
        """Неполное расписание короче любого полного — и потому опасно."""
        dag = get_scenario("slotclash")
        part = Schedule(dag, self.machine)
        part.place(0, 0, 0)
        hinted = OracleScheduler(
            hint=Hint(schedule=part, source="огрызок")
        ).schedule(dag, self.machine)
        self.assertFalse(hinted.search_stats["hint_gave_upper_bound"])
        self.assertEqual(hinted.schedule.validate(), [])


class TestHintIsCredited(unittest.TestCase):
    def test_upper_bound_from_hint_is_recorded(self):
        """Чья заслуга — должно быть видно в отчёте, а не растворяться."""
        dag = get_scenario("slotclash")
        machine = get_profile("e2k-v6-measured")
        opt = OracleScheduler().schedule(dag, machine).schedule
        answer = {p.instr: (p.cycle, 0) for p in opt.placements.values()}

        res = OracleScheduler(
            hint=hint_from_answer(dag, machine, answer, source="модель")
        ).schedule(dag, machine)

        self.assertTrue(res.search_stats["hint_gave_upper_bound"])
        self.assertEqual(res.search_stats["hint_source"], "модель")
        self.assertEqual(res.search_stats["baseline_upper_bound"], 23,
                         "baseline в метриках обязан остаться baseline'ом")
        self.assertEqual(res.search_stats["nodes"], 0,
                         "подсказка на нижней границе — доказательство без перебора")
        self.assertTrue(any("модель" in n for n in res.notes))


if __name__ == "__main__":
    unittest.main()
