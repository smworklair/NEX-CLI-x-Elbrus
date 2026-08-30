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
from pathlib import Path

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


class TestExampleCatalogue(unittest.TestCase):
    """Примеры из `examples/code/*.s` обязаны говорить о себе правду.

    В шапке каждого файла стоит строка `! nex: src=… orc=… err=…` — числа,
    которые пример обещает показать. Пример живёт годами, модель машины и
    планировщик меняются, и разъехаться эти числа могут молча: файл никто не
    открывает, пока он не понадобился на демонстрации. Тест пересчитывает их
    заново тем же кодом, что и режим КОД.
    """

    import re as _re

    HEADER = _re.compile(r"!\s*nex:\s*src=(\S+)\s+orc=(\d+)\s+err=(\d+)")

    def _files(self):
        from vliw.tui.screens.code_screen import EXAMPLES, examples_dir

        return [(name, examples_dir() / f"{name}.s") for name, _, _ in EXAMPLES]

    def test_every_catalogue_entry_has_a_file(self) -> None:
        for name, path in self._files():
            self.assertTrue(path.exists(), f"{name}: нет файла {path}")

    def test_headers_match_what_the_tool_computes(self) -> None:
        from vliw.core.oracle import OracleScheduler

        model = get_profile(DEFAULT_PROFILE)
        for name, path in self._files():
            with self.subTest(example=name):
                text = path.read_text(encoding="utf-8")
                m = self.HEADER.search(text)
                self.assertIsNotNone(m, f"{name}: нет строки `! nex: …`")
                want_src, want_orc, want_err = m.groups()

                parsed = asm_parser.parse_asm(text, source=name)
                dag = asm_parser.build_dag(parsed, key=f"asm:{name}")
                sched = asm_parser.compiler_schedule(parsed, dag, model)
                # То же правило, что в ядре: раскладка, которая не сходится с
                # моделью, расписанием НЕ считается.
                src = sched.makespan if sched and not sched.validate() else None
                orc = OracleScheduler(budget_s=6.0,
                                      portfolio_s=2.0).schedule(dag, model)
                problems = list(parsed.problems) + asm_parser.lint(parsed, model)
                errs = [p for p in problems if p.severity == "error"]

                self.assertEqual(str(src if src is not None else "none"),
                                 want_src, f"{name}: src разъехался")
                self.assertEqual(orc.schedule.makespan, int(want_orc),
                                 f"{name}: orc разъехался")
                self.assertEqual(len(errs), int(want_err),
                                 f"{name}: число ошибок разъехалось")


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


