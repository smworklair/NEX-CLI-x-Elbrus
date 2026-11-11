"""Экран-помощник: причина сбоя, план действий и согласие пользователя.

Проверяем не «красивый текст», а контракт помощника:
  · запрос обычными словами превращается в действие;
  · до выполнения показываются точные команды;
  · без согласия ничего не запускается;
  · при согласии ассистент сам ставит недостающее и открывает NEX CLI.
"""

from __future__ import annotations

import contextlib
import io
import sys
import unittest
from unittest import mock

from vliw.ui import setup_screen


def _plain(lines: list[str]) -> str:
    import re

    return "\n".join(re.sub(r"\033\[[0-9;]*m", "", line) for line in lines)


class TestReasons(unittest.TestCase):
    def test_both_packages_reported_in_pip_command(self):
        with mock.patch.object(setup_screen, "_has", return_value=False):
            self.assertEqual(
                setup_screen.missing(), ["textual>=8.2", "rich>=13"]
            )

    def test_nothing_missing_when_both_present(self):
        with mock.patch.object(setup_screen, "_has", return_value=True):
            self.assertEqual(setup_screen.missing(), [])

    def test_missing_textual_is_named_in_reasons(self):
        with mock.patch.object(setup_screen, "_has", return_value=False):
            text = " ".join(setup_screen.reasons())
        self.assertIn("textual", text)
        self.assertIn("полноэкранного интерфейса", text)

    def test_installed_but_not_a_terminal(self):
        with mock.patch.object(setup_screen, "_has", return_value=True), \
                mock.patch("sys.stdin.isatty", return_value=False), \
                mock.patch("sys.stdout.isatty", return_value=True):
            text = " ".join(setup_screen.reasons())
        self.assertIn("не подключён к терминалу", text)
        self.assertNotIn("не установлен пакет", text)


class TestIntent(unittest.TestCase):
    def test_launch_requests(self):
        for текст in ("запусти", "можешь запустить", "открой NEX CLI",
                      "как запустить", "launch"):
            with self.subTest(текст=текст):
                self.assertEqual(setup_screen._намерение(текст), "запуск")

    def test_install_requests(self):
        for текст in ("установи", "поставь textual", "как установить"):
            with self.subTest(текст=текст):
                self.assertEqual(setup_screen._намерение(текст), "установка")

    def test_repair_requests(self):
        for текст in ("не работает", "не запускается интерфейс", "чёрный экран"):
            with self.subTest(текст=текст):
                self.assertEqual(setup_screen._намерение(текст), "починка")

    def test_other_actions(self):
        ожидание = {
            "обнови textual": "обновление",
            "удали программу": "удаление",
            "проверь окружение": "проверка",
            "как создать venv": "venv",
        }
        for текст, вид in ожидание.items():
            with self.subTest(текст=текст):
                self.assertEqual(setup_screen._намерение(текст), вид)

    def test_informational_question_is_not_an_action(self):
        self.assertIsNone(setup_screen._намерение("что такое textual"))
        self.assertIsNone(setup_screen._намерение("зачем нужен nex cli"))


class TestQuestionWinsOverAction(unittest.TestCase):
    """Вопрос объясняется, даже если внутри есть корень команды."""

    def test_question_words_are_recognised(self):
        for текст in ("зачем нужны доп установки", "почему не работает",
                      "что такое textual", "как работает NNL",
                      "обязательно ли ставить rich", "нужно ли что-то еще"):
            with self.subTest(текст=текст):
                self.assertTrue(setup_screen._это_вопрос(текст))

    def test_commands_are_not_questions(self):
        for текст in ("запусти", "поставь textual", "не работает",
                      "проверь окружение", "обнови rich"):
            with self.subTest(текст=текст):
                self.assertFalse(setup_screen._это_вопрос(текст))

    def test_install_question_is_about_packages(self):
        self.assertTrue(setup_screen._спросили_зачем_установки(
            "зачем нужны доп установки"))
        self.assertFalse(setup_screen._спросили_зачем_установки(
            "установи textual"))

    def test_install_question_shows_explanation_not_plan(self):
        with mock.patch.object(setup_screen, "_показать_план") as план, \
                mock.patch.object(setup_screen, "_объяснить_установки",
                                  return_value=None) as объяснение:
            setup_screen._обработать_запрос("зачем нужны доп установки")
        объяснение.assert_called_once()
        план.assert_not_called()

    def test_nnl_question_gets_nnl_answer(self):
        self.assertEqual(setup_screen.help_nnl.спросить("как работает NNL"),
                         ("nnl", 1.0))
        self.assertIn("nnl", setup_screen.help_answers.темы())


