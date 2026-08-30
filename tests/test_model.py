"""Инварианты модели машины.

Профиль e2k-v6-measured — источник истины для генератора датасета, валидатора
и обучения. Здесь закреплено то, что ломать нельзя молча: матрица портов,
единственность делителя и ОТСУТСТВИЕ монополии умножителя.

Последнее — не придирка. Первая версия модели считала умножитель монопольным
(порт `,0`, держит 8 тактов), из этого следовали все выводы демо, и это
оказалось неверно. Тест стоит здесь, чтобы опровергнутая версия не вернулась
обратно тихой правкой.

Матрицу против настоящего ассемблера переснимает tools/probe_matrix.py —
там проверка железа, здесь проверка кода.
"""

from __future__ import annotations

import unittest

from vliw.core.model import (
    DEFAULT_PROFILE,
    E2K_V6_FIRSTPROBE,
    E2K_V6_MEASURED,
    PROFILES,
    capability_matrix,
    describe_model,
    get_profile,
)

M = E2K_V6_MEASURED


class TestMeasuredProfile(unittest.TestCase):
    def test_width_six(self):
        self.assertEqual(M.width, 6)

    def test_default_profile_is_measured(self):
        self.assertEqual(DEFAULT_PROFILE, M.name)
        self.assertIs(get_profile(DEFAULT_PROFILE), M)

    def test_port_matrix(self):
        self.assertEqual(M.channels_for("ADD"), (0, 1, 2, 3, 4, 5))
        self.assertEqual(M.channels_for("SUB"), (0, 1, 2, 3, 4, 5))
        self.assertEqual(M.channels_for("AND"), (0, 1, 2, 3, 4, 5))
        self.assertEqual(M.channels_for("SHL"), (0, 1, 2, 3, 4, 5))
        self.assertEqual(M.channels_for("MUL"), (0, 1, 3, 4))
        self.assertEqual(M.channels_for("DIV"), (5,))
        self.assertEqual(M.channels_for("LOAD"), (0, 2, 3, 5))
        self.assertEqual(M.channels_for("STORE"), (2, 5))

    def test_latency_and_occupancy(self):
        self.assertEqual(M.latency("MUL"), 4)
        self.assertEqual(M.latency("DIV"), 11)
        self.assertEqual(M.latency("LOAD"), 5)
        for op in ("ADD", "SUB", "AND", "SHL", "STORE"):
            self.assertEqual(M.latency(op), 1, op)
        # Делители — единственные устройства, которые держат порт дольше такта.
        # С 30.08.2026 их два: целочисленный и с плавающей точкой, и оба
        # сидят на одном и том же ,5 — измерено потоком независимых делений.
        self.assertEqual(M.occupancy("DIV"), 2)
        self.assertEqual(M.occupancy("FDIV"), 2)
        for op in M.ops:
            if op not in ("DIV", "FDIV"):
                self.assertEqual(M.occupancy(op), 1, op)

    def test_only_the_dividers_monopolise_a_port(self):
        """Порт ,5 — единственный монопольный, и держат его оба делителя.

        Раньше здесь стояло `{5: ["DIV"]}`. Деление с плавающей точкой,
        добавленное измерением, встало на тот же канал: ассемблер отвергает
        `fdivd` во всех остальных («cannot be encoded in ALCn»). То есть
        монополия не размылась, а стала плотнее — за один порт борются два
        разных устройства.
        """
        self.assertEqual(set(M.sole_host_ops()), {5})
        self.assertEqual(set(M.sole_host_ops()[5]), {"DIV", "FDIV"})

    def test_multiplier_is_not_a_monopoly(self):
        """Опровергнутая версия модели не должна вернуться."""
        self.assertGreater(len(M.channels_for("MUL")), 1)
        self.assertEqual(M.occupancy("MUL"), 1)
        self.assertNotIn("MUL", M.sole_host_ops().get(0, []))

    def test_every_op_has_a_host(self):
        for op in M.ops:
            self.assertTrue(M.channels_for(op), f"{op} негде исполнить")

    def test_not_uniform(self):
        """Если бы каналы были равноправны, планировать было бы нечего."""
        self.assertFalse(M.uniform_channels())
        self.assertTrue(M.has_blocking_ops())

    def test_unknown_op_raises_with_hint(self):
        with self.assertRaises(KeyError) as cm:
            M.op("FMA")
        self.assertIn("FMA", str(cm.exception))


class TestWithWidth(unittest.TestCase):
    """Сужение машины не должно делать граф непланируемым.

    У записи всего два порта, у деления один. При width 1-2 они легко теряют
    всех носителей — в модели на этот случай стоит доводка вручную, и она
    обязана срабатывать на КАЖДОЙ ширине, а не «обычно».
    """

    def test_every_op_keeps_a_host_at_any_width(self):
        for w in range(1, 9):
            m = M.with_width(w)
            self.assertEqual(m.width, w)
            for op in m.ops:
                self.assertTrue(m.channels_for(op),
                                f"ширина {w}: {op} негде исполнить")

    def test_channels_are_renumbered_contiguously(self):
        for w in (1, 3, 6, 8):
            m = M.with_width(w)
            self.assertEqual([p.index for p in m.ports], list(range(w)))

    def test_same_width_returns_same_object(self):
        self.assertIs(M.with_width(M.width), M)


class TestProfiles(unittest.TestCase):
    def test_firstprobe_kept_as_counterexample(self):
        """Опровергнутый профиль оставлен намеренно — он нужен для контраста."""
        self.assertIn(E2K_V6_FIRSTPROBE.name, PROFILES)
        self.assertEqual(E2K_V6_FIRSTPROBE.channels_for("MUL"), (0,))
        self.assertEqual(E2K_V6_FIRSTPROBE.occupancy("MUL"), 8)
        # И он не должен подменять собой измеренный.
        self.assertNotEqual(E2K_V6_FIRSTPROBE.name, DEFAULT_PROFILE)

    def test_unknown_profile_exits_with_list(self):
        with self.assertRaises(SystemExit) as cm:
            get_profile("e2k-v7-imaginary")
        self.assertIn(M.name, str(cm.exception))

    def test_describe_and_matrix_shapes(self):
        rows = describe_model(M)
        self.assertTrue(all(len(r) == 3 for r in rows))
        ops, grid = capability_matrix(M)
        self.assertEqual(len(grid), M.width)
        self.assertTrue(all(len(row) == len(ops) for row in grid))
        # Матрица и channels_for обязаны рассказывать одно и то же.
        for pi, row in enumerate(grid):
            for oi, can in enumerate(row):
                self.assertEqual(can, pi in M.channels_for(ops[oi]))


if __name__ == "__main__":
    unittest.main()
