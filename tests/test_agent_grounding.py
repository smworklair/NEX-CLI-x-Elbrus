"""Регресс-тест: агент не должен давать модели повод выдумывать такты.

История бага
------------
Mistral назвал неверный такт для инструкции. Разбор показал, что виновата не
модель, а то, ЧТО ей дали: блок ФАКТЫ собирался с раскладкой расписания только
если вопрос попадал под шаблон `такт|расписан|разлож|порядок|когда|выдал`.
Вопрос «на каком КАНАЛЕ стоит z0?» под шаблон не подходил — раскладка в факты
не попадала, а отвечать модель всё равно бралась. Взять числа было неоткуда.

Проверять сам ответ языковой модели тестом нельзя: он недетерминирован и стоит
сетевого вызова. Зато можно проверить ГРУНТОВКУ — что в фактах лежит вся
правда, которая нужна для ответа, и что она совпадает с расписанием из ядра.
Это ровно та половина, которая была сломана и которую мы контролируем.

Проверяются четыре свойства:
  1. в раскладке присутствует КАЖДАЯ инструкция со своим тактом и каналом;
  2. числа в раскладке совпадают с ядром (Schedule), а не пересчитаны заново;
  3. раскладка попадает в факты при любом вопросе о размещении;
  4. обрезка длинной раскладки объявлена явно, а не молчит.
"""

from __future__ import annotations

import re
import unittest
from types import SimpleNamespace

from vliw.agent import context
from vliw.agent.agent import Agent
from vliw.cli import Session

# Вопросы, на которых старый шаблон промахивался. Каждый требует знания
# размещения, и ни один (кроме первого) не содержит слова «такт».
PLACEMENT_QUESTIONS = [
    "в каком такте выдано dc?",
    "на каком канале стоит z0?",
    "где размещена операция g1?",
    "в какой широкой команде идёт m0?",
    "почему деление dc позже?",
    "что тут вообще происходит?",
]


def session(scenario: str = "slotclash") -> Session:
    s = Session(args=SimpleNamespace(budget=5.0, portfolio=1.0), scenario=scenario)
    s.results()
    return s


class TestLayoutCompleteness(unittest.TestCase):
    def setUp(self):
        self.s = session()
        self.base, _, _ = self.s.peek()

    def test_every_instruction_is_in_the_layout(self):
        lay = "\n".join(context.schedule_layout(self.s))
        for ins in self.s.dag_obj:
            self.assertIn(ins.name, lay, f"{ins.name} не попала в раскладку")

    def test_cycles_and_channels_match_the_core(self):
        """Раскладка — пересказ Schedule, а не независимый расчёт."""
        lines = context.schedule_layout(self.s)
        model, dag = self.s.model(), self.s.dag_obj
        seen: dict[str, tuple[int, int]] = {}
        for line in lines:
            m = re.match(r"\s*т\.(\d+):\s*(.+)", line)
            if not m:
                continue
            cycle = int(m.group(1))
            for cell in m.group(2).split(", "):
                port, _, rest = cell.partition("=")
                name = rest.split()[-1]
                seen[name] = (cycle, int(port.strip().lstrip(",")))

        for p in self.base.schedule.placements.values():
            name = dag[p.instr].name
            self.assertIn(name, seen)
            self.assertEqual(seen[name], (p.cycle, p.channel),
                             f"{name}: в фактах {seen[name]}, "
                             f"в расписании ({p.cycle}, {p.channel})")

    def test_layout_names_which_schedule_it_is(self):
        lay = "\n".join(context.schedule_layout(self.s))
        self.assertIn("baseline", lay)


class TestLayoutReachesTheModel(unittest.TestCase):
    def test_placement_questions_all_get_the_layout(self):
        """Тот самый баг: канал/размещение не подпадали под шаблон слов."""
        s = session()
        agent = Agent(session=s)
        for q in PLACEMENT_QUESTIONS:
            with self.subTest(question=q):
                self.assertTrue(agent._needs_layout(q))

    def test_facts_contain_the_layout(self):
        s = session()
        facts = context.build(s, include_layout=True)
        self.assertIn("РАСПИСАНИЕ", facts)
        for ins in s.dag_obj:
            self.assertIn(ins.name, facts)

    def test_no_layout_promised_before_the_run(self):
        """Пока расписания нет, выдумывать нечего — и раскладки быть не должно."""
        s = Session(args=SimpleNamespace(budget=5.0, portfolio=1.0),
                    scenario="slotclash")
        agent = Agent(session=s)
        self.assertFalse(agent._needs_layout("в каком такте dc?"))
        self.assertEqual(context.schedule_layout(s), [])
        self.assertIn("НЕ посчитано", context.build(s))


class TestTruncationIsAnnounced(unittest.TestCase):
    def test_cut_layout_says_so(self):
        s = session("ptrchase")
        lay = context.schedule_layout(s, max_rows=3)
        tail = "\n".join(lay)
        self.assertIn("обрезана", tail)
        self.assertIn("НЕТ", tail, "модель должна быть предупреждена явно")

    def test_full_layout_says_nothing_extra(self):
        s = session("simple4")
        self.assertNotIn("обрезана", "\n".join(context.schedule_layout(s)))


class TestMachineFacts(unittest.TestCase):
    """Опровергнутая модель не должна попасть в подсказку через факты."""

    def test_divider_named_as_the_only_monopoly(self):
        facts = "\n".join(context.machine_facts(session().model()))
        self.assertIn("DIV", facts)
        # С 30.08.2026 монополистов на ,5 двое: целочисленный делитель и
        # делитель плавающей точки — ассемблер отвергает fdivd во всех
        # остальных каналах. Проверяем сам факт монополии и что DIV в ней
        # назван, а не точную формулировку перечисления.
        self.assertRegex(facts, r"Порт ,5 — ЕДИНСТВЕННЫЙ исполнитель [\w/]*DIV")
        self.assertIn("монопольный", facts)
        self.assertNotRegex(facts, r"ЕДИНСТВЕННЫЙ исполнитель MUL")

    def test_narrow_ops_are_listed_with_their_ports(self):
        facts = "\n".join(context.machine_facts(session().model()))
        self.assertIn("MUL исполнима на портах", facts)
        self.assertIn("STORE исполнима на портах", facts)

    def test_system_prompt_forbids_inventing_numbers(self):
        self.assertIn("ТОЛЬКО из блока ФАКТЫ", context.SYSTEM)


if __name__ == "__main__":
    unittest.main()
