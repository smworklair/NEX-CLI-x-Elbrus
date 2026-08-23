"""Разбор буфера КОДА: номера строк, линтер и свежесть результатов.

Редактор режима КОД ставит расписание НА текст — такт и канал в гуттере той
самой строки, метку `▲` на строке с ошибкой, переход «замечание → курсор».
Всё это держится на двух вещах, которых у разбора раньше не было: номере
строки у операции и списке замечаний с этим номером. Здесь они и проверяются,
без интерфейса — чтобы поломка была видна в ядре, а не в скриншоте.

Отдельно проверяется линтер. Его смысл не в красоте: он ловит ошибки, которые
АССЕМБЛЕР ПРОПУСКАЕТ — код собирается, считает не то, и виноватой выглядит
логика. Поэтому у каждой проверки здесь свой тест с конкретным номером строки.
"""

from __future__ import annotations

import unittest

from vliw.core import asm_parser
from vliw.core.model import DEFAULT_PROFILE, get_profile


def _lint(text: str):
    parsed = asm_parser.parse_asm(text, source="<тест>")
    model = get_profile(DEFAULT_PROFILE)
    return parsed, asm_parser.lint(parsed, model)


class TestLineNumbers(unittest.TestCase):
    def test_op_knows_its_source_line(self) -> None:
        parsed, _ = _lint("! шапка\n{\n  adds,0 %r1, %r2, %r3\n}\n")
        self.assertEqual([o.line for o in parsed.ops], [3])

    def test_skipped_lines_do_not_shift_the_rest(self) -> None:
        """Нумерация идёт по ФАЙЛУ, а не по порядку разобранных операций."""
        parsed, _ = _lint("{\n  ???\n  adds,0 %r1, %r2, %r3\n}\n")
        self.assertEqual([o.line for o in parsed.ops], [3])

    def test_unparsed_line_is_reported_with_its_number(self) -> None:
        parsed, _ = _lint("{\n  ???\n}\n")
        self.assertEqual([(p.line, p.kind) for p in parsed.problems],
                         [(2, "parse")])

    def test_unknown_mnemonic_suggests_a_close_one(self) -> None:
        parsed, _ = _lint("{\n  addd,0 %r1, %r2, %r3\n  adfs,0 %r4, %r5, %r6\n}\n")
        problems = [p for p in parsed.problems if p.kind == "mnemonic"]
        self.assertEqual([p.line for p in problems], [3])
        self.assertIn("adds", problems[0].hint)


class TestLint(unittest.TestCase):
    def test_clean_fragment_has_nothing_to_say(self) -> None:
        """Законный код — ни одного замечания, кроме info про каналы."""
        text = ("{\n  muls,0 %r10, %r11, %r20\n  muls,1 %r12, %r13, %r21\n}\n"
                "nop 3\n{\n  adds,0 %r20, %r21, %r22\n}\n")
        _, problems = _lint(text)
        self.assertEqual([p for p in problems if p.severity == "error"], [])

    def test_channel_outside_the_port_matrix(self) -> None:
        """`muls,2` ассемблер отвергает: умножение живёт на ,0 ,1 ,3 ,4."""
        _, problems = _lint("{\n  muls,2 %r1, %r2, %r3\n}\n")
        chan = [p for p in problems if p.kind == "channel"]
        self.assertEqual([(p.line, p.severity) for p in chan], [(2, "error")])
        self.assertIn(",0", chan[0].hint)

    def test_second_division_while_the_port_is_still_held(self) -> None:
        """Делитель держит ,5 два такта — соседний такт его не примет."""
        _, problems = _lint("{\n  sdivs,5 %r0, %r1, %r2\n}\n"
                            "{\n  sdivs,5 %r3, %r4, %r5\n}\n")
        busy = [p for p in problems if p.kind == "busy"]
        self.assertEqual([p.line for p in busy], [5])
        self.assertIn("строки 2", busy[0].text)

    def test_reading_a_result_before_it_is_ready(self) -> None:
        """Латентность деления 11 тактов: чтение через такт читает старое."""
        _, problems = _lint("{\n  sdivs,5 %r0, %r1, %r2\n}\n"
                            "nop 2\n{\n  adds,0 %r2, %r3, %r4\n}\n")
        ready = [p for p in problems if p.kind == "ready"]
        self.assertEqual([p.line for p in ready], [6])
        self.assertIn("11", ready[0].text)

    def test_lint_agrees_with_the_core_validator(self) -> None:
        """Что линтер зовёт ошибкой, то и `Schedule.validate` считает ошибкой.

        Две независимые реализации одного правила разъезжаются молча, и
        разъехавшись, дают редактору право говорить «всё хорошо» о коде,
        который ядро потом отвергает. Поэтому — сверка на одном тексте.
        """
        text = ("{\n  muls,0 %r1, %r2, %r3\n}\n{\n  adds,0 %r3, %r4, %r5\n}\n")
        parsed, problems = _lint(text)
        model = get_profile(DEFAULT_PROFILE)
        dag = asm_parser.build_dag(parsed, key="asm:тест", title="тест")
        sched = asm_parser.compiler_schedule(parsed, dag, model)
        self.assertTrue([p for p in problems if p.kind == "ready"],
                        "линтер обязан увидеть чтение раньше латентности")
        self.assertTrue(sched.validate(),
                        "ядро обязано увидеть то же самое")

    def test_missing_channels_are_flagged_as_a_guess(self) -> None:
        """Без каналов раскладка — наша догадка, и это должно быть сказано."""
        _, problems = _lint("{\n  adds %r1, %r2, %r3\n}\n")
        self.assertEqual([p.kind for p in problems if p.kind == "free"],
                         ["free"])


class TestResultsFreshness(unittest.TestCase):
    """Правка буфера обязана менять числа, а не показывать прошлый прогон."""

    def test_set_dag_drops_the_cached_results(self) -> None:
        from vliw import cli

        args = cli._build_parser().parse_args([])
        session = cli.Session(args=args)

        short = asm_parser.parse_asm("{\n  adds,0 %r1, %r2, %r3\n}\n")
        session.set_dag(asm_parser.build_dag(short, key="asm:буфер"),
                        "asm:буфер")
        first = session.results()[1].schedule.makespan

        long = asm_parser.parse_asm(
            "{\n  sdivs,5 %r0, %r1, %r2\n}\n"
            "nop 11\n{\n  adds,0 %r2, %r3, %r4\n}\n")
        session.set_dag(asm_parser.build_dag(long, key="asm:буфер"),
                        "asm:буфер")
        second = session.results()[1].schedule.makespan

        self.assertNotEqual(first, second,
                            "второй прогон отдал числа первого — кэш не сброшен")


if __name__ == "__main__":
    unittest.main()
