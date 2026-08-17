"""Проверка Schedule.validate() — по одному тесту на класс нарушения.

`validate()` — то, чем меряется вся обученная модель: любая ошибка в нём
превращается либо в принятое незаконное расписание, либо в отвергнутое
законное. Поэтому каждый вид нарушения проверяется отдельно, и отдельно
проверяется, что законное расписание проходит молча.
"""

from __future__ import annotations

import unittest

from vliw.core.dag import DAG, Instr
from vliw.core.model import E2K_V6_MEASURED as M
from vliw.core.schedule import ChannelState, Schedule


def dag(*specs: tuple[str, tuple[int, ...]]) -> DAG:
    """Мини-граф: dag(("ADD", ()), ("MUL", (0,)))."""
    return DAG("t", "t", "", [
        Instr(i, f"n{i}", op, preds, f"n{i}")
        for i, (op, preds) in enumerate(specs)
    ])


def sched(d: DAG, *places: tuple[int, int, int]) -> Schedule:
    s = Schedule(d, M)
    for instr, cycle, ch in places:
        s.place(instr, cycle, ch)
    return s


class TestLegalSchedule(unittest.TestCase):
    def test_empty_graph_is_complete(self):
        s = Schedule(dag(), M)
        self.assertTrue(s.complete)
        self.assertEqual(s.validate(), [])
        self.assertEqual(s.makespan, 0)

    def test_simple_legal(self):
        d = dag(("ADD", ()), ("MUL", (0,)))
        s = sched(d, (0, 0, 0), (1, 1, 1))
        self.assertEqual(s.validate(), [])

    def test_two_ops_same_cycle_different_channels(self):
        d = dag(("ADD", ()), ("ADD", ()))
        self.assertEqual(sched(d, (0, 0, 0), (1, 0, 1)).validate(), [])

    def test_full_width_bundle_is_legal(self):
        d = dag(*[("ADD", ())] * 6)
        s = sched(d, *[(i, 0, i) for i in range(6)])
        self.assertEqual(s.validate(), [])


class TestViolations(unittest.TestCase):
    def test_incomplete_reports_missing(self):
        d = dag(("ADD", ()), ("ADD", ()))
        errs = sched(d, (0, 0, 0)).validate()
        self.assertEqual(len(errs), 1)
        self.assertIn("не размещены", errs[0])
        self.assertIn("[1]", errs[0])

    def test_dependency_too_early(self):
        """MUL латентности 4: потребитель не может выйти раньше такта 4."""
        d = dag(("MUL", ()), ("ADD", (0,)))
        errs = sched(d, (0, 0, 0), (1, 3, 1)).validate()
        self.assertTrue(any("готов только к такту 4" in e for e in errs), errs)
        # Ровно на границе — законно.
        self.assertEqual(sched(d, (0, 0, 0), (1, 4, 1)).validate(), [])

    def test_channel_cannot_execute_op(self):
        d = dag(("DIV", ()))
        errs = sched(d, (0, 0, 0)).validate()
        self.assertTrue(any("не исполняет" in e for e in errs), errs)
        self.assertEqual(sched(d, (0, 0, 5)).validate(), [])

    def test_channel_conflict_same_cycle(self):
        d = dag(("ADD", ()), ("ADD", ()))
        errs = sched(d, (0, 0, 1), (1, 0, 1)).validate()
        self.assertTrue(any("конфликт на канале 1" in e for e in errs), errs)

    def test_occupancy_blocks_next_cycle(self):
        """Деление держит порт 2 такта: второе в такте 1 — конфликт, в 2 — нет."""
        d = dag(("DIV", ()), ("DIV", ()))
        errs = sched(d, (0, 0, 5), (1, 1, 5)).validate()
        self.assertTrue(any("конфликт на канале 5 в такте 1" in e for e in errs), errs)
        self.assertEqual(sched(d, (0, 0, 5), (1, 2, 5)).validate(), [])

    def test_width_overflow(self):
        """Семь операций в одном такте при ширине 6.

        Ловится отдельно от конфликта каналов: каналы у всех разные (один
        повторяется), но широкая команда столько слотов не имеет.
        """
        d = dag(*[("ADD", ())] * 7)
        places = [(i, 0, i) for i in range(6)] + [(6, 0, 0)]
        errs = sched(d, *places).validate()
        self.assertTrue(any("при ширине 6" in e for e in errs), errs)


class TestMetrics(unittest.TestCase):
    def test_makespan_counts_readiness_not_issue(self):
        """Иначе деление в последней команде выглядело бы бесплатным."""
        d = dag(("DIV", ()))
        s = sched(d, (0, 0, 5))
        self.assertEqual(s.makespan, 11)
        self.assertEqual(s.span_cycles, 1)

    def test_ready_at_uses_latency(self):
        d = dag(("LOAD", ()))
        self.assertEqual(sched(d, (0, 3, 0)).ready_at(0), 8)

    def test_bundle_count_counts_nonempty_cycles(self):
        d = dag(("ADD", ()), ("ADD", ()), ("ADD", ()))
        s = sched(d, (0, 0, 0), (1, 0, 1), (2, 5, 0))
        self.assertEqual(s.bundle_count, 2)
        self.assertEqual(s.span_cycles, 6)

    def test_slot_utilization(self):
        d = dag(("ADD", ()), ("ADD", ()))
        s = sched(d, (0, 0, 0), (1, 0, 1))
        self.assertAlmostEqual(s.slot_utilization, 2 / 6)

    def test_busy_map_marks_occupancy_tail(self):
        d = dag(("DIV", ()))
        m = sched(d, (0, 4, 5)).busy_map()
        self.assertEqual(m[(4, 5)], (0, True))    # такт выдачи
        self.assertEqual(m[(5, 5)], (0, False))   # продолжение занятия
        self.assertNotIn((6, 5), m)


class TestChannelState(unittest.TestCase):
    def test_occupy_and_free(self):
        st = ChannelState(6)
        self.assertEqual(st.free_channels(0, (0, 1, 5)), [0, 1, 5])
        st.occupy(5, 0, 2)
        self.assertEqual(st.free_channels(0, (5,)), [])
        self.assertEqual(st.free_channels(1, (5,)), [])
        self.assertEqual(st.free_channels(2, (5,)), [5])

    def test_copy_is_independent(self):
        st = ChannelState(6)
        c = st.copy()
        c.occupy(0, 0, 5)
        self.assertEqual(st.free_channels(0, (0,)), [0])


if __name__ == "__main__":
    unittest.main()
