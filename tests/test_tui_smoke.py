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




@unittest.skipUnless(HAS_TEXTUAL, "textual не установлен — полноэкранный режим не проверяем")
class TestPanelMaximize(unittest.TestCase):
    """Двойной клик по панели разворачивает её на весь экран.

    Панелей на экране семь, и в каждой либо решётка тактов, либо длинный
    отчёт — в своей трети экрана они читаются с трудом. Двойной клик
    определяется по времени вручную: в Textual 8.2 у события Click нет поля
    `chain` (счётчика кликов подряд), только `time`.
    """

    @staticmethod
    def _click(panel, t):
        panel.on_click(type("E", (), {"time": t, "stop": lambda self: None})())

    def _run(self, steps):
        async def go():
            app, _ = _make_app("lab")
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(120, 40)) as pilot:
                    await pilot.pause()
                    from vliw.tui.widgets import Panel

                    panel = app.screen.query_one("#p-grid", Panel)
                    return await steps(app, pilot, panel)

        return asyncio.run(go())

    def test_single_click_does_not_maximize(self):
        async def steps(app, pilot, panel):
            self._click(panel, 100.0)
            await pilot.pause()
            return app.screen.maximized

        self.assertIsNone(self._run(steps))

    def test_double_click_maximizes_that_panel(self):
        async def steps(app, pilot, panel):
            self._click(panel, 100.0)
            self._click(panel, 100.2)
            await pilot.pause()
            return app.screen.maximized

        got = self._run(steps)
        self.assertIsNotNone(got, "панель не развернулась")
        self.assertEqual(got.id, "p-grid", "развернулась не та панель")

    def test_slow_second_click_is_not_double(self):
        """Два клика с большим зазором — не двойной клик, а два одиночных."""
        async def steps(app, pilot, panel):
            self._click(panel, 100.0)
            self._click(panel, 105.0)
            await pilot.pause()
            return app.screen.maximized

        self.assertIsNone(self._run(steps))

    def test_escape_minimizes(self):
        """Esc сворачивает — и это не ломает свой Esc у экрана РАЗБОР."""
        async def steps(app, pilot, panel):
            self._click(panel, 100.0)
            self._click(panel, 100.2)
            await pilot.pause()
            before = app.screen.maximized
            await pilot.press("escape")
            await pilot.pause()
            return before, app.screen.maximized

        before, after = self._run(steps)
        self.assertIsNotNone(before)
        self.assertIsNone(after)

if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(HAS_TEXTUAL, "textual не установлен — полноэкранный режим не проверяем")
class TestModelViewIsLive(unittest.TestCase):
    """Живой прогон модели в решётке РАЗБОРА.

    Проверяется то, чего построчный режим показать не может: решётка
    заполняется ПО ХОДУ генерации, незаконная клетка находится сама, а
    починка остаётся отдельным действием. Модель здесь не запускается —
    события подаются напрямую, поэтому тест идёт за миллисекунды и не
    требует ни весов, ни llama.cpp.

    Ответ взят с настоящего прогона `slotclash` (адаптер lora-eos): двенадцать
    законных размещений и STORE #12 на канал `,0`, который его не исполняет.
    """

    ANSWER = [(0, 0, 1), (1, 0, 5), (2, 2, 5), (3, 13, 1), (4, 17, 1),
              (5, 18, 1), (6, 19, 1), (7, 11, 1), (8, 0, 4), (9, 1, 1),
              (10, 20, 1), (11, 21, 1), (12, 22, 0)]

    def _run(self, repair: bool = False) -> dict:
        """Прогнать ответ модели событиями и снять показания.

        Всё — внутри `run_test()`: снаружи виджеты уже отвязаны от приложения,
        и обращение к ним падает с `NoActiveAppError`. Поэтому наружу уходят
        только числа и строки, а не сами виджеты.
        """
        from vliw.core import Placed, Repaired, Started
        from vliw.core.schedule import Placement

        async def go():
            app, _ = _make_app("lab")
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(150, 46)) as pilot:
                    await pilot.pause()
                    sc = app.screen
                    sc.on_scheduler_event(Started("learned", "модель"))
                    for i, cycle, ch in self.ANSWER:
                        sc.on_scheduler_event(
                            Placed(Placement(i, cycle, ch), live=True))
                    placed_live = len(sc.model_sched.placements)
                    sc.on_scheduler_event(Repaired(12, 0, 2))
                    sc._model_done(None)
                    await pilot.pause()
                    cur = sc.query_one("#grid").cursor_coordinate
                    out = {
                        "view": sc.view,
                        "placed_live": placed_live,
                        "illegal": sorted(sc._model_illegal()),
                        "cell": sc._first_illegal_cell(),
                        "cursor": (cur.row, cur.column),
                        "repairs": list(sc.model_repairs),
                        "before": sc.model_sched.placements[12],
                    }
                    if repair:
                        sc._repair_model()
                        out["after"] = sc.model_sched.placements[12]
                        out["illegal_after"] = sorted(sc._model_illegal())
                    return out

        return asyncio.run(go())

    def test_view_switches_to_model_and_grid_fills(self) -> None:
        got = self._run()
        self.assertEqual(got["view"], "model")
        self.assertEqual(got["placed_live"], len(self.ANSWER))

    def test_illegal_channel_is_found(self) -> None:
        """STORE на `,0` — незаконно, и это видно решётке, а не только отчёту."""
        got = self._run()
        self.assertEqual(got["illegal"], [12])
        self.assertEqual(got["cell"], (22, 0))

    def test_cursor_lands_on_the_illegal_cell(self) -> None:
        """Курсор сам встаёт на ошибку — иначе она за краем экрана.

        На `slotclash` ошибка модели в такте 22 из 23: без этого шага
        заголовок пишет «незаконных 1», а увидеть её можно, только
        пролистав двадцать два такта вниз.
        """
        got = self._run()
        self.assertEqual(got["cursor"], (22, 0))

    def test_repair_is_a_separate_action(self) -> None:
        """Само по себе ничего не чинится: сырой ответ остаётся сырым."""
        got = self._run()
        self.assertEqual(got["illegal"], [12])
        self.assertEqual(got["repairs"], [(12, 0, 2)])

    def test_repair_command_fixes_channel_and_keeps_cycle(self) -> None:
        """`/repair` меняет канал и НЕ трогает такт — makespan остаётся её же."""
        got = self._run(repair=True)
        self.assertEqual(got["illegal_after"], [])
        self.assertEqual(got["after"].cycle, got["before"].cycle)
        self.assertEqual(got["after"].channel, 2)