class TestPlans(unittest.TestCase):
    def test_launch_plan_installs_then_opens(self):
        with mock.patch.object(setup_screen, "_has", return_value=False), \
                mock.patch.object(setup_screen, "_tty", return_value=True), \
                mock.patch.object(setup_screen, "_store_stub", return_value=False):
            план = setup_screen._план_запуска()
        виды = [ш["вид"] for ш in план["шаги"]]
        self.assertEqual(виды, ["установка", "запуск"])
        self.assertEqual(план["шаги"][1]["команда"],
                         [sys.executable, "-m", "vliw"])
        self.assertEqual(план["кнопка"], "Установить и открыть")

    def test_launch_plan_with_ready_environment_only_opens(self):
        with mock.patch.object(setup_screen, "_has", return_value=True), \
                mock.patch.object(setup_screen, "_tty", return_value=True):
            план = setup_screen._план_запуска()
        self.assertEqual([ш["вид"] for ш in план["шаги"]], ["запуск"])

    def test_check_plan_does_not_change_anything(self):
        план = setup_screen._план_проверки()
        self.assertTrue(план["можно_выполнить"])
        self.assertEqual([ш["вид"] for ш in план["шаги"]], ["проверка"])

    def test_deletion_is_never_executed_automatically(self):
        план = setup_screen._план_удаления()
        self.assertFalse(план["можно_выполнить"])


class TestCommandText(unittest.TestCase):
    def test_windows_quotes_pip_version_specifier(self):
        with mock.patch.object(setup_screen.os, "name", "nt"):
            текст = setup_screen._команда_текст(
                ["python", "-m", "pip", "install", "textual>=8.2"])
        self.assertIn('"textual>=8.2"', текст)
        self.assertNotIn("textual>=8.2 ", текст)

    def test_windows_quotes_paths_with_spaces(self):
        with mock.patch.object(setup_screen.os, "name", "nt"):
            текст = setup_screen._команда_текст(
                ["C:\\Program Files\\Python\\python.exe", "-m", "vliw"])
        self.assertIn('"C:\\Program Files\\Python\\python.exe"', текст)

    def test_posix_quotes_pipe_and_space(self):
        with mock.patch.object(setup_screen.os, "name", "posix"):
            текст = setup_screen._команда_текст(["echo", "a b", "x|y"])
        self.assertIn("'a b'", текст)
        self.assertIn("'x|y'", текст)


