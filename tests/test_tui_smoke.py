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

    def test_home_is_the_picker_but_code_is_the_main_screen(self):
        """Запуск — выбор режима; КОД остаётся главным экраном по смыслу.

        Это два РАЗНЫХ решения, и их однажды спутали. КОД главный: он
        единственный, куда человек приносит своё, и остальные экраны стали
        вкладками его дока. Но СТАРТОВАТЬ прямо в нём оказалось ловушкой —
        человек попадает в редактор и не знает, что экранов четыре, потому
        что выход на ^O нигде не показан. Выбор режима стоит одного нажатия
        и сразу отвечает, что тут вообще есть.
        """
        from vliw.tui.app import NexApp

        self.assertEqual(NexApp.HOME, "code", "главным остаётся КОД")
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
        """Стрелка + Enter на списке экранов уводят на выбранный.

        Список открывается по ^O из работы, а не встречает на входе:
        рабочее место — КОД, отсюда только уходят.
        """
        async def run():
            app, _ = _make_app(None)
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(120, 40)) as pilot:
                    await pilot.pause()
                    await pilot.press("ctrl+o")
                    await pilot.pause()
                    await pilot.pause()
                    start = app.screen.__class__.__name__
                    await pilot.press("down", "enter")
                    await pilot.pause()
                    await pilot.pause()
                    return start, app.screen.__class__.__name__

        start, got = asyncio.run(run())
        self.assertEqual(start, "PickerScreen", "^O не открыл список экранов")
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
class TestLabRightColumnFits(unittest.TestCase):
    """Правая колонка РАЗБОРА помещается на экран целиком.

    Найдено на скриншоте: длинный ответ ИИ в «ПОЧЕМУ ЗДЕСЬ» распирал панель,
    ДИАГНОЗ сжимался в одну рамку, а МАШИНА уезжала за нижний край. Потолки
    высоты и прокрутка внутри панели обязаны держать все четыре панели в
    кадре при любом объёме текста.
    """

    def test_machine_stays_on_screen_with_long_detail(self) -> None:
        from rich.text import Text

        async def go():
            app, _ = _make_app("lab")
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(150, 46)) as pilot:
                    await pilot.pause()
                    sc = app.screen
                    sc._cell_ai_token += 1
                    # Длинный разбор — как после развёрнутого ответа ИИ.
                    sc._set_detail(Text(
                        "\n".join(f"строка разбора {i}" for i in range(40))))
                    await pilot.pause()
                    await pilot.pause()
                    mach = sc.query_one("#p-machine")
                    bottom = mach.region.y + mach.region.height
                    return bottom, sc.size.height

        bottom, screen_h = asyncio.run(go())
        self.assertLessEqual(bottom, screen_h,
                             "МАШИНА уехала за нижний край экрана")

    def test_command_line_lives_inside_git(self) -> None:
        """Командная строка — внутри GIT, а не большой полосой внизу."""
        from vliw.tui.widgets import PromptBar

        async def go():
            app, _ = _make_app("lab")
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(150, 46)) as pilot:
                    await pilot.pause()
                    sc = app.screen
                    bar = sc.query_one("#prompt", PromptBar)
                    dock = sc.query("#dock")
                    git = sc.query_one("#p-console")
                    inside = git.region.overlaps(bar.region)
                    return inside, len(list(dock)), bar.display

        inside, docks, shown = asyncio.run(go())
        self.assertTrue(inside, "строка ввода не внутри панели GIT")
        self.assertEqual(docks, 0, "большой нижний док должен исчезнуть")
        self.assertTrue(shown)


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

    Командная строка в РАЗБОРЕ одна: пока журнал развёрнут, это ЕГО строка
    (панельная спрятана — две одинаковых рядом только путают). Команда,
    набранная в ней, обязана сразу появиться в журнале — иначе разворот
    выглядит терминалом только на словах: набрал команду, а видишь по-
    прежнему старый запуск.
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

                    from vliw.tui.widgets import ConsoleJournal, Panel, PromptBar

                    panel = sc.query_one("#p-console", Panel)
                    sc.maximize(panel, container=False)
                    panel.post_message(Panel.Expanded(panel))
                    await pilot.pause()
                    await pilot.pause()

                    # Панельная строка спрятана — командная теперь одна.
                    self.assertFalse(sc.query_one("#prompt", PromptBar).display,
                                     "в развороте не должно быть двух строк")
                    inp = sc.query_one("#journal-input")
                    inp.focus()
                    inp.value = "/bounds"
                    await pilot.press("enter")
                    for _ in range(12):
                        await pilot.pause()

                    journal = sc.query_one("#journal", ConsoleJournal)
                    return len(journal.runs), journal.pos

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
        # «div» находит ОБА делителя — целочисленный и с плавающей точкой.
        # Раньше ждали ровно ["DIV"], потому что второго в модели не было;
        # измерение 30.08.2026 показало, что fdivd исполняется на том же
        # единственном порту ,5. Фильтр не сломался — он честно показывает
        # обоих претендентов на монопольный порт, а это ровно то, ради чего
        # на матрицу и смотрят.
        self.assertEqual(ops, ["DIV", "FDIV"])

    def test_filter_narrows_to_a_single_row(self) -> None:
        """Фильтр обязан уметь и до одной строки — иначе он не фильтр."""
        from vliw.tui.widgets import Panel

        async def body(sc, pilot):
            panel = sc.query_one("#p-machine", Panel)
            sc.maximize(panel, container=False)
            panel.post_message(Panel.Expanded(panel))
            await pilot.pause()
            inp = sc.query_one("#machine-filter")
            inp.focus()
            inp.value = "store"
            await pilot.pause()
            return list(sc._matrix_ops)

        self.assertEqual(self._screen(body), ["STORE"])


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
        """Переезд курсора разбирает НОВУЮ строку, а не держит старую.

        Полоса состояния меняется всегда, полный разбор — только когда
        вкладка СТРОКА открыта: закрытая вкладка не должна стоить отрисовки
        на каждое нажатие стрелки.
        """
        async def body(screen, pilot, session):
            op = screen.parsed.ops[2]
            screen.open_drawer("line")
            screen.query_one("#code-edit").goto_line(op.line)
            await pilot.pause()
            await pilot.pause()
            return (op.line,
                    str(screen.query_one("#code-line-chip").content),
                    str(screen.query_one("#code-line-info").content),
                    str(screen.query_one("#dock-note").content))

        line, chip, info, note = self._screen(body)
        self.assertIn(f"стр.{line}", chip)
        self.assertIn("латентность", info)
        self.assertIn(str(line), note)

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
        from vliw.tui.screens.code_screen import LintItem

        async def body(screen, pilot, session):
            screen.handle_line("/example broken")
            await pilot.pause()
            # Замечания живут во вкладке выдвижной панели: пока она закрыта,
            # их и не рисуют — так же, как в IDE не рисуют закрытый Problems.
            screen.open_drawer("lint")
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

    def test_dock_opens_on_the_schedule_and_f12_takes_it_away(self):
        """Док открыт на РАСПИСАНИИ, F12 убирает его — и код занимает всё.

        Два требования разом, и второе важнее первого. Расписание видно
        сразу, без клавиши, о которой надо знать: это ответ на вопрос, ради
        которого экран и открывают. Но панели независимы — убрал док, и
        редактор работает дальше, просто во весь экран. Пока снизу было ДВА
        окна, убрать их было нечем: расписание стояло всегда.
        """
        async def body(screen, pilot, session):
            open_at_start = (screen.drawer_open, screen.drawer_tab,
                             screen.query_one("#code-dock").display,
                             screen.query_one("#dock-sched").display)
            tall_with_dock = screen.query_one("#code-edit").size.height
            await pilot.press("f12")
            await pilot.pause()
            hidden = (screen.drawer_open,
                      screen.query_one("#code-dock").display)
            tall_without = screen.query_one("#code-edit").size.height
            await pilot.press("f12")
            await pilot.pause()
            return (open_at_start, tall_with_dock, hidden, tall_without,
                    screen.drawer_open)

        start, tall, hidden, without, back = self._screen(body)
        self.assertEqual(start, (True, "sched", True, True))
        self.assertEqual(hidden, (False, False))
        self.assertGreater(without, tall,
                           "без дока редактор обязан занять его место")
        self.assertTrue(back, "F12 обязан возвращать док")

    def test_ctrl_p_opens_the_terminal_tab(self):
        """^P — команда: панель на ОТЧЁТЕ, слэш уже введён.

        Клавиша именно непечатная: фокус в КОДЕ почти всегда в редакторе, и
        «/» там обязан оставаться символом — иначе командой не открыть
        терминал никогда, а слэш перестанет печататься.
        """
        async def body(screen, pilot, session):
            screen.query_one("#code-edit").focus()
            await pilot.press("ctrl+p")
            await pilot.pause()
            return (screen.drawer_open, screen.drawer_tab,
                    screen.query_one("#prompt").input.value)

        opened, tab, value = self._screen(body)
        self.assertTrue(opened)
        self.assertEqual(tab, "term")
        self.assertEqual(value, "/")

    def test_slash_inside_a_line_is_just_a_character(self):
        """«/» посреди строки печатается: отбирать у текста знак нельзя.

        А в НАЧАЛЕ пустой строки он открывает каталог команд — см. тест
        ниже. Различение по столбцу возможно потому, что в ассемблере e2k
        строка со слэша не начинается никогда: комментарий это «!», а
        операция — мнемоника.
        """
        async def body(screen, pilot, session):
            edit = screen.query_one("#code-edit")
            edit.focus()
            edit.move_cursor(edit.document.end)
            edit.insert("adds,0 %r1")      # курсор не в нулевой колонке
            await pilot.pause()
            await pilot.press("slash")
            await pilot.pause()
            return edit.text.endswith("/"), screen.drawer_tab

        typed, tab = self._screen(body)
        self.assertTrue(typed, "слэш не напечатался посреди строки")
        self.assertEqual(tab, "sched",
                         "набор в редакторе не должен переключать вкладку")

    def test_slash_at_line_start_suggests_the_commands(self):
        """«/» в пустой строке — список команд у курсора.

        До этого каталог жил только на ^P, про который надо знать, — а «/»
        люди жмут первым делом, потому что так работает почти везде. Команды
        при этом есть: /gen, /fill, /example, /rewrite, и найти их было
        неоткуда.

        Раньше проверялось, что слэш НЕ печатается, а открывается нижняя
        панель. Так было хуже вдвойне: список уезжал вниз экрана, далеко от
        курсора, а набранный символ пропадал — дописать «/gen 8 muls» одной
        строкой становилось нельзя. Теперь слэш печатается, а команды
        подсказывает тот же всплывающий список, что дополняет мнемоники, —
        как дополнение кода в IDE. Смысл проверки тот же: «/» обязан
        показывать команды, а не молчать.
        """
        async def body(screen, pilot, session):
            edit = screen.query_one("#code-edit")
            edit.focus()
            edit.load_text("")
            await pilot.pause()
            await pilot.press("slash")
            await pilot.pause()
            sug = screen.query_one("#suggest")
            return edit.text, sug.display, [i[1] for i in sug.items]

        text, shown, labels = self._screen(body)
        self.assertEqual(text, "/", "слэш обязан напечататься")
        self.assertTrue(shown, "список команд не всплыл")
        # В метке рядом с именем стоят аргументы («/gen <сколько> …») —
        # ради них список и нужен, поэтому сверяем начало, а не равенство.
        heads = [l.split()[0] for l in labels]
        self.assertIn("/gen", heads, f"нет /gen среди {labels}")
        self.assertIn("/fill", heads, f"нет /fill среди {labels}")
        self.assertEqual(heads[:2], ["/gen", "/fill"],
                         "скрипты сокращения работы обязаны стоять первыми")

    def test_broken_example_is_actually_caught(self):
        """Пример «с ошибками» обязан ловиться линтером, а не просто лежать."""
        async def body(screen, pilot, session):
            screen.handle_line("/example broken")
            await pilot.pause()
            await pilot.pause()
            return sorted({p.kind for p in screen.problems
                           if p.severity == "error"})

        self.assertEqual(self._screen(body), ["busy", "channel", "ready"])