class TestRealCompilerOutput(unittest.TestCase):
    """Разбор НАСТОЯЩЕГО вывода lcc, а не только калибровочных проб.

    Все три проверяемые здесь вещи найдены одинаково: сравнением разбора с
    выводом `lcc -O3` на обычной C-программе. На `examples/probes/*.s` ни
    одна из них не проявляется — пробы слишком просты, — поэтому и прожили
    незамеченными до первого настоящего файла.
    """

    def test_speculative_modifier_does_not_eat_the_line(self):
        """`,sm` после канала не должен выбрасывать операцию целиком.

        Компилятор помечает спекулятивные операции `merges,2,sm`. Прежний
        шаблон ждал после канала пробел, строка не подходила под него
        ЦЕЛИКОМ и молча пропадала: на обычном цикле так терялось 90 строк
        из 182 — больше половины кода.
        """
        from vliw.core.asm_parser import parse_asm

        src = "{\n  merges,2,sm\t0x1, %g17, %r9, %pred3\n  adds,0\t%r1, %r2, %r3\n}\n"
        parsed = parse_asm(src)
        self.assertEqual(len(parsed.ops), 2, "спекулятивная операция потерялась")
        spec = parsed.ops[0]
        self.assertEqual(spec.channel, 2, "канал перед модификатором не прочитан")
        self.assertEqual(spec.flags, ("sm",), "модификатор не сохранён")
        self.assertEqual(parsed.ops[1].flags, (), "обычной операции приписан флаг")

    def test_unknown_mnemonic_is_not_passed_off_as_addition(self):
        """Незнакомое с каналом — UNKNOWN, а не ADD.

        Прежде класс подменялся на ADD (иначе `model.op()` бросал KeyError),
        и `fdivd` уезжал в отчёт арифметикой с латентностью 1. Подмена была
        не видна: в сводке она выглядела как «88% ADD».
        """
        from vliw.core.asm_parser import parse_asm

        # Мнемоника ВЫМЫШЛЕННАЯ намеренно. Здесь дважды стояли настоящие
        # (`fdivd`, потом `aaurwd`), и дважды тест ломался — не потому что
        # сломалось поведение, а потому что словарь дорос до них. Проверяем
        # обработку неизвестного, а не то, чего в словаре пока нет.
        parsed = parse_asm("{\n  zzqwrt,1\t%r1, %r2, %r3\n}\n")
        self.assertEqual(len(parsed.ops), 1)
        self.assertEqual(parsed.ops[0].op, "UNKNOWN")
        self.assertFalse(parsed.ops[0].known)
        self.assertEqual(parsed.unknown_mnemonics, {"zzqwrt": 1})

    def test_unknown_without_channel_is_not_an_alc_operation(self):
        """Незнакомое БЕЗ канала в граф вычислений не идёт.

        В e2k всё, что исполняется на шести арифметических каналах, несёт
        `,N`. Без него это предикатная логика (`landp`, `pass`) или
        подготовка перехода (`ldisp`) — другой блок машины. Раньше такие
        занимали арифметические порты, и восстановление расписания
        компилятора падало на первом же из них.
        """
        from vliw.core.asm_parser import parse_asm

        parsed = parse_asm("{\n  landp\t~%pred0, ~%pred1, %pred2\n"
                           "  adds,0\t%r1, %r2, %r3\n}\n")
        self.assertEqual([o.mnemonic for o in parsed.ops], ["adds"])
        self.assertEqual(parsed.control_ops, 1)
        self.assertIn("landp", parsed.unknown_mnemonics)

    def test_setwd_and_friends_are_control_not_arithmetic(self):
        """`setwd` объявляет окно регистров — это не вычисление."""
        from vliw.core.asm_parser import parse_asm

        parsed = parse_asm("{\n  setwd\twsz = 0xc, nfx = 0x1\n"
                           "  adds,0\t%r1, %r2, %r3\n}\n")
        self.assertEqual([o.mnemonic for o in parsed.ops], ["adds"])
        self.assertEqual(parsed.control_ops, 1)
        self.assertEqual(parsed.unknown_mnemonics, {},
                         "управляющая операция не должна числиться незнакомой")

    def test_model_answers_for_unknown_class(self):
        """Модель обязана знать UNKNOWN во ВСЕХ профилях.

        Иначе парсер не может честно сказать «не знаю»: `model.op()` бросит
        KeyError и уронит всё, что ниже по цепочке. Ровно поэтому подмена на
        ADD и появилась.
        """
        from vliw.core.model import PROFILES, get_profile

        for name in PROFILES:
            with self.subTest(профиль=name):
                model = get_profile(name)
                self.assertEqual(model.latency("UNKNOWN"), 1)
                self.assertTrue(model.channels_for("UNKNOWN"),
                                "без портов операцию некуда поставить")

    def test_calibration_probes_still_parse(self):
        """Пробы, на которых снята модель машины, разбираются без незнакомых.

        Страховка от правок словаря: если из `MNEMONICS` пропадёт что-то
        нужное, это увидится здесь, а не в отчёте по настоящему коду.
        """
        from vliw.core.asm_parser import parse_asm

        root = Path(__file__).resolve().parent.parent / "examples" / "probes"
        found = sorted(root.glob("*.s"))
        self.assertTrue(found, "пробы не найдены — проверять нечего")
        for path in found:
            with self.subTest(проба=path.name):
                parsed = parse_asm(path.read_text(encoding="utf-8"))
                self.assertEqual(parsed.unknown_mnemonics, {})
                self.assertTrue(parsed.ops)