class TestConsent(unittest.TestCase):
    def test_plan_shows_commands_and_runs_after_consent(self):
        план = {
            "название": "тест",
            "тема": "запуск",
            "резюме": ["Проверка согласия"],
            "шаги": [{"текст": "поставить", "команда": ["x"], "вид": "установка"}],
            "можно_выполнить": True,
            "кнопка": "Выполнить",
        }
        out = io.StringIO()
        with mock.patch.object(setup_screen, "_меню", return_value=0), \
                mock.patch.object(setup_screen, "_выполнить_план", return_value=None) as run, \
                contextlib.redirect_stdout(out):
            setup_screen._показать_план(план)
        текст = out.getvalue()
        self.assertIn("План", текст)
        self.assertIn("поставить", текст)
        run.assert_called_once_with(план)

    def test_cancel_does_not_run_anything(self):
        план = {
            "название": "тест",
            "тема": "запуск",
            "резюме": [],
            "шаги": [{"текст": "поставить", "команда": ["x"], "вид": "установка"}],
            "можно_выполнить": True,
            "кнопка": "Выполнить",
        }

        def последний(пункты, **_):
            return len(пункты) - 1

        with mock.patch.object(setup_screen, "_меню", side_effect=последний), \
                mock.patch.object(setup_screen, "_выполнить_план") as run, \
                contextlib.redirect_stdout(io.StringIO()):
            setup_screen._показать_план(план)
        run.assert_not_called()

    def test_execution_runs_install_then_launch(self):
        план = {
            "тема": "запуск",
            "шаги": [
                {"текст": "поставить", "команда": ["pip"], "вид": "установка"},
                {"текст": "открыть", "команда": ["vliw"], "вид": "запуск"},
            ],
        }
        with mock.patch.object(setup_screen, "_has", return_value=True), \
                mock.patch.object(setup_screen, "_выполнить", return_value=0) as run, \
                mock.patch.object(setup_screen, "_пауза"):
            код = setup_screen._выполнить_план(план)
        self.assertEqual(код, 0)
        self.assertEqual([c.args[0] for c in run.call_args_list], [["pip"], ["vliw"]])

    def test_failed_install_stops_plan(self):
        план = {
            "тема": "запуск",
            "шаги": [
                {"текст": "поставить", "команда": ["pip"], "вид": "установка"},
                {"текст": "открыть", "команда": ["vliw"], "вид": "запуск"},
            ],
        }
        with mock.patch.object(setup_screen, "_has", return_value=True), \
                mock.patch.object(setup_screen, "_выполнить", return_value=1) as run, \
                mock.patch.object(setup_screen, "_пауза"):
            код = setup_screen._выполнить_план(план)
        self.assertIsNone(код)
        self.assertEqual(len(run.call_args_list), 1)


class TestMenu(unittest.TestCase):
    def test_question_mark_starts_a_question(self):
        with mock.patch.object(setup_screen, "_tty", return_value=True), \
                mock.patch.object(setup_screen, "_vt_доступен", return_value=True), \
                mock.patch.object(setup_screen, "_клавиша", return_value="?"), \
                mock.patch("builtins.input", return_value="как установить"), \
                contextlib.redirect_stdout(io.StringIO()):
            выбор = setup_screen._меню([("пункт", "")], приём_текста=True)
        self.assertEqual(выбор, "?как установить")

    def test_question_mark_alone_asks_again(self):
        with mock.patch.object(setup_screen, "_задать_вопрос",
                               return_value=None) as ask:
            setup_screen._обработать_запрос("?")
        ask.assert_called_once()

    def test_arrows_move_selection_and_enter_confirms(self):
        with mock.patch.object(setup_screen, "_tty", return_value=True), \
                mock.patch.object(setup_screen, "_vt_доступен", return_value=True), \
                mock.patch.object(setup_screen, "_клавиша", side_effect=["вниз", "ввод"]), \
                contextlib.redirect_stdout(io.StringIO()):
            выбор = setup_screen._меню([("первый", ""), ("второй", "")])
        self.assertEqual(выбор, 1)

    def test_typed_letter_starts_a_question(self):
        with mock.patch.object(setup_screen, "_tty", return_value=True), \
                mock.patch.object(setup_screen, "_vt_доступен", return_value=True), \
                mock.patch.object(setup_screen, "_клавиша", return_value="з"), \
                mock.patch("builtins.input", return_value="апусти"), \
                contextlib.redirect_stdout(io.StringIO()):
            выбор = setup_screen._меню([("пункт", "")], приём_текста=True)
        self.assertEqual(выбор, "запусти")

    def test_numbered_fallback(self):
        with mock.patch("builtins.input", return_value="2"), \
                contextlib.redirect_stdout(io.StringIO()):
            выбор = setup_screen._меню_вводом(
                [("первый", ""), ("второй", "")], "", "", False)
        self.assertEqual(выбор, 1)


