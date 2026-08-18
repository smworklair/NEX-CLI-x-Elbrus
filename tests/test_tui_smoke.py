"""Смоук-тест полноэкранного интерфейса: экраны поднимаются, команды доходят.

Зачем отдельный тест, если есть глазами
---------------------------------------
`vliw.tui.available()` требует настоящий tty, поэтому в скрипте и в CI
`python -m vliw` полноэкранный режим НЕ поднимает — он молча откатывается в
построчный, и «проверка» ничего не доказывает. Здесь приложение гоняется
headless через тестовый харнесс Textual (`App.run_test()`): экраны реально
монтируются, нажатия реально доходят до строки ввода, команды реально
выполняются ядром.

Что именно ловится: развалившийся `compose()`, потерянный `nex.tcss` или тема,
отвалившийся мост к ядру (`tui/bridge.py`) и любое исключение при монтировании
— то есть ровно тот класс поломок, который в построчном режиме не виден.

Textual — НЕОБЯЗАТЕЛЬНАЯ зависимость (без него инструмент работает, только без
полноэкранного режима), поэтому без него тест пропускается, а не падает.
"""

from __future__ import annotations

import asyncio
import io
import unittest
from contextlib import redirect_stdout

try:
    import textual  # noqa: F401

    HAS_TEXTUAL = True
except Exception:  # pragma: no cover - зависит от окружения
    HAS_TEXTUAL = False

from vliw import cli
from vliw.ui import render


def _make_app(start_mode):
    """Приложение и сессия — собранные ровно так же, как в `cli.run_tui()`."""
    from vliw.tui.app import NexApp

    args = cli._build_parser().parse_args([])
    session = cli.Session(args=args)
    cli._apply_mode(session, start_mode or "lab")
    app = NexApp(session, lambda line: cli.handle_input(session, line),
                 cli.COMMANDS, start_mode=start_mode)
    return app, session


@unittest.skipUnless(HAS_TEXTUAL, "textual не установлен — полноэкранный режим не проверяем")
class TestScreensMount(unittest.TestCase):
    """Каждый экран должен подниматься без исключений."""

    def _mounts(self, start_mode, expect_cls):
        async def run():
            app, _ = _make_app(start_mode)
            # Команды печатают отчёты в stdout; в тесте он нам не нужен.
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(120, 40)) as pilot:
                    await pilot.pause()
                    return app.screen.__class__.__name__

        self.assertEqual(asyncio.run(run()), expect_cls)

    def test_picker(self):
        self._mounts(None, "PickerScreen")

    def test_lab(self):
        self._mounts("lab", "LabScreen")

    def test_work(self):
        self._mounts("work", "CoreScreen")

    def test_mind(self):
        self._mounts("mind", "AgentScreen")


@unittest.skipUnless(HAS_TEXTUAL, "textual не установлен — полноэкранный режим не проверяем")
class TestPickerNavigation(unittest.TestCase):
    def test_arrow_and_enter_open_mode(self):
        """Стрелка + Enter на экране выбора уводят в рабочий режим."""
        async def run():
            app, _ = _make_app(None)
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(120, 40)) as pilot:
                    await pilot.pause()
                    start = app.screen.__class__.__name__
                    await pilot.press("down", "enter")
                    await pilot.pause()
                    await pilot.pause()
                    return start, app.screen.__class__.__name__

        start, got = asyncio.run(run())
        self.assertEqual(start, "PickerScreen")
        self.assertNotEqual(got, "PickerScreen", "экран выбора не сменился")


@unittest.skipUnless(HAS_TEXTUAL, "textual не установлен — полноэкранный режим не проверяем")
class TestCommandsReachCore(unittest.TestCase):
    """Набранная строка должна дойти до ядра и изменить состояние сессии."""

    @staticmethod
    def _type(start_mode, line):
        async def run():
            app, session = _make_app(start_mode)
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(120, 40)) as pilot:
                    await pilot.pause()
                    await pilot.press(*line, "enter")
                    await pilot.pause()
                    # Команды экрана уходят в рабочий поток (@work(thread=True)
                    # в screens/base.py), а /run внутри ещё и запускает точный
                    # поиск с бюджетом до 10 с. Ждём именно завершения воркеров:
                    # без этого проверка гонится с невыполненной командой.
                    await app.workers.wait_for_complete()
                    await pilot.pause()
            return session

        return asyncio.run(run())

    def test_run_switches_scenario(self):
        session = self._type("lab", "/run mulclash")
        self.assertEqual(session.scenario, "mulclash")

    def test_interpreter_line_reaches_workspace(self):
        """В режиме ядра обычная строка — не команда, а запись интерпретатора."""
        session = self._type("work", "sum 8")
        self.assertIsNotNone(session._workspace)

    def test_theme_command_switches_theme(self):
        """`/theme` меняет палитру всего инструмента — задевает reload_palette()."""
        before = render.THEME.name
        try:
            self._type("lab", "/theme kilo")
            self.assertEqual(render.THEME.name, "kilo")
        finally:
            render.apply_theme(before)

    def test_unknown_scenario_does_not_kill_screen(self):
        """Кривая команда — сообщение, а не падение интерфейса.

        Ядро бросает SystemExit на неизвестном сценарии; ловит его мост
        (`tui/bridge.py`) и отдаёт экрану как текст ошибки.
        """
        session = self._type("lab", "/run nosuchscenario")
        self.assertNotEqual(session.scenario, "nosuchscenario")


if __name__ == "__main__":
    unittest.main()
