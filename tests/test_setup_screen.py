"""Setup/welcome assistant screen: failure reasons, action plans, and user consent.

Verifies the assistant's core contract:
  - natural-language requests map cleanly to actions or help topics;
  - exact shell commands are displayed before execution;
  - nothing runs without explicit user consent;
  - upon consent, missing packages are installed and NEX CLI launches.
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
        self.assertIn("full-screen interface", text)

    def test_installed_but_not_a_terminal(self):
        with mock.patch.object(setup_screen, "_has", return_value=True), \
                mock.patch("sys.stdin.isatty", return_value=False), \
                mock.patch("sys.stdout.isatty", return_value=True):
            text = " ".join(setup_screen.reasons())
        self.assertIn("not attached to a terminal", text)
        self.assertNotIn("is not installed", text)


class TestIntent(unittest.TestCase):
    def test_launch_requests(self):
        for text in ("запусти", "можешь запустить", "открой NEX CLI",
                     "как запустить", "launch"):
            with self.subTest(text=text):
                self.assertEqual(setup_screen._намерение(text), "запуск")

    def test_install_requests(self):
        for text in ("установи", "поставь textual", "как установить"):
            with self.subTest(text=text):
                self.assertEqual(setup_screen._намерение(text), "установка")

    def test_repair_requests(self):
        for text in ("не работает", "не запускается интерфейс", "чёрный экран"):
            with self.subTest(text=text):
                self.assertEqual(setup_screen._намерение(text), "починка")

    def test_other_actions(self):
        expected = {
            "обнови textual": "обновление",
            "удали программу": "удаление",
            "проверь окружение": "проверка",
            "как создать venv": "venv",
        }
        for text, kind in expected.items():
            with self.subTest(text=text):
                self.assertEqual(setup_screen._намерение(text), kind)

    def test_informational_question_is_not_an_action(self):
        self.assertIsNone(setup_screen._намерение("что такое textual"))
        self.assertIsNone(setup_screen._намерение("зачем нужен nex cli"))


class TestQuestionWinsOverAction(unittest.TestCase):
    """Informational questions get explained even if they contain an action verb stem."""

    def test_question_words_are_recognised(self):
        for text in ("зачем нужны доп установки", "почему не работает",
                     "что такое textual", "как работает NNL",
                     "обязательно ли ставить rich", "нужно ли что-то еще"):
            with self.subTest(text=text):
                self.assertTrue(setup_screen._это_вопрос(text))

    def test_commands_are_not_questions(self):
        for text in ("запусти", "поставь textual", "не работает",
                     "проверь окружение", "обнови rich"):
            with self.subTest(text=text):
                self.assertFalse(setup_screen._это_вопрос(text))

    def test_install_question_is_about_packages(self):
        self.assertTrue(setup_screen._спросили_зачем_установки(
            "зачем нужны доп установки"))
        self.assertFalse(setup_screen._спросили_зачем_установки(
            "установи textual"))

    def test_install_question_shows_explanation_not_plan(self):
        with mock.patch.object(setup_screen, "_показать_план") as plan, \
                mock.patch.object(setup_screen, "_объяснить_установки",
                                  return_value=None) as explain:
            setup_screen._обработать_запрос("зачем нужны доп установки")
        explain.assert_called_once()
        plan.assert_not_called()

    def test_nnl_question_gets_nnl_answer(self):
        self.assertEqual(setup_screen.help_nnl.спросить("как работает NNL"),
                         ("nnl", 1.0))
        self.assertIn("nnl", setup_screen.help_answers.темы())


class TestPlans(unittest.TestCase):
    def test_launch_plan_installs_then_opens(self):
        with mock.patch.object(setup_screen, "_has", return_value=False), \
                mock.patch.object(setup_screen, "_tty", return_value=True), \
                mock.patch.object(setup_screen, "_store_stub", return_value=False):
            plan = setup_screen._план_запуска()
        kinds = [step["вид"] for step in plan["шаги"]]
        self.assertEqual(kinds, ["установка", "запуск"])
        self.assertEqual(plan["шаги"][1]["команда"],
                         [sys.executable, "-m", "vliw"])
        self.assertEqual(plan["кнопка"], "Install and open")

    def test_launch_plan_with_ready_environment_only_opens(self):
        with mock.patch.object(setup_screen, "_has", return_value=True), \
                mock.patch.object(setup_screen, "_tty", return_value=True):
            plan = setup_screen._план_запуска()
        self.assertEqual([step["вид"] for step in plan["шаги"]], ["запуск"])

    def test_check_plan_does_not_change_anything(self):
        plan = setup_screen._план_проверки()
        self.assertTrue(plan["можно_выполнить"])
        self.assertEqual([step["вид"] for step in plan["шаги"]], ["проверка"])

    def test_deletion_is_never_executed_automatically(self):
        plan = setup_screen._план_удаления()
        self.assertFalse(plan["можно_выполнить"])


class TestCommandText(unittest.TestCase):
    def test_windows_quotes_pip_version_specifier(self):
        with mock.patch.object(setup_screen.os, "name", "nt"):
            text = setup_screen._команда_текст(
                ["python", "-m", "pip", "install", "textual>=8.2"])
        self.assertIn('"textual>=8.2"', text)
        self.assertNotIn("textual>=8.2 ", text)

    def test_windows_quotes_paths_with_spaces(self):
        with mock.patch.object(setup_screen.os, "name", "nt"):
            text = setup_screen._команда_текст(
                ["C:\\Program Files\\Python\\python.exe", "-m", "vliw"])
        self.assertIn('"C:\\Program Files\\Python\\python.exe"', text)

    def test_posix_quotes_pipe_and_space(self):
        with mock.patch.object(setup_screen.os, "name", "posix"):
            text = setup_screen._команда_текст(["echo", "a b", "x|y"])
        self.assertIn("'a b'", text)
        self.assertIn("'x|y'", text)


class TestConsent(unittest.TestCase):
    def test_plan_shows_commands_and_runs_after_consent(self):
        plan = {
            "название": "test",
            "тема": "запуск",
            "резюме": ["Consent check"],
            "шаги": [{"текст": "install", "команда": ["x"], "вид": "установка"}],
            "можно_выполнить": True,
            "кнопка": "Execute",
        }
        out = io.StringIO()
        with mock.patch.object(setup_screen, "_меню", return_value=0), \
                mock.patch.object(setup_screen, "_выполнить_план", return_value=None) as run, \
                contextlib.redirect_stdout(out):
            setup_screen._показать_план(plan)
        text = out.getvalue()
        self.assertIn("Plan:", text)
        self.assertIn("install", text)
        run.assert_called_once_with(plan)

    def test_cancel_does_not_run_anything(self):
        plan = {
            "название": "test",
            "тема": "запуск",
            "резюме": [],
            "шаги": [{"текст": "install", "команда": ["x"], "вид": "установка"}],
            "можно_выполнить": True,
            "кнопка": "Execute",
        }

        def pick_last(items, **_):
            return len(items) - 1

        with mock.patch.object(setup_screen, "_меню", side_effect=pick_last), \
                mock.patch.object(setup_screen, "_выполнить_план") as run, \
                contextlib.redirect_stdout(io.StringIO()):
            setup_screen._показать_план(plan)
        run.assert_not_called()

    def test_execution_runs_install_then_launch(self):
        plan = {
            "тема": "запуск",
            "шаги": [
                {"текст": "install", "команда": ["pip"], "вид": "установка"},
                {"текст": "open", "команда": ["vliw"], "вид": "запуск"},
            ],
        }
        with mock.patch.object(setup_screen, "_has", return_value=True), \
                mock.patch.object(setup_screen, "_выполнить", return_value=0) as run, \
                mock.patch.object(setup_screen, "_пауза"):
            code = setup_screen._выполнить_план(plan)
        self.assertEqual(code, 0)
        self.assertEqual([c.args[0] for c in run.call_args_list], [["pip"], ["vliw"]])

    def test_failed_install_stops_plan(self):
        plan = {
            "тема": "запуск",
            "шаги": [
                {"текст": "install", "команда": ["pip"], "вид": "установка"},
                {"текст": "open", "команда": ["vliw"], "вид": "запуск"},
            ],
        }
        with mock.patch.object(setup_screen, "_has", return_value=True), \
                mock.patch.object(setup_screen, "_выполнить", return_value=1) as run, \
                mock.patch.object(setup_screen, "_пауза"):
            code = setup_screen._выполнить_план(plan)
        self.assertIsNone(code)
        self.assertEqual(len(run.call_args_list), 1)


class TestMenu(unittest.TestCase):
    def test_question_mark_starts_a_question(self):
        with mock.patch.object(setup_screen, "_tty", return_value=True), \
                mock.patch.object(setup_screen, "_vt_доступен", return_value=True), \
                mock.patch.object(setup_screen, "_клавиша", return_value="?"), \
                mock.patch("builtins.input", return_value="how to install"), \
                contextlib.redirect_stdout(io.StringIO()):
            choice = setup_screen._меню([("item", "")], приём_текста=True)
        self.assertEqual(choice, "?how to install")

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
            choice = setup_screen._меню([("first", ""), ("second", "")])
        self.assertEqual(choice, 1)

    def test_typed_letter_starts_a_question(self):
        with mock.patch.object(setup_screen, "_tty", return_value=True), \
                mock.patch.object(setup_screen, "_vt_доступен", return_value=True), \
                mock.patch.object(setup_screen, "_клавиша", return_value="l"), \
                mock.patch("builtins.input", return_value="aunch"), \
                contextlib.redirect_stdout(io.StringIO()):
            choice = setup_screen._меню([("item", "")], приём_текста=True)
        self.assertEqual(choice, "launch")

    def test_numbered_fallback(self):
        with mock.patch("builtins.input", return_value="2"), \
                contextlib.redirect_stdout(io.StringIO()):
            choice = setup_screen._меню_вводом(
                [("first", ""), ("second", "")], "", "", False)
        self.assertEqual(choice, 1)


class TestRequestRouting(unittest.TestCase):
    def test_launch_request_opens_a_plan_not_a_reference(self):
        with mock.patch.object(setup_screen, "_показать_план", return_value=None) as plan:
            setup_screen._обработать_запрос("можешь запустить")
        shown = plan.call_args.args[0]
        self.assertEqual(shown["тема"], "запуск")

    def test_informational_question_gets_short_answer_and_action(self):
        with mock.patch("vliw.help_nnl.спросить", return_value=("textual", 0.9)), \
                mock.patch.object(setup_screen, "_показать_кратко", return_value=None) as short:
            setup_screen._обработать_запрос("что такое textual")
        short.assert_called_once_with("textual")

    def test_unknown_question_stays_short(self):
        with mock.patch("vliw.help_nnl.спросить", return_value=None), \
                mock.patch.object(setup_screen, "_не_понял") as fallback:
            setup_screen._обработать_запрос("what is two plus two")
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
        self.assertIn(sys.executable, text, "command must be copy-pasteable")

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
        self.assertIn("real terminal", text)

    def test_explain_returns_error_code(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = setup_screen.explain()
        self.assertEqual(code, 1)
        self.assertIn("full-screen interface did not start", buf.getvalue())


class TestMainShowsSetupInsteadOfPlainMenu(unittest.TestCase):
    """Without `--plain`, the legacy line-by-line menu does not open automatically."""

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
        self.assertIn("full-screen interface did not start", text)
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
    """Interactive welcome screen: menu, questions, action dispatch, and exit."""

    def _run(self, menu, inputs=(), extra_patches=()):
        from vliw.ui.render import Style

        queue = iter(menu)

        def show_and_pick(items, *, заголовок="", подсказка="", приём_текста=False):
            if заголовок:
                print("  " + заголовок)
            for label, _ in items:
                print("  " + label)
            return next(queue)

        out = io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(Style, "enabled", False))
            stack.enter_context(mock.patch.object(setup_screen, "_меню",
                                                  side_effect=show_and_pick))
            stack.enter_context(mock.patch("builtins.input", side_effect=inputs))
            for target, value in extra_patches:
                stack.enter_context(mock.patch.object(setup_screen, target, value))
            stack.enter_context(contextlib.redirect_stdout(out))
            code = setup_screen.welcome()
        return code, out.getvalue()

    def test_main_menu_is_about_actions_not_reference(self):
        # Deterministic test env: pretend packages are installed so item 0 is "Launch NEX CLI".
        code, text = self._run(
            [4],
            extra_patches=(("missing", mock.Mock(return_value=[])),),
        )
        self.assertEqual(code, 1)
        self.assertIn("How can I help?", text)
        self.assertIn("Launch NEX CLI", text)
        self.assertIn("Check environment", text)
        self.assertIn("Goodbye", text)

    def test_launch_item_goes_through_a_plan(self):
        code, text = self._run(
            [0],
            extra_patches=(("_показать_план", mock.Mock(return_value=0)),),
        )
        self.assertEqual(code, 0)

    def test_free_text_question_gets_routed_to_assistant(self):
        with mock.patch.object(setup_screen, "_показать_кратко",
                               return_value=None) as short:
            code, text = self._run([3, 4], inputs=("как установить",))
        self.assertEqual(code, 1)
        short.assert_called_once_with("установка")

    def test_about_item_uses_short_answer(self):
        with mock.patch.object(setup_screen, "_показать_кратко",
                               return_value=None) as short:
            code, _ = self._run([2, 4])
        self.assertEqual(code, 1)
        short.assert_called_once_with("зачем")


class TestBootDesign(unittest.TestCase):
    """Boot screen header: block-letter 'NEX CLI NNL' banner and purple theme."""

    def test_big_title_fits_and_uses_block_letters(self):
        from vliw.ui.logo import render_title
        from vliw.ui.render import Style

        with mock.patch.object(Style, "enabled", False):
            lines = render_title()
        self.assertTrue(lines)
        self.assertIn("▄", lines[0], "top row uses half-block caps")
        for line in lines[1:]:
            self.assertIn("█", line, "letters are rendered with full blocks")
            self.assertLessEqual(len(line.strip()), 60,
                                 "banner must fit within 60 columns")

    def test_header_keeps_big_title_and_name_line(self):
        import re

        head = [re.sub(r"\033\[[0-9;]*m", "", s)
                for s in setup_screen._шапка_кратко()]
        blocks = [s for s in head if "█" in s]
        self.assertTrue(blocks, "block letters must appear in the header")
        # Compact header: logo + title line so the screen fits in 30 terminal rows.
        self.assertLessEqual(len(head), 10, "header must stay compact")
        text = "\n".join(head)
        self.assertIn("NEX CLI", text)
        self.assertIn("NNL Assistant", text)

    def test_boot_theme_exists_and_is_purple(self):
        from vliw.ui import theme as t

        th = t.load_theme("nnl-purple")
        self.assertEqual(th.name, "nnl-purple")
        self.assertEqual(th.role("banner").color, 135)
        self.assertEqual(th.role("banner_alt").color, 183)
        self.assertEqual(th.role("border").color, 61)


class TestExplainDispatch(unittest.TestCase):
    def test_terminal_gets_interactive_welcome(self):
        from vliw.ui import setup_screen

        with mock.patch.object(setup_screen, "_tty", return_value=True), \
                mock.patch.object(setup_screen, "welcome", return_value=7) as welcome:
            self.assertEqual(setup_screen.explain("reason"), 7)
        welcome.assert_called_once_with("reason")


if __name__ == "__main__":
    unittest.main()
