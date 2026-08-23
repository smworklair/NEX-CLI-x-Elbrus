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

    def test_code(self):
        self._mounts("code", "CodeScreen")


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
                    target = sc._cursor_target()
                    out = {
                        "cursor_cycle": target[1] if target else None,
                        "cursor_port": cur.column,
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

        Проверяем ТАКТ, а не номер строки: простои схлопнуты, и строка
        решётке больше не равна такту. Именно ради этого и заведён
        `_cursor_target()` — он единственный знает про схлопывание.
        """
        got = self._run()
        self.assertEqual((got["cursor_cycle"], got["cursor_port"]), (22, 0))

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


@unittest.skipUnless(HAS_TEXTUAL, "textual не установлен — полноэкранный режим не проверяем")
class TestMaximizedPanelFillsScreen(unittest.TestCase):
    """Развёрнутая панель занимает экран, а не остаётся полосой посреди него.

    Найдено на скриншоте пользователя: у половины панелей высота задана числом
    по id (#p-console: 10, #p-detail: 9, #p-seen: 12), и своя высота никуда не
    девалась при развороте — по специфичности id побеждает класс `-maximized`,
    который вешает Textual. Панель с фиксированной высотой повисала узкой
    полосой в пустом экране. Разворачивают как раз такие панели: в них текст
    не помещается.
    """

    def _size(self, panel_id: str) -> tuple[int, int]:
        async def go():
            app, _ = _make_app("lab")
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(150, 46)) as pilot:
                    await pilot.pause()
                    from vliw.tui.widgets import Panel

                    panel = app.screen.query_one(panel_id, Panel)
                    app.screen.maximize(panel, container=False)
                    await pilot.pause()
                    await pilot.pause()
                    return panel.size.width, panel.size.height

        return asyncio.run(go())

    def test_fixed_height_panel_still_fills_screen(self) -> None:
        """#p-console объявлен высотой 10 — развёрнутый обязан быть во весь экран."""
        _w, h = self._size("#p-console")
        self.assertGreater(h, 30, "панель осталась полосой вместо разворота")

    def test_flexible_panel_unaffected(self) -> None:
        _w, h = self._size("#p-grid")
        self.assertGreater(h, 30)


@unittest.skipUnless(HAS_TEXTUAL, "textual не установлен — полноэкранный режим не проверяем")
class TestCursorAI(unittest.TestCase):
    """ИИ в РАЗБОРЕ подключён к курсору, а не к строке ввода.

    Решение по интерфейсу: у этого экрана уже есть способ спросить — курсор.
    Человек показывает на клетку, панель «ПОЧЕМУ ЗДЕСЬ» отвечает точно, а ИИ
    дописывает фразу обычным языком. Поле ввода рядом заставляло бы
    ПЕРЕСПРАШИВАТЬ словами то, на что уже показали курсором.

    Модель здесь не запускается: проверяется механика — отмена по движению,
    задержка перед запуском и узость подсказки.
    """

    def _screen(self, body):
        async def go():
            app, _ = _make_app("lab")
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(150, 46)) as pilot:
                    await pilot.pause()
                    await pilot.pause()
                    return await body(app.screen, pilot)

        return asyncio.run(go())

    def test_lab_asks_from_below_not_from_the_side(self) -> None:
        """Спрашивают снизу, а не колонкой сбоку.

        Колонка (PanelChat) отбирала треть ширины у решётки — ровно у того,
        ради чего панель и разворачивают. Всплывающая строка снизу ширины не
        отбирает, поэтому её получает каждая панель, а колонки нет ни у
        одной. Факты при этом собираются по ТЕМЕ открытой панели, а не «всё
        про сессию»: спрашивают всегда про то, на что смотрят.
        """

        async def body(sc, pilot):
            from vliw.tui.widgets import Panel, PanelChat, PanelPrompt

            panel = sc.query_one("#p-grid", Panel)
            sc.maximize(panel, container=False)
            panel.post_message(Panel.Expanded(panel))
            for _ in range(6):
                await pilot.pause(0.05)
            await pilot.press("tab")          # справочник — только по Tab
            for _ in range(4):
                await pilot.pause(0.05)
            return (len(list(sc.query(PanelChat))),
                    len(list(sc.query(PanelPrompt))),
                    sc.panel_facts("grid"),
                    sc.panel_chips("grid"),
                    sc.panel_chips("machine"))

        chats, prompts, facts, grid_chips, machine_chips = self._screen(body)
        self.assertEqual(chats, 0, "колонка сбоку не должна появляться")
        self.assertEqual(prompts, 1, "строка снизу должна появиться")
        self.assertTrue(facts, "панели есть что рассказать про себя")
        self.assertTrue(any("решётк" in f.lower() for f in facts),
                        "факты должны быть про решётку, а не вообще")
        # Готовые вопросы у панелей разные: общий список на все панели был бы
        # тем же боковым чатом, только без колонки.
        self.assertTrue(grid_chips and machine_chips)
        self.assertNotEqual(grid_chips, machine_chips)

    def test_cursor_move_invalidates_previous_answer(self) -> None:
        """Ушёл с клетки — прежний ответ снят, а не дописывается к чужой."""

        async def body(sc, pilot):
            sc._cell_ai_token = 5
            sc._cell_ai_text = "старый ответ"
            sc._cell_ai_state = "готово"
            sc._cell_ai_restart()
            await pilot.pause()
            return sc._cell_ai_token, sc._cell_ai_text, sc._cell_ai_state

        tok, text, state = self._screen(body)
        self.assertEqual(tok, 6)
        self.assertEqual(text, "")
        self.assertEqual(state, "")

    def test_stale_request_cannot_write(self) -> None:
        """Запрос с чужим номером молчит, даже если успел вернуться."""

        async def body(sc, pilot):
            sc._cell_ai_token = 9
            sc._cell_ai_piece(3, "ответ от прошлой клетки")
            await pilot.pause()
            return sc._cell_ai_text

        self.assertEqual(self._screen(body), "")

    def test_ai_starts_only_after_the_cursor_rests(self) -> None:
        """Запуск не на каждое нажатие стрелки: иначе очередь брошенных задач.

        Здесь проверяется не число, а сам факт задержки: без неё быстрая
        прокрутка решётки на двадцать тактов подняла бы двадцать запросов к
        модели, каждый по несколько секунд и шесть потоков.
        """
        from vliw.tui.screens.lab_screen import LabScreen

        self.assertGreaterEqual(LabScreen.CELL_AI_DELAY, 1.0)

    def test_cell_prompt_is_a_retelling_not_a_reasoning_task(self) -> None:
        """В подсказку уходит только разбор панели, и считать запрещено."""
        from vliw.agent import context

        prompt = context.cell_prompt(["store out #12 стоит в такте 22 на порту ,0",
                                      "STORE исполняют только ,2 и ,5"])
        self.assertIn("store out #12", prompt)
        self.assertIn("НИ ОДНОГО числа, которого нет", prompt)
        self.assertNotIn("ФАКТЫ (единственный источник чисел)", prompt)
        self.assertLess(len(prompt), 1500)


@unittest.skipUnless(HAS_TEXTUAL, "textual не установлен — полноэкранный режим не проверяем")
class TestDiagGridBridge(unittest.TestCase):
    """Разворот ДИАГНОЗА и РЕШЁТКИ — два разных режима, связанные переходом.

    ДИАГНОЗ развёрнутый показывает находки целиком (без потолка top-5) и
    кликом уводит на клетку в РЕШЁТКЕ; РЕШЁТКА развёрнутая мостиком уводит
    обратно на ту же находку. Ни то ни другое не открывает общий чат сбоку
    (см. TestCursorAI.test_lab_has_no_side_chat — тот же принцип для панели
    grid, здесь для diag).
    """

    def _screen(self, body):
        async def go():
            app, _ = _make_app("lab")
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(150, 46)) as pilot:
                    await pilot.pause()
                    await pilot.pause()
                    return await body(app.screen, pilot)

        return asyncio.run(go())

    def test_expanded_diag_lists_every_finding_not_just_top_five(self) -> None:
        from vliw.tui.widgets import Panel

        async def body(sc, pilot):
            from vliw.tui.screens.lab_screen import FindingItem

            panel = sc.query_one("#p-diag", Panel)
            sc.maximize(panel, container=False)
            panel.post_message(Panel.Expanded(panel))
            await pilot.pause()
            rows = list(sc.query(FindingItem))
            return len(rows), len(sc._findings())

        rows, total = self._screen(body)
        self.assertGreater(total, 0, "у slotclash должны быть находки")
        self.assertEqual(rows, total)

    def test_no_side_chat_when_diag_maximized(self) -> None:
        """То же решение, что и для решётки: здесь свой режим, не чат."""
        from vliw.tui.widgets import Panel, PanelChat

        async def body(sc, pilot):
            panel = sc.query_one("#p-diag", Panel)
            sc.maximize(panel, container=False)
            panel.post_message(Panel.Expanded(panel))
            for _ in range(6):
                await pilot.pause(0.05)
            return len(list(sc.query(PanelChat)))

        self.assertEqual(self._screen(body), 0)

    def test_click_on_finding_jumps_grid_and_maximizes_it(self) -> None:
        from vliw.tui.widgets import Panel

        async def body(sc, pilot):
            from vliw.tui.screens.lab_screen import FindingItem

            diag = sc.query_one("#p-diag", Panel)
            sc.maximize(diag, container=False)
            diag.post_message(Panel.Expanded(diag))
            await pilot.pause()
            row = sc.query(FindingItem).first()
            f = sc._filtered_findings()[row.index]
            row.post_message(FindingItem.Picked(row.index))
            await pilot.pause()
            return sc.screen.maximized.id, sc._active_finding(), f

        maxed_id, active, picked = self._screen(body)
        self.assertEqual(maxed_id, "p-grid")
        self.assertEqual(active, picked)

    def test_grid_link_jumps_back_to_diag_on_same_finding(self) -> None:
        from vliw.tui.widgets import Panel

        async def body(sc, pilot):
            from vliw.tui.screens.lab_screen import GridLink

            grid = sc.query_one("#p-grid", Panel)
            sc.maximize(grid, container=False)
            grid.post_message(Panel.Expanded(grid))
            sc._find_pos = -1
            sc._cmd_find("next")          # курсор на первую находку
            await pilot.pause()
            f_before = sc._active_finding()
            link = sc.query_one("#grid-link", GridLink)
            self.assertTrue(link.active, "мостик должен включиться под находкой")
            link.post_message(GridLink.Picked())
            await pilot.pause()
            return sc.screen.maximized.id, sc._active_finding(), f_before

        maxed_id, after, before = self._screen(body)
        self.assertEqual(maxed_id, "p-diag")
        self.assertEqual(after, before)

    def test_find_command_cycles_through_distinct_findings(self) -> None:
        """`/find next` обходит весь список по разу и ставит курсор верно.

        Не у каждой находки есть своя клетка (например «23 т. против нижней
        границы» — про расписание целиком, без instrs): для таких курсор не
        трогаем. Но там, где клетка есть (idle-stall или instrs), после
        перехода курсор обязан стоять ровно на ней.
        """
        async def body(sc, pilot):
            findings = sc._filtered_findings()
            out = []
            for _ in range(len(findings)):
                sc._cmd_find("next")
                await pilot.pause()
                out.append((sc._find_pos, sc._active_finding()))
            return findings, out

        findings, out = self._screen(body)
        self.assertEqual(sorted(pos for pos, _ in out), list(range(len(findings))))
        for pos, active in out:
            f = findings[pos]
            if f.code == "idle-stall" or f.instrs:
                self.assertEqual(active, f,
                    f"находка {f.code} {f.where} не подсветилась после /find")




