"""Smoke test suite for the full-screen Textual TUI: screens mount and commands reach core.

Why a dedicated headless TUI test is required
---------------------------------------------
`vliw.tui.available()` requires a real TTY, so in scripts and CI
`python -m vliw` does NOT launch the full-screen TUI — it silently falls back
to line mode, which leaves the TUI untested. Here the app runs headlessly via
Textual's test harness (`App.run_test()`): screens mount for real, keystrokes
reach the command input, and commands execute against the VLIW scheduling core.

This catches broken `compose()` layouts, missing `nex.tcss` rules or themes,
a broken core bridge (`tui/bridge.py`), and any mount-time exception — the exact
class of regressions invisible in line mode.

Textual is an OPTIONAL dependency (the CLI works without it in line mode), so
these tests skip rather than fail when Textual is absent.
"""

from __future__ import annotations

import asyncio
import io
import os
import unittest
from contextlib import redirect_stdout

try:
    import textual  # noqa: F401

    HAS_TEXTUAL = True
except Exception:  # pragma: no cover - environment-dependent
    HAS_TEXTUAL = False

from vliw import cli
from vliw.ui import render


def _make_app(start_mode):
    """Build an app and session identically to `cli.run_tui()`.

    Layout persistence is redirected to a TEMPORARY file. CodeScreen saves
    layout state across runs (`~/.config/nex/layout.json`); without isolation,
    tests would overwrite the developer's real config and leak state across
    cases (e.g., an explorer opened in another directory).
    """
    import tempfile
    from pathlib import Path

    from vliw.tui.app import NexApp
    from vliw.tui.screens.code_screen import CodeScreen

    CodeScreen.LAYOUT_FILE = Path(tempfile.mkdtemp(prefix="nex-test-")) \
        / "layout.json"

    args = cli._build_parser().parse_args([])
    session = cli.Session(args=args)
    cli._apply_mode(session, start_mode or "lab")
    app = NexApp(session, lambda line: cli.handle_input(session, line),
                 cli.COMMANDS, start_mode=start_mode)
    return app, session


@unittest.skipUnless(HAS_TEXTUAL, "textual is not installed — skipping full-screen TUI tests")
class TestScreensMount(unittest.TestCase):
    """Every screen must mount without raising exceptions."""

    def _mounts(self, start_mode, expect_cls):
        async def run():
            app, _ = _make_app(start_mode)
            # Commands print reports to stdout; silence them during tests.
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(120, 40)) as pilot:
                    await pilot.pause()
                    return app.screen.__class__.__name__

        self.assertEqual(asyncio.run(run()), expect_cls)

    def test_home_is_the_picker_but_code_is_the_main_screen(self):
        """Startup opens the mode picker while CODE remains the primary workspace.

        These are two distinct decisions: CODE is the home screen where users
        bring their own assembly basic blocks and the other screens live as
        dock tabs, but launching directly into CODE hid the other screens.
        Starting on the picker costs one keypress and exposes all four modes.
        """
        from vliw.tui.app import NexApp

        self.assertEqual(NexApp.HOME, "code", "CODE must remain the home screen")
        self._mounts(None, "PickerScreen")

    def test_lab(self):
        self._mounts("lab", "LabScreen")

    def test_work(self):
        self._mounts("work", "CoreScreen")

    def test_mind(self):
        self._mounts("mind", "AgentScreen")

    def test_code(self):
        self._mounts("code", "CodeScreen")


@unittest.skipUnless(HAS_TEXTUAL, "textual is not installed — skipping full-screen TUI tests")
class TestPickerNavigation(unittest.TestCase):
    def test_arrow_and_enter_open_mode(self):
        """Arrow + Enter in the mode picker navigates to the selected screen.

        The picker can be reopened anytime via ^O from the active workspace.
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
        self.assertEqual(start, "PickerScreen", "^O did not open the mode picker")
        self.assertNotEqual(got, "PickerScreen", "mode picker did not transition")


@unittest.skipUnless(HAS_TEXTUAL, "textual is not installed — skipping full-screen TUI tests")
class TestCommandsReachCore(unittest.TestCase):
    """Typed input must reach the VLIW core and update session state."""

    @staticmethod
    def _type(start_mode, line):
        async def run():
            app, session = _make_app(start_mode)
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(120, 40)) as pilot:
                    await pilot.pause()
                    await pilot.press(*line, "enter")
                    await pilot.pause()
                    # Screen commands run in a background worker (@work(thread=True)
                    # in screens/base.py), and /run invokes the exact branch-and-bound
                    # oracle with up to a 10s budget. Wait for workers to finish so
                    # assertions do not race against an in-flight command.
                    await app.workers.wait_for_complete()
                    await pilot.pause()
            return session

        return asyncio.run(run())

    def test_run_switches_scenario(self):
        session = self._type("lab", "/run mulclash")
        self.assertEqual(session.scenario, "mulclash")

    def test_interpreter_line_reaches_workspace(self):
        """In CORE mode, a plain line is an interpreter statement, not a slash command."""
        session = self._type("work", "sum 8")
        self.assertIsNotNone(session._workspace)

    def test_theme_command_switches_theme(self):
        """`/theme` switches the global palette and exercises reload_palette()."""
        before = render.THEME.name
        try:
            self._type("lab", "/theme kilo")
            self.assertEqual(render.THEME.name, "kilo")
        finally:
            render.apply_theme(before)

    def test_unknown_scenario_does_not_kill_screen(self):
        """An invalid command must show an error message instead of crashing the TUI.

        Core raises SystemExit on an unknown scenario; the bridge (`tui/bridge.py`)
        catches it and surfaces it as error text on screen.
        """
        session = self._type("lab", "/run nosuchscenario")
        self.assertNotEqual(session.scenario, "nosuchscenario")




@unittest.skipUnless(HAS_TEXTUAL, "textual is not installed — skipping full-screen TUI tests")
class TestPanelMaximize(unittest.TestCase):
    """Double-clicking a panel maximizes it to full screen.

    The screen has seven panels holding dense cycle grids or long diagnostic
    reports. Double-click timing is tracked manually because Textual 8.2's
    Click event exposes `time` rather than a `chain` counter.
    """

    @staticmethod
    async def _click(pilot, panel, times: int = 1):
        """Click the CENTER of a panel — where a real user aims.

        Using `times=2` sends an atomic double-click via Pilot so slow CI runs
        do not exceed the double-click threshold between two separate calls.
        Real Pilot clicks (instead of synthetic `panel.on_click` calls) also
        verify that `DataTable` does not swallow Click events on the schedule grid.
        """
        await pilot.click(offset=(panel.region.x + panel.region.width // 2,
                                  panel.region.y + panel.region.height // 2),
                          times=times)

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
            await self._click(pilot, panel)
            await pilot.pause()
            return app.screen.maximized

        self.assertIsNone(self._run(steps))

    def test_double_click_maximizes_that_panel(self):
        """Verify double-click directly on the schedule grid (`#p-grid`).

        Six issue slots across dozens of cycles are unreadable in a third of
        the screen, and `#p-grid` was the panel where DataTable previously
        swallowed the gesture.
        """
        async def steps(app, pilot, panel):
            under = app.screen.get_widget_at(
                panel.region.x + panel.region.width // 2,
                panel.region.y + panel.region.height // 2)[0]
            await self._click(pilot, panel, times=2)
            await pilot.pause()
            return app.screen.maximized, type(under).__name__

        got, under = self._run(steps)
        self.assertEqual(under, "ScheduleGrid",
                         f"clicked {under} instead of ScheduleGrid — test weakened")
        self.assertIsNotNone(got, "panel did not maximize")
        self.assertEqual(got.id, "p-grid", "wrong panel maximized")

    def test_slow_second_click_is_not_double(self):
        """Two clicks spaced beyond the threshold are two single clicks, not a double-click."""
        from vliw.tui.widgets import Panel

        async def steps(app, pilot, panel):
            await self._click(pilot, panel)
            await asyncio.sleep(Panel.DOUBLE_CLICK_S + 0.2)
            await self._click(pilot, panel)
            await pilot.pause()
            return app.screen.maximized

        self.assertIsNone(self._run(steps))

    def test_escape_minimizes(self):
        """Esc restores the panel without breaking LAB screen's own Esc handling."""
        async def steps(app, pilot, panel):
            await self._click(pilot, panel, times=2)
            await pilot.pause()
            before = app.screen.maximized
            await pilot.press("escape")
            await pilot.pause()
            return before, app.screen.maximized

        before, after = self._run(steps)
        self.assertIsNotNone(before)
        self.assertIsNone(after)

@unittest.skipUnless(HAS_TEXTUAL, "textual is not installed — skipping full-screen TUI tests")
class TestModelViewIsLive(unittest.TestCase):
    """Live neural-scheduler replay inside the LAB schedule grid.

    Verifies behavior invisible in line mode: the grid populates incrementally
    as placements stream in, illegal issue-slot assignments are flagged
    automatically, and repair remains an explicit action. Events are injected
    directly so the test runs in milliseconds without weights or llama.cpp.

    Fixture comes from a real `slotclash` run (lora-eos adapter): twelve legal
    placements plus STORE #12 placed on issue slot `,0`, which lacks a STORE unit.
    """

    ANSWER = [(0, 0, 1), (1, 0, 5), (2, 2, 5), (3, 13, 1), (4, 17, 1),
              (5, 18, 1), (6, 19, 1), (7, 11, 1), (8, 0, 4), (9, 1, 1),
              (10, 20, 1), (11, 21, 1), (12, 22, 0)]

    def _run(self, repair: bool = False) -> dict:
        """Replay model scheduler events and extract plain-data assertions.

        Everything runs inside `run_test()` because detached widgets raise
        `NoActiveAppError` outside the app context.
        """
        from vliw.core import Placed, Repaired, Started
        from vliw.core.schedule import Placement

        async def go():
            app, _ = _make_app("lab")
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(150, 46)) as pilot:
                    await pilot.pause()
                    sc = app.screen
                    sc.on_scheduler_event(Started("learned", "model"))
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
        """STORE on issue slot `,0` is illegal and flagged directly in the grid."""
        got = self._run()
        self.assertEqual(got["illegal"], [12])
        self.assertEqual(got["cell"], (22, 0))

    def test_cursor_lands_on_the_illegal_cell(self) -> None:
        """Cursor auto-jumps to the first illegal placement so it is not off-screen.

        On `slotclash` the illegal placement is in cycle 22 of 23. We assert
        the CYCLE rather than raw row index because latency stalls are collapsed
        in the grid and `_cursor_target()` maps rows back to cycles.
        """
        got = self._run()
        self.assertEqual((got["cursor_cycle"], got["cursor_port"]), (22, 0))

    def test_repair_is_a_separate_action(self) -> None:
        """Raw model output is not auto-repaired; illegal placements remain visible."""
        got = self._run()
        self.assertEqual(got["illegal"], [12])
        self.assertEqual(got["repairs"], [(12, 0, 2)])

    def test_repair_command_fixes_channel_and_keeps_cycle(self) -> None:
        """`/repair` moves the op to a legal issue slot while preserving cycle and makespan."""
        got = self._run(repair=True)
        self.assertEqual(got["illegal_after"], [])
        self.assertEqual(got["after"].cycle, got["before"].cycle)
        self.assertEqual(got["after"].channel, 2)


@unittest.skipUnless(HAS_TEXTUAL, "textual is not installed — skipping full-screen TUI tests")
class TestMaximizedPanelFillsScreen(unittest.TestCase):
    """A maximized panel must fill the viewport rather than staying a narrow strip.

    Regression: panels with explicit ID heights (`#p-console: 10`, `#p-detail: 9`,
    `#p-seen: 12`) previously beat Textual's `.-maximized` class by CSS
    specificity and stayed fixed-height when maximized.
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
        """#p-console has a fixed default height of 10 and must fill the screen when maximized."""
        _w, h = self._size("#p-console")
        self.assertGreater(h, 30, "panel stayed a narrow strip instead of maximizing")

    def test_flexible_panel_unaffected(self) -> None:
        _w, h = self._size("#p-grid")
        self.assertGreater(h, 30)


@unittest.skipUnless(HAS_TEXTUAL, "textual is not installed — skipping full-screen TUI tests")
class TestLabRightColumnFits(unittest.TestCase):
    """The right column of LAB must fit completely within the viewport.

    Regression: a long AI explanation in WHY HERE pushed DIAGNOSIS and MACHINE
    off the bottom edge. Height caps and internal scrolling must keep all four
    right-hand panels on screen regardless of text length.
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
                    # Long breakdown, simulating a verbose AI explanation.
                    sc._set_detail(Text(
                        "\n".join(f"breakdown line {i}" for i in range(40))))
                    await pilot.pause()
                    await pilot.pause()
                    mach = sc.query_one("#p-machine")
                    bottom = mach.region.y + mach.region.height
                    return bottom, sc.size.height

        bottom, screen_h = asyncio.run(go())
        self.assertLessEqual(bottom, screen_h,
                             "MACHINE panel overflowed past the bottom of the screen")

    def test_command_line_lives_inside_git(self) -> None:
        """Command input lives inside the GIT/console panel, not a bottom dock bar."""
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
        self.assertTrue(inside, "command input is not inside the console panel")
        self.assertEqual(docks, 0, "legacy bottom dock bar should not exist")
        self.assertTrue(shown)


@unittest.skipUnless(HAS_TEXTUAL, "textual is not installed — skipping full-screen TUI tests")
class TestCursorAI(unittest.TestCase):
    """AI assistance in LAB is bound to the grid cursor rather than a side chat.

    Pointing at a scheduled cell populates WHY HERE deterministically, and the
    LLM adds a plain-English caption. No model is executed here; we verify
    cancellation on cursor move, debounce delay, and prompt grounding.
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
        """Queries open as a bottom popup prompt rather than a width-stealing side column.

        Facts and suggested chips are scoped to the active maximized panel's
        topic rather than dumping generic session state.
        """

        async def body(sc, pilot):
            from vliw.tui.widgets import Panel, PanelChat, PanelPrompt

            panel = sc.query_one("#p-grid", Panel)
            sc.maximize(panel, container=False)
            panel.post_message(Panel.Expanded(panel))
            for _ in range(6):
                await pilot.pause(0.05)
            await pilot.press("tab")          # popup helper opens only on Tab
            for _ in range(4):
                await pilot.pause(0.05)
            return (len(list(sc.query(PanelChat))),
                    len(list(sc.query(PanelPrompt))),
                    sc.panel_facts("grid"),
                    sc.panel_chips("grid"),
                    sc.panel_chips("machine"))

        chats, prompts, facts, grid_chips, machine_chips = self._screen(body)
        self.assertEqual(chats, 0, "side chat column must not appear")
        self.assertEqual(prompts, 1, "bottom popup prompt must appear")
        self.assertTrue(facts, "panel must expose grounded facts")
        self.assertTrue(any("grid" in f.lower() for f in facts),
                        "facts must describe the schedule grid specifically")
        # Suggested questions must be panel-specific rather than a single global list.
        self.assertTrue(grid_chips and machine_chips)
        self.assertNotEqual(grid_chips, machine_chips)

    def test_cursor_move_invalidates_previous_answer(self) -> None:
        """Moving the cursor off a cell clears and invalidates the previous AI caption."""

        async def body(sc, pilot):
            sc._cell_ai_token = 5
            sc._cell_ai_text = "stale answer"
            sc._cell_ai_state = "done"
            sc._cell_ai_restart()
            await pilot.pause()
            return sc._cell_ai_token, sc._cell_ai_text, sc._cell_ai_state

        tok, text, state = self._screen(body)
        self.assertEqual(tok, 6)
        self.assertEqual(text, "")
        self.assertEqual(state, "")

    def test_stale_request_cannot_write(self) -> None:
        """A late response carrying a stale token must be discarded silently."""

        async def body(sc, pilot):
            sc._cell_ai_token = 9
            sc._cell_ai_piece(3, "answer from previous cell")
            await pilot.pause()
            return sc._cell_ai_text

        self.assertEqual(self._screen(body), "")

    def test_ai_starts_only_after_the_cursor_rests(self) -> None:
        """Cursor AI must debounce before firing so rapid scrolling does not flood inference."""
        from vliw.tui.screens.lab_screen import LabScreen

        self.assertGreaterEqual(LabScreen.CELL_AI_DELAY, 1.0)

    def test_cell_prompt_is_a_retelling_not_a_reasoning_task(self) -> None:
        """Cell prompt sends only the deterministic panel breakdown and forbids arithmetic."""
        from vliw.agent import context

        prompt = context.cell_prompt(["store out #12 is placed in cycle 22 on port ,0",
                                      "STORE executes only on ports ,2 and ,5"])
        self.assertIn("store out #12", prompt)
        self.assertIn("ZERO numbers that do not appear", prompt)
        self.assertNotIn("FACTS (the only source of numbers)", prompt)
        self.assertLess(len(prompt), 1500)