@unittest.skipUnless(HAS_TEXTUAL, "textual не установлен — полноэкранный режим не проверяем")
class TestJournalIsSessionBridge(unittest.TestCase):
    """Журнал — «гит сессии»: метка режима, мостик в ЯДРО, поток событий.

    Журнал общий на все экраны, и запись без пометки, ГДЕ она сделана, —
    просто текст. Метка режима, кнопки «в разбор / в агента / в ядро» и
    отдельная лента событий превращают его в место, откуда человек сам
    решает, что из сессии куда поедет.
    """

    @staticmethod
    def _journal(body):
        async def go():
            app, session = _make_app("lab")
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(150, 46)) as pilot:
                    await pilot.pause()
                    sc = app.screen
                    from vliw.tui.widgets import Panel

                    panel = sc.query_one("#p-console", Panel)
                    sc.maximize(panel, container=False)
                    panel.post_message(Panel.Expanded(panel))
                    await pilot.pause()
                    await pilot.pause()
                    return await body(sc, pilot, session)

        return asyncio.run(go())

    def test_run_records_its_mode(self) -> None:
        """Запись журнала помнит режим, в котором её сделали."""
        async def body(sc, pilot, session):
            sc.handle_line("/bounds")
            for _ in range(10):
                await pilot.pause()
            return session.journal_runs[-1].get("mode")

        self.assertEqual(self._journal(body), "lab")

    def test_bridge_to_core_is_present_and_works(self) -> None:
        """«В ядро» открывает ЯДРО и оставляет там пометку о прогоне."""
        async def body(sc, pilot, session):
            from vliw.tui.widgets import Tool

            sc.handle_line("/bounds")
            for _ in range(10):
                await pilot.pause()
            # Кнопка обязана существовать и быть видимой: мостик без графа
            # всё равно имеет смысл — контекст прогона нужен и ядру.
            tool = sc.query_one("#bridge-work", Tool)
            self.assertTrue(tool.display)
            sc.panel_tool("@work")
            await pilot.pause()
            await pilot.pause()
            return (sc.app.screen.__class__.__name__, session.pending_note)

        where, note = self._journal(body)
        self.assertEqual(where, "CoreScreen")
        # Пустая пометка после перехода — не потеря, а показ: ЯДРО гасит её
        # в on_ready (это отдельный тест ниже). Здесь важно, что мостик
        # довёл до другого режима и ничего не оставил висеть.
        self.assertEqual(note, "")

    def test_core_consumes_pending_note_on_mount(self) -> None:
        """Приехавшая в ЯДРО пометка показывается строкой листа, не теряется."""
        async def go():
            app, session = _make_app("work")
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(150, 46)) as pilot:
                    await pilot.pause()
                    sc = app.screen
                    sheet = sc.query_one("#tape-sheet")
                    before = len(list(sheet.children))
                    session.pending_note = "из журнала: прогон тест"
                    sc._take_pending_note()
                    await pilot.pause()
                    return (len(list(sheet.children)) > before,
                            session.pending_note)

        shown, rest = asyncio.run(go())
        self.assertTrue(shown, "пометка мостика не дошла до листа ЯДРА")
        self.assertEqual(rest, "", "пометка должна гаснуть после показа")

    def test_scheduler_text_goes_to_events_not_console(self) -> None:
        """Живой поток пишется в СОБЫТИЯ и не мешает отчётам команд.

        Экран нарочно КОД: у РАЗБОРА этот поток — содержимое решётки, там
        он переопределён и в ленту событий не попадает. Базовое поведение
        проверять честнее всего там, где переопределения нет.
        """
        async def go():
            app, session = _make_app("code")
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(150, 46)) as pilot:
                    await pilot.pause()
                    sc = app.screen
                    sc.on_scheduler_text("модель пишет расписание")
                    await pilot.pause()
                    journal = sc.query_one("#journal")
                    return (len(session.journal_events), len(journal.events),
                            journal._feed)

        n_session, n_journal, feed = asyncio.run(go())
        self.assertEqual(n_session, 1)
        self.assertEqual(n_journal, 1, "события обязаны доехать до журнала")
        self.assertEqual(feed, "runs", "по умолчанию показан поток команд")

    def test_events_feed_switches_and_renders(self) -> None:
        """Вкладка СОБЫТИЯ реально переключает правую колонку журнала."""
        async def go():
            app, session = _make_app("code")
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(150, 46)) as pilot:
                    await pilot.pause()
                    sc = app.screen
                    from vliw.tui.widgets import RichLog

                    sc.on_scheduler_text("строка потока")
                    await pilot.pause()
                    journal = sc.query_one("#journal")
                    journal.show_feed("events")
                    await pilot.pause()
                    out = sc.query_one("#journal-out", RichLog)
                    ev = sc.query_one("#events-out", RichLog)
                    return out.display, ev.display

        runs_visible, events_visible = asyncio.run(go())
        self.assertFalse(runs_visible, "при событиях отчёты обязаны прятаться")
        self.assertTrue(events_visible)

    def test_journal_reloads_after_command_finishes(self) -> None:
        """Открытый журнал видит мостик-поля прогона БЕЗ переоткрытия.

        Команда едет в фоне: запись появляется в ЗАПУСКАХ сразу, а граф
        проставляется только в конце. Если журнал не перечитывается после
        завершения, у свежего прогона навсегда спрятаны «в разбор / в
        агента» — мостик выглядит сломанным ровно на самом нужном прогоне.
        """
        async def body(sc, pilot, session):
            sc.handle_line("/bounds")
            for _ in range(14):
                await pilot.pause()
            await sc.app.workers.wait_for_complete()
            await pilot.pause()
            from vliw.tui.widgets import Tool

            lab_btn = sc.query_one("#bridge-lab", Tool)
            rec = session.journal_runs[-1]
            return lab_btn.display, rec.get("dag") is not None

        visible, has_dag = self._journal(body)
        self.assertTrue(has_dag, "граф не доехал до записи журнала")
        self.assertTrue(visible, "открытый журнал не показал мостик после "
                                 "завершения команды")

    def test_bridge_to_code_carries_the_source(self) -> None:
        """«В код» возвращает исходник прогона в буфер редактора."""
        async def body(sc, pilot, session):
            from vliw.tui.widgets import Tool

            session.journal_runs.append(
                {"cmd": "/code run", "lines": [], "error": False,
                 "mode": "code",
                 "code": "{\n  adds,0 %r1, %r2, %r3\n}\n",
                 "scenario": "буфер", "dag": None})
            sc.panel_tool("@code")
            await pilot.pause()
            await pilot.pause()
            screen = sc.app.screen
            return (screen.__class__.__name__,
                    session.code_text,
                    session.pending_note)

        where, text, note = self._journal(body)
        self.assertEqual(where, "CodeScreen")
        self.assertIn("adds,0", text, "исходник прогона не попал в буфер")
        # Пустая пометка — она уже показана строкой в отчёте КОДА (on_ready
        # гасит её, как и ЯДРО). Главное здесь — текст в буфере.
        self.assertEqual(note, "")

    def test_history_rows_look_like_commits(self) -> None:
        """История — не лог команд, а коммиты: граф, номер, время, состояние.

        Пользователь ищет «гит»: запись обязана отвечать на «что это было
        за состояние», а не только «что я набрал». Точка графа и линия —
        чтобы список читался как git log с первого взгляда.
        """
        async def body(sc, pilot, session):
            session.journal_runs.append(
                {"cmd": "/doctor", "lines": ["a", "b"], "error": False,
                 "mode": "lab", "time": "14:02",
                 "scenario": "slotclash", "dag": [1, 2, 3]})
            journal = sc.query_one("#journal")
            journal.load(session.journal_runs, "lab", [])
            await pilot.pause()
            text = journal._row(0, session.journal_runs[0]).plain
            return ("#1" in text, "14:02" in text,
                    "slotclash" in text, "3 оп." in text,
                    "●" in text, "│" in text)

        has_num, has_time, has_scen, has_ops, dot, line = self._journal(body)
        self.assertTrue(has_num, "в истории нет номера записи")
        self.assertTrue(has_time, "в истории нет времени прогона")
        self.assertTrue(has_scen, "в истории не видно участок")
        self.assertTrue(has_ops, "в истории не видно размер графа")
        self.assertTrue(dot, "в истории нет точки графа")
        self.assertTrue(line, "в истории нет линии графа")

    def test_restore_returns_state_without_leaving(self) -> None:
        """«Вернуть» — checkout: состояние прогона восстанавливается,
        экран остаётся текущим."""
        async def body(sc, pilot, session):
            from vliw.tui.widgets import Tool

            session.set_scenario("mulclash")
            session.journal_runs.append(
                {"cmd": "/run mulclash", "lines": [], "error": False,
                 "mode": "lab", "time": "14:02",
                 "scenario": "mulclash", "dag": session.dag_obj})
            before = session.scenario
            session.set_scenario("slotclash")
            sc.panel_tool("@restore")
            await pilot.pause()
            btn = sc.query_one("#bridge-restore", Tool)
            return before, session.scenario, btn.display, \
                sc.app.screen.__class__.__name__

        before, after, visible, where = self._journal(body)
        self.assertEqual(before, "mulclash")
        self.assertEqual(after, "mulclash",
                         "«вернуть» не восстановил участок прогона")
        self.assertTrue(visible)
        self.assertEqual(where, "LabScreen",
                         "«вернуть» не должен уводить с экрана")