@unittest.skipUnless(HAS_TEXTUAL, "textual не установлен — полноэкранный режим не проверяем")
class TestPanelPromptIsAgentic(unittest.TestCase):
    """Всплывающая строка панели отвечает НАСТОЯЩИМ агентом, а не облегчённой копией.

    Раньше `_panel_prompt_worker` строил свой собственный узкий промпт и звал
    голый `llm.stream` — ни одного действия агент оттуда сделать не мог.
    Теперь это тот же `Agent.ask_stream`, что ведёт ДИАЛОГ в АГЕНТЕ: спросить
    «переключись на X» можно из всплывающей строки ЛЮБОЙ панели.
    """

    def _screen(self, body, mode="lab"):
        async def go():
            app, session = _make_app(mode)
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(150, 46)) as pilot:
                    await pilot.pause()
                    await pilot.pause()
                    return await body(app.screen, pilot, session)

        return asyncio.run(go())

    def test_scenario_switch_from_popup_does_not_crash_and_updates_screen(self) -> None:
        """Регрессия: действие агента меняло сценарий, `redraw()` падал IndexError.

        `redraw()` красит уже посчитанное — единственный прежний вызывающий,
        `repaint()`, зовёт его при смене темы, когда `self.base` и
        `session.dag_obj` гарантированно согласованы. Действие агента уводит
        `session.dag_obj` вперёд раньше, чем в РАЗБОРЕ пересчитается
        `self.base` — звать `redraw()` напрямую значило читать старое
        расписание для нового графа. На mulclash (другое число инструкций)
        это падало `IndexError` в `_render_grid`. Правильный хук —
        `after_command()`: он либо ничего не делает, либо (в РАЗБОРЕ) сам
        запускает пересчёт в фоне.
        """
        import unittest.mock as mock

        from vliw.agent import llm
        from vliw.tui.widgets import Panel, PanelPrompt

        def fake_stream(system, q, history=None, temperature=0.3, nudge=True):
            yield "готово"

        async def body(sc, pilot, session):
            panel = sc.query_one("#p-machine", Panel)
            sc.maximize(panel, container=False)
            panel.post_message(Panel.Expanded(panel))
            await pilot.pause()
            await pilot.pause()
            # Справочник приходит только по Tab — сам он не выскакивает.
            await pilot.press("tab")
            await pilot.pause()
            await pilot.pause()
            pp = sc.query_one(PanelPrompt)
            inp = pp.query_one("#pp-input")
            with mock.patch.object(llm, "stream", fake_stream):
                inp.value = "переключись на mulclash и сравни"
                await pilot.press("enter")
                for _ in range(30):
                    await pilot.pause(0.05)
            return session.scenario

        scenario = self._screen(body)
        self.assertEqual(scenario, "mulclash")

    def test_clear_wipes_answer_log_but_keeps_facts_and_chips(self) -> None:
        """`/clear` — не закрытие: факты и готовые вопросы остаются на месте."""
        import unittest.mock as mock

        from vliw.agent import llm
        from vliw.tui.widgets import Panel, PanelPrompt

        def fake_stream(system, q, history=None, temperature=0.3, nudge=True):
            yield "короткий ответ"

        async def body(sc, pilot, session):
            panel = sc.query_one("#p-numbers", Panel)
            sc.maximize(panel, container=False)
            panel.post_message(Panel.Expanded(panel))
            await pilot.pause()
            await pilot.pause()
            # Справочник приходит только по Tab — сам он не выскакивает.
            await pilot.press("tab")
            await pilot.pause()
            await pilot.pause()
            pp = sc.query_one(PanelPrompt)
            inp = pp.query_one("#pp-input")
            with mock.patch.object(llm, "stream", fake_stream):
                inp.value = "почему предел такой?"
                await pilot.press("enter")
                for _ in range(20):
                    await pilot.pause(0.05)
            lines_before = len(list(pp.query(".pp-line")))
            facts_before = len(pp.facts)
            inp.value = "/clear"
            await pilot.press("enter")
            await pilot.pause()
            return (lines_before, len(list(pp.query(".pp-line"))),
                    facts_before, len(pp.facts),
                    pp.query_one("#pp-answer").display)

        before, after, facts_before, facts_after, log_visible = self._screen(body)
        self.assertGreater(before, 0)
        self.assertEqual(after, 0)
        self.assertEqual(facts_before, facts_after)
        self.assertFalse(log_visible)

    def test_close_key_is_printed_not_only_a_tooltip(self) -> None:
        """Клавиша закрытия видна текстом — подсказка по наведению мышью в
        терминале не видна ни на скриншоте, ни без мыши."""
        from vliw.tui.widgets import Panel, PanelPrompt

        async def body(sc, pilot, session):
            panel = sc.query_one("#p-machine", Panel)
            sc.maximize(panel, container=False)
            panel.post_message(Panel.Expanded(panel))
            await pilot.pause()
            await pilot.pause()
            # Справочник приходит только по Tab — сам он не выскакивает.
            await pilot.press("tab")
            await pilot.pause()
            await pilot.pause()
            pp = sc.query_one(PanelPrompt)
            return pp.query_one("#pp-close").content.plain

        text = self._screen(body)
        self.assertIn("Esc", text)