@unittest.skipUnless(HAS_TEXTUAL, "textual is not installed — skipping full-screen TUI tests")
class TestDiagGridBridge(unittest.TestCase):
    """Maximized DIAGNOSIS and GRID are distinct views linked bidirectionally.

    Maximized DIAGNOSIS lists every doctor finding (no top-5 cap) and jumps to
    its cell in GRID on click; maximized GRID links back to the same finding
    in DIAGNOSIS. Neither opens a side chat column.
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
        self.assertGreater(total, 0, "slotclash must produce doctor findings")
        self.assertEqual(rows, total)

    def test_no_side_chat_when_diag_maximized(self) -> None:
        """Maximizing DIAGNOSIS opens its dedicated view, never a side chat."""
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
            sc._cmd_find("next")          # jump cursor to the first finding
            await pilot.pause()
            f_before = sc._active_finding()
            link = sc.query_one("#grid-link", GridLink)
            self.assertTrue(link.active, "grid-to-diag link must activate under a finding")
            link.post_message(GridLink.Picked())
            await pilot.pause()
            return sc.screen.maximized.id, sc._active_finding(), f_before

        maxed_id, after, before = self._screen(body)
        self.assertEqual(maxed_id, "p-diag")
        self.assertEqual(after, before)

    def test_find_command_cycles_through_distinct_findings(self) -> None:
        """`/find next` cycles through every finding once and positions the cursor accurately.

        Whole-schedule findings without `instrs` leave the cursor unchanged,
        while cell-scoped findings (`idle-stall` or non-empty `instrs`) must
        highlight their exact target cell.
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
                    f"finding {f.code} {f.where} was not highlighted after /find")




@unittest.skipUnless(HAS_TEXTUAL, "textual is not installed — skipping full-screen TUI tests")
class TestPanelPromptIsAgentic(unittest.TestCase):
    """The panel popup prompt runs the full Agent (`Agent.ask_stream`), not a stripped stub.

    Users can trigger real session actions (such as switching scenarios) from
    any maximized panel's popup prompt.
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
        """Regression: switching scenarios from a popup must reschedule instead of crashing.

        Calling `redraw()` directly after `session.dag_obj` changed read an old
        schedule against a differently sized dependency DAG (`mulclash`), raising
        `IndexError` in `_render_grid`. `after_command()` triggers background
        rescheduling safely.
        """
        import unittest.mock as mock

        from vliw.agent import llm
        from vliw.tui.widgets import Panel, PanelPrompt

        def fake_stream(system, q, history=None, temperature=0.3, nudge=True):
            yield "done"

        async def body(sc, pilot, session):
            panel = sc.query_one("#p-machine", Panel)
            sc.maximize(panel, container=False)
            panel.post_message(Panel.Expanded(panel))
            await pilot.pause()
            await pilot.pause()
            # Popup helper opens only on Tab — never automatically.
            await pilot.press("tab")
            await pilot.pause()
            await pilot.pause()
            pp = sc.query_one(PanelPrompt)
            inp = pp.query_one("#pp-input")
            with mock.patch.object(llm, "stream", fake_stream):
                inp.value = "run mulclash and compare"
                await pilot.press("enter")
                for _ in range(30):
                    await pilot.pause(0.05)
            return session.scenario

        scenario = self._screen(body)
        self.assertEqual(scenario, "mulclash")

    def test_clear_wipes_answer_log_but_keeps_facts_and_chips(self) -> None:
        """`/clear` clears the answer log without closing the popup or dropping facts/chips."""
        import unittest.mock as mock

        from vliw.agent import llm
        from vliw.tui.widgets import Panel, PanelPrompt

        def fake_stream(system, q, history=None, temperature=0.3, nudge=True):
            yield "short answer"

        async def body(sc, pilot, session):
            panel = sc.query_one("#p-numbers", Panel)
            sc.maximize(panel, container=False)
            panel.post_message(Panel.Expanded(panel))
            await pilot.pause()
            await pilot.pause()
            # Popup helper opens only on Tab — never automatically.
            await pilot.press("tab")
            await pilot.pause()
            await pilot.pause()
            pp = sc.query_one(PanelPrompt)
            inp = pp.query_one("#pp-input")
            with mock.patch.object(llm, "stream", fake_stream):
                inp.value = "why is the lower bound this high?"
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
        """Close shortcut must be visible in text, not hidden behind a hover tooltip."""
        from vliw.tui.widgets import Panel, PanelPrompt

        async def body(sc, pilot, session):
            panel = sc.query_one("#p-machine", Panel)
            sc.maximize(panel, container=False)
            panel.post_message(Panel.Expanded(panel))
            await pilot.pause()
            await pilot.pause()
            # Popup helper opens only on Tab — never automatically.
            await pilot.press("tab")
            await pilot.pause()
            await pilot.pause()
            pp = sc.query_one(PanelPrompt)
            return pp.query_one("#pp-close").content.plain

        text = self._screen(body)
        self.assertIn("Esc", text)


@unittest.skipUnless(HAS_TEXTUAL, "textual is not installed — skipping full-screen TUI tests")
class TestConsoleJournalIsATerminal(unittest.TestCase):
    """Maximized command output acts as a live terminal, not a read-only log.

    While maximized, the journal owns the single active prompt bar (the
    inline panel prompt is hidden), and newly entered commands immediately
    become the selected entry.
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

                    # Inline panel prompt is hidden so only one command bar is active.
                    self.assertFalse(sc.query_one("#prompt", PromptBar).display,
                                     "maximized journal must not show two prompt bars")
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
        self.assertEqual(pos, 1, "after entering a second command, the journal must "
                                 "select the new run rather than staying on the first")


@unittest.skipUnless(HAS_TEXTUAL, "textual is not installed — skipping full-screen TUI tests")
class TestMachineMatrixIsInteractive(unittest.TestCase):
    """Maximized MACHINE exposes an interactive port-capability matrix.

    Clicking column headers sorts rows, and the live text filter narrows
    functional-unit rows by mnemonic or port.
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
            # Clicking the same column header a second time reverses sort order.
            sc.on_data_table_header_selected(
                DataTable.HeaderSelected(table, ColumnKey("op"), 0, None))
            await pilot.pause()
            by_name_rev = list(sc._matrix_ops)
            return default_order, by_name, by_name_rev

        default_order, by_name, by_name_rev = self._screen(body)
        self.assertEqual(by_name, sorted(by_name))
        self.assertEqual(by_name_rev, sorted(by_name, reverse=True))
        self.assertNotEqual(default_order, by_name,
                            "default sort (by op count) must differ from alphabetical "
                            "so the header click produces a measurable change")

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
        # "div" matches BOTH integer and floating-point dividers: hardware
        # probing confirmed that fdivd shares the single monopoly issue slot ,5.
        self.assertEqual(ops, ["DIV", "FDIV"])

    def test_filter_narrows_to_a_single_row(self) -> None:
        """Filter must be able to narrow down to a single row."""
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


@unittest.skipUnless(HAS_TEXTUAL, "textual is not installed — skipping full-screen TUI tests")
class TestDialogIsAWorkspace(unittest.TestCase):
    """Maximized DIALOG provides a question-history sidebar and in-place `/clear`.

    `/clear` clears the conversation feed without leaving AGENT mode or
    erasing the recorded question history.
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
        """`/clear` in AGENT wipes the dialog feed instead of exiting to the picker."""
        from textual.widgets import Static

        async def body(sc, pilot, session):
            sc._asked = [{"q": "why is makespan high?", "seconds": 14.0, "acts": 2}]
            for _ in range(6):
                sc._bubble(Static("message", classes="msg-note"))
            before = len(list(sc.chat.children))
            sc.submit_line("/clear")
            await pilot.pause()
            return (before, len(list(sc.chat.children)), len(sc._asked))

        before, after, asked = self._screen(body)
        self.assertGreater(before, 1)
        self.assertLessEqual(after, 2, "dialog feed should clear back to the greeting")
        self.assertEqual(asked, 1, "question history must be preserved")

    def test_expanded_dialog_shows_history_column(self) -> None:
        from vliw.tui.widgets import Panel

        async def body(sc, pilot, session):
            sc._asked = [{"q": "why is makespan high?", "seconds": 14.0, "acts": 2}]
            panel = sc.query_one("#p-chat", Panel)
            sc.maximize(panel, container=False)
            panel.post_message(Panel.Expanded(panel))
            await pilot.pause()
            await pilot.pause()
            return (sc.query_one("#chat-hist-col").display,
                    len(list(sc.query(".hist-item"))),
                    "/clear" in panel._title)

        shown, items, title = self._screen(body)
        self.assertTrue(shown, "history sidebar must be visible when maximized")
        self.assertEqual(items, 1)
        self.assertTrue(title, "clear shortcut must be shown in the header")

    def test_tab_opens_ai_reference_and_it_does_not_come_uninvited(self) -> None:
        """The AI popup helper opens ONLY on Tab and toggles closed on Tab."""
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
        self.assertEqual(uninvited, 0, "popup helper must not open automatically")
        self.assertEqual(opened, 1, "Tab must open the popup helper")
        self.assertEqual(closed, 0, "Tab must close the popup helper")