class TestStandaloneCollectorMatchesCore(unittest.TestCase):
    """`tools/collect_real_schedule.py` обязан разбирать так же, как ядро.

    Скрипт самодостаточен НАМЕРЕННО: его отдают человеку, у которого
    репозитория нет. Цена самодостаточности — копия логики разбора, и она
    уже один раз разошлась молча: скрипт перестал выдавать незнакомую
    мнемонику за сложение и получил полный список управляющих операций, а
    ядро осталось со старым поведением. Расхождение обнаружилось только
    когда его результаты сравнили с результатами проекта на одном файле.

    Тест сравнивает не построчно (копия имеет право быть иначе устроена), а
    по наблюдаемому итогу: словари, списки и разбор настоящего файла.
    """

    @staticmethod
    def _script():
        import importlib.util
        import sys

        path = Path(__file__).resolve().parent.parent / "tools" / "collect_real_schedule.py"
        spec = importlib.util.spec_from_file_location("_collector", path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["_collector"] = mod
        spec.loader.exec_module(mod)
        return mod

    def test_mnemonic_tables_agree(self):
        scr = self._script()
        self.assertEqual(scr.MNEMONICS, asm_parser.MNEMONICS,
                         "словарь мнемоник разошёлся со скриптом")

    def test_control_lists_agree(self):
        scr = self._script()
        self.assertEqual(set(scr.CONTROL), set(asm_parser.CONTROL),
                         "список управляющих операций разошёлся со скриптом")

    def test_same_classes_on_the_same_source(self):
        """Один и тот же текст — один и тот же разбор по классам операций."""
        import collections

        scr = self._script()
        src = ("{\n  setwd\twsz = 0xc\n  merges,2,sm\t0x1, %g17, %r9, %pred3\n"
               "  landp\t~%pred0, ~%pred1, %pred2\n  adds,0\t%r1, %r2, %r3\n"
               "  ldw,3\t0x0, [ %dr1 ], %r4\n}\n")
        mine = asm_parser.parse_asm(src)
        theirs = scr.parse_asm(src)
        self.assertEqual(
            collections.Counter(o.op for o in mine.ops),
            collections.Counter(o.op for o in theirs.ops))
        self.assertEqual([o.mnemonic for o in mine.ops],
                         [o.mnemonic for o in theirs.ops])
        self.assertEqual(mine.control_ops, theirs.control_ops)


class TestWideInstructionSemantics(unittest.TestCase):
    """Внутри широкой команды все читают ДО того, как ляжет любая запись.

    Найдено на настоящем выводе lcc: расписание самого компилятора не
    проходило `Schedule.validate()` — инструмент объявлял вывод lcc
    незаконным. Причина была не в модели машины, а в разборе: зависимости
    строились по порядку строк внутри `{ … }`, и соседи по одному такту
    получали выдуманное ребро «запись → чтение».
    """

    def test_same_bundle_read_sees_the_old_value(self):
        """Загрузка и потребитель в одном такте — НЕ зависимость.

        Пара из probe.s: `ldw` пишет %r5, соседний `sdivs` читает %r5. Это
        СТАРЫЙ %r5 — загрузка готовит регистр следующему потребителю. Ребро
        здесь завышало критический путь и ломало проверку расписания.
        """
        src = ("{\n  ldw,0\t0x0, [ %dr1 ], %r5\n"
               "  sdivs,5\t%r5, %r6, %r4\n}\n")
        parsed = asm_parser.parse_asm(src)
        dag = asm_parser.build_dag(parsed)
        self.assertEqual(len(dag.instrs), 2)
        self.assertEqual(dag.instrs[1].preds, (),
                         "сосед по такту не может быть производителем")

    def test_next_bundle_does_depend(self):
        """А через такт зависимость настоящая и обязана быть."""
        src = ("{\n  ldw,0\t0x0, [ %dr1 ], %r5\n}\n"
               "{\n  adds,1\t%r5, %r6, %r7\n}\n")
        parsed = asm_parser.parse_asm(src)
        dag = asm_parser.build_dag(parsed)
        self.assertEqual(dag.instrs[1].preds, (0,),
                         "зависимость между тактами потерялась")

    def test_compiler_schedule_of_real_probes_validates(self):
        """Расписание lcc из проб обязано проходить нашу же проверку.

        Прямая страховка от возврата бага: если разбор снова начнёт выдумывать
        рёбра, `validate()` на выводе компилятора это увидит.
        """
        from vliw.core.model import get_profile

        model = get_profile(DEFAULT_PROFILE)
        root = Path(__file__).resolve().parent.parent / "examples" / "probes"
        checked = 0
        for path in sorted(root.glob("*.s")):
            parsed = asm_parser.parse_asm(path.read_text(encoding="utf-8"))
            dag = asm_parser.build_dag(parsed)
            sched = asm_parser.compiler_schedule(parsed, dag, model)
            if sched is None:
                continue          # раскладка по каналам не сошлась — другой случай
            checked += 1
            with self.subTest(проба=path.name):
                self.assertEqual(sched.validate(), [],
                                 "расписание компилятора объявлено незаконным")
        self.assertTrue(checked, "ни одной пробы не проверено")


class TestHonestCompilerComparison(unittest.TestCase):
    """Разницу с компилятором нельзя называть резервом, если модель не знает
    половины операций.

    На выводе `lcc -O3` обычного цикла инструмент показывал «резерв 71%»:
    63 из 132 операций получили класс UNKNOWN с латентностью-заглушкой 1,
    и точный поиск обыгрывал компилятор просто потому, что не знал их
    настоящей цены. Такое число, показанное как достижение, — неправда.
    """

    @staticmethod
    def _render(ops_unknown: int, ops_known: int, comp: int, orc: int):
        from types import SimpleNamespace

        from vliw.ui import diagnostics

        ops = ([SimpleNamespace(op="UNKNOWN")] * ops_unknown
               + [SimpleNamespace(op="ADD")] * ops_known)
        parsed = SimpleNamespace(ops=ops, bundles=1, nop_cycles=0,
                                 skipped_lines=0, unknown_mnemonics={},
                                 problems=[], source="t",
                                 op_counts=lambda: {"ADD": ops_known})
        return "\n".join(diagnostics.render_parsed(
            parsed, None, comp, orc, None))

    def test_large_unknown_share_blocks_the_claim(self):
        text = self._render(63, 69, comp=77, orc=22)
        self.assertIn("несостоятельно", text)
        self.assertNotIn("резерв 55", text)

    def test_clean_graph_still_reports_the_reserve(self):
        text = self._render(0, 36, comp=35, orc=26)
        self.assertIn("резерв 9", text)
        self.assertNotIn("несостоятельно", text)


class TestSingleBundleFile(unittest.TestCase):
    """Файл из ОДНОЙ широкой команды не должен растаскиваться по тактам.

    Запасная ветка разбора («файл без фигурных скобок — каждая операция свой
    такт») смотрела на то, находимся ли мы ВНУТРИ команды в конце файла. После
    закрывающей `}` флаг снят, а такты у всех операций нулевые — и ветка
    срабатывала на совершенно обычном файле, разнося соседей по такту на
    разные такты. На многотактных файлах не проявлялось: там такты разные.
    """

    ONE = "{\n  ldw,0\t0x0, [ %dr1 ], %r5\n  adds,1\t%r6, %r7, %r8\n}\n"

    def test_one_bundle_stays_one(self):
        parsed = asm_parser.parse_asm(self.ONE)
        self.assertEqual(parsed.bundles, 1)
        self.assertEqual([o.cycle for o in parsed.ops], [0, 0])

    def test_file_without_braces_still_splits(self):
        """А настоящий файл без скобок по-прежнему считается по операции в такт."""
        src = "  ldw,0\t0x0, [ %dr1 ], %r5\n  adds,1\t%r6, %r7, %r8\n"
        parsed = asm_parser.parse_asm(src)
        self.assertEqual([o.cycle for o in parsed.ops], [0, 1])
        self.assertEqual(parsed.bundles, 2)


class TestLinterDoesNotBlameTheCompiler(unittest.TestCase):
    """Линтер не должен объявлять вывод настоящего lcc незаконным.

    Проверка «результат ещё не готов» шла по порядку строк и не знала, что
    внутри широкой команды все читают ДО записей. На probe.s это давало три
    ошибки на ровном месте — инструмент говорил, что компилятор Эльбруса
    выдал неверный код. Та же ошибка была в build_dag; здесь отдельная копия
    логики, и она отстала.
    """

    def test_real_probes_have_no_dependency_errors(self):
        from vliw.core.model import get_profile

        model = get_profile(DEFAULT_PROFILE)
        root = Path(__file__).resolve().parent.parent / "examples" / "probes"
        for path in sorted(root.glob("*.s")):
            parsed = asm_parser.parse_asm(path.read_text(encoding="utf-8"))
            errs = [p for p in asm_parser.lint(parsed, model)
                    if p.severity == "error" and p.kind == "ready"]
            with self.subTest(проба=path.name):
                self.assertEqual(
                    errs, [], "вывод lcc объявлен незаконным: "
                    + "; ".join(e.text for e in errs[:2]))

    def test_real_violation_across_bundles_is_still_caught(self):
        """А настоящее нарушение — через такт — линтер обязан находить."""
        from vliw.core.model import get_profile

        # LOAD отдаёт результат через 5 тактов; читаем через один.
        src = ("{\n  ldw,0\t0x0, [ %dr1 ], %r5\n}\n"
               "{\n  adds,1\t%r5, %r6, %r7\n}\n")
        parsed = asm_parser.parse_asm(src)
        errs = [p for p in asm_parser.lint(parsed, get_profile(DEFAULT_PROFILE))
                if p.kind == "ready"]
        self.assertEqual(len(errs), 1, "нарушение между тактами пропущено")
        self.assertIn("%r5", errs[0].text)


class TestModeFlagSkipsThePicker(unittest.TestCase):
    """`--mode` обязан пропускать экран выбора в ОБОИХ интерфейсах.

    Полноэкранный так и делал (`pick_app = args.mode is None`), а построчный
    применял режим и тут же затирал его вопросом «наберите 1, 2 или 3»: флаг,
    обещающий в справке «пропустить экран выбора», в `--plain` не работал.
    Классическое расхождение двух интерфейсов — то же, что и с линтером.
    """

    @staticmethod
    def _run(argv, feed):
        import io
        import contextlib
        from unittest import mock

        from vliw.cli import main

        out = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(feed)), \
                contextlib.redirect_stdout(out):
            try:
                main(argv)
            except SystemExit:
                pass
        return out.getvalue()

    def test_plain_with_mode_does_not_ask(self):
        text = self._run(["--plain", "--no-color", "--mode", "lab"], "/quit\n")
        self.assertNotIn("наберите 1, 2 или 3", text)

    def test_plain_without_mode_still_asks(self):
        text = self._run(["--plain", "--no-color"], "q\n")
        self.assertIn("1 / 2 / 3", text)