@unittest.skipUnless(HAS_TEXTUAL, "textual не установлен — полноэкранный режим не проверяем")
class TestConsoleJournalIsATerminal(unittest.TestCase):
    """Развёрнутый ВЫВОД КОМАНД — живой терминал, а не список для чтения.

    Глобальная строка ввода остаётся доступной, пока панель развёрнута
    (`ALLOW_IN_MAXIMIZED_VIEW`), и команда, набранная там, обязана сразу
    появиться в журнале — иначе разворот выглядит терминалом только на
    словах: набрал команду, а видишь по-прежнему старый запуск.
    """

    def test_new_run_while_maximized_jumps_to_it(self) -> None:
        async def go():
            app, session = _make_app("lab")
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(150, 46)) as pilot:
                    await pilot.pause()
                    await pilot.pause()
                    sc = app.screen
                    sc.handle_line("/doctor")
                    for _ in range(12):
                        await pilot.pause()

                    from vliw.tui.widgets import Panel, PromptBar

                    panel = sc.query_one("#p-console", Panel)
                    sc.maximize(panel, container=False)
                    panel.post_message(Panel.Expanded(panel))
                    await pilot.pause()
                    await pilot.pause()

                    bar = sc.query_one("#prompt", PromptBar)
                    bar.focus_input()
                    bar.set_value("/bounds")
                    await pilot.press("enter")
                    for _ in range(12):
                        await pilot.pause()

                    journal = sc.query_one("#journal")
                    return len(journal.runs), journal.pos

            return None

        n, pos = asyncio.run(go())
        self.assertEqual(n, 2)
        self.assertEqual(pos, 1, "после набора второй команды журнал обязан "
                                 "показывать именно её, а не первую")


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(HAS_TEXTUAL, "textual не установлен — полноэкранный режим не проверяем")
class TestMachineMatrixIsInteractive(unittest.TestCase):
    """Развёрнутая МАШИНА — таблица, которой манипулируют, а не только читают.

    Клик по заголовку столбца пересортировывает строки, живой текстовый
    фильтр прячет несовпавшие операции. Раньше матрица была вычисленной, но
    ФИКСИРОВАННОЙ таблицей — ровно тем самым «большим окном с выводом»,
    который и в свёрнутом виде можно было пересказать столбиком.
    """

    def _screen(self, body):
        async def go():
            app, session = _make_app("lab")
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(150, 46)) as pilot:
                    await pilot.pause()
                    await pilot.pause()
                    return await body(app.screen, pilot)

        return asyncio.run(go())

    def test_header_click_toggles_sort(self) -> None:
        from textual.widgets import DataTable
        from textual.widgets._data_table import ColumnKey
        from vliw.tui.widgets import Panel

        async def body(sc, pilot):
            panel = sc.query_one("#p-machine", Panel)
            sc.maximize(panel, container=False)
            panel.post_message(Panel.Expanded(panel))
            await pilot.pause()
            table = sc.query_one("#machine-matrix", DataTable)
            default_order = list(sc._matrix_ops)
            sc.on_data_table_header_selected(
                DataTable.HeaderSelected(table, ColumnKey("op"), 0, None))
            await pilot.pause()
            by_name = list(sc._matrix_ops)
            # Клик по тому же столбцу второй раз — переворачивает направление.
            sc.on_data_table_header_selected(
                DataTable.HeaderSelected(table, ColumnKey("op"), 0, None))
            await pilot.pause()
            by_name_rev = list(sc._matrix_ops)
            return default_order, by_name, by_name_rev

        default_order, by_name, by_name_rev = self._screen(body)
        self.assertEqual(by_name, sorted(by_name))
        self.assertEqual(by_name_rev, sorted(by_name, reverse=True))
        self.assertNotEqual(default_order, by_name,
                            "сортировка по умолчанию (по числу операций) не "
                            "совпадает с алфавитной — иначе клик было бы не "
                            "проверить")

    def test_live_filter_hides_non_matching_rows(self) -> None:
        from vliw.tui.widgets import Panel

        async def body(sc, pilot):
            panel = sc.query_one("#p-machine", Panel)
            sc.maximize(panel, container=False)
            panel.post_message(Panel.Expanded(panel))
            await pilot.pause()
            inp = sc.query_one("#machine-filter")
            inp.focus()
            inp.value = "div"
            await pilot.pause()
            return list(sc._matrix_ops)

        ops = self._screen(body)
        self.assertEqual(ops, ["DIV"])