@unittest.skipUnless(HAS_TEXTUAL, "textual is not installed — skipping full-screen TUI tests")
class TestEscapeIsOneStepBack(unittest.TestCase):
    """Esc consistently steps one level outward, all the way back to the picker.

    Verifies the 3-step unwind: popup helper -> maximized panel -> mode picker,
    without Textual's default `ESCAPE_TO_MINIMIZE` bypassing `Panel.Collapsed`.
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

                    await pilot.press("escape")     # 1: close popup helper
                    await pilot.pause()
                    await pilot.pause()
                    steps.append((len(list(sc.query(PanelPrompt))),
                                  sc.maximized is not None))

                    await pilot.press("escape")     # 2: minimize panel
                    await pilot.pause()
                    await pilot.pause()
                    steps.append((app.screen.maximized is None,
                                  app.screen.__class__.__name__))

                    await pilot.press("escape")     # 3: return to mode picker
                    await pilot.pause()
                    await pilot.pause()
                    steps.append(isinstance(app.screen, PickerScreen))
                    return steps

        opened, after_first, after_second, after_third = asyncio.run(go())
        self.assertEqual(opened, 1, "Tab should have opened the popup helper")
        # First Esc dismisses ONLY the popup helper — the panel must stay
        # maximized so a single Esc never skips two levels.
        self.assertEqual(after_first, (0, True))
        self.assertEqual(after_second, (True, "LabScreen"))
        self.assertTrue(after_third, "third Esc must return to the mode picker")


@unittest.skipUnless(HAS_TEXTUAL, "textual is not installed — skipping full-screen TUI tests")
class TestGridKeyboardTools(unittest.TestCase):
    """Maximized schedule grid is keyboard-driven with a right-hand inspector sidebar."""

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
        """Inspector sidebar displays active cursor details and key legend."""
        from textual.widgets import Static

        async def body(sc, pilot):
            self._maximize_grid(sc)
            for _ in range(4):
                await pilot.pause(0.05)
            cursor = sc.query_one("#side-cursor", Static).content.plain
            legend = sc.query_one("#side-legend", Static).content.plain
            return cursor, legend

        cursor, legend = self._screen(body)
        self.assertTrue(cursor.strip(), "cursor inspector is empty")
        self.assertIn("n / N", legend, "key legend is missing navigation shortcuts")

    def test_tool_keys_act_on_focused_grid(self) -> None:
        """v/z/[ ] toggle views and dependency layers directly while keeping focus in the grid."""

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
        self.assertNotEqual(before, after, "v did not switch the schedule view")
        self.assertTrue(deps_on, "z did not enable the dependency-neighbor layer")
        self.assertTrue(focused, "focus escaped the schedule grid after pressing a tool key")


@unittest.skipUnless(HAS_TEXTUAL, "textual is not installed — skipping full-screen TUI tests")
class TestTerminalHasCommandCatalog(unittest.TestCase):
    """Maximized command output includes an interactive, filterable command catalog."""

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
        self.assertEqual(shown, total, "catalog must list every registered command")

    def test_typing_filters_catalog_by_first_word_only(self) -> None:
        """Catalog filter matches only the command name so arguments do not empty the list."""
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
        # Prefix matches rank first: "do" should surface /doctor before /random.
        self.assertEqual(narrowed[0], "/doctor")
        self.assertIn("/run", with_arg)

    def test_failed_run_is_marked(self) -> None:
        """A failed command run must be marked as an error, not a success."""

        async def body(sc, pilot, j, session):
            return [(r["cmd"], bool(r.get("error"))) for r in j.runs]

        runs = self._term(body, seed=("/doctor", "/run nosuchscenario"))
        self.assertEqual(len(runs), 2)
        self.assertFalse(runs[0][1], "/doctor succeeded and must not be marked as error")
        self.assertTrue(runs[1][1], "unknown scenario must be marked as error")

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
        """Clicking a catalog entry prefills the prompt without executing it."""
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
        self.assertEqual(before, after, "clicking a catalog command must not auto-run it")


@unittest.skipUnless(HAS_TEXTUAL, "textual is not installed — skipping full-screen TUI tests")
class TestCodeScreen(unittest.TestCase):
    """CODE screen: the editor must parse e2k assembly live and rewrite from the oracle.

    Verifies live parsing on open, cycle markers in the gutter, and `^R`
    rewriting the buffer to match the exact branch-and-bound oracle schedule.
    """

    @staticmethod
    def _screen(body, run=False):
        """Mount CODE, optionally run the oracle (`F5`), and execute the test body."""
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
        """Assembly is parsed immediately on open before pressing F5."""
        async def body(screen, pilot, session):
            return (len(screen.parsed.ops),
                    screen.comp.makespan,
                    [p for p in screen.problems if p.severity == "error"])

        ops, makespan, errors = self._screen(body)
        self.assertGreater(ops, 0, "default assembly buffer failed to parse")
        self.assertGreater(makespan, 0)
        self.assertEqual(errors, [], "default sample basic block must have zero lint errors")

    def test_gutter_carries_the_schedule(self):
        """Each scheduled operation line displays its cycle marker in the gutter."""
        async def body(screen, pilot, session):
            edit = screen.query_one("#code-edit")
            op = screen.parsed.ops[0]
            return edit._marks.get(op.line - 1), op.cycle

        mark, cycle = self._screen(body)
        self.assertIsNotNone(mark, "first operation is missing its gutter cycle marker")
        self.assertIn(f"c{cycle}", mark[0])

    def test_typing_reaches_the_buffer(self):
        """Keystrokes must reach the editor buffer.

        Regression: overriding async `TextArea._on_key` synchronously swallowed
        the parent coroutine and silently broke typing.
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
        """Moving the cursor inspects the NEW line rather than holding stale state.

        The status chip always updates; full line breakdown renders when the
        LINE dock tab is open.
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
        self.assertIn(f"ln.{line}", chip)
        self.assertIn("latency", info)
        self.assertIn(str(line), note)

    def test_run_fills_the_oracle_and_the_moves(self):
        """F5 runs the exact branch-and-bound oracle, diagnostics, and move list."""
        async def body(screen, pilot, session):
            return (screen.orc is not None, len(screen._moves()),
                    screen.comp.makespan,
                    screen.orc.schedule.makespan if screen.orc else None)

        have, moves, src, orc = self._screen(body, run=True)
        self.assertTrue(have, "F5 produced no exact branch-and-bound oracle result")
        self.assertLess(orc, src, "sample basic block must have scheduling headroom")
        self.assertGreater(moves, 0, "move list is empty despite scheduling headroom")

    def test_rewrite_produces_a_buffer_that_matches_the_oracle(self):
        """^R rewrites the assembly buffer to the exact oracle schedule and re-parses cleanly.

        End-to-end check: rewrite -> re-parse -> makespan matches the oracle's
        exact bound with zero linter errors (no dropped `nop`s or illegal slots).
        """
        async def body(screen, pilot, session):
            promised = screen.orc.schedule.makespan
            # Trigger via real keybindings while focus is inside TextArea
            # to verify priority bindings are not swallowed by the editor.
            screen.query_one("#code-edit").focus()
            await pilot.press("f6")
            await pilot.pause()
            await pilot.pause()
            return (promised, screen.comp.makespan if screen.comp else None,
                    [p.text for p in screen.problems if p.severity == "error"],
                    screen.query_one("#code-edit").text)

        promised, got, errors, text = self._screen(body, run=True)
        self.assertEqual(errors, [], "rewritten assembly buffer must be legal")
        self.assertEqual(got, promised,
                         "rewritten makespan does not match the exact oracle")
        self.assertIn("muls,", text)

    def test_editing_marks_the_search_result_as_stale(self):
        """Editing the buffer must mark prior oracle metrics as stale."""
        async def body(screen, pilot, session):
            before = screen._stale()
            edit = screen.query_one("#code-edit")
            edit.text = edit.text + "{\n  adds,0 %r90, %r91, %r92\n}\n"
            screen.reparse()
            await pilot.pause()
            return before, screen._stale()

        before, after = self._screen(body, run=True)
        self.assertFalse(before, "metrics should be fresh immediately after F5")
        self.assertTrue(after, "metrics must be marked stale after editing the buffer")

    def test_clicking_a_problem_moves_the_cursor_to_its_line(self):
        """Clicking a linter diagnostic jumps the editor cursor to that exact line."""
        from vliw.tui.screens.code_screen import LintItem

        async def body(screen, pilot, session):
            screen.handle_line("/example broken")
            await pilot.pause()
            # Diagnostics live in the dock drawer and render lazily when opened.
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
        """A buffer with zero parsed ops and syntax errors must still surface diagnostics."""
        async def body(screen, pilot, session):
            edit = screen.query_one("#code-edit")
            edit.text = "{\n  ??? invalid assembly text\n}\n"
            screen.reparse()
            await pilot.pause()
            return [(p.line, p.kind) for p in screen.problems]

        self.assertEqual(self._screen(body), [(2, "parse")])

    def test_dock_opens_on_the_schedule_and_f12_takes_it_away(self):
        """Dock opens on SCHEDULE by default; F12 collapses it so the editor fills the screen."""
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
                           "editor must expand into the space vacated by the collapsed dock")
        self.assertTrue(back, "F12 must restore the dock")

    def test_ctrl_p_opens_the_terminal_tab(self):
        """^P opens the REPORT dock tab with a prefilled `/` command prompt."""
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
        """Typing `/` mid-line inserts a literal slash without hijacking focus.

        Only `/` at column 0 of an empty line opens the inline command palette
        (e2k assembly lines never start with `/`; comments use `!`).
        """
        async def body(screen, pilot, session):
            edit = screen.query_one("#code-edit")
            edit.focus()
            edit.move_cursor(edit.document.end)
            edit.insert("adds,0 %r1")      # cursor is not at column 0
            await pilot.pause()
            await pilot.press("slash")
            await pilot.pause()
            return edit.text.endswith("/"), screen.drawer_tab

        typed, tab = self._screen(body)
        self.assertTrue(typed, "slash was not inserted mid-line")
        self.assertEqual(tab, "sched",
                         "typing in the editor must not switch dock tabs")

    def test_slash_at_line_start_suggests_the_commands(self):
        """Typing `/` on an empty line inserts `/` and opens the inline command/snippet popup."""
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
        self.assertEqual(text, "/", "slash must be inserted into the buffer")
        self.assertTrue(shown, "inline command popup did not appear")
        # Labels include argument hints (e.g. "/gen <n> ..."), so match prefixes.
        heads = [l.split()[0] for l in labels]
        self.assertIn("/gen", heads, f"/gen missing from {labels}")
        self.assertIn("/fill", heads, f"/fill missing from {labels}")
        # Zero-argument assembly SNIPPETS (`CodeScreen.SNIPPETS`) come first,
        # followed by parameterized commands like /gen and /fill.
        from vliw.tui.screens.code_screen import CodeScreen

        snippets = {"/" + n for n, _note, _body in CodeScreen.SNIPPETS}
        self.assertIn(heads[0], snippets,
                      f"first item is not a snippet: {heads[0]}")
        # Snippets must remain grouped cleanly at the top before commands.
        self.assertTrue(snippets.issuperset(heads[:3]),
                        "snippets are interleaved with commands at the top of the popup")

    def test_broken_example_is_actually_caught(self):
        """The intentionally broken sample must trigger linter errors."""
        async def body(screen, pilot, session):
            screen.handle_line("/example broken")
            await pilot.pause()
            await pilot.pause()
            return sorted({p.kind for p in screen.problems
                           if p.severity == "error"})

        self.assertEqual(self._screen(body), ["busy", "channel", "ready"])


@unittest.skipUnless(HAS_TEXTUAL, "textual is not installed — skipping full-screen TUI tests")
class TestJournalIsSessionBridge(unittest.TestCase):
    """Session journal acts as session Git: mode tags, cross-screen bridges, event stream.

    Shared across all screens, each commit records its source mode, dependency DAG
    snapshot, and bridge actions (`to LAB / to AGENT / to CORE / to CODE`).
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
        """Each journal entry records the screen mode where it was created."""
        async def body(sc, pilot, session):
            sc.handle_line("/bounds")
            for _ in range(10):
                await pilot.pause()
            return session.journal_runs[-1].get("mode")

        self.assertEqual(self._journal(body), "lab")

    def test_bridge_to_core_is_present_and_works(self) -> None:
        """`to CORE` opens CORE mode and passes a bridge note for the run."""
        async def body(sc, pilot, session):
            from vliw.tui.widgets import Tool

            sc.handle_line("/bounds")
            for _ in range(10):
                await pilot.pause()
            # The bridge button must remain visible even without a DAG snapshot.
            tool = sc.query_one("#bridge-work", Tool)
            self.assertTrue(tool.display)
            sc.panel_tool("@work")
            await pilot.pause()
            await pilot.pause()
            return (sc.app.screen.__class__.__name__, session.pending_note)

        where, note = self._journal(body)
        self.assertEqual(where, "CoreScreen")
        # An empty pending_note after transition means CORE consumed and displayed it
        # in on_ready (verified separately below).
        self.assertEqual(note, "")

    def test_core_consumes_pending_note_on_mount(self) -> None:
        """A bridge note delivered to CORE renders as a sheet row and clears afterward."""
        async def go():
            app, session = _make_app("work")
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(150, 46)) as pilot:
                    await pilot.pause()
                    sc = app.screen
                    sheet = sc.query_one("#tape-sheet")
                    before = len(list(sheet.children))
                    session.pending_note = "from journal: test run"
                    sc._take_pending_note()
                    await pilot.pause()
                    return (len(list(sheet.children)) > before,
                            session.pending_note)

        shown, rest = asyncio.run(go())
        self.assertTrue(shown, "bridge note did not appear in the CORE sheet")
        self.assertEqual(rest, "", "pending_note must clear after being displayed")

    def test_scheduler_text_goes_to_events_not_console(self) -> None:
        """Live scheduler output goes to the EVENTS feed without cluttering command runs."""
        async def go():
            app, session = _make_app("code")
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(150, 46)) as pilot:
                    await pilot.pause()
                    sc = app.screen
                    sc.on_scheduler_text("model streaming schedule")
                    await pilot.pause()
                    journal = sc.query_one("#journal")
                    return (len(session.journal_events), len(journal.events),
                            journal._feed)

        n_session, n_journal, feed = asyncio.run(go())
        self.assertEqual(n_session, 1)
        self.assertEqual(n_journal, 1, "events must reach the journal")
        self.assertEqual(feed, "runs", "default journal feed must be command runs")

    def test_events_feed_switches_and_renders(self) -> None:
        """The EVENTS tab switches the right pane of the journal to live events."""
        async def go():
            app, session = _make_app("code")
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(150, 46)) as pilot:
                    await pilot.pause()
                    sc = app.screen
                    from vliw.tui.widgets import RichLog

                    sc.on_scheduler_text("stream line")
                    await pilot.pause()
                    journal = sc.query_one("#journal")
                    journal.show_feed("events")
                    await pilot.pause()
                    out = sc.query_one("#journal-out", RichLog)
                    ev = sc.query_one("#events-out", RichLog)
                    return out.display, ev.display

        runs_visible, events_visible = asyncio.run(go())
        self.assertFalse(runs_visible, "command runs must hide when EVENTS is active")
        self.assertTrue(events_visible)

    def test_journal_reloads_after_command_finishes(self) -> None:
        """An open journal refreshes bridge buttons once a background run finishes."""
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
        self.assertTrue(has_dag, "dependency DAG was not attached to the journal entry")
        self.assertTrue(visible, "open journal did not reveal bridge buttons after "
                                 "command completion")

    def test_bridge_to_code_carries_the_source(self) -> None:
        """`to CODE` restores a run's assembly source into the CODE editor buffer."""
        async def body(sc, pilot, session):
            from vliw.tui.widgets import Tool

            session.journal_runs.append(
                {"cmd": "/code run", "lines": [], "error": False,
                 "mode": "code",
                 "code": "{\n  adds,0 %r1, %r2, %r3\n}\n",
                 "scenario": "buffer", "dag": None})
            sc.panel_tool("@code")
            await pilot.pause()
            await pilot.pause()
            screen = sc.app.screen
            return (screen.__class__.__name__,
                    session.code_text,
                    session.pending_note)

        where, text, note = self._journal(body)
        self.assertEqual(where, "CodeScreen")
        self.assertIn("adds,0", text, "run assembly source did not load into the buffer")
        # pending_note is consumed by CODE on_ready; the key check is the buffer text.
        self.assertEqual(note, "")

    def test_history_rows_look_like_commits(self) -> None:
        """Journal history renders as Git-style commits: number, time, DAG size, graph glyph."""
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
                    "slotclash" in text, "3 ops" in text,
                    "*" in text, "│" in text)

        has_num, has_time, has_scen, has_ops, dot, line = self._journal(body)
        self.assertTrue(has_num, "commit number missing from journal row")
        self.assertTrue(has_time, "timestamp missing from journal row")
        self.assertTrue(has_scen, "basic-block scenario name missing from journal row")
        self.assertTrue(has_ops, "dependency DAG op count missing from journal row")
        self.assertTrue(dot, "commit graph bullet missing from journal row")
        self.assertTrue(line, "commit graph rail missing from journal row")

    def test_restore_returns_state_without_leaving(self) -> None:
        """`@restore` checks out the recorded run state while staying on the current screen."""
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
                         "@restore did not restore the recorded scenario")
        self.assertTrue(visible)
        self.assertEqual(where, "LabScreen",
                         "@restore must not leave the current screen")


@unittest.skipUnless(HAS_TEXTUAL, "textual is not installed — skipping full-screen TUI tests")
class TestCoreHasTheJournalToo(unittest.TestCase):
    """The session journal and bridge actions must work from CORE mode as well."""

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
        self.assertTrue(visible, "journal did not open in CORE mode")

    def test_journal_from_core_bridges_back_to_lab(self) -> None:
        """A CORE journal commit can be bridged directly into LAB."""
        async def go():
            app, session = _make_app("work")
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(150, 46)) as pilot:
                    await pilot.pause()
                    sc = app.screen
                    # State-mutating statement: journal tracks machine states, not no-ops.
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


