"""Справочник системы команд: числа наружу — только с указанием источника.

Документ уходит людям, у которых есть настоящая машина, и его будут
проверять. Поэтому здесь стережётся не форматирование, а одно свойство:
**ни одно допущение не должно уехать в документ как измерение.**

Регрессия выглядела бы так: кто-то добавляет класс в `model.py` с
латентностью по умолчанию, справочник печатает единицу наравне с измеренными
числами, и человек с железом читает выдумку как факт. Ошибка молчаливая —
документ соберётся и будет выглядеть безупречно.
"""

from __future__ import annotations

import unittest

from vliw.core import get_profile
from vliw.core.asm_parser import MNEMONICS
from vliw.core.isa import COMBINATION_BANS, collect, gaps
from vliw.core.model import ASM, ASSUMED, BURST, CHAIN
from vliw.ui import isa_view

KNOWN_SOURCES = {ASM, CHAIN, BURST, ASSUMED}


class TestCollect(unittest.TestCase):
    def setUp(self):
        self.machine = get_profile("e2k-v6-measured")
        self.rows = collect(self.machine)

    def test_unknown_is_not_published(self):
        """`UNKNOWN` — честное «не знаю» разбора, а не класс машины.

        Его латентность и каналы — заглушка по построению; напечатать их
        справочником значит выдать заглушку за характеристику железа.
        """
        self.assertNotIn("UNKNOWN", [r.name for r in self.rows])

    def test_every_mnemonic_reaches_a_class(self):
        """Разметка мнемоник и справочник обязаны сходиться по составу."""
        published = {m for r in self.rows for m in r.mnemonics}
        expected = {m for m, cls in MNEMONICS.items() if cls != "UNKNOWN"}
        self.assertEqual(published, expected)

    def test_no_invented_sources(self):
        """Источник числа — одна из четырёх известных формулировок.

        Свободный текст в этом поле означал бы, что кто-то дописал источник
        руками, а вместе с ним — и число.
        """
        for r in self.rows:
            with self.subTest(cls=r.name):
                self.assertIn(r.latency_source, KNOWN_SOURCES)
                self.assertIn(r.occupancy_source, KNOWN_SOURCES)

    def test_peak_is_channels_over_occupancy(self):
        """Пик — производная величина, а не ещё одно измерение."""
        for r in self.rows:
            with self.subTest(cls=r.name):
                self.assertAlmostEqual(r.peak_per_cycle,
                                       len(r.channels) / r.occupancy)

    def test_monopoly_classes_are_the_narrow_ones(self):
        mono = {r.name for r in self.rows if r.monopoly}
        self.assertIn("DIV", mono)
        self.assertIn("FDIV", mono)
        self.assertNotIn("ADD", mono)

    def test_gaps_are_exactly_the_assumed_latencies(self):
        holes = {r.name for r in gaps(self.rows)}
        assumed = {r.name for r in self.rows if r.latency_source == ASSUMED}
        self.assertEqual(holes, assumed)
        self.assertTrue(holes, "фикстура: допущения в модели есть")


class TestDocument(unittest.TestCase):
    def setUp(self):
        self.machine = get_profile("e2k-v6-measured")
        self.rows = collect(self.machine)
        self.md = isa_view.render_markdown(self.rows, self.machine, "тест")

    def test_every_gap_is_listed_as_a_gap(self):
        """Главный сторож: допущение обязано попасть в раздел «чего нет».

        Не «где-то упомянуто», а именно в таблицу дыр — там, где человек с
        железом ищет, чем помочь.
        """
        tail = self.md.split("## Чего не измерено", 1)
        self.assertEqual(len(tail), 2, "раздел с дырами пропал из документа")
        for r in gaps(self.rows):
            with self.subTest(cls=r.name):
                self.assertIn(f"`{r.name}`", tail[1])

    def _summary_rows(self) -> dict[str, str]:
        """Строки СВОДНОЙ таблицы. Таблица дыр ниже устроена иначе, и мерить
        её теми же правилами — проверять форматирование, а не смысл."""
        body = self.md.split("## Сводная таблица", 1)[1]
        body = body.split("## Классы и мнемоники", 1)[0]
        return {l.split("`")[1]: l for l in body.splitlines() if l.startswith("| `")}

    def test_assumed_numbers_are_marked_in_the_table(self):
        """В сводной таблице допущение выделено, а не выглядит как измерение."""
        rows = self._summary_rows()
        self.assertEqual(set(rows), {r.name for r in self.rows},
                         "сводная таблица разошлась со справочником")
        for r in self.rows:
            with self.subTest(cls=r.name):
                if r.latency_measured:
                    self.assertIn("измерено", rows[r.name])
                else:
                    self.assertIn("**допущение**", rows[r.name])

    def test_document_refuses_to_be_an_isa_manual(self):
        """Документ обязан сам сказать, чего в нём нет.

        Без этой оговорки таблицы читаются как «описание системы команд», а
        описания у нас нет и взять неоткуда.
        """
        self.assertIn("SDM", self.md)
        self.assertIn("Здесь этого нет", self.md)

    def test_bans_are_quoted_verbatim(self):
        """Запреты — цитата ответа ассемблера, а не пересказ."""
        for *_ignored, text in COMBINATION_BANS:
            self.assertIn(text, self.md)
class TestCrossCheckWithVendorDocs(unittest.TestCase):
    """Сверка с официальной таблицей МЦСТ обязана оставаться сверкой.

    Соблазн, против которого стоит этот тест: увидев расхождение, подставить
    документированное число в модель и объявить вопрос закрытым. Так делать
    нельзя — документ описывает Е4С/Е8С, а модель e2k-v6, это разные машины.
    Числа отсюда сравниваются, но не импортируются.
    """

    def setUp(self):
        from vliw.core.isa import DOC_LATENCY
        self.doc = DOC_LATENCY
        self.rows = {r.name: r for r in collect(get_profile("e2k-v6-measured"))}

    def test_no_stale_entries(self):
        """Класс из таблицы сверки обязан существовать в модели.

        Иначе сверка тихо перестаёт что-либо сверять: строка есть, класса нет,
        расхождение не всплывает никогда.
        """
        for cls in self.doc:
            self.assertIn(cls, self.rows, f"{cls} есть в сверке, но нет в модели")

    def test_known_discrepancy_is_still_there(self):
        """LOAD расходится намеренно — 5 у нас против 3 у МЦСТ.

        Если кто-то «починит» это подстановкой тройки, тест упадёт и заставит
        прочитать разбор: измерение на настоящем выводе lcc для e2k-v6 даёт 5
        по 36 зависимым парам, и это разница поколений, а не ошибка.
        """
        self.assertEqual(self.rows["LOAD"].latency, 5)
        self.assertEqual(self.doc["LOAD"][0], "3")

    def test_measured_classes_agree_with_docs(self):
        """Там, где мы ИЗМЕРИЛИ, мы обязаны сходиться с документом.

        Кроме LOAD, у которого расхождение разобрано отдельно. Если сойтись
        перестанет что-то ещё — это либо сломанное измерение, либо новое
        открытие, и в обоих случаях об этом надо узнать сразу.
        """
        for cls, row in self.rows.items():
            if cls in ("LOAD",) or cls not in self.doc:
                continue
            if not row.latency_measured:
                continue
            with self.subTest(cls=cls):
                self.assertEqual(str(row.latency), self.doc[cls][0],
                                 f"{cls}: измерение разошлось с документацией МЦСТ")


if __name__ == "__main__":
    unittest.main()