class TestDialogIsAWorkspace(unittest.TestCase):
    """Развёрнутый ДИАЛОГ — рабочая область: история вопросов + /clear.

    Долгое время разворот ДИАЛОГА был просто лентой покрупнее — ровно то,
    за что критиковали остальные панели до переделки. Теперь слева история
    вопросов с их счётом, клик повторяет вопрос, а `/clear` стирает ленту,
    не покидая режим (история остаётся: чистится разговор, не работа).
    """

    def _screen(self, body):
        async def go():
            app, session = _make_app("mind")
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(150, 46)) as pilot:
                    await pilot.pause()
                    await pilot.pause()
                    return await body(app.screen, pilot, session)

        return asyncio.run(go())

    def test_clear_wipes_dialog_but_keeps_history(self) -> None:
        """`/clear` в АГЕНТЕ чистит ленту диалога, а не уводит к выбору режима.

        Лента растёт и при активном использовании занимает весь экран.
        Раньше /clear означал «покинуть режим» — стереть разговор, не
        уходя, было нельзя вообще.
        """
        from textual.widgets import Static

        async def body(sc, pilot, session):
            sc._asked = [{"q": "почему медленно?", "seconds": 14.0, "acts": 2}]
            for _ in range(6):
                sc._bubble(Static("сообщение", classes="msg-note"))
            before = len(list(sc.chat.children))
            sc.submit_line("/clear")
            await pilot.pause()
            return (before, len(list(sc.chat.children)), len(sc._asked))

        before, after, asked = self._screen(body)
        self.assertGreater(before, 1)
        self.assertLessEqual(after, 2, "лента должна стереться до приветствия")
        self.assertEqual(asked, 1, "история вопросов должна остаться")

    def test_expanded_dialog_shows_history_column(self) -> None:
        from vliw.tui.widgets import Panel

        async def body(sc, pilot, session):
            sc._asked = [{"q": "почему медленно?", "seconds": 14.0, "acts": 2}]
            panel = sc.query_one("#p-chat", Panel)
            sc.maximize(panel, container=False)
            panel.post_message(Panel.Expanded(panel))
            await pilot.pause()
            await pilot.pause()
            return (sc.query_one("#chat-hist-col").display,
                    len(list(sc.query(".hist-item"))),
                    "/clear" in panel._title)

        shown, items, title = self._screen(body)
        self.assertTrue(shown, "колонка истории видна при развороте")
        self.assertEqual(items, 1)
        self.assertTrue(title, "клавиша очистки напечатана в заголовке")

    def test_tab_opens_ai_reference_and_it_does_not_come_uninvited(self) -> None:
        """Справочник ИИ приходит ТОЛЬКО по Tab и по нему же уходит.

        Раньше он выскакивал сам при развороте: панель разворачивают, чтобы
        работать в ней, и чужая строка снизу в этот момент только мешает.
        Проверяем обе половины: сразу после разворота его нет, Tab поднимает,
        Tab убирает.
        """
        from vliw.tui.widgets import Panel, PanelPrompt

        async def body(sc, pilot, session):
            panel = sc.query_one("#p-seen", Panel)
            sc.maximize(panel, container=False)
            panel.post_message(Panel.Expanded(panel))
            for _ in range(4):
                await pilot.pause(0.05)
            uninvited = len(list(sc.query(PanelPrompt)))
            await pilot.press("tab")
            for _ in range(3):
                await pilot.pause(0.05)
            opened = len(list(sc.query(PanelPrompt)))
            await pilot.press("tab")
            for _ in range(3):
                await pilot.pause(0.05)
            return uninvited, opened, len(list(sc.query(PanelPrompt)))

        uninvited, opened, closed = self._screen(body)
        self.assertEqual(uninvited, 0, "справочник не должен приходить сам")
        self.assertEqual(opened, 1, "Tab должен его поднять")
        self.assertEqual(closed, 0, "Tab должен его убрать")