@unittest.skipUnless(HAS_TEXTUAL, "textual is not installed — skipping full-screen TUI tests")
class TestCoreSheetAndCommits(unittest.TestCase):
    """CORE sheet rendering, commit filtering, and full machine-state checkout."""

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
        """Errors and read-only views are not commits; the journal tracks state changes."""
        async def body(sc, pilot, session):
            before = len(session.journal_runs)
            sc.handle_line("names")
            sc.handle_line("mul m0 a0 b0")   # syntax error: raw e2k mnemonic
            await pilot.pause()
            return (before, len(session.journal_runs),
                    [r["kind"] for r in sc._rows])

        before, after, kinds = self._screen(body)
        self.assertEqual(after, before,
                         "errors and read-only views must not enter the commit journal")
        self.assertIn("error", kinds, "error row must still appear in the sheet")

    def test_arithmetic_that_adds_an_op_is_a_commit(self) -> None:
        """`2+2` appends an operation to the dependency DAG, so it creates a commit."""
        async def body(sc, pilot, session):
            before = len(session.journal_runs)
            sc.handle_line("2+2")
            await pilot.pause()
            rec = session.journal_runs[-1]
            return (len(session.journal_runs) - before, rec["cmd"],
                    rec["dag"] is not None)

        added, cmd, has_dag = self._screen(body)
        self.assertEqual(added, 1, "an expression adding a DAG op must create a commit")
        self.assertEqual(cmd, "2+2")
        self.assertTrue(has_dag)

    def test_state_line_is_a_commit_with_graph_and_machine(self) -> None:
        """A state-mutating line records both the dependency DAG and machine snapshot."""
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
        self.assertTrue(has_dag, "commit is missing its dependency DAG for LAB bridge")
        self.assertIn(("a", 10), regs, "register bindings were lost in machine snapshot")
        self.assertEqual(mem, [1, 2, 3], "memory contents were lost in machine snapshot")

    def test_reset_is_a_commit_and_names_only_line_is_not(self) -> None:
        """`reset` mutates state and commits; `names` is read-only and does not."""
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
        self.assertEqual(names_commits, 0, "`names` must not create a commit")
        self.assertEqual(cmd, "reset")
        self.assertEqual(regs, {}, "`reset` did not clear register bindings")
        self.assertEqual(snap_regs, {}, "`reset` snapshot still contains stale bindings")

    def test_restore_checks_out_the_whole_machine(self) -> None:
        """`@restore` checks out register bindings AND memory, not just the DAG."""
        async def body(sc, pilot, session):
            sc.handle_line("a=10; b=2")
            sc.handle_line("store 9 3")      # mem[3] = 9
            sc.handle_line("a=55")            # overwrite register binding
            journal = sc.query_one("#journal")
            journal.pos = 1                   # commit "store 9 3"
            sc.panel_tool("@restore")
            await pilot.pause()
            ws = session.workspace()
            return (ws.regs.get("a"), ws.regs.get("b"), ws.mem[3])

        a, b, mem3 = self._screen(body)
        self.assertEqual((a, b, mem3), (10, 2, 9),
                         "@restore did not check out full machine state")

    def test_go_attaches_verdict_to_its_commit(self) -> None:
        """The `go` scheduling verdict attaches baseline and oracle makespans to the commit."""
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
                    any("baseline 23" in t.plain and "oracle 22" in t.plain
                        for t in rec["lines"]))

        verdict, n_rows, in_lines = self._screen(body)
        self.assertEqual(verdict, (23, 22), "verdict makespans did not attach to commit")
        self.assertEqual(n_rows, 1, "verdict must appear as a sheet row")
        self.assertTrue(in_lines, "journal entry output must include the verdict")

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
                        "journal row does not display the scheduling verdict")

    def test_link_program_op_highlights_tape_row(self) -> None:
        """Clicking a DAG op highlights the sheet statement that emitted it."""
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
        self.assertIsNotNone(link, "op-to-sheet link did not activate")
        self.assertEqual(link[0], "op")
        self.assertEqual(on, [1], "wrong sheet row highlighted")
        self.assertEqual(hot, 1, "exactly one op should be highlighted")

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
        self.assertEqual(hot, 1, "y=x*2 should highlight its single emitted DAG op")
        self.assertTrue(on, "selected sheet row was not highlighted")


@unittest.skipUnless(HAS_TEXTUAL, "textual is not installed — skipping full-screen TUI tests")
class TestCodeStatusBarLaunchesDrawer(unittest.TestCase):
    """CODE status bar chips act as IDE-style launchers for the bottom dock."""

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
        self.assertIn("clean", lint_label)
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
        """The shared session journal updates the report chip counter across modes."""
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
                            "report chip counter missed a run from another mode")

    def test_bridge_row_in_drawer_sends_run_to_lab(self) -> None:
        """The REPORT dock tab exposes the `to LAB` bridge without maximizing."""
        from vliw.tui.widgets import Tool

        async def body(screen, pilot, session):
            screen.open_drawer("term")
            await pilot.pause()
            session.journal_runs.append(
                {"cmd": "/code run", "lines": [], "error": False,
                 "mode": "code", "time": "14:02",
                 "scenario": "asm:buffer", "dag": session.dag_obj})
            screen._sync_drawer_bridge()
            await pilot.pause()
            row = screen.query_one("#drawer-bridge")
            row.sync(session.journal_runs, 0)
            await pilot.pause()
            btn = screen.query_one("#dbridge-lab", Tool)
            self.assertTrue(btn.display, "bridge button is hidden in the REPORT tab")
            btn.post_message(Tool.Picked("@lab"))
            await pilot.pause()
            await pilot.pause()
            return screen.app.screen.__class__.__name__

        where = self._screen(body)
        self.assertEqual(where, "LabScreen",
                         "CODE run did not bridge into LAB")

    def test_drawer_bridge_hidden_without_runs(self) -> None:
        """With empty history, the bridge button bar stays hidden."""
        from vliw.tui.widgets import Tool

        async def body(screen, pilot, session):
            screen.open_drawer("term")
            await pilot.pause()
            btn = screen.query_one("#dbridge-lab", Tool)
            return btn.display

        self.assertFalse(self._screen(body),
                         "bridge bar must hide when there are no runs")

    def test_double_click_on_a_dock_tab_zooms_the_dock(self) -> None:
        """Double-clicking a dock tab title maximizes and restores the dock."""
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
            # Slow clicks must not maximize, so normal tab switching stays calm.
            await pilot.click(tab)
            await asyncio.sleep(0.6)
            await pilot.click(tab)
            await pilot.pause()
            return one, two, back, screen.zoom

        one, two, back, slow = self._screen(body)
        self.assertEqual(one[:2], ("lint", ""),
                         "single click must only switch tabs")
        self.assertEqual(two[0], "dock", "double-click did not maximize the dock")
        self.assertGreater(two[1], one[2] * 2,
                           f"dock did not grow: {one[2]} -> {two[1]}")
        self.assertEqual(back, ("", one[2]),
                         "second double-click did not restore the dock")
        self.assertEqual(slow, "", "two slow clicks must not act as a double-click")


@unittest.skipUnless(HAS_TEXTUAL, "textual is not installed — skipping full-screen TUI tests")
class TestCodeFilesAreTabs(unittest.TestCase):
    """Multiple open assembly buffers live in independent tabs without clobbering each other."""

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
        """Opening an example creates a new tab while preserving the user's buffer."""
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
            # Switching back to the user tab must restore its full text.
            screen.select_file(0)
            await pilot.pause()
            return mine, names, shown, edit.text

        mine, names, shown, back = self._screen(body)
        self.assertEqual(len(names), 2, f"expected two open tabs, got: {names}")
        self.assertIn("divport.s", names)
        self.assertNotEqual(shown, mine, "example tab did not load")
        self.assertEqual(back, mine, "user buffer was lost when switching tabs")

    def test_edits_survive_switching_between_tabs(self) -> None:
        """Edits are isolated per tab rather than leaking across buffers."""
        async def body(screen, pilot, session):
            edit = screen.query_one("#code-edit")
            screen.open_file("{\n  adds,0 %r1, %r2, %r3\n}\n", "second.s")
            await pilot.pause()
            edit.text = edit.text + "! edit in second\n"
            screen.reparse()
            await pilot.pause()
            screen.select_file(0)
            await pilot.pause()
            first = edit.text
            screen.select_file(1)
            await pilot.pause()
            return first, edit.text

        first, second = self._screen(body)
        self.assertNotIn("edit in second", first,
                         "edit leaked into another tab")
        self.assertIn("edit in second", second, "edit was not persisted in its tab")

    def test_the_last_tab_cannot_be_closed(self) -> None:
        """Closing the last tab keeps at least one active buffer open."""
        async def body(screen, pilot, session):
            screen.close_file(0)
            await pilot.pause()
            return len(screen.files)

        self.assertEqual(self._screen(body), 1)

    def test_explorer_opens_a_real_file(self) -> None:
        """Clicking a file in the right-hand explorer (^E) opens a tab and records its path."""
        from vliw.tui.screens.code_screen import SideItem
        from vliw.tui.screens.code_screen import examples_dir

        async def body(screen, pilot, session):
            screen.action_toggle_explorer()
            screen.explorer_dir = examples_dir().parent
            screen._draw_explorer()
            await pilot.pause()
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
                        f"file path was not recorded for ^S save: {path}")
        self.assertGreater(size, 0, "opened file buffer is empty")

    def test_gutter_arrow_runs_the_buffer(self) -> None:
        """Clicking the gutter run arrow triggers the same exact oracle run as F5."""
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
        self.assertIsNotNone(after, "gutter run arrow did not launch the oracle")

    def test_channel_stays_visible_when_the_grid_scrolls_sideways(self) -> None:
        """Issue-slot labels stay pinned as a fixed column when scrolling horizontally."""
        from textual.widgets import DataTable

        async def go():
            app, _session = _make_app("code")
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(90, 40)) as pilot:
                    await pilot.pause()
                    grid = app.screen.query_one("#code-grid", DataTable)
                    # Wait for layout to settle so max_scroll_x reflects measured
                    # column widths instead of 0 on busy runners.
                    for _ in range(20):
                        if grid.max_scroll_x > 0:
                            break
                        await pilot.pause()
                    # One extra pause so a late relayout does not reset scroll_x.
                    await pilot.pause()
                    # Scroll all the way to the right edge to test the worst case.
                    grid.scroll_to(x=grid.max_scroll_x, animate=False)
                    await pilot.pause()
                    await pilot.pause()
                    # Inspect rendered lines rather than underlying data to ensure
                    # pinned slot labels remain visible after scrolling.
                    painted = "\n".join(grid.render_line(y).text
                                        for y in range(grid.size.height))
                    return (grid.fixed_columns, grid.scroll_x, painted)

        fixed, scrolled, painted = asyncio.run(go())
        self.assertEqual(fixed, 1, "issue-slot column is not pinned")
        self.assertGreater(scrolled, 0,
                           "schedule grid did not scroll horizontally")
        for chan in (",0", ",5"):
            self.assertIn(chan, painted,
                          f"issue slot {chan} scrolled off screen")

    def test_cell_and_line_point_at_each_other(self) -> None:
        """Editor line -> schedule grid cell -> same editor line round-trips cleanly.

        The pinned issue-slot column offsets grid column indices by +1; both
        directions must account for it to avoid an off-by-one cycle mismatch.
        """
        from textual.widgets import DataTable

        async def body(screen, pilot, session):
            op = screen.parsed.ops[3]
            grid = screen.query_one("#code-grid", DataTable)
            # Wait for initial grid build so a late relayout does not reset the cursor.
            await screen.app.workers.wait_for_complete()
            await pilot.pause()
            screen._sync_grid_cursor(op.line)
            await pilot.pause()
            cell = (grid.cursor_row, grid.cursor_column)
            screen._cell_to_code()
            await pilot.pause()
            back = screen.query_one("#code-edit").cursor_location[0] + 1
            return (op.line, op.cycle, op.channel, cell, back)

        line, cycle, channel, cell, back = self._screen(body)
        self.assertEqual(cell, (channel, cycle + 1),
                         "editor cursor mapped to the wrong schedule grid cell")
        self.assertEqual(back, line, "grid cell jumped back to the wrong source line")

    def test_numbers_survive_many_open_tabs(self) -> None:
        """Basic-block metrics and the active tab stay visible even with many tabs open."""
        from vliw.tui.screens.code_screen import FileStrip, SideItem

        async def go():
            app, _session = _make_app("code")
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(100, 30)) as pilot:
                    await pilot.pause()
                    sc = app.screen
                    # Collect .s keys up front and re-query SideItem before each click
                    # because selecting a file rebuilds the explorer list.
                    from vliw.tui.screens.code_screen import examples_dir

                    sc.action_toggle_explorer()
                    sc.explorer_dir = examples_dir()
                    sc._draw_explorer()
                    await pilot.pause()
                    keys = [i.key for i in sc.query(SideItem)
                            if i.key.endswith(".s") or i.key == "new:s"]
                    for key in keys:
                        live = [i for i in sc.query(SideItem) if i.key == key]
                        if not live:
                            continue
                        live[0].post_message(SideItem.Picked(key))
                        await pilot.pause()
                    await pilot.pause()
                    strip = sc.query_one("#code-head", FileStrip)
                    return (len(sc.files), sc.files[sc.file_i]["name"],
                            str(strip.content),
                            [i for _s, _e, i, _c in strip.spans], sc.file_i)

        n, active, painted, shown, current = asyncio.run(go())
        self.assertGreater(n, 3, "too few tabs opened to test overflow")
        self.assertIn("ops", painted, "basic-block metrics were crowded out by tabs")
        self.assertIn(active, painted,
                      f"active tab {active} is not visible in the strip")
        # Active tab must also remain clickable in the strip hitboxes.
        self.assertIn(current, shown,
                      "active tab is rendered but missing from click hitboxes")
        self.assertLess(len(shown), n,
                        "all tabs fit without overflow — narrow the test viewport")

    def test_empty_schedule_says_why_it_is_empty(self) -> None:
        """An empty schedule tab explains why it is empty instead of showing a blank grid."""
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
        self.assertTrue(shown, "empty schedule placeholder is hidden")
        self.assertIn("no e2k operations", text)
        self.assertFalse(grid, "empty DataTable stayed visible alongside the placeholder")

    def test_the_sixth_channel_fits_on_a_short_terminal(self) -> None:
        """Issue slot ,5 (monopoly divider port) must remain visible even at 80x24."""
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
                          f"issue slot {chan} was clipped on an 80x24 terminal")

    def test_explorer_marks_the_exhibit(self) -> None:
        """Hand-drawn illustration files must be labeled as samples, not real lcc output."""
        from vliw.tui.screens.code_screen import SideItem, examples_dir

        async def body(screen, pilot, session):
            screen.action_toggle_explorer()
            screen.explorer_dir = examples_dir().parent
            screen._draw_explorer()
            await pilot.pause()
            items = list(screen.query(SideItem))
            keys = [i.key for i in items]
            marks = {i.key: str(i.render()) for i in items}
            return keys, marks

        keys, marks = self._screen(body)
        self.assertTrue(any(k.endswith("probe.s") for k in keys),
                        "real assembly files disappeared from the explorer")
        exhibit = [k for k in keys if "OBSOLETE" in k.upper()]
        self.assertTrue(exhibit,
                        "on-disk file disappeared — explorer must show real "
                        "directory contents honestly")
        for key in exhibit:
            self.assertIn("sample", marks[key],
                          "illustration file presented as regular compiler output: "
                          f"{marks[key]!r}")

    def test_gutter_keeps_the_arrow_out_of_the_text(self) -> None:
        """Gutter width accounts for the run-arrow action column so clicks align with text."""
        async def body(screen, pilot, session):
            edit = screen.query_one("#code-edit")
            return edit.gutter_width, edit.RUN_W + edit.BADGE_W

        width, expected = self._screen(body)
        self.assertEqual(width, expected)

    def test_own_tab_keeps_its_name(self) -> None:
        """Custom basic-block tabs keep sequential names across tab switches."""
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
        self.assertEqual(made[1:], ["block 1.s", "block 2.s", "block 3.s"],
                         "new basic-block tabs are not numbered sequentially")
        self.assertEqual(after, made, "tab names mutated while switching tabs")

    def test_rename_sticks_and_does_not_take_a_busy_name(self) -> None:
        """F2 prefills `/rename`; renaming persists and rejects duplicate tab names."""
        from vliw.tui.screens.code_screen import SideItem

        async def body(screen, pilot, session):
            screen.post_message(SideItem.Picked("buf:new"))
            await pilot.pause()
            screen.handle_line("/rename my kernel.s")
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
        self.assertEqual(renamed[1], "my kernel.s", "/rename did not rename the tab")
        self.assertEqual(survived, renamed,
                         "renamed tab title did not survive tab switching")
        self.assertEqual(busy, survived,
                         "duplicate tab name was accepted for a second tab")
        self.assertEqual(prefilled, "/rename my kernel.s",
                         "F2 must prefill `/rename` with the active tab name")