@unittest.skipUnless(HAS_TEXTUAL, "textual не установлен — полноэкранный режим не проверяем")
class TestCoreHasTheJournalToo(unittest.TestCase):
    """Мостик обязан работать ИЗ ядра: журнал доступен и там.

    Раньше у ЯДРА журнала не было вовсе — единственное место сессии,
    откуда нельзя было ни вернуться к прошлому прогону, ни отправить
    результат дальше.
    """

    def test_tape_tool_opens_the_journal(self) -> None:
        async def go():
            app, session = _make_app("work")
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(150, 46)) as pilot:
                    await pilot.pause()
                    sc = app.screen
                    sc.panel_tool("tape-journal")
                    await pilot.pause()
                    await pilot.pause()
                    journal = sc.query_one("#journal")
                    return (sc._wide, journal.display,
                            app.screen.__class__.__name__)

        wide, visible, _ = asyncio.run(go())
        self.assertEqual(wide, "tape")
        self.assertTrue(visible, "журнал не открылся в ЛЕНТЕ")

    def test_journal_from_core_bridges_back_to_lab(self) -> None:
        """Из журнала ЯДРО прогон уезжает в РАЗБОР — полный круг."""
        async def go():
            app, session = _make_app("work")
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(150, 46)) as pilot:
                    await pilot.pause()
                    sc = app.screen
                    # Строка, меняющая состояние: чистая арифметика коммитом
                    # не бывает (журнал — история состояний, не нажатий).
                    sc.handle_line("x=load 0")
                    await pilot.pause()
                    sc.panel_tool("tape-journal")
                    await pilot.pause()
                    await pilot.pause()
                    sc.panel_tool("@lab")
                    await pilot.pause()
                    await pilot.pause()
                    return app.screen.__class__.__name__

        self.assertEqual(asyncio.run(go()), "LabScreen")