@unittest.skipUnless(HAS_TEXTUAL, "textual не установлен — полноэкранный режим не проверяем")
class TestEscapeIsOneStepBack(unittest.TestCase):
    """Esc везде значит одно: шаг наружу, вплоть до начального экрана.

    Раньше он значил три разных вещи в зависимости от фокуса (закрыть
    справочник / переключить решётка⇄ввод / уйти к выбору режима), причём
    поверх всего этого Textual перехватывал Esc ЕЩЁ РАНЬШЕ любых биндингов,
    когда панель развёрнута (`App.ESCAPE_TO_MINIMIZE`), и схлопывал её сам —
    минуя наш обработчик и не посылая `Panel.Collapsed`.
    """

    def test_escape_unwinds_level_by_level(self) -> None:
        from vliw.tui.screens.picker import PickerScreen
        from vliw.tui.widgets import Panel, PanelPrompt

        async def go():
            app, _ = _make_app("lab")
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(150, 46)) as pilot:
                    await pilot.pause()
                    await pilot.pause()
                    sc = app.screen
                    panel = sc.query_one("#p-machine", Panel)
                    sc.maximize(panel, container=False)
                    panel.post_message(Panel.Expanded(panel))
                    await pilot.pause()
                    await pilot.pause()
                    await pilot.press("tab")
                    await pilot.pause()
                    await pilot.pause()
                    steps = [len(list(sc.query(PanelPrompt)))]

                    await pilot.press("escape")     # 1: убрать справочник
                    await pilot.pause()
                    await pilot.pause()
                    steps.append((len(list(sc.query(PanelPrompt))),
                                  sc.maximized is not None))

                    await pilot.press("escape")     # 2: свернуть панель
                    await pilot.pause()
                    await pilot.pause()
                    steps.append((app.screen.maximized is None,
                                  app.screen.__class__.__name__))

                    await pilot.press("escape")     # 3: к выбору режима
                    await pilot.pause()
                    await pilot.pause()
                    steps.append(isinstance(app.screen, PickerScreen))
                    return steps

        opened, after_first, after_second, after_third = asyncio.run(go())
        self.assertEqual(opened, 1, "Tab должен был поднять справочник")
        # Первый Esc снимает ТОЛЬКО справочник — панель обязана остаться
        # развёрнутой, иначе один Esc проскакивает через два уровня.
        self.assertEqual(after_first, (0, True))
        self.assertEqual(after_second, (True, "LabScreen"))
        self.assertTrue(after_third, "третий Esc — на начальный экран")