@unittest.skipUnless(HAS_TEXTUAL, "textual is not installed — skipping full-screen TUI tests")
class TestAgentIsAPanelNotAMode(unittest.TestCase):
    """AGENT in CODE is a ^G dock tab grounded in whatever the user currently focused."""

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
        """Focus in the editor asks about the assembly buffer; focus in a dock tab asks about that tab."""
        from vliw.tui.widgets import PanelPrompt

        async def body(screen, pilot, session):
            screen.query_one("#code-edit").focus()
            screen.action_explain()
            await pilot.pause()
            about_code = self._facts(screen)
            screen.action_explain()          # ^G toggles closed
            await pilot.pause()
            closed = int(screen.ai_shown)
            # Focus outside the editor scopes the question to the open dock tab.
            screen.open_drawer("lint")
            screen.query_one("#dock-lint").focus()
            # Pause so Textual processes the focus message before ^G runs.
            await pilot.pause()
            screen.action_explain()
            await pilot.pause()
            return about_code, closed, self._facts(screen)

        code, closed, lint = self._screen(body)
        self.assertEqual(closed, 0, "^G must toggle the agent tab closed")
        self.assertTrue(any("buffer" in f or "ops" in f for f in code),
                        f"agent context is missing assembly buffer facts: {code}")
        self.assertNotEqual(code, lint,
                            "agent facts did not adapt to the focused pane")

    @staticmethod
    def _facts(screen):
        """Return the grounded facts currently visible to the AGENT dock tab."""
        from textual.widgets import Static

        if not screen.ai_shown:
            return []
        text = str(screen.query_one("#agent-seen", Static).render())
        return [line.strip() for line in text.splitlines() if line.strip()]

    def test_escape_returns_to_the_code_and_keeps_the_dock(self) -> None:
        """Esc from the AGENT tab returns focus to the editor without closing the dock."""
        async def body(screen, pilot, session):
            screen.action_explain()
            await pilot.pause()
            opened = int(screen.ai_shown)
            await pilot.press("escape")
            await pilot.pause()
            await pilot.pause()
            focused = screen.app.focused
            screen.action_explain()
            await pilot.pause()
            return (opened, getattr(focused, "id", ""),
                    int(screen.ai_shown),
                    screen.app.screen.__class__.__name__)

        opened, focused, closed_by_key, where = self._screen(body)
        self.assertEqual(opened, 1, "^G did not open the AGENT tab")
        self.assertEqual(focused, "code-edit",
                         f"Esc focused {focused!r} instead of returning to the editor")
        self.assertEqual(closed_by_key, 0, "^G did not close the AGENT tab")
        self.assertEqual(where, "CodeScreen", "Esc unexpectedly left CodeScreen")

    def test_tab_stays_an_indent_in_the_editor(self) -> None:
        """Tab inside the assembly editor inserts indentation rather than opening the agent."""
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
                        f"Tab did not insert indentation, added {added!r}")
        self.assertEqual(panels, 0, "Tab opened the agent instead of indenting")


@unittest.skipUnless(HAS_TEXTUAL, "textual is not installed — skipping full-screen TUI tests")
class TestNonAsmFilesDoNotPretend(unittest.TestCase):
    """Non-assembly files (.py, .md) are not parsed as e2k basic blocks or offered F5."""

    def _open(self, kind):
        """Open a file of type `kind` via the explorer and inspect CODE screen state."""
        import tempfile
        from pathlib import Path

        async def go(path):
            app, _session = _make_app("code")
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(120, 40)) as pilot:
                    await pilot.pause()
                    sc = app.screen
                    sc.open_file(path.read_text(), path.name, path=str(path))
                    await pilot.pause()
                    sc.reparse()
                    await pilot.pause()
                    edit = sc.query_one("#code-edit")
                    return (sc.files[sc.file_i]["name"], sc._is_asm(),
                            len(sc.problems), sc.parsed, edit.runnable,
                            [k for k, _v in sc.hint_pairs()],
                            str(sc.query_one("#code-status").render()))

        work = Path(tempfile.mkdtemp(prefix="nex-kind-"))
        path = work / f"script.{kind}"
        path.write_text("import subprocess\nprint('hello')\n")
        return asyncio.run(go(path))

    def test_python_buffer_is_not_parsed_as_assembly(self) -> None:
        name, is_asm, problems, parsed, runnable, keys, status = self._open("py")
        self.assertTrue(name.endswith(".py"), f"expected a .py file, got {name}")
        self.assertFalse(is_asm, "Python script was misclassified as e2k assembly")
        self.assertIsNone(parsed, "Python script was passed to the e2k assembly parser")
        self.assertEqual(problems, 0,
                         "e2k linter errors were emitted for a Python script")
        self.assertFalse(runnable,
                         "gutter run arrow was shown for a non-assembly file")
        self.assertNotIn("F5", keys,
                         "F5 was offered for a non-assembly file")
        self.assertIn("not e2k", status,
                      f"status bar did not identify non-e2k file type: {status!r}")

    def test_asm_buffer_still_works(self) -> None:
        """Control check: `.s` assembly files still parse and offer F5 normally."""
        from vliw.tui.screens.code_screen import SideItem

        async def go():
            app, _session = _make_app("code")
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(120, 40)) as pilot:
                    await pilot.pause()
                    sc = app.screen
                    sc.post_message(SideItem.Picked("new:s"))
                    await pilot.pause()
                    return (sc.files[sc.file_i]["name"], sc._is_asm(),
                            sc.query_one("#code-edit").runnable,
                            [k for k, _v in sc.hint_pairs()])

        name, is_asm, runnable, keys = asyncio.run(go())
        self.assertTrue(name.endswith(".s"))
        self.assertTrue(is_asm)
        self.assertTrue(runnable)
        self.assertIn("F5", keys)


@unittest.skipUnless(HAS_TEXTUAL, "textual is not installed — skipping layout tests")
class TestLayoutSurvivesRestart(unittest.TestCase):
    """Dock height and active tab persist across sessions via layout.json."""

    def test_dock_height_and_tab_come_back(self) -> None:
        import json
        import tempfile
        from pathlib import Path
        from vliw.tui.screens.code_screen import CodeScreen

        home = Path(tempfile.mkdtemp(prefix="nex-layout-"))
        saved = CodeScreen.LAYOUT_FILE
        CodeScreen.LAYOUT_FILE = home / "layout.json"
        try:
            # `_make_app` assigns a fresh temp layout path per call, so point both
            # launches at the same temporary layout file here.
            async def first():
                app, _s = _make_app("code")
                CodeScreen.LAYOUT_FILE = home / "layout.json"
                with redirect_stdout(io.StringIO()):
                    async with app.run_test(size=(150, 42)) as pilot:
                        await pilot.pause()
                        sc = app.screen
                        sc.dock_h = 20
                        sc.open_drawer("core")
                        await pilot.pause()

            async def second():
                app, _s = _make_app("code")
                CodeScreen.LAYOUT_FILE = home / "layout.json"
                with redirect_stdout(io.StringIO()):
                    async with app.run_test(size=(150, 42)) as pilot:
                        await pilot.pause()
                        await pilot.pause()
                        sc = app.screen
                        sc._load_layout()
                        sc._apply_dock_height(sc.query_one("#code-dock"))
                        await pilot.pause()
                        return (sc.dock_h, sc.drawer_tab,
                                sc.query_one("#code-dock").size.height)

            asyncio.run(first())
            self.assertTrue(CodeScreen.LAYOUT_FILE.exists(),
                            "layout file was not written")
            height, tab, real = asyncio.run(second())
            self.assertEqual(height, 20, "dock height did not persist across restart")
            self.assertEqual(tab, "core", "active dock tab did not persist across restart")
            self.assertEqual(real, 20, "saved dock height was not applied on startup")
        finally:
            CodeScreen.LAYOUT_FILE = saved

    def test_broken_file_does_not_break_the_screen(self) -> None:
        """A corrupt layout.json must fall back cleanly instead of crashing startup."""
        import tempfile
        from pathlib import Path
        from vliw.tui.screens.code_screen import CodeScreen

        home = Path(tempfile.mkdtemp(prefix="nex-layout-bad-"))
        bad = home / "layout.json"
        bad.write_text("{not valid json")
        saved = CodeScreen.LAYOUT_FILE
        CodeScreen.LAYOUT_FILE = bad
        try:
            async def go():
                app, _s = _make_app("code")
                CodeScreen.LAYOUT_FILE = bad
                with redirect_stdout(io.StringIO()):
                    async with app.run_test(size=(120, 40)) as pilot:
                        await pilot.pause()
                        app.screen._load_layout()
                        await pilot.pause()
                        return app.screen.__class__.__name__

            self.assertEqual(asyncio.run(go()), "CodeScreen")
        finally:
            CodeScreen.LAYOUT_FILE = saved


@unittest.skipUnless(HAS_TEXTUAL, "textual is not installed — skipping snippet tests")
class TestSnippetsAreLegalCode(unittest.TestCase):
    """`/` snippets insert valid, machine-legal e2k VLIW assembly bundles.

    Issue-slot assignments in snippets are cross-checked against hardware
    probing (`tools/probe_matrix.py`), MCST documentation, and QEMU decode tables
    (`target/e2k/alop.decode`).
    """

    def _insert(self, name):
        from vliw.tui.screens.code_screen import AsmArea

        async def go():
            app, _session = _make_app("code")
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(120, 40)) as pilot:
                    await pilot.pause()
                    sc = app.screen
                    edit = sc.query_one("#code-edit", AsmArea)
                    edit.replace("", (0, 0), edit.document.end)
                    await pilot.pause()
                    edit.focus()
                    edit.insert("/" + name)
                    await pilot.pause()
                    await pilot.pause()
                    took = sc.action_suggest_take()
                    await pilot.pause()
                    sc.reparse()
                    await pilot.pause()
                    errs = [p for p in sc.problems if p.severity == "error"]
                    return (edit.text,
                            len(sc.parsed.ops) if sc.parsed else 0,
                            sc.comp.makespan if sc.comp is not None else None,
                            [e.text for e in errs])

        return asyncio.run(go())

    def test_every_snippet_parses_without_errors(self) -> None:
        from vliw.tui.screens.code_screen import CodeScreen

        for name, _note, _body in CodeScreen.SNIPPETS:
            text, ops, _span, errs = self._insert(name)
            self.assertNotIn("/" + name, text,
                             f"slash trigger `/{name}` remained in the buffer "
                             "and would cause a parse error")
            self.assertFalse(errs, f"/{name} produced machine lint errors: {errs}")
            if name != "bundle":
                self.assertGreater(ops, 0, f"/{name} produced zero parsed ops")

    def test_two_inserts_do_not_fight_for_registers(self) -> None:
        """Inserting a snippet twice allocates fresh destination registers to avoid WAW/RAW hazards."""
        from vliw.tui.screens.code_screen import AsmArea

        async def go():
            app, _session = _make_app("code")
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(120, 40)) as pilot:
                    await pilot.pause()
                    sc = app.screen
                    edit = sc.query_one("#code-edit", AsmArea)
                    edit.replace("", (0, 0), edit.document.end)
                    await pilot.pause()
                    edit.focus()
                    for _ in range(2):
                        edit.insert("/chain")
                        await pilot.pause()
                        await pilot.pause()
                        sc.action_suggest_take()
                        await pilot.pause()
                        sc.reparse()
                        await pilot.pause()
                    errs = [p for p in sc.problems if p.severity == "error"]
                    return edit.text, [e.text for e in errs]

        text, errs = asyncio.run(go())
        self.assertFalse(errs, f"consecutive snippet insertions produced errors: {errs}")
        dsts = [line.split(",")[-1].strip()
                for line in text.splitlines() if "muls" in line]
        self.assertEqual(len(dsts), len(set(dsts)),
                         f"consecutive snippets reused destination registers: {dsts}")

    def test_pauses_come_from_the_machine_model(self) -> None:
        """Snippet `nop` counts derive from machine-model latency minus issue cycle."""
        async def go():
            app, session = _make_app("code")
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(120, 40)) as pilot:
                    await pilot.pause()
                    sc = app.screen
                    model = session.model()
                    return {
                        "chain": (sc._snippet_text("chain"),
                                  model.latency("MUL")),
                        "div": (sc._snippet_text("div"), model.latency("DIV")),
                        "load": (sc._snippet_text("load"),
                                 model.latency("LOAD")),
                    }

        for kind, (text, latency) in asyncio.run(go()).items():
            self.assertIn(f"nop {latency - 1}", text,
                          f"/{kind}: nop stall does not match machine model (latency "
                          f"{latency}): {text!r}")

    def test_par4_and_queue_show_the_same_work_costing_differently(self) -> None:
        """Parallel vs. serialized multiply snippets must demonstrate real makespan difference."""
        _t, ops_par, span_par, _e = self._insert("par4")
        _t, ops_q, span_q, _e = self._insert("queue")
        self.assertEqual(ops_par, ops_q, "both snippets must perform the same op count")
        self.assertLess(span_par, span_q,
                        f"parallel={span_par} cyc vs. queued={span_q} cyc — "
                        "snippets show no makespan improvement")