@unittest.skipUnless(HAS_TEXTUAL, "textual не установлен — полноэкранный режим не проверяем")
class TestCoreSheetAndCommits(unittest.TestCase):
    """Лист ЛЕНТЫ, фильтр коммитов и полный чекаут машины.

    Лист — главный вид ЛЕНТЫ: каждая строка человека с её итогом. В
    git-журнал попадают только строки, изменившие машину, — у записи
    лежит снимок машины, и «вернуть» восстанавливает её целиком.
    """

    def _screen(self, body):
        async def go():
            app, session = _make_app("work")
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(150, 46)) as pilot:
                    await pilot.pause()
                    await pilot.pause()
                    return await body(app.screen, pilot, session)

        return asyncio.run(go())

    def test_errors_and_view_verbs_are_not_commits(self) -> None:
        """Ошибки и служебные виды — не коммиты: журнал не лог нажатий."""
        async def body(sc, pilot, session):
            before = len(session.journal_runs)
            sc.handle_line("names")
            sc.handle_line("mul m0 a0 b0")   # ошибка: мнемоника e2k
            await pilot.pause()
            return (before, len(session.journal_runs),
                    [r["kind"] for r in sc._rows])

        before, after, kinds = self._screen(body)
        self.assertEqual(after, before,
                         "ошибки и views не должны попадать в git-журнал")
        self.assertIn("error", kinds, "ошибка обязана быть видна в листе")

    def test_arithmetic_that_adds_an_op_is_a_commit(self) -> None:
        """`2+2` кладёт в граф операцию — значит, это честный коммит."""
        async def body(sc, pilot, session):
            before = len(session.journal_runs)
            sc.handle_line("2+2")
            await pilot.pause()
            rec = session.journal_runs[-1]
            return (len(session.journal_runs) - before, rec["cmd"],
                    rec["dag"] is not None)

        added, cmd, has_dag = self._screen(body)
        self.assertEqual(added, 1, "строка с операцией обязана стать коммитом")
        self.assertEqual(cmd, "2+2")
        self.assertTrue(has_dag)

    def test_state_line_is_a_commit_with_graph_and_machine(self) -> None:
        """Строка, изменившая машину, — коммит с графом и снимком машины."""
        async def body(sc, pilot, session):
            sc.handle_line("a=10")
            sc.handle_line("x=load 0")
            await pilot.pause()
            rec = session.journal_runs[-1]
            return (rec["cmd"], rec["mode"], rec["scenario"],
                    rec["dag"] is not None,
                    sorted(rec["ws"]["regs"].items()),
                    rec["ws"]["mem"][:3])

        cmd, mode, scenario, has_dag, regs, mem = self._screen(body)
        self.assertEqual(cmd, "x=load 0")
        self.assertEqual(mode, "work")
        self.assertEqual(scenario, "interp")
        self.assertTrue(has_dag, "у коммита нет графа — мостик в РАЗБОР мёртв")
        self.assertIn(("a", 10), regs, "в снимке машины потерялись имена")
        self.assertEqual(mem, [1, 2, 3], "в снимке потерялась память")

    def test_reset_is_a_commit_and_names_only_line_is_not(self) -> None:
        """`reset` меняет машину — коммит; `names` ничего не меняет — нет."""
        async def body(sc, pilot, session):
            sc.handle_line("a=10")
            n1 = len(session.journal_runs)
            sc.handle_line("names")
            n2 = len(session.journal_runs)
            sc.handle_line("reset")
            await pilot.pause()
            rec = session.journal_runs[-1]
            return (n2 - n1, rec["cmd"], session.workspace().regs,
                    rec["ws"]["regs"])

        names_commits, cmd, regs, snap_regs = self._screen(body)
        self.assertEqual(names_commits, 0, "names — не коммит")
        self.assertEqual(cmd, "reset")
        self.assertEqual(regs, {}, "reset не очистил имена")
        self.assertEqual(snap_regs, {}, "в снимке reset остались имена")

    def test_restore_checks_out_the_whole_machine(self) -> None:
        """«Вернуть» восстанавливает имена И память, а не только граф."""
        async def body(sc, pilot, session):
            sc.handle_line("a=10; b=2")
            sc.handle_line("store 9 3")      # mem[3] = 9
            sc.handle_line("a=55")            # испортили имя
            journal = sc.query_one("#journal")
            journal.pos = 1                   # коммит «store 9 3»
            sc.panel_tool("@restore")
            await pilot.pause()
            ws = session.workspace()
            return (ws.regs.get("a"), ws.regs.get("b"), ws.mem[3])

        a, b, mem3 = self._screen(body)
        self.assertEqual((a, b, mem3), (10, 2, 9),
                         "«вернуть» не чекаутнуло машину целиком")

    def test_go_attaches_verdict_to_its_commit(self) -> None:
        """Вердикт `go` ложится в запись журнала числами (baseline/oracle)."""
        async def body(sc, pilot, session):
            sc.handle_line("x=load 0")
            rec = session.journal_runs[-1]
            base = type("R", (), {"schedule": type("S", (), {"makespan": 23})()})()
            orc = type("R", (), {"schedule": type("S", (), {"makespan": 22})()})()
            met = type("M", (), {"lower_bound": 22})()
            sc._verdict(base, orc, met)
            await pilot.pause()
            verdict_rows = [r for r in sc._rows if r["kind"] == "verdict"]
            return (rec.get("verdict"), len(verdict_rows),
                    any("baseline 23" in t.plain and "оракул 22" in t.plain
                        for t in rec["lines"]))

        verdict, n_rows, in_lines = self._screen(body)
        self.assertEqual(verdict, (23, 22), "числа вердикта не доехали до коммита")
        self.assertEqual(n_rows, 1, "вердикт обязан быть строкой листа")
        self.assertTrue(in_lines, "журнал обязан показать вердикт в выводе записи")

    def test_verdict_number_visible_in_journal_row(self) -> None:
        async def body(sc, pilot, session):
            session.journal_runs.append(
                {"cmd": "go", "lines": [], "error": False,
                 "mode": "work", "time": "14:02",
                 "scenario": "interp", "dag": [1], "verdict": (23, 22)})
            journal = sc.query_one("#journal")
            journal.load(session.journal_runs, "work", [])
            await pilot.pause()
            return "23→22" in journal._row(0, session.journal_runs[0]).plain

        self.assertTrue(self._screen(body),
                        "в строке журнала не видно итог прогона")

    def test_link_program_op_highlights_tape_row(self) -> None:
        """Клик по операции подсвечивает строку, которая её породила."""
        from vliw.tui.screens.core_screen import ProgramItem, TapeRow

        async def body(sc, pilot, session):
            sc.handle_line("x=load 0")
            sc.handle_line("y=x*2")
            await pilot.pause()
            items = list(sc.query(ProgramItem))
            mul = next(i for i in items if "y" in str(i.content))
            mul.post_message(ProgramItem.Picked(mul.node))
            await pilot.pause()
            rows = {r.index: r for r in sc.query(TapeRow)}
            on = [i for i, r in rows.items() if r.has_class("on")]
            hot = sum(1 for i in items if i.has_class("hot"))
            return (sc._link, on, hot)

        link, on, hot = self._screen(body)
        self.assertIsNotNone(link, "связка не включилась")
        self.assertEqual(link[0], "op")
        self.assertEqual(on, [1], "подсвечена не та строка листа")
        self.assertEqual(hot, 1, "подсветиться должна ровно одна операция")

    def test_link_tape_row_highlights_its_ops(self) -> None:
        from vliw.tui.screens.core_screen import ProgramItem, TapeRow

        async def body(sc, pilot, session):
            sc.handle_line("x=load 0")
            sc.handle_line("y=x*2")
            await pilot.pause()
            sc._set_link(("row", 1))
            await pilot.pause()
            items = list(sc.query(ProgramItem))
            return (sum(1 for i in items if i.has_class("hot")),
                    list(sc.query(TapeRow))[-1].has_class("on"))

        hot, on = self._screen(body)
        self.assertEqual(hot, 1, "строка y=x*2 положила в граф одну операцию")
        self.assertTrue(on, "выбранная строка листа не подсвечена")


@unittest.skipUnless(HAS_TEXTUAL, "textual не установлен — полноэкранный режим не проверяем")
class TestCodeStatusBarLaunchesDrawer(unittest.TestCase):
    """Строка состояния КОДА — лаунчер нижней панели, как в IDE.

    Пункты «замечания» и «отчёт» обязаны жить на виду, нести живые счётчики
    и открывать свою вкладку одним кликом: функциональность, спрятанная за
    клавишей, которую надо знать заранее, — это функциональность, которой
    нет.
    """

    @staticmethod
    def _screen(body):
        async def go():
            app, session = _make_app("code")
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(150, 46)) as pilot:
                    await pilot.pause()
                    return await body(app.screen, pilot, session)

        return asyncio.run(go())

    def test_chips_exist_with_live_counters(self) -> None:
        async def body(screen, pilot, session):
            lint = screen.query_one("#status-lint")
            term = screen.query_one("#status-term")
            return lint._label, term._label

        lint_label, term_label = self._screen(body)
        self.assertIn("чисто", lint_label)
        self.assertIn("git", term_label)

    def test_clicking_term_chip_opens_drawer_on_report_tab(self) -> None:
        from vliw.tui.screens.code_screen import DrawerChip

        async def body(screen, pilot, session):
            chip = screen.query_one("#status-term", DrawerChip)
            chip.post_message(DrawerChip.Picked("term"))
            await pilot.pause()
            await pilot.pause()
            return screen.drawer_open, screen.drawer_tab

        opened, tab = self._screen(body)
        self.assertTrue(opened)
        self.assertEqual(tab, "term")

    def test_counter_grows_after_a_command_from_another_mode(self) -> None:
        """Журнал общий: счётчик отчёта реагирует на чужие команды."""
        async def body(screen, pilot, session):
            before = screen.query_one("#status-term")._label
            session.journal_runs.append(
                {"cmd": "/run slotclash", "lines": [], "error": False,
                 "mode": "lab"})
            screen.refresh_status()
            after = screen.query_one("#status-term")._label
            return before, after

        before, after = self._screen(body)
        self.assertNotEqual(before, after,
                            "счётчик не увидел команду из другого режима")

    def test_bridge_row_in_drawer_sends_run_to_lab(self) -> None:
        """Мостик доступен БЕЗ разворота: вкладка ОТЧЁТ → «в разбор».

        Ровно тот сценарий, ради которого мостик существует: прогнал
        буфер в КОДЕ — и тут же отправил его в РАЗБОР, не догадываясь
        про разворот панели.
        """
        from vliw.tui.widgets import Tool

        async def body(screen, pilot, session):
            screen.open_drawer("term")
            await pilot.pause()
            session.journal_runs.append(
                {"cmd": "/code run", "lines": [], "error": False,
                 "mode": "code", "time": "14:02",
                 "scenario": "asm:буфер", "dag": session.dag_obj})
            screen._sync_drawer_bridge()
            await pilot.pause()
            row = screen.query_one("#drawer-bridge")
            row.sync(session.journal_runs, 0)
            await pilot.pause()
            btn = screen.query_one("#dbridge-lab", Tool)
            self.assertTrue(btn.display, "мостик не виден во вкладке ОТЧЁТ")
            btn.post_message(Tool.Picked("@lab"))
            await pilot.pause()
            await pilot.pause()
            return screen.app.screen.__class__.__name__

        where = self._screen(body)
        self.assertEqual(where, "LabScreen",
                         "прогон из КОДА не доехал до РАЗБОРА")

    def test_drawer_bridge_hidden_without_runs(self) -> None:
        """Пустая история — ряд мостика пуст: кнопки не обещают лишнего."""
        from vliw.tui.widgets import Tool

        async def body(screen, pilot, session):
            screen.open_drawer("term")
            await pilot.pause()
            btn = screen.query_one("#dbridge-lab", Tool)
            return btn.display

        self.assertFalse(self._screen(body),
                         "без прогонов мостик обязан прятаться")

    def test_double_click_on_a_dock_tab_zooms_the_dock(self) -> None:
        """Двойной клик по НАЗВАНИЮ вкладки разворачивает док и сворачивает.

        Тот же жест, что в IDE, и целятся в него именно в название вкладки.
        Полоса вкладок двойной клик тоже ловит (`DockTabs.on_click`), но
        только на голом промежутке между кнопками шириной в пару символов:
        `Tool.on_click` останавливает событие, и до полосы клик по самой
        вкладке не доходит вовсе. Полгода жест числился сделанным и не
        работал нигде, куда человек мог попасть.
        """
        from vliw.tui.widgets import Tool

        async def body(screen, pilot, session):
            dock = screen.query_one("#code-dock")
            tab = screen.query_one("#tab-lint", Tool)
            await pilot.click(tab)
            await pilot.pause()
            one = (screen.drawer_tab, screen.zoom, dock.size.height)
            await pilot.click(tab)
            await pilot.pause()
            two = (screen.zoom, dock.size.height)
            await pilot.click(tab)
            await pilot.click(tab)
            await pilot.pause()
            back = (screen.zoom, dock.size.height)
            # Медленные клики — не двойной: иначе спокойное переключение
            # вкладок туда-обратно случайно разворачивало бы док.
            await pilot.click(tab)
            await asyncio.sleep(0.6)
            await pilot.click(tab)
            await pilot.pause()
            return one, two, back, screen.zoom

        one, two, back, slow = self._screen(body)
        self.assertEqual(one[:2], ("lint", ""),
                         "одиночный клик обязан только переключать вкладку")
        self.assertEqual(two[0], "dock", "двойной клик не развернул док")
        self.assertGreater(two[1], one[2] * 2,
                           f"док не вырос: {one[2]} → {two[1]}")
        self.assertEqual(back, ("", one[2]),
                         "повторный двойной клик не свернул док обратно")
        self.assertEqual(slow, "", "два медленных клика — не двойной")