@unittest.skipUnless(HAS_TEXTUAL, "textual не установлен — полноэкранный режим не проверяем")
class TestGridKeyboardTools(unittest.TestCase):
    """Развёрнутая решётка управляется клавишами, а не строкой кнопок.

    Строка «тегов» над расписанием режется по краям и дублирует подсказки.
    Вместо неё: клавиши при фокусе решётки + правая колонка-инспектор,
    где список клавиш и состояние слоёв видно всегда.
    """

    def _screen(self, body):
        async def go():
            app, _ = _make_app("lab")
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(150, 46)) as pilot:
                    await pilot.pause()
                    await pilot.pause()
                    return await body(app.screen, pilot)

        return asyncio.run(go())

    def _maximize_grid(self, sc):
        from vliw.tui.screens.lab_screen import ScheduleGrid
        from vliw.tui.widgets import Panel

        panel = sc.query_one("#p-grid", Panel)
        sc.maximize(panel, container=False)
        panel.post_message(Panel.Expanded(panel))
        sc.query_one("#grid", ScheduleGrid).focus()

    def test_side_inspector_is_drawn(self) -> None:
        """Правая колонка не пустует: курсор и клавиши заполнены."""
        from textual.widgets import Static

        async def body(sc, pilot):
            self._maximize_grid(sc)
            for _ in range(4):
                await pilot.pause(0.05)
            cursor = sc.query_one("#side-cursor", Static).content.plain
            legend = sc.query_one("#side-legend", Static).content.plain
            return cursor, legend

        cursor, legend = self._screen(body)
        self.assertTrue(cursor.strip(), "инспектор курса пуст")
        self.assertIn("n / N", legend, "в легенде нет списка клавиш")

    def test_tool_keys_act_on_focused_grid(self) -> None:
        """v/z/[ ] — инструменты прямо с клавиатуры; фокус остаётся в решётке."""

        async def body(sc, pilot):
            self._maximize_grid(sc)
            for _ in range(3):
                await pilot.pause(0.05)
            before = sc.view
            await pilot.press("v")
            await pilot.pause()
            after = sc.view
            await pilot.press("z")
            await pilot.pause()
            deps_on = sc._deps_on
            from vliw.tui.screens.lab_screen import ScheduleGrid

            focused = sc.focused is sc.query_one("#grid", ScheduleGrid) \
                or sc.query_one("#grid", ScheduleGrid).has_focus
            return before, after, deps_on, focused

        before, after, deps_on, focused = self._screen(body)
        self.assertNotEqual(before, after, "v не переключил вид")
        self.assertTrue(deps_on, "z не включил слой соседей")
        self.assertTrue(focused, "фокус сбежал из решётки после инструмента")