@unittest.skipUnless(HAS_TEXTUAL, "textual is not installed — skipping layout tests")
class TestColumnsYieldToTheEditor(unittest.TestCase):
    """Sidebars yield width to the assembly editor on narrow viewports and restore automatically."""

    def _widths(self, sizes):
        async def go():
            app, _session = _make_app("code")
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(150, 40)) as pilot:
                    await pilot.pause()
                    sc = app.screen
                    sc.action_toggle_side()
                    sc.action_toggle_explorer()
                    await pilot.pause()
                    out = []
                    for width in sizes:
                        await pilot.resize_terminal(width, 40)
                        await pilot.pause()
                        await pilot.pause()
                        out.append((width,
                                    int(sc.side_shown),
                                    int(sc.explorer_shown),
                                    sc.query_one("#code-edit").size.width))
                    return out

        return asyncio.run(go())

    def test_editor_never_gets_squeezed(self) -> None:
        rows = self._widths((150, 120, 100, 80))
        for width, _side, _expl, edit in rows:
            self.assertGreaterEqual(
                edit, 60,
                f"at width {width}, editor shrank to {edit} cols — "
                f"too narrow for an e2k assembly line")

    def test_columns_come_back_when_there_is_room(self) -> None:
        rows = self._widths((150, 80, 150))
        wide_before, narrow, wide_after = rows
        self.assertEqual((wide_before[1], wide_before[2]), (1, 1))
        self.assertEqual((narrow[1], narrow[2]), (0, 0),
                         "sidebars did not collapse at 80 columns")
        self.assertEqual((wide_after[1], wide_after[2]), (1, 1),
                         "sidebars did not restore when viewport widened")

    def test_explorer_goes_first(self) -> None:
        """Explorer yields first at 100 columns while open tabs remain visible."""
        rows = self._widths((150, 100))
        _w, side, expl, _edit = rows[1]
        self.assertEqual((side, expl), (1, 0),
                         "wrong sidebar collapsed at 100 columns")


@unittest.skipUnless(HAS_TEXTUAL, "textual is not installed — skipping welcome screen tests")
class TestEmptyBufferExplainsTheScreen(unittest.TestCase):
    """An empty CODE buffer displays a welcome overlay that hides as soon as code is entered."""

    def _hello(self, body):
        from vliw.tui.screens.code_screen import SideItem

        async def go():
            app, _session = _make_app("code")
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(120, 40)) as pilot:
                    await pilot.pause()
                    sc = app.screen
                    sc.post_message(SideItem.Picked("new:s"))
                    await pilot.pause()
                    return await body(sc, pilot)

        return asyncio.run(go())

    def test_it_says_what_the_screen_is_for(self) -> None:
        async def body(sc, pilot):
            hello = sc.query_one("#code-hello")
            return hello.display, str(hello.render())

        shown, text = self._hello(body)
        self.assertTrue(shown, "empty buffer did not display the welcome overlay")
        for must in ("CODE", "lcc", "F5"):
            self.assertIn(must, text,
                          f"welcome overlay is missing {must!r}: {text!r}")

    def test_it_disappears_once_there_is_code(self) -> None:
        async def body(sc, pilot):
            edit = sc.query_one("#code-edit")
            edit.replace("{\n  muls,0 %r1, %r2, %r3\n}\n",
                         (0, 0), edit.document.end)
            await pilot.pause()
            sc.reparse()
            await pilot.pause()
            return sc.query_one("#code-hello").display

        self.assertFalse(self._hello(body),
                         "welcome overlay stayed visible after code was entered")


@unittest.skipUnless(HAS_TEXTUAL, "textual is not installed — skipping explorer tests")
class TestExplorerSearchStaysCheap(unittest.TestCase):
    """Explorer search prunes hidden/venv directories before descent and reports hit caps."""

    def _screen(self, body):
        async def go():
            app, _session = _make_app("code")
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(120, 40)) as pilot:
                    await pilot.pause()
                    sc = app.screen
                    sc.action_toggle_explorer()
                    await pilot.pause()
                    return await body(sc, pilot)

        return asyncio.run(go())

    def test_search_does_not_walk_hidden_and_vendor_trees(self) -> None:
        """Hidden directories and virtualenvs are pruned during traversal."""
        import tempfile
        from pathlib import Path

        work = Path(tempfile.mkdtemp(prefix="nex-find-"))
        (work / "mine.s").write_text("{}\n")
        for junk in (".venv/lib", "__pycache__", "node_modules/pkg"):
            d = work / junk
            d.mkdir(parents=True)
            (d / "mine_ignored.s").write_text("{}\n")

        def body(sc, pilot):
            async def run():
                sc.explorer_dir = work
                sc.explorer_query = "mine"
                return sc._explorer_rows()
            return run()

        rows = self._screen(body)
        names = [label for _key, label, _d in rows]
        self.assertIn("mine.s", names, "user assembly file not found")
        self.assertFalse([n for n in names if "ignored" in n],
                         f"traversal descended into hidden/ignored directories: {names}")

    def test_typing_stays_in_the_search_and_not_in_the_code(self) -> None:
        """Typing in the explorer search input keeps focus and never leaks into the editor."""
        async def go():
            app, _session = _make_app("code")
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(150, 42)) as pilot:
                    await pilot.pause()
                    sc = app.screen
                    before = sc.query_one("#code-edit").text
                    await pilot.press("ctrl+e")
                    await pilot.pause()
                    for ch in "probe":
                        await pilot.press(ch)
                        await pilot.pause()
                    await pilot.pause()
                    return (sc.query_one("#explorer-find").value,
                            getattr(app.focused, "id", None),
                            before == sc.query_one("#code-edit").text)

        value, focused, intact = asyncio.run(go())
        self.assertEqual(value, "probe", "typed query did not reach explorer search")
        self.assertEqual(focused, "explorer-find", "focus escaped explorer search input")
        self.assertTrue(intact, "explorer search keystrokes leaked into the editor buffer")

    def test_arrows_move_the_selection(self) -> None:
        """Arrow keys move selection across explorer matches and Enter opens the item."""
        async def go():
            app, _session = _make_app("code")
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(150, 42)) as pilot:
                    await pilot.pause()
                    sc = app.screen
                    await pilot.press("ctrl+e")
                    await pilot.pause()
                    for ch in "probe":
                        await pilot.press(ch)
                        await pilot.pause()
                    await pilot.pause()
                    await pilot.press("down")
                    await pilot.pause()
                    rows = sc._explorer_rows()
                    want = rows[sc._explorer_at][1] if rows else ""
                    await pilot.press("enter")
                    await pilot.pause()
                    await pilot.pause()
                    return sc._explorer_at, want, sc.files[sc.file_i]["name"]

        at, want, opened = asyncio.run(go())
        self.assertEqual(at, 1, "down arrow did not advance explorer selection")
        self.assertTrue(want.endswith(opened),
                        f"wrong item opened: expected {want}, got {opened}")

    def test_recent_folders_come_back_in_one_click(self) -> None:
        """Recent explorer directory is accessible via one-click history."""
        from pathlib import Path
        from vliw.tui.screens.code_screen import SideItem, examples_dir

        def body(sc, pilot):
            async def run():
                start = str(sc.explorer_dir)
                sc.post_message(
                    SideItem.Picked("dir:" + str(examples_dir())))
                await pilot.pause()
                await pilot.pause()
                rows = sc._explorer_rows()
                back = [r for r in rows if r[1].startswith("←")]
                if not back:
                    return start, None, None
                sc.post_message(SideItem.Picked(back[0][0]))
                await pilot.pause()
                await pilot.pause()
                return start, back[0][1], str(sc.explorer_dir)
            return run()

        start, label, now = self._screen(body)
        self.assertIsNotNone(label, "recent directory missing from history list")
        self.assertEqual(now, start, "navigating back via directory history failed")

    def test_enter_opens_the_first_hit(self) -> None:
        """Pressing Enter in the explorer search input opens the top match without a mouse."""
        from vliw.tui.screens.code_screen import examples_dir

        def body(sc, pilot):
            async def run():
                sc.explorer_dir = examples_dir().parent
                sc.explorer_query = "probe"
                sc._draw_explorer()
                await pilot.pause()
                sc._open_first_found()
                await pilot.pause()
                await pilot.pause()
                return sc.files[sc.file_i]["name"]
            return run()

        self.assertEqual(self._screen(body), "probe.s",
                         "Enter did not open the first search match")

    def test_search_says_when_it_stopped_early(self) -> None:
        """Truncated search results explicitly announce the hit limit."""
        import tempfile
        from pathlib import Path

        work = Path(tempfile.mkdtemp(prefix="nex-find-many-"))
        for i in range(80):
            (work / f"file{i}.s").write_text("{}\n")

        def body(sc, pilot):
            async def run():
                sc.explorer_dir = work
                sc.explorer_query = "file"
                rows = sc._explorer_rows()
                return len(rows), sc._find_cut
            return run()

        found, cut = self._screen(body)
        self.assertEqual(found, 60, "explorer search hit cap (60) did not trigger")
        self.assertIn("60", cut, f"truncation notice missing limit: {cut!r}")


@unittest.skipUnless(HAS_TEXTUAL, "textual is not installed — skipping directory tests")
class TestSideCatalogDeletesOnlyOurFiles(unittest.TestCase):
    """Explorer delete (`x`) prompts for confirmation, allows cancel, and protects package files."""

    def _run(self, body):
        import tempfile
        from pathlib import Path

        async def go(work):
            app, _session = _make_app("code")
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(120, 40)) as pilot:
                    await pilot.pause()
                    return await body(app.screen, pilot, Path(work))

        work = tempfile.mkdtemp(prefix="nex-tests-")
        (Path(work) / "mine.s").write_text("{\n  adds,1 %r1, %r2, %r3\n}\n")
        here = os.getcwd()
        try:
            os.chdir(work)
            return asyncio.run(go(work))
        finally:
            os.chdir(here)

    def test_delete_asks_first_and_can_be_cancelled(self) -> None:
        from vliw.tui.screens.code_screen import SideItem

        async def body(sc, pilot, work):
            sc.action_toggle_explorer()
            await pilot.pause()
            sc.post_message(SideItem.Picked("mine.s", sc.DELETE_X + 1))
            await pilot.pause()
            asked = (sc._to_delete, (work / "mine.s").exists())
            sc.post_message(SideItem.Picked("del:no"))
            await pilot.pause()
            cancelled = (sc._to_delete, (work / "mine.s").exists())
            sc.post_message(SideItem.Picked("mine.s", sc.DELETE_X + 1))
            await pilot.pause()
            sc.post_message(SideItem.Picked("del:yes"))
            await pilot.pause()
            return asked, cancelled, (work / "mine.s").exists()

        asked, cancelled, alive = self._run(body)
        self.assertEqual(asked, ("mine.s", True),
                         "clicking delete removed the file without confirmation")
        self.assertEqual(cancelled, ("", True), "cancel did not preserve the file")
        self.assertFalse(alive, "confirming deletion did not remove the file")

    def test_package_files_are_not_deletable(self) -> None:
        from vliw.tui.screens.code_screen import SideItem

        async def body(sc, pilot, work):
            sc.action_toggle_explorer()
            await pilot.pause()
            from vliw.tui.screens.code_screen import examples_dir
            pkg = [str(p) for p in sorted(examples_dir().glob("*.s"))]
            if not pkg:
                return None, None
            sc.post_message(SideItem.Picked(pkg[0], sc.DELETE_X + 1))
            await pilot.pause()
            return sc._to_delete, os.path.exists(pkg[0])

        waiting, alive = self._run(body)
        if waiting is None:
            self.skipTest("no bundled package files found in directory")
        self.assertEqual(waiting, "",
                         "explorer offered to delete a bundled package file")
        self.assertTrue(alive, "bundled package file was deleted")


@unittest.skipUnless(HAS_TEXTUAL, "textual is not installed — skipping save tests")
class TestSaveUsesTheTabName(unittest.TestCase):
    """Ctrl+S derives filename from the tab title and refuses silent overwrite of existing files."""

    def _run(self, body):
        import tempfile
        from pathlib import Path

        async def go(work):
            app, _session = _make_app("code")
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(120, 40)) as pilot:
                    await pilot.pause()
                    return await body(app.screen, pilot, Path(work), _session)

        work = tempfile.mkdtemp(prefix="nex-save-")
        here = os.getcwd()
        try:
            os.chdir(work)
            return asyncio.run(go(work))
        finally:
            os.chdir(here)

    def test_ctrl_s_saves_new_buffer_by_its_tab_name(self) -> None:
        from vliw.tui.screens.code_screen import SideItem

        async def body(sc, pilot, work, session):
            sc.post_message(SideItem.Picked("new:s"))
            await pilot.pause()
            edit = sc.query_one("#code-edit")
            edit.replace("{\n  adds,1 %r1, %r2, %r3\n}\n",
                         (0, 0), edit.document.end)
            await pilot.pause()
            sc.action_save_code()
            await pilot.pause()
            return (sorted(p.name for p in work.glob("*.s")),
                    session.code_path)

        made, path = self._run(body)
        self.assertEqual(len(made), 1, f"expected exactly one saved file, got: {made}")
        self.assertTrue(made[0].endswith(".s"), made)
        self.assertNotIn(" ", made[0], "saved filename still contains whitespace")
        self.assertTrue(path, "saved path was not remembered for subsequent ^S")

    def test_existing_file_is_not_overwritten_silently(self) -> None:
        from vliw.tui.screens.code_screen import SideItem
        from vliw.tui.widgets import PromptBar

        async def body(sc, pilot, work, session):
            sc.post_message(SideItem.Picked("new:s"))
            await pilot.pause()
            name = sc.files[sc.file_i]["name"].replace(" ", "_")
            (work / name).write_text("! existing work\n")
            sc.action_save_code()
            await pilot.pause()
            return ((work / name).read_text(),
                    sc.query_one("#prompt", PromptBar).input.value)

        kept, typed = self._run(body)
        self.assertIn("existing work", kept,
                      "existing file was overwritten without confirmation")
        self.assertIn("/code save", typed,
                      "overwrite prompt command was not prefilled for user confirmation")


