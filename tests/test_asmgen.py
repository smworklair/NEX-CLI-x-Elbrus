"""Генератор ассемблера: он не имеет права выдать незаконный код.

Весь смысл генератора в одном: каналы он берёт из модели машины, а не из
головы, поэтому `muls,2` (где умножение не исполняется) получиться не может
в принципе. Если это сломается, инструмент начнёт выдавать код, который
ассемблер отвергнет, — и станет тратить время инженера вместо того, чтобы
его экономить, то есть будет делать ровно противоположное задуманному.

Проверка идёт двумя слоями. Здесь — против модели, быстро и везде. В
`tools/probe_matrix.py` — против настоящего ассемблера e2k, но только там,
где установлен тулчейн.
"""

from __future__ import annotations

import unittest

from vliw.core import asmgen
from vliw.core import get_profile
from vliw.core.asm_parser import parse_asm


class TestOnlyLegalChannels(unittest.TestCase):
    def setUp(self):
        self.machine = get_profile("e2k-v6-measured")

    def _channels_used(self, text: str) -> dict[str, set[int]]:
        """Какие каналы реально встретились у каждого класса операций."""
        out: dict[str, set[int]] = {}
        for op in parse_asm(text).ops:
            if op.channel is not None:
                out.setdefault(op.op, set()).add(op.channel)
        return out

    def test_generated_channels_are_legal_for_every_class(self):
        """Главный сторож: ни одной операции в чужом канале."""
        for name in asmgen.known_names():
            for packed in (False, True):
                text = asmgen.independent(self.machine, name, 8, packed=packed)
                for op, channels in self._channels_used(text).items():
                    legal = set(self.machine.channels_for(op))
                    with self.subTest(op=name, packed=packed):
                        self.assertTrue(
                            channels <= legal,
                            f"{op} выдан в каналы {sorted(channels - legal)}, "
                            f"а исполним только в {sorted(legal)}")

    def test_chain_channels_are_legal_too(self):
        for name in ("MUL", "DIV", "FMUL", "ADD"):
            text = asmgen.chain(self.machine, name, 5)
            for op, channels in self._channels_used(text).items():
                with self.subTest(op=name):
                    self.assertTrue(channels <= set(self.machine.channels_for(op)))

    def test_nothing_unknown_gets_generated(self):
        """Сгенерированное обязано разбираться СВОИМ же парсером.

        UNKNOWN здесь означал бы, что генератор пишет мнемонику, которой нет
        в разметке, — и весь дальнейший разбор поедет на заглушке.
        """
        for text in (asmgen.independent(self.machine, "MUL", 6),
                     asmgen.chain(self.machine, "FMUL", 4),
                     asmgen.filler(self.machine, 6)):
            ops = parse_asm(text).ops
            self.assertTrue(ops)
            for op in ops:
                self.assertNotEqual(op.op, "UNKNOWN", op.mnemonic)


class TestRegisterFile(unittest.TestCase):
    """Регистры обязаны укладываться в окно: %r0…%r63.

    Проверено перебором у настоящего ассемблера — предел один при любом
    `wsz`. Первая версия генератора выдавала %r70 и дальше, и ассемблер
    отвечал `Illegal register index`. Тест стоит здесь, чтобы это не
    вернулось незамеченным: своя модель такую ошибку не ловит вовсе.
    """

    def setUp(self):
        self.machine = get_profile("e2k-v6-measured")

    def test_all_register_indices_fit_the_window(self):
        import re

        for text in (asmgen.independent(self.machine, "MUL", 40),
                     asmgen.independent(self.machine, "ADD", 40, packed=True),
                     asmgen.chain(self.machine, "FMUL", 40),
                     asmgen.filler(self.machine, 40)):
            for num in re.findall(r"%d?r\[?(\d+)", text):
                self.assertLessEqual(int(num), asmgen.MAX_REG)


class TestHonestHeader(unittest.TestCase):
    def test_wraparound_is_announced(self):
        """Когда приёмники пошли по кругу, операции перестали быть независимыми.

        Молча выдать «40 независимых операций», из которых независимы первые
        32, — это ровно тот сорт неправды, который инструмент существует
        ловить у других.
        """
        machine = get_profile("e2k-v6-measured")
        few = asmgen.independent(machine, "ADD", 8)
        many = asmgen.independent(machine, "ADD", 40)
        self.assertNotIn("ВНИМАНИЕ", few)
        self.assertIn("ВНИМАНИЕ", many)

    def test_header_states_the_measured_facts(self):
        """В шапке стоят каналы и латентность — из модели, а не из текста."""
        machine = get_profile("e2k-v6-measured")
        text = asmgen.independent(machine, "DIV", 4)
        self.assertIn(",5", text)                     # единственный канал деления
        self.assertIn(str(machine.latency("DIV")), text)
        self.assertIn("держит порт", text)            # occupancy 2 у делителя


if __name__ == "__main__":
    unittest.main()