class TestRequestRouting(unittest.TestCase):
    def test_launch_request_opens_a_plan_not_a_reference(self):
        with mock.patch.object(setup_screen, "_показать_план", return_value=None) as plan:
            setup_screen._обработать_запрос("можешь запустить")
        план = plan.call_args.args[0]
        self.assertEqual(план["тема"], "запуск")

    def test_informational_question_gets_short_answer_and_action(self):
        with mock.patch("vliw.help_nnl.спросить", return_value=("textual", 0.9)), \
                mock.patch.object(setup_screen, "_показать_кратко", return_value=None) as short:
            setup_screen._обработать_запрос("что такое textual")
        short.assert_called_once_with("textual")

    def test_unknown_question_stays_short(self):
        with mock.patch("vliw.help_nnl.спросить", return_value=None), \
                mock.patch.object(setup_screen, "_не_понял") as fallback:
            setup_screen._обработать_запрос("сколько будет два плюс два")
        fallback.assert_called_once_with()


class TestScreen(unittest.TestCase):
    def test_install_command_points_at_current_python(self):
        with mock.patch.object(setup_screen, "_has", return_value=False), \
                mock.patch("sys.stdin.isatty", return_value=False), \
                mock.patch("sys.stdout.isatty", return_value=False):
            text = _plain(setup_screen.lines())
        self.assertIn("-m pip install", text)
        self.assertIn("textual>=8.2", text)
        self.assertIn("rich>=13", text)
        self.assertIn(sys.executable, text, "команда должна годиться для копипаста")

    def test_mentions_commands_that_work_without_deps(self):
        with mock.patch.object(setup_screen, "_has", return_value=False):
            text = _plain(setup_screen.lines())
        self.assertIn("run slotclash", text)
        self.assertIn("--plain", text)

    def test_no_install_block_when_packages_present(self):
        with mock.patch.object(setup_screen, "_has", return_value=True), \
                mock.patch("sys.stdin.isatty", return_value=False), \
                mock.patch("sys.stdout.isatty", return_value=False):
            text = _plain(setup_screen.lines())
        self.assertNotIn("pip install", text)
        self.assertIn("настоящего окна терминала", text)

    def test_explain_returns_error_code(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = setup_screen.explain()
        self.assertEqual(code, 1)
        self.assertIn("полноэкранный интерфейс не запустился", buf.getvalue())


class TestMainShowsSetupInsteadOfPlainMenu(unittest.TestCase):
    """Без `--plain` построчное меню больше не показывается автоматически."""

    def _run(self, argv):
        from vliw.cli import main

        out = io.StringIO()
        with mock.patch("vliw.tui.available", return_value=False), \
                mock.patch.object(setup_screen, "_has", return_value=False), \
                contextlib.redirect_stdout(out):
            code = main(argv)
        return code, out.getvalue()

    def test_no_args_shows_setup_screen(self):
        code, text = self._run([])
        self.assertEqual(code, 1)
        self.assertIn("полноэкранный интерфейс не запустился", text)
        self.assertIn("pip install", text)
        self.assertNotIn("1 / 2 / 3", text)

    def test_plain_still_opens_the_old_menu(self):
        import io as _io

        from vliw.cli import main

        out = _io.StringIO()
        with mock.patch("vliw.tui.available", return_value=False), \
                mock.patch("sys.stdin", _io.StringIO("q\n")), \
                contextlib.redirect_stdout(out):
            main(["--plain", "--no-color"])
        self.assertIn("1 / 2 / 3", out.getvalue())


class TestWelcome(unittest.TestCase):
    """Интерактивный экран: меню, вопросы, действие и выход."""

    def _run(self, menu, inputs=(), extra_patches=()):
        from vliw.ui.render import Style

        очередь = iter(menu)

        def показать_и_выбрать(пункты, *, заголовок="", подсказка="", приём_текста=False):
            if заголовок:
                print("  " + заголовок)
            for метка, _ in пункты:
                print("  " + метка)
            return next(очередь)

        out = io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(Style, "enabled", False))
            stack.enter_context(mock.patch.object(setup_screen, "_меню",
                                                  side_effect=показать_и_выбрать))
            stack.enter_context(mock.patch("builtins.input", side_effect=inputs))
            for target, value in extra_patches:
                stack.enter_context(mock.patch.object(setup_screen, target, value))
            stack.enter_context(contextlib.redirect_stdout(out))
            code = setup_screen.welcome()
        return code, out.getvalue()

    def test_main_menu_is_about_actions_not_reference(self):
        # Окружение теста детерминированное: пакеты считаем установленными,
        # иначе подпись первого пункта зависит от того, что стоит на машине.
        код, text = self._run(
            [4],
            extra_patches=(("missing", mock.Mock(return_value=[])),),
        )
        self.assertEqual(код, 1)
        self.assertIn("Чем помочь?", text)
        self.assertIn("Запустить NEX CLI", text)
        self.assertIn("Проверить окружение", text)
        self.assertIn("До встречи", text)

    def test_launch_item_goes_through_a_plan(self):
        code, text = self._run(
            [0],
            extra_patches=(("_показать_план", mock.Mock(return_value=0)),),
        )
        self.assertEqual(code, 0)

    def test_free_text_question_gets_routed_to_assistant(self):
        # «как установить» — вопрос: объяснение через NNL-блок, а не запуск.
        with mock.patch.object(setup_screen, "_показать_кратко",
                               return_value=None) as short:
            код, text = self._run([3, 4], inputs=("как установить",))
        self.assertEqual(код, 1)
        short.assert_called_once_with("установка")

    def test_about_item_uses_short_answer(self):
        with mock.patch.object(setup_screen, "_показать_кратко",
                               return_value=None) as short:
            code, _ = self._run([2, 4])
        self.assertEqual(code, 1)
        short.assert_called_once_with("зачем")