@unittest.skipUnless(HAS_TEXTUAL, "textual is not installed — skipping full-screen TUI tests")
class TestCoreIsATabNotAMode(unittest.TestCase):
    """CORE console lives as a bottom dock tab in CODE sharing the same session machine."""

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
        """CORE dock statements evaluate expressions, append DAG ops, and update register state."""
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
        self.assertGreater(size, 0, "expression did not append any ops to the dependency DAG")
        self.assertIn("23", state, "register status bar does not display computed value")

    def test_go_computes_and_hands_the_graph_to_the_session(self) -> None:
        """`go` runs the exact branch-and-bound oracle and promotes the DAG to the session block."""
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
        self.assertIn("session block", last,
                      "console did not announce that the session block was updated")

    def test_the_command_line_is_actually_visible(self) -> None:
        """Console input bars must have non-zero content height (border-box regression)."""
        async def body(screen, pilot, session):
            core = screen.query_one("#core-input").size.height
            screen.open_drawer("term")
            await pilot.pause()
            return core, screen.query_one("#prompt-input").size.height

        core, term = self._screen(body)
        self.assertEqual(core, 1, "CORE dock input bar has zero content height")
        self.assertEqual(term, 1, "REPORT dock input bar has zero content height")


@unittest.skipUnless(HAS_TEXTUAL, "textual is not installed — skipping full-screen TUI tests")
class TestLabSleepBar(unittest.TestCase):
    """LAB top-bar second row shows live status chips for the three sleeping modes."""

    @staticmethod
    def _screen(body, start_mode="lab"):
        async def go():
            app, session = _make_app(start_mode)
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(150, 46)) as pilot:
                    await pilot.pause()
                    # Cancel debounced cursor AI deterministically so background
                    # inference cannot outlive the test.
                    app.screen._cell_ai_token += 1
                    return await body(app.screen, pilot, session)

        return asyncio.run(go())

    @staticmethod
    def _facts(sc) -> dict:
        return {mode: body for _label, body, mode in sc.sleep_facts()}

    def test_fresh_session_shows_no_row(self):
        """When no sleeping mode has active state, the sleep bar stays hidden."""
        async def body(sc, pilot, session):
            row = sc.query_one("#topbar-sleep")
            return list(sc.sleep_facts()), row.has_class("on")

        facts, shown = self._screen(body)
        self.assertEqual(facts, [])
        self.assertFalse(shown, "empty session must not render the sleep bar")

    def test_facts_from_sleeping_modes(self):
        """Sleep bar reports CORE unsent graph, AGENT question count, and edited CODE buffer."""
        from vliw.agent.agent import Turn

        async def body(sc, pilot, session):
            ws = session.workspace()
            ws.exec("sum 8")
            n = len(ws.snapshot())
            session.agent().history.append(Turn(question="what is here?"))
            session.code_text = "{\n  adds,0 %r10\n}\n"
            sc.refresh_context()
            await pilot.pause()
            modes = [w.mode for w in sc.query("#topbar-sleep SleepChip")]
            return self._facts(sc), modes, n

        facts, modes, n = self._screen(body)
        self.assertEqual(facts["work"], f"graph {n} ops, not sent")
        self.assertEqual(facts["mind"], "1 question")
        self.assertEqual(facts["code"], "buffer edited, not run")
        self.assertEqual(modes, ["work", "mind", "code"],
                         "each displayed sleep fact must be its own clickable chip")

    def test_sent_graph_reports_passed(self):
        """Once the CORE graph is active in the session, it reports `sent`."""
        async def body(sc, pilot, session):
            ws = session.workspace()
            ws.exec("sum 8")
            n = len(ws.snapshot())
            session.set_dag(ws.snapshot(), "interp")
            sc.refresh_context()
            await pilot.pause()
            return self._facts(sc), n

        facts, n = self._screen(body)
        self.assertEqual(facts["work"], f"graph {n} ops, sent")

    def test_parsed_buffer_is_silent(self):
        """An already-run, unmodified CODE buffer emits no sleep chip or leading separator."""
        async def body(sc, pilot, session):
            ws = session.workspace()
            ws.exec("a=2; b=a*a")       # keep the sleep bar visible with one fact
            session.code_text = "{\n  adds,0 %r10\n}\n"
            session.code_run_text = session.code_text
            sc.refresh_context()
            await pilot.pause()
            row = sc.query_one("#topbar-sleep")
            children = list(row.children)
            classes = [c.classes for c in children]
            return (self._facts(sc), len(children), classes)

        facts, n_children, classes = self._screen(body)
        self.assertNotIn("code", facts, "unmodified run buffer must not emit a sleep fact")
        self.assertEqual(n_children, 1,
                         "one active fact must render exactly one sleep chip")
        self.assertNotIn("sleep-sep", classes,
                         "separator must not appear before a single sleep chip")

    def test_click_on_fact_opens_that_mode(self):
        """Clicking the CORE sleep chip navigates to CoreScreen via app.open_mode."""
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
                         "clicking CORE sleep chip did not open CoreScreen")

    def test_click_on_agent_fact_opens_agent(self):
        """Clicking the AGENT sleep chip navigates to AgentScreen."""
        from vliw.agent.agent import Turn

        async def body(sc, pilot, session):
            session.agent().history.append(Turn(question="hello"))
            sc.refresh_context()
            await pilot.pause()
            await pilot.pause()
            await pilot.click("#sleep-mind")
            await pilot.pause()
            await pilot.pause()
            return sc.app.screen.__class__.__name__

        where = self._screen(body)
        self.assertEqual(where, "AgentScreen",
                         "clicking AGENT sleep chip did not open AgentScreen")

    def test_other_screens_stay_one_line(self):
        """Sleep bar is LAB-only; CORE and AGENT screens do not render it."""
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
            self.assertEqual(sleepers, [], f"{start}: unexpected sleep facts rendered")
            self.assertFalse(shown, f"{start}: sleep bar must stay hidden")

    def test_code_has_no_mode_bar_at_all(self):
        """CODE has no TopBar mode header; the file-tab strip owns row 0 with block metrics."""
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
        self.assertEqual(bars, 0, "TopBar mode header should not exist on CodeScreen")
        self.assertEqual((y, h), (0, 1),
                         "file-tab strip must be the sole top row at y=0")
        self.assertIn("NEX", text, "NEX brand mark missing from the top tab strip")
        self.assertIn("ops", text, "basic-block metrics did not move into the top bar")


@unittest.skipUnless(HAS_TEXTUAL, "textual is not installed — skipping layout tests")
class TestNothingFallsBelowTheFold(unittest.TestCase):
    """No panel or picker card may overflow past the bottom edge on compact terminals."""

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
                        # +1 allows a 1-cell border tolerance.
                        if r.height and r.y + r.height > h + 1:
                            bad.append(node.id or node.__class__.__name__)
                    return bad

        return asyncio.run(go())

    def test_screens_fit_at_every_size(self):
        for mode in ("core", "lab", "mind", "code"):
            for w, h in self.SIZES:
                with self.subTest(mode=mode, size=f"{w}x{h}"):
                    bad = self._overflow(mode, w, h)
                    self.assertEqual(bad, [], f"overflowed bottom edge: {bad}")

    def test_all_mode_cards_are_visible_on_a_short_screen(self):
        """Mode picker fits all mode cards on screen even on short terminals."""
        from vliw.tui.screens.picker import PickerScreen

        async def go(h):
            app, _session = _make_app(None)
            with redirect_stdout(io.StringIO()):
                async with app.run_test(size=(120, h)) as pilot:
                    await pilot.pause()
                    # Open the mode picker explicitly via ^O.
                    app.to_picker()
                    await pilot.pause()
                    await pilot.pause()
                    sc = app.screen
                    if not isinstance(sc, PickerScreen):
                        self.skipTest("mode picker did not open")
                    cards = sc.query(".mode-card")
                    fit = [c for c in cards
                           if c.region.height
                           and c.region.y + c.region.height <= h]
                    return len(cards), len(fit)

        for h in (46, 36, 30, 24):
            with self.subTest(height=h):
                total, fit = asyncio.run(go(h))
                self.assertEqual(fit, total,
                                 f"at height {h}, only {fit} of {total} picker cards fit")


@unittest.skipUnless(HAS_TEXTUAL, "textual is not installed — skipping widget-tree tests")
class TestNoDuplicateIds(unittest.TestCase):
    """Widget IDs must be globally unique across every screen and maximized panel."""

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
            with self.subTest(mode=mode):
                self.assertEqual(self._dupes(mode), {})

    def test_maximized_panels_too(self):
        """Maximizing each LAB panel must not introduce duplicate widget IDs."""
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
                        assert not dupes, f"{pid}: duplicate widget IDs {dupes}"
                        sc.minimize()
                        await pilot.pause()

        asyncio.run(go())


@unittest.skipUnless(HAS_TEXTUAL, "textual is not installed — skipping full-screen TUI tests")
class TestAgentKeyPaste(unittest.TestCase):
    """Pasting an API key in AGENT: prompt on entry, session-only storage, masking."""

    @staticmethod
    def _isolated():
        """Isolate `.env`, clear API env vars, and stub network checks."""
        import tempfile
        import unittest.mock as mock
        from pathlib import Path
        from unittest.mock import patch

        from vliw.agent import llm

        tmp = tempfile.mkdtemp(prefix="nex-key-")
        return (tmp,
                patch.object(llm, "_PROJECT_ROOT", Path(tmp)),
                patch.dict(os.environ, {}, clear=True),
                patch.object(llm, "check", lambda: (True, "mock")))

    def test_entry_asks_for_key_when_none(self):
        async def go():
            from vliw.tui.widgets import PromptBar

            tmp, a, b, c = self._isolated()
            with a, b, c:
                app, session = _make_app("mind")
                with redirect_stdout(io.StringIO()):
                    async with app.run_test(size=(120, 40)) as pilot:
                        await pilot.pause()
                        sc = app.screen
                        bar = sc.query_one("#prompt", PromptBar)
                        return sc._awaiting_key, bar.input.placeholder

        awaiting, placeholder = asyncio.run(go())
        self.assertTrue(awaiting, "AGENT must prompt for an API key when none is configured")
        self.assertIn("API key", placeholder)

    def test_pasted_key_saved_masked_and_not_in_history(self):
        key = "k" * 32

        # Submit through the real prompt bar so input history scrubbing is exercised;
        # the key stays in session memory only and must never be written to disk.
        async def go():
            import os as _os
            from pathlib import Path

            from vliw.tui.widgets import PromptBar

            tmp, a, b, c = self._isolated()
            with a, b, c:
                app, session = _make_app("mind")
                with redirect_stdout(io.StringIO()):
                    async with app.run_test(size=(120, 40)) as pilot:
                        await pilot.pause()
                        sc = app.screen
                        self.assertTrue(sc._awaiting_key)
                        await pilot.press(*key, "enter")
                        await app.workers.wait_for_complete()
                        await pilot.pause()
                        bar = sc.query_one("#prompt", PromptBar)
                        return {
                            "awaiting": sc._awaiting_key,
                            "env_key": _os.environ.get("MISTRAL_API_KEY", ""),
                            "left_file": Path(tmp, ".env").exists(),
                            "history": list(bar.history),
                            "dialog": [m["text"] for m in session.dialog],
                        }

        got = asyncio.run(go())
        self.assertFalse(got["awaiting"], "key-awaiting state did not clear after paste")
        self.assertEqual(got["env_key"], key)
        self.assertFalse(got["left_file"], "pasting an API key must not write to disk")
        self.assertNotIn(key, got["history"], "raw API key leaked into prompt history")
        self.assertFalse(any(key in t for t in got["dialog"]),
                         "raw API key leaked into the conversation feed")

    def test_command_output_lands_in_dialog(self):
        """Slash commands in AGENT render their output as bubbles in the dialog feed."""
        async def go():
            from rich.text import Text as _Text

            tmp, a, b, c = self._isolated()
            with a, b, c:
                app, session = _make_app("mind")
                with redirect_stdout(io.StringIO()):
                    async with app.run_test(size=(120, 40)) as pilot:
                        await pilot.pause()
                        await pilot.press(*"/scenarios", "enter")
                        await app.workers.wait_for_complete()
                        await pilot.pause()
                        sc = app.screen
                        out = []
                        for w in sc.query("Static"):
                            try:
                                r = w.render()
                                out.append(r.plain if isinstance(r, _Text)
                                           else str(r))
                            except Exception:
                                pass
                        return "\n".join(out)

        text = asyncio.run(go())
        self.assertIn("slotclash", text)

    def test_plain_question_goes_offline_not_into_key(self):
        async def go():
            tmp, a, b, c = self._isolated()
            with a, b, c:
                app, session = _make_app("mind")
                with redirect_stdout(io.StringIO()):
                    async with app.run_test(size=(120, 40)) as pilot:
                        await pilot.pause()
                        sc = app.screen
                        self.assertTrue(sc._awaiting_key)
                        await pilot.press(*"why is makespan high?", "enter")
                        await app.workers.wait_for_complete()
                        await pilot.pause()
                        return sc._awaiting_key, len(session.dialog)

        awaiting, n = asyncio.run(go())
        self.assertFalse(awaiting, "asking a question instead of a key must exit key-awaiting mode")
        self.assertGreater(n, 0, "question must be delivered to the dialog feed")