@unittest.skipUnless(HAS_TEXTUAL, "textual не установлен — полноэкранный режим не проверяем")
class TestCodeFilesAreTabs(unittest.TestCase):
    """Открытых буферов может быть несколько, и они не затирают друг друга.

    Пока буфер был один на сессию, «посмотреть пример» значило потерять свой
    код: `/example` писал прямо в него. Сравнение двух участков — своего и
    того, что выдал lcc, — при этом было невозможно вовсе, а это основная
    работа в инструменте.
    """

    @staticmethod
    def _screen(body):
        async def go():
            app, session = _make_app("code")
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(150, 46)) as pilot:
                    await pilot.pause()
                    return await body(app.screen, pilot, session)

        return asyncio.run(go())

    def test_example_opens_a_tab_and_does_not_eat_the_buffer(self) -> None:
        """Пример открывается вкладкой, а свой код остаётся на месте."""
        async def body(screen, pilot, session):
            edit = screen.query_one("#code-edit")
            edit.text = "{\n  adds,0 %r1, %r2, %r3\n}\n"
            screen.reparse()
            await pilot.pause()
            mine = edit.text
            screen.handle_line("/example divport")
            await pilot.pause()
            await pilot.pause()
            names = [r["name"] for r in screen.files]
            shown = edit.text
            # Назад на свою вкладку — текст обязан вернуться целиком.
            screen.select_file(0)
            await pilot.pause()
            return mine, names, shown, edit.text

        mine, names, shown, back = self._screen(body)
        self.assertEqual(len(names), 2, f"вкладок должно быть две: {names}")
        self.assertIn("divport.s", names)
        self.assertNotEqual(shown, mine, "пример не открылся")
        self.assertEqual(back, mine, "свой код потерян при переключении")

    def test_edits_survive_switching_between_tabs(self) -> None:
        """Правка запоминается за вкладкой, а не за экраном."""
        async def body(screen, pilot, session):
            edit = screen.query_one("#code-edit")
            screen.open_file("{\n  adds,0 %r1, %r2, %r3\n}\n", "второй.s")
            await pilot.pause()
            edit.text = edit.text + "! правка второго\n"
            screen.reparse()
            await pilot.pause()
            screen.select_file(0)
            await pilot.pause()
            first = edit.text
            screen.select_file(1)
            await pilot.pause()
            return first, edit.text

        first, second = self._screen(body)
        self.assertNotIn("правка второго", first,
                         "правка протекла в чужую вкладку")
        self.assertIn("правка второго", second, "правка не сохранилась")

    def test_the_last_tab_cannot_be_closed(self) -> None:
        """Пустого редактора без единого буфера быть не должно."""
        async def body(screen, pilot, session):
            screen.close_file(0)
            await pilot.pause()
            return len(screen.files)

        self.assertEqual(self._screen(body), 1)

    def test_catalog_on_the_left_opens_a_real_file(self) -> None:
        """Каталог слева — вход в работу: клик открывает файл вкладкой."""
        from vliw.tui.screens.code_screen import SideItem

        async def body(screen, pilot, session):
            item = next(i for i in screen.query(SideItem)
                        if i.key.endswith("probe.s"))
            item.post_message(SideItem.Picked(item.key))
            await pilot.pause()
            await pilot.pause()
            return ([r["name"] for r in screen.files],
                    screen.files[screen.file_i]["path"],
                    len(screen.query_one("#code-edit").text))

        names, path, size = self._screen(body)
        self.assertIn("probe.s", names)
        self.assertTrue(path.endswith("probe.s"),
                        f"путь не запомнен — ^S не будет знать, куда писать: {path}")
        self.assertGreater(size, 0, "файл открылся пустым")

    def test_gutter_arrow_runs_the_buffer(self) -> None:
        """Стрелка в гуттере — то же, что F5. Действие живёт у строки.

        Ряд текстовых кнопок над кодом убран, и если стрелка не работает,
        мышью прогнать буфер становится нечем.
        """
        from vliw.tui.screens.code_screen import AsmArea

        async def body(screen, pilot, session):
            edit = screen.query_one("#code-edit", AsmArea)
            before = screen.orc
            edit.post_message(AsmArea.RunHere())
            await pilot.pause()
            await screen.app.workers.wait_for_complete()
            await pilot.pause()
            await pilot.pause()
            return before, screen.orc

        before, after = self._screen(body)
        self.assertIsNone(before)
        self.assertIsNotNone(after, "клик по стрелке не запустил поиск")

    def test_channel_stays_visible_when_the_grid_scrolls_sideways(self) -> None:
        """Канал — закреплённая колонка, а не подпись строки DataTable.

        Решётка развёрнута: тактов много, и вбок её прокручивают всегда.
        Подпись строки уезжает вместе с содержимым — стоило уехать трём
        знакам «,0», и решётка переставала отвечать на свой единственный
        вопрос: в какой канал встала операция. Вдобавок ширина подписи
        считается лениво и в узком окне схлопывалась в ноль, унося подписи
        совсем.

        Окно нарочно узкое: на широком решётка помещается целиком, прокрутки
        не происходит, и тест не проверял бы ничего.
        """
        from textual.widgets import DataTable

        async def go():
            app, _session = _make_app("code")
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(90, 40)) as pilot:
                    await pilot.pause()
                    grid = app.screen.query_one("#code-grid", DataTable)
                    # Прокрутка ДО упора вправо: проверяем самый плохой
                    # случай, а не «немножко сдвинули».
                    grid.scroll_to(x=grid.max_scroll_x, animate=False)
                    await pilot.pause()
                    await pilot.pause()
                    # Смотрим на то, что НАРИСОВАНО, а не на данные: данные
                    # вернут канал в любом случае, вопрос ровно в том, видно
                    # ли его на экране после прокрутки.
                    painted = "\n".join(grid.render_line(y).text
                                        for y in range(grid.size.height))
                    return (grid.fixed_columns, grid.scroll_x, painted)

        fixed, scrolled, painted = asyncio.run(go())
        self.assertEqual(fixed, 1, "колонка канала не закреплена")
        self.assertGreater(scrolled, 0,
                           "решётка не прокрутилась — тест ничего не проверил")
        for chan in (",0", ",5"):
            self.assertIn(chan, painted,
                          f"канал {chan} уехал вместе с прокруткой")

    def test_cell_and_line_point_at_each_other(self) -> None:
        """Курсор кода → клетка решётки → та же строка кода. Круг замкнут.

        Колонка канала сдвинула нумерацию колонок на единицу. Забудь вычесть
        её в одном из двух направлений — и связь разъезжается на такт: экран
        работает, курсор ездит, ничего не падает, а показывает не ту
        операцию. Заметно, только если знать правильный ответ.
        """
        from textual.widgets import DataTable

        async def body(screen, pilot, session):
            op = screen.parsed.ops[3]
            grid = screen.query_one("#code-grid", DataTable)
            screen._sync_grid_cursor(op.line)
            await pilot.pause()
            cell = (grid.cursor_row, grid.cursor_column)
            screen._cell_to_code()
            await pilot.pause()
            back = screen.query_one("#code-edit").cursor_location[0] + 1
            return (op.line, op.cycle, op.channel, cell, back)

        line, cycle, channel, cell, back = self._screen(body)
        self.assertEqual(cell, (channel, cycle + 1),
                         "курсор кода встал не в свою клетку")
        self.assertEqual(back, line, "клетка увела на чужую строку")

    def test_numbers_survive_many_open_tabs(self) -> None:
        """Числа участка не вытесняются вкладками, активная всегда видна.

        Пока приоритета не было, шесть открытых файлов молча выдавливали
        «15→8 т.» за край — ровно тогда, когда открыто много всего и
        разобраться нужнее всего. А активная вкладка уезжала следом, и
        экран показывал содержимое файла, чьего имени на нём нет.
        """
        from vliw.tui.screens.code_screen import FileStrip, SideItem

        async def go():
            app, _session = _make_app("code")
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(100, 30)) as pilot:
                    await pilot.pause()
                    sc = app.screen
                    # Ключи снимаем заранее, а виджет ищем перед каждым
                    # кликом заново: панель перерисовывается на каждом
                    # выборе (в ней есть раздел «открыто», он обязан
                    # показывать активную вкладку), старые виджеты при этом
                    # отсоединяются, и сообщение отсоединённому уходит в
                    # никуда — цикл по снятому заранее списку открывал ровно
                    # одну вкладку и молчал об этом.
                    for key in [i.key for i in sc.query(SideItem)]:
                        live = [i for i in sc.query(SideItem) if i.key == key]
                        if not live:
                            continue
                        live[0].post_message(SideItem.Picked(key))
                        await pilot.pause()
                    await pilot.pause()
                    strip = sc.query_one("#code-head", FileStrip)
                    return (len(sc.files), sc.files[sc.file_i]["name"],
                            str(strip.content),
                            [i for _s, _e, i, _c in strip.spans])

        n, active, painted, shown = asyncio.run(go())
        self.assertGreater(n, 3, "вкладок мало — тест ничего не проверяет")
        self.assertIn("оп.", painted, "числа участка вытеснены вкладками")
        self.assertIn(active, painted,
                      f"активной вкладки {active} нет на экране")
        self.assertIn(n - 1, shown,
                      "активная вкладка есть в тексте, но по ней не кликнуть")
        self.assertLess(len(shown), n,
                        "все вкладки влезли — окно не проверено, нужно уже")

    def test_empty_schedule_says_why_it_is_empty(self) -> None:
        """Пустая вкладка объясняет пустоту, а не молчит прямоугольником.

        Буфер без операций — самый частый первый экран. До сих пор вкладка
        «расписание» показывала в этом случае пустой прямоугольник в треть
        экрана: подписана, а внутри ничего и почему — молчок.
        """
        async def body(screen, pilot, session):
            edit = screen.query_one("#code-edit")
            edit.text = ""
            screen.reparse()
            await pilot.pause()
            await pilot.pause()
            return (screen.query_one("#sched-empty").display,
                    str(screen.query_one("#sched-empty").content),
                    screen.query_one("#code-grid-wrap").display)

        shown, text, grid = self._screen(body)
        self.assertTrue(shown, "пустая решётка снова молчит")
        self.assertIn("ни одной операции", text)
        self.assertFalse(grid, "пустая таблица осталась рядом с объяснением")

    def test_the_sixth_channel_fits_on_a_short_terminal(self) -> None:
        """Канал ,5 обязан быть виден: это монопольный делитель.

        Шесть каналов — инвариант решётки, записанный в её коде: обрезанный
        шестой делает её бесполезной ровно там, где она нужнее всего. На
        80x24 он уезжал за нижний край молча, без полосы прокрутки и без
        единого признака, что там что-то есть.
        """
        async def go():
            app, _session = _make_app("code")
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(80, 24)) as pilot:
                    await pilot.pause()
                    await pilot.pause()
                    grid = app.screen.query_one("#code-grid")
                    return "\n".join(grid.render_line(y).text
                                     for y in range(grid.size.height))

        painted = asyncio.run(go())
        for chan in (",0", ",5"):
            self.assertIn(chan, painted,
                          f"канал {chan} не поместился на терминале 80x24")

    def test_catalog_does_not_pass_the_exhibit_off_as_real_code(self) -> None:
        """В «настоящем коде» нет файлов-экспонатов.

        probe_ILLUSTRATION_OBSOLETE.s сам про себя пишет: «ЭТО НЕ ВЫВОД
        КОМПИЛЯТОРА, рисованная от руки иллюстрация, не использовать как
        источник данных». Оставлен намеренно — но выдавать его за вывод lcc
        значит ровно то враньё, от которого весь проект защищается
        пометками источника у каждого числа.
        """
        from vliw.tui.screens.code_screen import SideItem

        async def body(screen, pilot, session):
            return [i.key for i in screen.query(SideItem)]

        keys = self._screen(body)
        self.assertTrue(any(k.endswith("probe.s") for k in keys),
                        "настоящий код пропал из каталога совсем")
        self.assertFalse([k for k in keys if "OBSOLETE" in k.upper()],
                         "экспонат подан как настоящий код")

    def test_gutter_keeps_the_arrow_out_of_the_text(self) -> None:
        """Ширина гуттера учитывает колонку действия.

        Иначе клик по коду попадал бы на две колонки левее, чем виден
        курсор, — и это заметно только руками, тестом «экран поднялся» нет.
        """
        async def body(screen, pilot, session):
            edit = screen.query_one("#code-edit")
            return edit.gutter_width, edit.RUN_W + edit.BADGE_W

        width, expected = self._screen(body)
        self.assertEqual(width, expected)

    def test_own_tab_keeps_its_name(self) -> None:
        """Имя своего участка не сбрасывается уходом на другую вкладку.

        Имя вкладки — единственное, чем участки различаются на экране, и
        держаться оно обязано ровно столько, сколько живёт вкладка.

        Ломалось так: имя пересчитывалось из сессии при каждом уходе со
        вкладки (`_stash_current`), а у своего участка выводить его не из
        чего — ни файла, ни примера. Все безымянные схлопывались в «буфер»,
        и «участок 1.s» терял имя ровно в тот момент, когда заводили
        «участок 2.s», то есть когда различать их и понадобилось.
        """
        from vliw.tui.screens.code_screen import SideItem

        async def body(screen, pilot, session):
            for _ in range(3):
                screen.post_message(SideItem.Picked("buf:new"))
                await pilot.pause()
            made = [f["name"] for f in screen.files]
            for key in ("buf:0", "buf:1", "buf:3", "buf:2"):
                screen.post_message(SideItem.Picked(key))
                await pilot.pause()
            return made, [f["name"] for f in screen.files]

        made, after = self._screen(body)
        self.assertEqual(made[1:], ["участок 1.s", "участок 2.s", "участок 3.s"],
                         "новые вкладки нумеруются не по порядку")
        self.assertEqual(after, made, "имена вкладок пережили не всё хождение")

    def test_rename_sticks_and_does_not_take_a_busy_name(self) -> None:
        """F2 переименовывает вкладку, и имя держится; занятое — отклоняется.

        Две вкладки с одним именем — способ потерять правки, а не удобство:
        `open_file` ищет уже открытую именно по имени и перешла бы на чужую.
        """
        from vliw.tui.screens.code_screen import SideItem

        async def body(screen, pilot, session):
            screen.post_message(SideItem.Picked("buf:new"))
            await pilot.pause()
            screen.handle_line("/rename моё ядро.s")
            await pilot.pause()
            renamed = [f["name"] for f in screen.files]
            screen.post_message(SideItem.Picked("buf:0"))
            await pilot.pause()
            screen.post_message(SideItem.Picked("buf:1"))
            await pilot.pause()
            survived = [f["name"] for f in screen.files]
            screen.handle_line("/rename " + screen.files[0]["name"])
            await pilot.pause()
            screen.action_rename_buffer()
            await pilot.pause()
            return (renamed, survived, [f["name"] for f in screen.files],
                    screen.query_one("#prompt").input.value)

        renamed, survived, busy, prefilled = self._screen(body)
        self.assertEqual(renamed[1], "моё ядро.s", "/rename не переименовал")
        self.assertEqual(survived, renamed,
                         "имя не пережило переключения вкладок")
        self.assertEqual(busy, survived,
                         "занятое имя отдано второй вкладке")
        self.assertEqual(prefilled, "/rename моё ядро.s",
                         "F2 обязана подставить команду с текущим именем")