@unittest.skipUnless(HAS_TEXTUAL, "textual не установлен — полноэкранный режим не проверяем")
class TestTerminalHasCommandCatalog(unittest.TestCase):
    """Развёрнутый ВЫВОД КОМАНД — терминал с каталогом, а не поле для слепого набора.

    Команд три десятка, и держать их в голове (или лезть за ними в /docs,
    теряя развёрнутый экран) — ровно та работа, которую инструмент должен
    делать за человека.
    """

    def _term(self, body, seed=("/doctor",)):
        async def go():
            app, session = _make_app("lab")
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(150, 46)) as pilot:
                    await pilot.pause()
                    await pilot.pause()
                    sc = app.screen
                    for line in seed:
                        sc.handle_line(line)
                        for _ in range(14):
                            await pilot.pause()

                    from vliw.tui.widgets import ConsoleJournal, Panel

                    panel = sc.query_one("#p-console", Panel)
                    sc.maximize(panel, container=False)
                    panel.post_message(Panel.Expanded(panel))
                    await pilot.pause()
                    await pilot.pause()
                    return await body(sc, pilot,
                                      sc.query_one(ConsoleJournal), session)

        return asyncio.run(go())

    def test_catalog_lists_every_command(self) -> None:
        from vliw.tui.widgets import CommandItem

        async def body(sc, pilot, j, session):
            return len(list(j.query(CommandItem))), len(cli.COMMANDS)

        shown, total = self._term(body)
        self.assertEqual(shown, total, "в каталоге должны быть все команды")

    def test_typing_filters_catalog_by_first_word_only(self) -> None:
        """Фильтр берёт только имя команды: «run slotclash» — это всё ещё /run.

        Если фильтровать по всей строке, каталог пустеет ровно в тот момент,
        когда команда набрана правильно и с аргументом.
        """
        from vliw.tui.widgets import CommandItem

        async def body(sc, pilot, j, session):
            inp = j.query_one("#journal-input")
            inp.focus()
            inp.value = "do"
            await pilot.pause()
            await pilot.pause()
            narrowed = [c.line.split()[0] for c in j.query(CommandItem)]
            inp.value = "/run slotclash"
            await pilot.pause()
            await pilot.pause()
            with_arg = [c.line.split()[0] for c in j.query(CommandItem)]
            return narrowed, with_arg

        narrowed, with_arg = self._term(body)
        self.assertIn("/doctor", narrowed)
        self.assertLess(len(narrowed), len(cli.COMMANDS))
        # Совпадения с начала имени — первыми: «do» ищут ради /doctor, а не
        # ради /random, где «do» просто попалось в середине (ran-do-m).
        self.assertEqual(narrowed[0], "/doctor")
        self.assertIn("/run", with_arg)

    def test_failed_run_is_marked(self) -> None:
        """Провалившийся запуск не должен выглядеть как удачный."""

        async def body(sc, pilot, j, session):
            return [(r["cmd"], bool(r.get("error"))) for r in j.runs]

        runs = self._term(body, seed=("/doctor", "/run nosuchscenario"))
        self.assertEqual(len(runs), 2)
        self.assertFalse(runs[0][1], "/doctor отработал — пометки быть не должно")
        self.assertTrue(runs[1][1], "неизвестный сценарий обязан быть помечен")

    def test_history_walks_previous_commands(self) -> None:
        from vliw.tui.widgets import JournalInput

        async def body(sc, pilot, j, session):
            inp = j.query_one("#journal-input", JournalInput)
            inp.focus()
            await pilot.press("up")
            await pilot.pause()
            return inp.value

        self.assertEqual(self._term(body, seed=("/doctor", "/bounds")),
                         "/bounds")

    def test_clicking_a_command_inserts_it_without_running(self) -> None:
        """Клик подставляет, но не запускает: у половины команд есть аргумент."""
        from vliw.tui.widgets import CommandItem

        async def body(sc, pilot, j, session):
            before = len(j.runs)
            item = next(c for c in j.query(CommandItem)
                        if c.line.startswith("/run "))
            item.post_message(CommandItem.Picked(item.line))
            await pilot.pause()
            await pilot.pause()
            return j.query_one("#journal-input").value, before, len(j.runs)

        value, before, after = self._term(body)
        self.assertTrue(value.startswith("/run "))
        self.assertEqual(before, after, "клик не должен запускать команду")