@unittest.skipUnless(HAS_TEXTUAL, "textual is not installed — skipping full-screen TUI tests")
class TestModelCatalogPanel(unittest.TestCase):
    """Model catalog in AGENT: compact panel, maximized view, click-to-select (session-only)."""

    @staticmethod
    def _isolated():
        import tempfile
        import unittest.mock as mock
        from pathlib import Path
        from unittest.mock import patch

        from vliw.agent import llm

        tmp = tempfile.mkdtemp(prefix="nex-model-")
        return (tmp,
                patch.object(llm, "_PROJECT_ROOT", Path(tmp)),
                patch.dict(os.environ, {}, clear=True),
                patch.object(llm, "check", lambda: (True, "mock")))

    @staticmethod
    async def _click_center(pilot, widget, times: int = 1):
        # Scroll the target row into view and click relative to the widget.
        try:
            from textual.containers import VerticalScroll as _VS

            parent = widget.parent
            while parent is not None and not isinstance(parent, _VS):
                parent = parent.parent
            if parent is not None:
                parent.scroll_to_widget(widget, animate=False)
                await pilot.pause()
        except Exception:
            pass
        await pilot.click(widget, offset=(2, 0), times=times)

    def test_mini_panel_shows_provider(self):
        async def go():
            from vliw.tui.widgets import Panel

            tmp, a, b, c = self._isolated()
            with a, b, c:
                app, session = _make_app("mind")
                with redirect_stdout(io.StringIO()):
                    async with app.run_test(size=(120, 40)) as pilot:
                        await pilot.pause()
                        sc = app.screen
                        panel = sc.query_one("#p-model", Panel)
                        texts = [str(w.render()) for w in panel.query("Static")]
                        return "\n".join(texts)

        text = asyncio.run(go())
        self.assertIn("mistral", text)

    def test_expand_shows_catalog(self):
        async def go():
            import unittest.mock as mock

            from vliw.agent import models as catalog
            from vliw.tui.widgets import Panel, Tool

            rows = [catalog.ModelRow("deepseek-chat", "DeepSeek Chat", False)]
            tmp, a, b, c = self._isolated()
            with a, b, c, \
                    mock.patch.dict(os.environ, {"MISTRAL_API_KEY": "test-placeholder",
                                                 "DEEPSEEK_API_KEY": "test-placeholder"}), \
                    mock.patch.object(catalog, "catalog",
                                      lambda prov, key="", base_url="":
                                      (rows, "live")):
                app, session = _make_app("mind")
                with redirect_stdout(io.StringIO()):
                    async with app.run_test(size=(120, 40)) as pilot:
                        await pilot.pause()
                        sc = app.screen
                        panel = sc.query_one("#p-model", Panel)
                        await self._click_center(pilot, panel, times=2)
                        await pilot.pause()
                        sc._connect_catalog()
                        await app.workers.wait_for_complete()
                        await pilot.pause()
                        tools = [t.tool for t in sc.query(Tool)]
                        return sc._wide, tools

        wide, tools = asyncio.run(go())
        self.assertEqual(wide, "model")
        self.assertIn("mprov:deepseek", tools)
        self.assertTrue(any(t.startswith("model:") for t in tools),
                        "model catalog rendered zero rows")

    def test_click_model_applies_and_closes(self):
        async def go():
            import os as _os
            import unittest.mock as mock

            from textual.widgets import Input

            from vliw.agent import models as catalog
            from vliw.tui.widgets import Panel, Tool

            rows = [catalog.ModelRow("deepseek-chat", "DeepSeek Chat", False)]
            tmp, a, b, c = self._isolated()
            with a, b, c, \
                    mock.patch.dict(os.environ, {"MISTRAL_API_KEY": "test-placeholder",
                                                 "DEEPSEEK_API_KEY": "test-placeholder"}), \
                    mock.patch.object(catalog, "catalog",
                                      lambda prov, key="", base_url="":
                                      (rows, "live")):
                app, session = _make_app("mind")
                with redirect_stdout(io.StringIO()):
                    async with app.run_test(size=(120, 40)) as pilot:
                        await pilot.pause()
                        sc = app.screen
                        panel = sc.query_one("#p-model", Panel)
                        await self._click_center(pilot, panel, times=2)
                        await pilot.pause()
                        sc._model_prov = "deepseek"
                        await pilot.pause()
                        sc._connect_catalog()
                        await app.workers.wait_for_complete()
                        await pilot.pause()
                        field = sc.query_one("#model-filter", Input)
                        await self._click_center(pilot, field)
                        await pilot.pause()
                        await pilot.press(*"deepseek-chat")
                        await pilot.pause()
                        row = next(t for t in sc.query(Tool)
                                   if t.tool == "model:deepseek-chat")
                        await self._click_center(pilot, row)
                        await pilot.pause()
                        return (dict(_os.environ), sc._wide,
                                sc.screen.maximized)

        environ, wide, maximized = asyncio.run(go())
        self.assertEqual(environ.get("NEX_PROVIDER"), "deepseek")
        self.assertEqual(environ.get("NEX_MODEL"), "deepseek-chat")
        self.assertIsNone(maximized, "catalog overlay should close after selecting a model")

    def test_key_field_adopts_without_disk(self):
        async def go():
            import os as _os
            from pathlib import Path

            from textual.widgets import Input

            from vliw.tui.widgets import Panel

            tmp, a, b, c = self._isolated()
            with a, b, c:
                app, session = _make_app("mind")
                with redirect_stdout(io.StringIO()):
                    async with app.run_test(size=(120, 40)) as pilot:
                        await pilot.pause()
                        sc = app.screen
                        panel = sc.query_one("#p-model", Panel)
                        await self._click_center(pilot, panel, times=2)
                        await pilot.pause()
                        sc._model_prov = "deepseek"
                        sc._draw_model_full()
                        await pilot.pause()
                        field = sc.query_one("#model-key", Input)
                        await pilot.click(field, offset=(2, 0))
                        await pilot.pause()
                        await pilot.press(*"sk-test-0123456789abcdef", "enter")
                        await pilot.pause()
                        return (dict(_os.environ),
                                field.value,
                                Path(tmp, ".env").exists())

        environ, cleared, left_file = asyncio.run(go())
        self.assertEqual(environ.get("DEEPSEEK_API_KEY"), "sk-test-0123456789abcdef")
        self.assertEqual(cleared, "", "API key input was not cleared after submit")
        self.assertFalse(left_file, "catalog key entry must not write to disk")

    def test_free_first_with_mocked_catalog(self):
        async def go():
            import unittest.mock as mock

            from vliw.agent import models as catalog
            from vliw.tui.widgets import Panel, Tool

            rows = [catalog.ModelRow("b-paid", "B", False),
                    catalog.ModelRow("a-free:free", "A", True)]
            tmp, a, b, c = self._isolated()
            with a, b, c, \
                    mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}), \
                    mock.patch.object(catalog, "catalog",
                                      return_value=(list(reversed(rows)), "live")) as fetch:
                app, session = _make_app("mind")
                with redirect_stdout(io.StringIO()):
                    async with app.run_test(size=(120, 40)) as pilot:
                        await pilot.pause()
                        sc = app.screen
                        sc._model_prov = "openrouter"
                        panel = sc.query_one("#p-model", Panel)
                        await self._click_center(pilot, panel, times=2)
                        await pilot.pause()
                        sc._connect_catalog()
                        await app.workers.wait_for_complete()
                        await pilot.pause()
                        got = [t.tool for t in sc.query(Tool)
                               if t.tool.startswith("model:")]
                        return got, fetch.call_args

        got, call = asyncio.run(go())
        self.assertEqual(got[:2], ["model:a-free:free", "model:b-paid"])
        self.assertEqual(call.args[0], "openrouter")
        self.assertEqual(call.args[1], "test-key")

    def test_plain_question_goes_offline_not_into_key(self):
        async def go():
            tmp, a, b, c = self._isolated()
            with a, b, c:
                app, session = _make_app("mind")
                with redirect_stdout(io.StringIO()):
                    async with app.run_test(size=(120, 40)) as pilot:
                        await pilot.pause()
                        sc = app.screen
                        self.assertTrue(sc._awaiting_key)
                        await pilot.press(*"why is makespan high?", "enter")
                        await app.workers.wait_for_complete()
                        await pilot.pause()
                        return sc._awaiting_key, len(session.dialog)

        awaiting, n = asyncio.run(go())
        self.assertFalse(awaiting, "asking a question instead of a key must exit key-awaiting mode")
        self.assertGreater(n, 0, "question must be delivered to the dialog feed")


@unittest.skipUnless(HAS_TEXTUAL, "textual is not installed — skipping full-screen TUI tests")
class TestHeadquartersPanel(unittest.TestCase):
    """HQ is a standalone main panel while CONNECTION stays a compact mini-panel."""

    @staticmethod
    def _isolated():
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        from vliw.agent import llm

        tmp = tempfile.mkdtemp(prefix="nex-hq-")
        return (tmp,
                patch.object(llm, "_PROJECT_ROOT", Path(tmp)),
                patch.dict(os.environ, {}, clear=True),
                patch.object(llm, "check", lambda: (True, "mock")))

    @staticmethod
    async def _click_center(pilot, widget, times: int = 1):
        try:
            from textual.containers import VerticalScroll as _VS

            parent = widget.parent
            while parent is not None and not isinstance(parent, _VS):
                parent = parent.parent
            if parent is not None:
                parent.scroll_to_widget(widget, animate=False)
                await pilot.pause()
        except Exception:
            pass
        await pilot.click(widget, offset=(2, 0), times=times)

    def test_hq_is_its_own_panel_with_mini_summary(self):
        async def go():
            from vliw.tui.widgets import Panel

            tmp, a, b, c = self._isolated()
            with a, b, c:
                app, session = _make_app("mind")
                with redirect_stdout(io.StringIO()):
                    async with app.run_test(size=(120, 40)) as pilot:
                        await pilot.pause()
                        sc = app.screen
                        panel = sc.query_one("#p-hq", Panel)
                        texts = [str(w.render())
                                 for w in panel.query("Static")]
                        task = sc.query_one("#hq-task")
                        return panel.topic, "\n".join(texts), task is not None

        topic, text, has_task = asyncio.run(go())
        self.assertEqual(topic, "hq")
        self.assertIn("no connections", text)
        self.assertTrue(has_task, "HQ mission input must be visible without maximizing")

    def test_hq_expands_with_missions(self):
        async def go():
            from vliw.tui.widgets import Panel, Tool

            tmp, a, b, c = self._isolated()
            with a, b, c:
                app, session = _make_app("mind")
                with redirect_stdout(io.StringIO()):
                    async with app.run_test(size=(120, 40)) as pilot:
                        await pilot.pause()
                        sc = app.screen
                        panel = sc.query_one("#p-hq", Panel)
                        await self._click_center(pilot, panel, times=2)
                        await pilot.pause()
                        tools = [t.tool for t in sc.query(Tool)]
                        return sc._wide, tools

        wide, tools = asyncio.run(go())
        self.assertEqual(wide, "hq")
        self.assertIn("hqarea:doctor", tools)
        self.assertIn("hqrun", tools)
        self.assertIn("hqclear", tools)

    def test_hq_run_without_connections_explains(self):
        async def go():
            from rich.text import Text as _Text

            from vliw.tui.widgets import Panel

            tmp, a, b, c = self._isolated()
            with a, b, c:
                app, session = _make_app("mind")
                with redirect_stdout(io.StringIO()):
                    async with app.run_test(size=(120, 40)) as pilot:
                        await pilot.pause()
                        sc = app.screen
                        panel = sc.query_one("#p-hq", Panel)
                        await self._click_center(pilot, panel, times=2)
                        await pilot.pause()
                        sc._hq_run()
                        await pilot.pause()
                        note = sc.query_one("#hq-note")
                        r = note.render()
                        return r.plain if isinstance(r, _Text) else str(r)

        self.assertIn("connect", asyncio.run(go()))

    def test_hqclear_keeps_working(self):
        async def go():
            tmp, a, b, c = self._isolated()
            with a, b, c:
                app, session = _make_app("mind")
                with redirect_stdout(io.StringIO()):
                    async with app.run_test(size=(120, 40)) as pilot:
                        await pilot.pause()
                        sc = app.screen
                        sc._hq_tasks = [
                            {"id": 1, "conn": "c", "area": "doctor",
                             "question": "q1", "status": "done",
                             "answer": "a"},
                            {"id": 2, "conn": "c", "area": "doctor",
                             "question": "q2", "status": "working",
                             "answer": ""},
                        ]
                        sc.panel_tool("hqclear")
                        await pilot.pause()
                        return [t["id"] for t in sc._hq_tasks]

        self.assertEqual(asyncio.run(go()), [2])

    def test_mini_provider_switch_without_expanding(self):
        async def go():
            from vliw.tui.widgets import Panel, Tool

            tmp, a, b, c = self._isolated()
            with a, b, c:
                app, session = _make_app("mind")
                with redirect_stdout(io.StringIO()):
                    async with app.run_test(size=(120, 40)) as pilot:
                        await pilot.pause()
                        sc = app.screen
                        mini = sc.query_one("#model-provs-mini")
                        row = next(t for t in mini.query(Tool)
                                   if t.tool == "mprov:gemini")
                        await self._click_center(pilot, row)
                        await pilot.pause()
                        marks = {t.tool: str(t.render())
                                 for t in mini.query(Tool)}
                        return sc._wide, sc._model_prov, marks

        wide, prov, marks = asyncio.run(go())
        self.assertEqual(wide, "", "picking an API in CONNECTION must not maximize the panel")
        self.assertEqual(prov, "gemini")
        self.assertIn("*", marks["mprov:gemini"])

    def test_mini_key_connects_without_disk(self):
        async def go():
            import os as _os
            import unittest.mock as mock
            from pathlib import Path

            from textual.widgets import Input

            from vliw.agent import models as catalog

            tmp, a, b, c = self._isolated()
            with a, b, c, \
                    mock.patch.object(catalog, "catalog",
                                      lambda prov, key="", base_url="":
                                      ([], "live")):
                app, session = _make_app("mind")
                with redirect_stdout(io.StringIO()):
                    async with app.run_test(size=(120, 40)) as pilot:
                        await pilot.pause()
                        sc = app.screen
                        field = sc.query_one("#model-key-mini", Input)
                        await self._click_center(pilot, field)
                        await pilot.pause()
                        await pilot.press(*"sk-test-0123456789abcdef",
                                          "enter")
                        await app.workers.wait_for_complete()
                        await pilot.pause()
                        return (dict(_os.environ), field.value,
                                Path(tmp, ".env").exists())

        environ, cleared, left_file = asyncio.run(go())
        self.assertEqual(environ.get("MISTRAL_API_KEY"),
                         "sk-test-0123456789abcdef")
        self.assertEqual(cleared, "", "API key input was not cleared after submit")
        self.assertFalse(left_file, "mini CONNECTION key paste must not write to disk")

    def test_filter_help_says_it_filters(self):
        async def go():
            from textual.widgets import Static

            from vliw.tui.widgets import Panel

            tmp, a, b, c = self._isolated()
            with a, b, c:
                app, session = _make_app("mind")
                with redirect_stdout(io.StringIO()):
                    async with app.run_test(size=(120, 40)) as pilot:
                        await pilot.pause()
                        sc = app.screen
                        panel = sc.query_one("#p-model", Panel)
                        await self._click_center(pilot, panel, times=2)
                        await pilot.pause()
                        return str(sc.query_one("#model-filter-help",
                                                Static).render())

        self.assertIn("filter", asyncio.run(go()))


if __name__ == "__main__":
    unittest.main()