@unittest.skipUnless(HAS_TEXTUAL, "textual не установлен — полноэкранный режим не проверяем")
class TestAgentIsAPanelNotAMode(unittest.TestCase):
    """АГЕНТ в КОДЕ — объяснятель по ^G, знающий, на что человек смотрит.

    Целого экрана и четверти главного меню он не стоит: по замерам проекта
    подсказка обученной модели оракулу дала 5% даже с идеальной подсказкой,
    а интервальная нижняя граница отсекла 89% узлов перебора. Место в
    интерфейсе должно совпадать с этими числами.
    """

    @staticmethod
    def _screen(body):
        async def go():
            app, session = _make_app("code")
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(150, 46)) as pilot:
                    await pilot.pause()
                    return await body(app.screen, pilot, session)

        return asyncio.run(go())

    def test_it_asks_about_what_is_on_screen(self) -> None:
        """Фокус в редакторе — вопрос про код; вкладка — про её содержимое."""
        from vliw.tui.widgets import PanelPrompt

        async def body(screen, pilot, session):
            screen.query_one("#code-edit").focus()
            screen.action_explain()
            await pilot.pause()
            about_code = self._facts(screen)
            screen.action_explain()          # ^G закрывает
            await pilot.pause()
            closed = int(screen.ai_shown)
            # Фокус не в тексте — спрашивают про открытую вкладку.
            screen.open_drawer("lint")
            screen.query_one("#dock-lint").focus()
            screen.action_explain()
            await pilot.pause()
            return about_code, closed, self._facts(screen)

        code, closed, lint = self._screen(body)
        self.assertEqual(closed, 0, "^G обязан и закрывать")
        self.assertTrue(any("буфер" in f or "операц" in f for f in code),
                        f"объяснятель не знает про код: {code}")
        self.assertNotEqual(code, lint,
                            "факты не зависят от того, на что смотришь")

    @staticmethod
    def _facts(screen):
        """Что объяснятель показывает в блоке ПОСЧИТАНО.

        С 03.09.2026 он живёт столбцом справа, а не всплывающей строкой:
        объяснение должно стоять рядом с тем, что объясняет. Поведение, ради
        которого тест написан, то же — знать, на что человек смотрит.
        """
        from textual.widgets import Static

        if not screen.ai_shown:
            return []
        return str(screen.query_one("#ai-facts", Static).render()).splitlines()

    def test_escape_closes_it_before_anything_else(self) -> None:
        """Esc убирает объяснятель первым: он всплывающий и лежит поверх."""
        from vliw.tui.widgets import PanelPrompt

        async def body(screen, pilot, session):
            screen.action_explain()
            await pilot.pause()
            opened = int(screen.ai_shown)
            await pilot.press("escape")
            await pilot.pause()
            await pilot.pause()
            return (opened, int(screen.ai_shown),
                    screen.app.screen.__class__.__name__)

        opened, after, where = self._screen(body)
        self.assertEqual(opened, 1)
        self.assertEqual(after, 0, "Esc не убрал объяснятель")
        self.assertEqual(where, "CodeScreen", "Esc унёс с экрана целиком")

    def test_tab_stays_an_indent_in_the_editor(self) -> None:
        """Tab в ассемблере — отступ, а не открытие справочника.

        Отбирать Tab у редактора нельзя: им расставляют отступы в коде.
        Поэтому объяснятель и живёт на ^G, а не на Tab, как справочник у
        развёрнутых панелей в остальных режимах.
        """
        from vliw.tui.widgets import PanelPrompt

        async def body(screen, pilot, session):
            edit = screen.query_one("#code-edit")
            edit.focus()
            edit.move_cursor(edit.document.end)
            before = edit.text
            await pilot.press("tab")
            await pilot.pause()
            return (edit.text[len(before):],
                    len(list(screen.query(PanelPrompt))))

        added, panels = self._screen(body)
        self.assertTrue(added and added.isspace(),
                        f"Tab перестал делать отступ, добавлено {added!r}")
        self.assertEqual(panels, 0, "Tab открыл объяснятель вместо отступа")