class TestBootDesign(unittest.TestCase):
    """Шапка экрана запуска: крупные буквы «NEX CLI NNL» и фиолетовая тема."""

    def test_big_title_fits_and_uses_block_letters(self):
        from vliw.ui.logo import render_title
        from vliw.ui.render import Style

        with mock.patch.object(Style, "enabled", False):
            строки = render_title()
        self.assertTrue(строки)
        self.assertIn("▄", строки[0], "верхняя строка — шляпки кирпичиков")
        for строка in строки[1:]:
            self.assertIn("█", строка, "буквы набраны блоками")
            self.assertLessEqual(len(строка.strip()), 60,
                                 "заголовок должен влезать в 60 колонок")

    def test_header_keeps_big_title_and_name_line(self):
        import re

        head = [re.sub(r"\033\[[0-9;]*m", "", s)
                for s in setup_screen._шапка_кратко()]
        блоки = [s for s in head if "█" in s]
        self.assertTrue(блоки, "крупные буквы должны быть в шапке")
        # Шапка компактная: логотип и строка названия, без лишних строк —
        # экран должен целиком влезать в окно в 30 строк.
        self.assertLessEqual(len(head), 10, "шапка не должна разрастаться")
        текст = "\n".join(head)
        self.assertIn("NEX CLI", текст)
        self.assertIn("NNL-помощник", текст)

    def test_boot_theme_exists_and_is_purple(self):
        from vliw.ui import theme as t

        т = t.load_theme("nnl-purple")
        self.assertEqual(т.name, "nnl-purple")
        self.assertEqual(т.role("banner").color, 135)
        self.assertEqual(т.role("banner_alt").color, 183)
        self.assertEqual(т.role("border").color, 61)


class TestExplainDispatch(unittest.TestCase):
    def test_terminal_gets_interactive_welcome(self):
        from vliw.ui import setup_screen

        with mock.patch.object(setup_screen, "_tty", return_value=True), \
                mock.patch.object(setup_screen, "welcome", return_value=7) as welcome:
            self.assertEqual(setup_screen.explain("причина"), 7)
        welcome.assert_called_once_with("причина")


if __name__ == "__main__":
    unittest.main()