@unittest.skipUnless(HAS_TEXTUAL, "textual не установлен — полноэкранный режим не проверяем")
class TestCodeScreen(unittest.TestCase):
    """КОД: редактор обязан ЗНАТЬ, что в нём написано.

    Разница между этим режимом и текстовым полем с логом ровно в этом: буфер
    разбирается на лету, расписание стоит в гуттере у своей строки, а `^R`
    переписывает код по точному поиску. Каждая из трёх вещей и проверяется —
    остальное (цвета, рамки) не сломается молча, а это сломается.
    """

    @staticmethod
    def _screen(body, run=False):
        """Поднять КОД, при желании прогнать буфер, отдать тело теста экрану."""
        async def go():
            app, session = _make_app("code")
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(150, 46)) as pilot:
                    await pilot.pause()
                    screen = app.screen
                    if run:
                        screen.action_run_code()
                        await app.workers.wait_for_complete()
                        await pilot.pause()
                        await pilot.pause()
                    return await body(screen, pilot, session)

        return asyncio.run(go())

    def test_buffer_is_parsed_without_running_anything(self):
        """Разбор идёт при открытии: расписание видно до всякого F5."""
        async def body(screen, pilot, session):
            return (len(screen.parsed.ops),
                    screen.comp.makespan,
                    [p for p in screen.problems if p.severity == "error"])

        ops, makespan, errors = self._screen(body)
        self.assertGreater(ops, 0, "буфер по умолчанию не разобрался")
        self.assertGreater(makespan, 0)
        self.assertEqual(errors, [], "пример по умолчанию обязан быть законным")

    def test_gutter_carries_the_schedule(self):
        """У строки с операцией в гуттере стоит её такт, а не просто номер."""
        async def body(screen, pilot, session):
            edit = screen.query_one("#code-edit")
            op = screen.parsed.ops[0]
            return edit._marks.get(op.line - 1), op.cycle

        mark, cycle = self._screen(body)
        self.assertIsNotNone(mark, "у первой операции нет метки расписания")
        self.assertIn(f"т{cycle}", mark[0])

    def test_typing_reaches_the_buffer(self):
        """Буквы обязаны печататься — это редактор, а не витрина.

        Тест дословный, потому что поломка была ровно такая: перехваченный
        `TextArea._on_key` объявлен `async`, обычное переопределение
        проглатывало корутину родителя, и редактор молча переставал
        принимать ввод. Ни один тест «экран поднялся» этого не видит.
        """
        async def body(screen, pilot, session):
            edit = screen.query_one("#code-edit")
            edit.focus()
            edit.move_cursor(edit.document.end)
            await pilot.press("a", "d", "d", "s")
            await pilot.pause()
            return edit.text.rstrip()

        self.assertTrue(self._screen(body).endswith("adds"))

    def test_cursor_move_redraws_the_line_panel(self):
        """Переезд курсора разбирает НОВУЮ строку, а не держит старую."""
        async def body(screen, pilot, session):
            op = screen.parsed.ops[2]
            screen.query_one("#code-edit").goto_line(op.line)
            await pilot.pause()
            await pilot.pause()
            info = screen.query_one("#code-line-info").content
            return op.line, str(info)

        line, info = self._screen(body)
        self.assertIn(f"СТРОКА {line}", info)
        self.assertIn("латентность", info)

    def test_run_fills_the_oracle_and_the_moves(self):
        """F5 доводит до конца: точный поиск, находки и список перестановок."""
        async def body(screen, pilot, session):
            return (screen.orc is not None, len(screen._moves()),
                    screen.comp.makespan,
                    screen.orc.schedule.makespan if screen.orc else None)

        have, moves, src, orc = self._screen(body, run=True)
        self.assertTrue(have, "после F5 нет результата точного поиска")
        self.assertLess(orc, src, "пример обязан иметь резерв")
        self.assertGreater(moves, 0, "нечего переставлять — список пуст")

    def test_rewrite_produces_a_buffer_that_matches_the_oracle(self):
        """^R пишет код, а не совет: переписанный буфер обязан пере-разбираться.

        Самая дорогая ошибка этого действия — выдать текст, который сам себя
        не читает (потерянный `nop`, канал не из матрицы). Поэтому проверка
        сквозная: переписали → разобрали заново → длина совпала с той, что
        обещал точный поиск, и ни одной ошибки линтера.
        """
        async def body(screen, pilot, session):
            promised = screen.orc.schedule.makespan
            # Именно клавишей: F5/F6 приоритетные, и проверить их стоит на
            # том же фокусе, что у человека, — курсор стоит в редакторе, а
            # TextArea забирает себе почти все нажатия.
            screen.query_one("#code-edit").focus()
            await pilot.press("f6")
            await pilot.pause()
            await pilot.pause()
            return (promised, screen.comp.makespan if screen.comp else None,
                    [p.text for p in screen.problems if p.severity == "error"],
                    screen.query_one("#code-edit").text)

        promised, got, errors, text = self._screen(body, run=True)
        self.assertEqual(errors, [], "переписанный буфер обязан быть законным")
        self.assertEqual(got, promised,
                         "переписали не в то расписание, которое обещали")
        self.assertIn("muls,", text)

    def test_editing_marks_the_search_result_as_stale(self):
        """Правка буфера обязана обесценить прошлые числа, а не молчать."""
        async def body(screen, pilot, session):
            before = screen._stale()
            edit = screen.query_one("#code-edit")
            edit.text = edit.text + "{\n  adds,0 %r90, %r91, %r92\n}\n"
            screen.reparse()
            await pilot.pause()
            return before, screen._stale()

        before, after = self._screen(body, run=True)
        self.assertFalse(before, "сразу после прогона числа свежие")
        self.assertTrue(after, "после правки числа относятся к другому тексту")

    def test_clicking_a_problem_moves_the_cursor_to_its_line(self):
        """Замечание — ссылка: клик ведёт курсор на ту самую строку."""
        from vliw.tui.screens.code_screen import LintItem, SEED_BROKEN

        async def body(screen, pilot, session):
            screen.panel_tool("code-broken")
            await pilot.pause()
            await pilot.pause()
            items = list(screen.query(LintItem))
            target = next(i for i in items if i.line)
            target.post_message(LintItem.Picked(target.line))
            await pilot.pause()
            await pilot.pause()
            return target.line, screen.query_one("#code-edit").cursor_location[0] + 1

        line, cursor = self._screen(body)
        self.assertEqual(cursor, line)

    def test_buffer_where_nothing_parsed_still_says_so(self):
        """Буфер, в котором не разобралась ни одна строка, — не «всё хорошо».

        Самый частый первый опыт: человек вставил не то или набрал по памяти.
        Замечания разбора обязаны показываться и тогда, когда операций ноль,
        иначе экран молча выглядит как чистый.
        """
        async def body(screen, pilot, session):
            edit = screen.query_one("#code-edit")
            edit.text = "{\n  ??? какой-то текст\n}\n"
            screen.reparse()
            await pilot.pause()
            return [(p.line, p.kind) for p in screen.problems]

        self.assertEqual(self._screen(body), [(2, "parse")])

    def test_broken_example_is_actually_caught(self):
        """Пример «с ошибками» обязан ловиться линтером, а не просто лежать."""
        async def body(screen, pilot, session):
            screen.panel_tool("code-broken")
            await pilot.pause()
            await pilot.pause()
            return sorted({p.kind for p in screen.problems
                           if p.severity == "error"})

        self.assertEqual(self._screen(body), ["busy", "channel", "ready"])