@unittest.skipUnless(HAS_TEXTUAL, "textual не установлен — полноэкранный режим не проверяем")
class TestCoreIsATabNotAMode(unittest.TestCase):
    """ЯДРО — вкладка-консоль нижнего дока, а не отдельный экран.

    Его ценность ровно одна: собрать граф выражениями, не умея писать
    ассемблер e2k, и узнать, во сколько тактов он укладывается. Целого
    экрана и четверти главного меню эта работа не стоит. Машина одна на
    сессию, поэтому имена и память здесь те же, что в полноэкранном ЯДРЕ.
    """

    @staticmethod
    def _screen(body):
        async def go():
            app, session = _make_app("code")
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(150, 46)) as pilot:
                    await pilot.pause()
                    screen = app.screen
                    screen.open_drawer("core")
                    await pilot.pause()
                    return await body(screen, pilot, session)

        return asyncio.run(go())

    def test_expressions_build_a_graph_and_show_state(self) -> None:
        """Строки консоли считают, кладут узлы в граф и меняют панельку."""
        async def body(screen, pilot, session):
            for line in ("a = 10", "t = a*2 + 3"):
                screen._exec_core(line)
                await pilot.pause()
            ws = session.workspace()
            return (dict(ws.regs), ws.graph_size(),
                    str(screen.query_one("#core-state").content))

        regs, size, state = self._screen(body)
        self.assertEqual(regs.get("a"), 10)
        self.assertEqual(regs.get("t"), 23)
        self.assertGreater(size, 0, "выражение не положило ничего в граф")
        self.assertIn("23", state, "панелька имён не показывает значение")

    def test_go_computes_and_hands_the_graph_to_the_session(self) -> None:
        """`go` считает точным поиском и делает граф участком сессии.

        Без второго консоль была бы калькулятором: посчитала и забыла, а
        РАЗБОР с АГЕНТОМ продолжали бы говорить про демо-сценарий.
        """
        async def body(screen, pilot, session):
            screen._exec_core("sum 8")
            await pilot.pause()
            screen._exec_core("go")
            await pilot.pause()
            await screen.app.workers.wait_for_complete()
            await pilot.pause()
            await pilot.pause()
            return (session.scenario, len(session.dag_obj),
                    str(screen.query_one("#core-log").lines[-1]))

        scenario, ops, last = self._screen(body)
        self.assertEqual(scenario, "interp")
        self.assertGreater(ops, 0)
        self.assertIn("участок сессии", last,
                      "консоль не сказала, куда уехал граф")

    def test_the_command_line_is_actually_visible(self) -> None:
        """Строка ввода обязана иметь высоту: невидимое поле — не поле.

        У Textual box-sizing по умолчанию border-box, и `height: 1` вместе с
        волоском сверху даёт НОЛЬ строк содержимого. Поле при этом
        фокусируется и принимает нажатия — то есть набирать приходится
        вслепую, и заметить это можно только глазами.
        """
        async def body(screen, pilot, session):
            core = screen.query_one("#core-input").size.height
            screen.open_drawer("term")
            await pilot.pause()
            return core, screen.query_one("#prompt-input").size.height

        core, term = self._screen(body)
        self.assertEqual(core, 1, "строка ввода ЯДРА невидима")
        self.assertEqual(term, 1, "строка ввода ВЫВОДА невидима")


@unittest.skipUnless(HAS_TEXTUAL, "textual не установлен — полноэкранный режим не проверяем")
class TestLabSleepBar(unittest.TestCase):
    """Вторая строка шапки РАЗБОРА: факты трёх спящих режимов.

    Экраны уже читают одну Session, но видеть чужое состояние можно было,
    только физически перейдя в чужой режим. Строка показывает ЯДРО/АГЕНТ/
    КОД прямо в РАЗБОРЕ: пустой факт не рисуется вовсе, клик по факту
    открывает тот режим тем же путём, что и мостик журнала.
    """

    @staticmethod
    def _screen(body, start_mode="lab"):
        async def go():
            app, session = _make_app(start_mode)
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(150, 46)) as pilot:
                    await pilot.pause()
                    # Курсорный ИИ решётки здесь не участник: его запрос к
                    # локальной модели может длиться дольше теста (на машине
                    # с тёплым llama-server это уже ломает чужие тесты —
                    # см. TestCoreHasTheJournalToo). Подъём токена гасит
                    # отложенный запуск детерминированно.
                    app.screen._cell_ai_token += 1
                    return await body(app.screen, pilot, session)

        return asyncio.run(go())

    @staticmethod
    def _facts(sc) -> dict:
        return {mode: body for _label, body, mode in sc.sleep_facts()}

    def test_fresh_session_shows_no_row(self):
        """Нечего показать — второй строки нет вовсе: ни места, ни прочерков."""
        async def body(sc, pilot, session):
            row = sc.query_one("#topbar-sleep")
            return list(sc.sleep_facts()), row.has_class("on")

        facts, shown = self._screen(body)
        self.assertEqual(facts, [])
        self.assertFalse(shown, "пустая сессия не должна рисовать строку")

    def test_facts_from_sleeping_modes(self):
        """ЯДРО: граф не отправлен; АГЕНТ: счёт вопросов; КОД: буфер правлен."""
        from vliw.agent.agent import Turn

        async def body(sc, pilot, session):
            ws = session.workspace()
            ws.exec("sum 8")
            n = len(ws.snapshot())
            session.agent().history.append(Turn(question="что тут?"))
            session.code_text = "{\n  adds,0 %r10\n}\n"
            sc.refresh_context()
            await pilot.pause()
            modes = [w.mode for w in sc.query("#topbar-sleep SleepChip")]
            return self._facts(sc), modes, n

        facts, modes, n = self._screen(body)
        self.assertEqual(facts["work"], f"граф {n} оп., не отправлен")
        self.assertEqual(facts["mind"], "1 вопрос")
        self.assertEqual(facts["code"], "буфер изменён, не разобран")
        self.assertEqual(modes, ["work", "mind", "code"],
                         "каждый показанный факт — свой кликабельный кусок")

    def test_sent_graph_reports_passed(self):
        """Граф ядра — текущий граф сессии: «передан», а не «не отправлен»."""
        async def body(sc, pilot, session):
            ws = session.workspace()
            ws.exec("sum 8")
            n = len(ws.snapshot())
            session.set_dag(ws.snapshot(), "interp")
            sc.refresh_context()
            await pilot.pause()
            return self._facts(sc), n

        facts, n = self._screen(body)
        self.assertEqual(facts["work"], f"граф {n} оп., передан")

    def test_parsed_buffer_is_silent(self):
        """Буфер прогнан и не правился — факта про КОД нет, куска и точки нет."""
        async def body(sc, pilot, session):
            ws = session.workspace()
            ws.exec("a=2; b=a*a")       # чтобы строка жиля хотя бы одним фактом
            session.code_text = "{\n  adds,0 %r10\n}\n"
            session.code_run_text = session.code_text
            sc.refresh_context()
            await pilot.pause()
            row = sc.query_one("#topbar-sleep")
            children = list(row.children)
            classes = [c.classes for c in children]
            return (self._facts(sc), len(children), classes)

        facts, n_children, classes = self._screen(body)
        self.assertNotIn("code", facts, "разобранный буфер — не факт")
        self.assertEqual(n_children, 1,
                         "один факт — один кусок, без пустых мест")
        self.assertNotIn("sleep-sep", classes,
                         "разделитель не должен стоять перед единственным")

    def test_click_on_fact_opens_that_mode(self):
        """Клик по факту ЯДРА открывает ЯДРО — путь мостика, app.open_mode."""
        async def body(sc, pilot, session):
            ws = session.workspace()
            ws.exec("sum 8")
            sc.refresh_context()
            await pilot.pause()
            await pilot.pause()
            await pilot.click("#sleep-work")
            await pilot.pause()
            await pilot.pause()
            return sc.app.screen.__class__.__name__

        where = self._screen(body)
        self.assertEqual(where, "CoreScreen",
                         "клик по факту не открыл режим ЯДРО")

    def test_click_on_agent_fact_opens_agent(self):
        """Клик по факту АГЕНТА открывает АГЕНТА."""
        from vliw.agent.agent import Turn

        async def body(sc, pilot, session):
            session.agent().history.append(Turn(question="привет"))
            sc.refresh_context()
            await pilot.pause()
            await pilot.pause()
            await pilot.click("#sleep-mind")
            await pilot.pause()
            await pilot.pause()
            return sc.app.screen.__class__.__name__

        where = self._screen(body)
        self.assertEqual(where, "AgentScreen",
                         "клик по факту не открыл режим АГЕНТ")

    def test_other_screens_stay_one_line(self):
        """Строка — пилот РАЗБОРА: ЯДРО и АГЕНТ её не получают."""
        from vliw.tui.widgets import TopBar

        async def go():
            out = {}
            for start in ("work", "mind"):
                app, _ = _make_app(start)
                with redirect_stdout(io.StringIO()):
                    async with app.run_test(size=(150, 46)) as pilot:
                        await pilot.pause()
                        bar = app.screen.query_one("#topbar", TopBar)
                        row = app.screen.query_one("#topbar-sleep")
                        out[start] = (list(bar.sleepers),
                                      row.has_class("on"))
            return out

        for start, (sleepers, shown) in asyncio.run(go()).items():
            self.assertEqual(sleepers, [], f"{start}: строка пришла без спроса")
            self.assertFalse(shown, f"{start}: строка не должна рисоваться")

    def test_code_has_no_mode_bar_at_all(self):
        """У КОДА шапки режима нет: верхняя строка — вкладки файлов.

        Строк наверху было две, и они говорили одно и то же дважды: «КОД
        редактор» дублировало то, что и так видно, а числа участка стояли
        ещё и в строке состояния внизу. Сильнее прежней проверки: там
        требовалось, чтобы вторая строка шапки не рисовалась, здесь — чтобы
        самой шапки не было.
        """
        from vliw.tui.widgets import TopBar

        async def go():
            app, _ = _make_app("code")
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(150, 46)) as pilot:
                    await pilot.pause()
                    sc = app.screen
                    head = sc.query_one("#code-head")
                    return (len(list(sc.query(TopBar))),
                            head.region.y, head.region.height,
                            str(head.content))

        bars, y, h, text = asyncio.run(go())
        self.assertEqual(bars, 0, "шапка режима осталась на экране КОД")
        self.assertEqual((y, h), (0, 1),
                         "верхняя строка не одна и не самая верхняя")
        self.assertIn("NEX", text, "марка потерялась вместе с шапкой")
        self.assertIn("оп.", text, "числа участка не переехали в верхнюю строку")


@unittest.skipUnless(HAS_TEXTUAL, "textual не установлен — раскладку не проверяем")
class TestNothingFallsBelowTheFold(unittest.TestCase):
    """Ни один виджет не должен уезжать за нижний край экрана.

    Ширину раскладка учитывала с самого начала (классы `narrow`/`tight`),
    высоту — нет. На невысоком терминале правая колонка РАЗБОРА уходила за
    край: `#p-detail` рос по содержимому без потолка, а у панелей под ним
    стоял min-height, которому уже негде было поместиться. Панель МАШИНА
    вместе с матрицей портов просто оказывалась за экраном — молча, без
    полосы прокрутки и без единого признака, что там что-то есть.

    Стартовый экран страдал тем же: знак, подпись и четыре карточки по
    шесть строк требуют 41 строку, и на терминале ниже четвёртая карточка
    (КОД) не показывалась вовсе.
    """

    SIZES = ((150, 46), (120, 40), (100, 32), (90, 30), (80, 24))

    @staticmethod
    def _overflow(mode, w, h):
        async def go():
            app, _session = _make_app(mode)
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(w, h)) as pilot:
                    await pilot.pause()
                    bad = []
                    for node in app.screen.query("*"):
                        r = node.region
                        # +1 — терпимость к рамке в один символ.
                        if r.height and r.y + r.height > h + 1:
                            bad.append(node.id or node.__class__.__name__)
                    return bad

        return asyncio.run(go())

    def test_screens_fit_at_every_size(self):
        for mode in ("core", "lab", "mind", "code"):
            for w, h in self.SIZES:
                with self.subTest(режим=mode, размер=f"{w}x{h}"):
                    bad = self._overflow(mode, w, h)
                    self.assertEqual(bad, [], f"за краем: {bad}")

    def test_all_mode_cards_are_visible_on_a_short_screen(self):
        """Стартовый экран показывает ВСЕ режимы, даже когда места мало."""
        from vliw.tui.screens.picker import PickerScreen

        async def go(h):
            app, _session = _make_app(None)
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(120, h)) as pilot:
                    await pilot.pause()
                    # Список экранов больше не стартовый — открываем его сами.
                    app.to_picker()
                    await pilot.pause()
                    await pilot.pause()
                    sc = app.screen
                    if not isinstance(sc, PickerScreen):
                        self.skipTest("экран выбора не показан")
                    cards = sc.query(".mode-card")
                    fit = [c for c in cards
                           if c.region.height
                           and c.region.y + c.region.height <= h]
                    return len(cards), len(fit)

        for h in (46, 36, 30, 24):
            with self.subTest(высота=h):
                total, fit = asyncio.run(go(h))
                self.assertEqual(fit, total,
                                 f"на высоте {h} видно {fit} из {total} карточек")


@unittest.skipUnless(HAS_TEXTUAL, "textual не установлен — дерево не проверяем")
class TestNoDuplicateIds(unittest.TestCase):
    """Двух виджетов с одним id быть не должно.

    Стоило один раз занять чужое имя (`journal-side` уже принадлежал левой
    колонке каталога шириной 32) — и правило `width: auto`, написанное для
    новой подсказки, прилетело в колонку. Вывод журнала схлопнулся до двух
    символов, развёрнутая панель показывала пустой экран. Ни один тест этого
    не заметил: за край ничего не уехало, исключений не было, всё «работало».

    Проверка дешёвая и ловит целый класс таких поломок разом.
    """

    @staticmethod
    def _dupes(mode):
        async def go():
            app, _session = _make_app(mode)
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(150, 46)) as pilot:
                    await pilot.pause()
                    seen: dict[str, int] = {}
                    for node in app.screen.query("*"):
                        if node.id:
                            seen[node.id] = seen.get(node.id, 0) + 1
                    return {k: v for k, v in seen.items() if v > 1}

        return asyncio.run(go())

    def test_every_screen_has_unique_ids(self):
        for mode in ("core", "lab", "mind", "code"):
            with self.subTest(режим=mode):
                self.assertEqual(self._dupes(mode), {})

    def test_maximized_panels_too(self):
        """Разворот панели поднимает в дерево то, что обычно свёрнуто."""
        from vliw.tui.widgets import Panel

        async def go():
            app, _session = _make_app("lab")
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(150, 46)) as pilot:
                    await pilot.pause()
                    sc = app.screen
                    for pid in ("#p-console", "#p-machine", "#p-numbers"):
                        panel = sc.query_one(pid, Panel)
                        sc.maximize(panel, container=False)
                        panel.post_message(Panel.Expanded(panel))
                        await pilot.pause()
                        seen: dict[str, int] = {}
                        for node in sc.query("*"):
                            if node.id:
                                seen[node.id] = seen.get(node.id, 0) + 1
                        dupes = {k: v for k, v in seen.items() if v > 1}
                        assert not dupes, f"{pid}: повторы {dupes}"
                        sc.minimize()
                        await pilot.pause()

        asyncio.run(go())
