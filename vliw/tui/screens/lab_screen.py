"""LAB — interactive VLIW schedule explorer.

Instead of printing static schedule tables to a scroll log, LAB renders an
interactive `cycles x channels` grid with cursor navigation and a live "WHY
HERE" pane explaining why each operation landed where it did.

Layout:
    left    BLOCK (scenario chips), SCHEDULE grid, GIT (command output)
    right   NUMBERS, NEURAL NETS, WHY HERE, DIAGNOSIS, MACHINE

Keyboard sharing: while the prompt has focus, all keys type text; F2 toggles
focus between the grid and prompt, and any unbound printable key in the grid
returns focus to the prompt. Esc always steps back one level.
"""

from __future__ import annotations

from rich.text import Text
from textual import work
from textual.containers import Horizontal, ItemGrid, Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import DataTable, Input, Static

from ...core import SCENARIOS
from .. import palette
from ..widgets import (Chip, Console, ConsoleJournal, HintBar, Panel,
                       PanelToolbar, PromptBar, SleepChip, TopBar, plural)
from .base import ModeScreen

CONT = "│"
EMPTY = "·"
VIEWS = {"baseline": "baseline", "oracle": "oracle", "model": "model"}


def _takt(n: int) -> str:
    """Return 'cycle' or 'cycles' for count `n`."""
    return "cycle" if n == 1 else "cycles"


def _wrapped(text: str, width: int, indent: int) -> str:
    """Wrap text with a hanging indent."""
    import textwrap

    pad = " " * indent
    lines = textwrap.wrap(text, max(12, width - indent)) or [""]
    return ("\n" + pad).join(lines)


class ScheduleGrid(DataTable):
    """Interactive schedule grid with single-key navigation and layer toggles."""

    #: Key -> screen panel_tool action ID.
    TOOL_KEYS = {
        "n": "diag-next", "N": "diag-prev",
        "]": "op-next", "[": "op-prev",
        "c": "chain-step",
        "v": "/view",
        "z": "deps-toggle", "x": "gaps-toggle",
        "p": "crit-toggle", "w": "cells-toggle",
        "o": "open-console",
        "d": "open-diag",
    }

    def on_key(self, event) -> None:
        ch = event.character
        if ch in self.TOOL_KEYS:
            event.stop()
            event.prevent_default()
            screen = self.screen
            if hasattr(screen, "panel_tool"):
                screen.panel_tool(self.TOOL_KEYS[ch])
            return
        if ch and ch.isprintable() and event.key not in ("space",):
            event.stop()
            event.prevent_default()
            bar = self.screen.query_one("#prompt", PromptBar)
            bar.focus_input()
            bar.set_value(bar.input.value + ch)


class FindingItem(Static):
    """Clickable finding row in maximized DIAGNOSIS; jumps grid cursor to it."""

    class Picked(Message):
        def __init__(self, index: int) -> None:
            super().__init__()
            self.index = index

    def __init__(self, index: int, *args, **kw) -> None:
        super().__init__(*args, **kw)
        self.index = index

    def on_click(self, event) -> None:
        event.stop()
        self.post_message(self.Picked(self.index))


class GridLink(Static):
    """Bridge bar under maximized SCHEDULE jumping to the active finding in DIAGNOSIS."""

    class Picked(Message):
        pass

    def __init__(self, *args, **kw) -> None:
        super().__init__(*args, **kw)
        self.active = False

    def on_click(self, event) -> None:
        event.stop()
        if self.active:
            self.post_message(self.Picked())


class InstrLink(Static):
    """Clickable operation link that jumps the schedule grid cursor to its cell."""

    class Picked(Message):
        def __init__(self, instr: int) -> None:
            super().__init__()
            self.instr = instr

    def __init__(self, instr: int, *args, **kw) -> None:
        super().__init__(*args, **kw)
        self.instr = instr

    def on_click(self, event) -> None:
        event.stop()
        self.post_message(self.Picked(self.instr))


class LabScreen(ModeScreen):
    mode = "lab"
    mode_title = "LAB"
    mode_subtitle = "analysis"
    placeholder = "command or question"
    hint = "'/' catalog   ·   ↑ history"
    SIDE_ID = "#lab-right"
    TIPS_ID = "#p-scen"

    BINDINGS = ModeScreen.BINDINGS + [
        ("f2", "swap_focus", "grid <> input"),
    ]

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self.view = "baseline"
        self.base = None
        self.orc = None
        self.met = None
        self.diverged: set[int] = set()
        self._cells: dict[tuple[int, int], int] = {}
        # Live trained-model schedule run (keeps raw output with illegal slots
        # until the user explicitly runs `/repair`).
        self.model_sched = None
        self.model_note = ""
        self.model_repairs: list[tuple[int, int, int]] = []
        # Target (cycle, port) to restore after async grid rebuilds.
        self._want_cell: tuple[int, int] | None = None
        # Cursor-driven AI explanation state.
        self._detail_base: Text | None = None
        self._cell_ai_token = 0
        self._cell_ai_text = ""
        self._cell_ai_state = ""        # "" | "waiting" | "ready" | error text
        self._cell_ai_on = True
        self._cell_ai_facts: list[str] = []
        # Grid row map: ("cycle", c) or ("gap", start, end).
        self._rows: list[tuple] = []
        self._expanded_gaps: set[tuple[int, int]] = set()
        # Per-panel maximized mode flags.
        self._diag_expanded = False
        self._grid_expanded = False
        self._numbers_expanded = False
        self._machine_expanded = False
        self._detail_expanded = False
        self._console_expanded = False
        self._scen_expanded = False
        self._matrix_ops: list[str] = []
        # Sort/filter state for maximized MACHINE matrix.
        self._matrix_sort_key = "cnt"
        self._matrix_sort_rev = True
        self._matrix_filter = ""
        # Sort/filter state for maximized BLOCK catalog.
        self._scen_sort_key = "family"
        self._scen_sort_rev = False
        self._scen_filter = ""
        self._scen_keys: list[str] = []
        self._diag_filter = "all"      # all | high | medium | low | limit
        self._find_pos = -1
        # Schedule grid display toggles (x, p, w, z).
        self._all_cycles = False
        self._crit_on = True
        self._wide_cells = False
        self._deps_on = False

    # --- layout -----------------------------------------------------------

    def compose(self):
        """LAB scaffold: embedded prompt inside GIT instead of a bottom dock."""
        yield TopBar(self.mode, self.mode_title, self.mode_subtitle, id="topbar")
        yield from self.compose_body()
        yield HintBar(id="hints")

    def compose_body(self):
        with Horizontal(id="lab-body"):
            with Vertical(id="lab-left"):
                yield Panel(ItemGrid(id="scenario-chips", min_column_width=13),
                            Vertical(
                                Static(id="scen-head"),
                                Horizontal(
                                    Static("filter", id="scen-filter-label"),
                                    Input(placeholder="name, family, or "
                                                       "description",
                                          id="scen-filter"),
                                    id="scen-filter-row"),
                                DataTable(id="scen-table", cursor_type="row",
                                         zebra_stripes=False),
                                Static(id="scen-foot"),
                                id="scen-wide"),
                            title="BLOCK", id="p-scen", topic="scen")
                yield Panel(
                    Horizontal(
                        Horizontal(id="view-chips"),
                        Static("", id="grid-hud"),
                        id="grid-head"),
                    Horizontal(
                        ScheduleGrid(id="grid", cursor_type="cell",
                                     zebra_stripes=False),
                        VerticalScroll(
                            Static(id="side-cursor"),
                            Static(id="side-finding"),
                            Static(id="side-ports"),
                            Static(id="side-legend"),
                            id="grid-side"),
                        id="grid-main"),
                    GridLink(id="grid-link"),
                    title="SCHEDULE", id="p-grid", topic="grid")
                yield Panel(
                    PanelToolbar(
                        ("~ repeat", "journal-repeat",
                         "re-run selected history entry (^R)"),
                        ("clear", "journal-wipe",
                         "clear git history (^L)"),
                        ("grid >", "open-grid",
                         "maximize SCHEDULE"),
                    ),
                    Console(id="console",
                            runs=self.app.session.journal_runs),
                    PromptBar(self.mode, self.placeholder,
                              list(self.app.commands) + self.extra_commands(),
                              hint=self.hint, id="prompt"),
                    ConsoleJournal(id="journal"),
                    title="GIT",
                    id="p-console", topic="console",
                    has_own_input=True)
            with Vertical(id="lab-right"):
                yield Panel(
                    PanelToolbar(
                        ("grid >", "open-grid", "maximize SCHEDULE"),
                        ("diagnosis >", "open-diag",
                         "maximize DIAGNOSIS — all findings"),
                    ),
                    Static(id="numbers"),
                    VerticalScroll(
                        Static(id="numbers-head"),
                        Vertical(id="numbers-chain"),
                        Static(id="numbers-res"),
                        id="numbers-why"),
                    title="NUMBERS",
                    id="p-numbers", topic="numbers")
                yield Panel(
                    VerticalScroll(Static(id="ai-body"), id="ai-scroll"),
                    title="NEURAL NETS",
                    id="p-ai", topic="ai")
                yield Panel(
                    PanelToolbar(
                        ("< op", "op-prev",
                         "jump cursor to previous scheduled op"),
                        ("op >", "op-next",
                         "jump cursor to next scheduled op"),
                        ("chain >", "chain-step",
                         "next op on critical path", "tb-spare"),
                        ("grid >", "open-grid",
                         "maximize SCHEDULE", "tb-spare"),
                    ),
                    VerticalScroll(Static(id="detail"), id="detail-scroll"),
                    Horizontal(
                        Vertical(id="detail-preds"),
                        Vertical(id="detail-succs"),
                        id="detail-graph"),
                    title="WHY HERE",
                    id="p-detail", topic="detail")
                yield Panel(
                    PanelToolbar(
                        ("< prev", "diag-prev", "previous finding"),
                        ("next >", "diag-next", "next finding"),
                        ("reset filter", "/find filter all",
                         "show findings of all severities", "tb-spare"),
                        ("grid >", "show-active",
                         "jump cursor to active finding cell", "tb-spare"),
                    ),
                    Horizontal(id="diag-filter"),
                    VerticalScroll(id="diag-scroll"),
                    title="DIAGNOSIS", id="p-diag", topic="diag")
                yield Panel(
                    PanelToolbar(
                        ("by count", "matrix-sort-cnt",
                         "sort by op count in current block"),
                        ("by latency", "matrix-sort-lat",
                         "sort by operation latency"),
                        ("grid >", "open-grid",
                         "maximize SCHEDULE", "tb-spare"),
                    ),
                    Static(id="machine"),
                    Horizontal(
                        Static("filter", id="machine-filter-label"),
                        Input(placeholder="op name substring",
                              id="machine-filter"),
                        id="machine-filter-row"),
                    DataTable(id="machine-matrix", cursor_type="row",
                              zebra_stripes=False),
                    Static(id="machine-foot"),
                    title="MACHINE",
                    id="p-machine", topic="machine")

    def on_ready(self) -> None:
        self._fill_chips()
        self._draw_machine()
        self._seed_console()
        self.recompute()

    def _seed_console(self) -> None:
        con = self.console
        if con is None:
            return
        dim = palette.role_hex("dim")
        accent = palette.role_hex("lab")
        con.write(Text("command reports appear here", style=dim))
        for cmd, note in (
            ("/compare", "baseline and oracle side by side"),
            ("/doctor", "where cycles are lost"),
            ("/asm", "schedule as e2k wide instructions { … }"),
            ("/load examples/probe.s", "analyze real .s assembly from lcc"),
        ):
            row = Text()
            row.append("  " + cmd.ljust(24), style=accent)
            row.append(note, style=dim)
            con.write(row)

    def hint_pairs(self):
        out = [("F2", "grid <> input"), ("↑↓←→", "cycles"),
               ("Enter", "explain cycle"), ("Esc", "back")]
        if self._grid_expanded:
            out += [("n/N", "findings"), ("[/]", "ops"),
                    ("c", "chain"), ("v", "view"), ("z", "neighbors"),
                    ("d", "diagnosis")]
        return out

    # --- dormant mode facts in second header line -------------------------

    def sleep_facts(self) -> list[tuple[str, str, str]]:
        """Return `(label, summary, mode)` for dormant modes with active state."""
        out = []
        for label, mode in (("CORE", "work"), ("AGENT", "mind"),
                            ("CODE", "code")):
            body = getattr(self, f"_sleep_{mode}")()
            if body:
                out.append((label, body, mode))
        return out

    def _sleep_work(self) -> str | None:
        """Report interpreter graph size and whether it is the active LAB block."""
        s = self.app.session
        ws = s._workspace
        if ws is None or ws.empty():
            return None
        snap = ws.snapshot()
        sent = (s.dag_obj is not None and s.dag_obj.key == snap.key
                and len(s.dag_obj) == len(snap))
        return f"graph {len(snap)} ops, " + ("sent" if sent else "not sent")

    def _sleep_mind(self) -> str | None:
        """Report number of questions asked in AGENT this session."""
        ag = self.app.session._agent
        if ag is None or not ag.history:
            return None
        n = len(ag.history)
        return f"{n} {plural(n, 'question', 'questions', 'questions')}"

    def _sleep_code(self) -> str | None:
        """Report if CODE buffer was edited since the last `/code run` / F5."""
        s = self.app.session
        if not s.code_text.strip() or s.code_text == s.code_run_text:
            return None
        return "buffer edited, not run"

    def on_sleep_chip_goto(self, event: SleepChip.Goto) -> None:
        event.stop()
        self.app.open_mode(event.mode)

    def refresh_context(self) -> None:
        super().refresh_context()
        try:
            self.query_one("#topbar", TopBar).sleepers = \
                tuple(self.sleep_facts())
        except Exception:
            pass

    def on_nex_input_pasted(self, event) -> None:
        super().on_nex_input_pasted(event)
        self.refresh_context()

    def _pp_done(self, seconds: float, acted: bool = False) -> None:
        super()._pp_done(seconds, acted)
        self.refresh_context()

    # --- chips ------------------------------------------------------------

    def _fill_chips(self) -> None:
        row = self.query_one("#view-chips", Horizontal)
        row.mount(Static("view", classes="chip-label"))
        for key, label in VIEWS.items():
            chip = Chip(label, f"/view {key}", classes="chip chip-view",
                        id=f"view-{key}")
            chip.tooltip = "select which schedule to show in the grid"
            row.mount(chip)
        grid = self.query_one("#scenario-chips", ItemGrid)
        for key in sorted(SCENARIOS):
            chip = Chip(key, f"/run {key}", classes="chip chip-scen",
                        id=f"scen-{key}")
            chip.tooltip = "run this block"
            grid.mount(chip)
        self._mark_view()

    def _mark_view(self) -> None:
        for key in VIEWS:
            try:
                self.query_one(f"#view-{key}", Chip).set_class(
                    key == self.view, "chip-on")
            except Exception:
                pass
        current = self.app.session.scenario
        for key in SCENARIOS:
            try:
                self.query_one(f"#scen-{key}", Chip).set_class(
                    key == current, "chip-on")
            except Exception:
                pass

    # --- input ------------------------------------------------------------

    def extra_commands(self) -> list[dict]:
        return [
            {"name": "view", "arg": "[baseline|oracle|model]",
             "help": "which schedule to show in the grid", "local": True},
            {"name": "repair", "arg": "",
             "help": "reassign illegal channels in model output",
             "local": True},
            {"name": "find", "arg": "[next|prev|filter <severity>]",
             "help": "jump cursor to next/previous doctor finding",
             "local": True},
        ]

    def handle_line(self, line: str) -> None:
        head, _, arg = line.lstrip("/").partition(" ")
        if head.lower() == "view":
            self._set_view(arg.strip().lower() or
                           ("oracle" if self.view == "baseline" else "baseline"))
            return
        if head.lower() == "repair":
            self._repair_model()
            return
        if head.lower() == "find":
            self._cmd_find(arg.strip().lower())
            return
        self.run_core(line)

    # --- maximized panel tools --------------------------------------------

    def panel_tool(self, tool: str) -> None:
        if tool in ("@lab", "@agent", "@work", "@code"):
            return super().panel_tool(tool)
        if tool.startswith("/"):
            self.handle_line(tool)
            return
        if tool == "grid-home":
            self._cursor_to_row(0)
        elif tool == "grid-end":
            grid = self.query_one("#grid", ScheduleGrid)
            self._cursor_to_row(max(len(self._rows) - 1, 0), grid)
        elif tool == "gaps-toggle":
            self._toggle_all_cycles()
        elif tool == "crit-toggle":
            self._toggle_crit()
        elif tool == "cells-toggle":
            self._toggle_wide_cells()
        elif tool == "deps-toggle":
            self._toggle_deps()
        elif tool == "op-prev":
            self._step_op(-1)
        elif tool == "op-next":
            self._step_op(1)
        elif tool == "chain-step":
            self._step_chain()
        elif tool == "diag-prev":
            self._cmd_find("prev")
        elif tool == "diag-next":
            self._cmd_find("next")
        elif tool == "show-active":
            f = self._active_finding()
            if f is not None:
                findings = self._filtered_findings()
                self._find_pos = findings.index(f) if f in findings else -1
                self._jump_to_finding(f)
        elif tool.startswith("open-"):
            panels = {"open-grid": ("#p-grid", "grid"),
                      "open-diag": ("#p-diag", "diag"),
                      "open-console": ("#p-console", "console")}
            if tool in panels:
                self._open_panel(*panels[tool])
        elif tool == "journal-repeat" or tool == "journal-wipe":
            try:
                journal = self.query_one("#journal", ConsoleJournal)
            except Exception:
                return
            journal.action_repeat() if tool == "journal-repeat" \
                else journal.action_wipe()
        elif tool.startswith("matrix-sort-"):
            key = tool[len("matrix-sort-"):]
            if key in ("cnt", "lat", "op", "occ"):
                self._matrix_sort_key = key
                self._matrix_sort_rev = self.MATRIX_SORT_DEFAULT_REV.get(key,
                                                                         True)
                self._draw_machine_matrix()
        else:
            super().panel_tool(tool)

    def _cursor_to_row(self, row: int, grid: ScheduleGrid | None = None) -> None:
        """Move grid cursor to a cycle/gap row and refresh dependent panes."""
        if not self._rows:
            return
        grid = grid or self.query_one("#grid", ScheduleGrid)
        col = min(grid.cursor_coordinate.column,
                  max(self.app.session.model().width - 1, 0))
        grid.move_cursor(row=min(row, len(self._rows) - 1), column=col)
        self._draw_detail()
        self._draw_diag()
        self._draw_grid_link()
        self._update_grid_hud()

    def _toggle_all_cycles(self) -> None:
        """Toggle collapsing idle gaps (`x`)."""
        self._all_cycles = not self._all_cycles
        self._redraw_grid_keep_cursor()
        self._draw_side()

    def _toggle_crit(self) -> None:
        """Toggle critical-path highlighting (`p`)."""
        self._crit_on = not self._crit_on
        self._redraw_grid_keep_cursor()

    def _toggle_wide_cells(self) -> None:
        """Toggle wide cells (`w`): 11 -> 17 columns so longer names fit."""
        self._wide_cells = not self._wide_cells
        self._redraw_grid_keep_cursor()

    def _toggle_deps(self) -> None:
        """Toggle neighbor dimming (`z`): highlight direct preds/succs only."""
        self._deps_on = not self._deps_on
        self._last_deps_instr = None
        self._redraw_grid_keep_cursor()

    @property
    def _cell_w(self) -> int:
        return 17 if self._wide_cells else 11

    def _cycle_of_row(self, row: int) -> int:
        if 0 <= row < len(self._rows):
            return self._rows[row][1]
        return 0

    def _redraw_grid_keep_cursor(self) -> None:
        grid = self.query_one("#grid", ScheduleGrid)
        cur = grid.cursor_coordinate
        if 0 <= cur.row < len(self._rows):
            self._want_cell = (self._cycle_of_row(cur.row), cur.column)
        self._draw_grid()

    def _cursor_relatives(self) -> set[int]:
        """Direct predecessors and successors of the op under the cursor."""
        target = self._cursor_target()
        if not target or target[0] != "cycle" or target[3] is None:
            return set()
        dag = self.app.session.dag_obj
        ins = dag[target[3]]
        return {target[3], *ins.preds, *dag.succs[target[3]]}

    def _sync_grid_tools(self) -> None:
        self._draw_side()

    def _step_op(self, delta: int) -> None:
        """Move grid cursor to the next/previous op by instruction ID."""
        instrs = sorted(set(self._cells.values()))
        if not instrs:
            return
        target = self._cursor_target()
        cur = target[3] if target and target[0] == "cycle" else None
        idx = instrs.index(cur) if cur in instrs else -1 if delta > 0 else 0
        nxt = instrs[(idx + delta) % len(instrs)]
        if not self._jump_to_instr(nxt):
            self.app.bell()

    def _step_chain(self) -> None:
        """Move grid cursor to the next op along the critical path."""
        chain = self._critical_chain()
        if not chain:
            return
        target = self._cursor_target()
        cur = target[3] if target and target[0] == "cycle" else None
        idx = chain.index(cur) if cur in chain else -1
        if not self._jump_to_instr(chain[(idx + 1) % len(chain)]):
            self.app.bell()

    def _open_panel(self, panel_id: str, topic: str) -> None:
        """Switch maximized view cleanly to another LAB panel."""
        for t in ("scen", "grid", "detail", "console",
                  "numbers", "diag", "machine"):
            setattr(self, f"_{t}_expanded", t == topic)
        self.screen.minimize()
        panel = self.query_one(panel_id, Panel)
        self.screen.maximize(panel, container=False)
        self.post_message(Panel.Expanded(panel))
        self._draw_journal()
        self._draw_scen_catalog()
        self._draw_diag()
        self._draw_grid_link()
        self._draw_numbers()
        self._draw_machine()
        self._draw_detail()

    def _repair_model(self) -> None:
        """Reassign illegal channels in model output without changing cycles."""
        con = self.console
        if self.model_sched is None or not self.model_sched.placements:
            if con is not None:
                con.note("  nothing to repair: model has not run yet", "warning")
            return
        if not self.model_repairs:
            if con is not None:
                con.note("  nothing to repair: no illegal channels", "dim")
            return
        was = len(self._model_illegal())
        for i, _frm, to in self.model_repairs:
            p = self.model_sched.placements.get(i)
            if p is not None:
                self.model_sched.place(i, p.cycle, to)
        self.model_note = f"hybrid: repaired {len(self.model_repairs)} channels"
        self.model_repairs = []
        if con is not None:
            con.note(f"  repaired channels: {was}  ·  model cycles untouched, "
                     f"makespan unchanged", "success")
        self.view = "model"
        self._mark_view()
        self._draw_model_grid()
        self._draw_detail()

    def _set_view(self, view: str) -> None:
        view = {"base": "baseline", "оракул": "oracle", "orc": "oracle",
                "модель": "model", "learned": "model"}.get(view, view)
        if view not in VIEWS:
            if self.console is not None:
                self.console.note("  view must be baseline, oracle, or model",
                                  "warning")
            return
        self.view = view
        self._want_cell = None
        self._mark_view()
        self._draw_grid()
        self._draw_detail()

    # --- live model stream ------------------------------------------------

    def on_scheduler_text(self, text: str) -> None:
        con = self.console
        if con is not None:
            con.note("  " + text.replace("[end of text]", "").rstrip(), "dim")

    def on_scheduler_event(self, ev) -> None:
        from ...core import Done, Failed, Note, Placed, Repaired, Started
        from ...core.schedule import Schedule

        con = self.console
        if isinstance(ev, Started):
            if ev.who != "learned":
                return
            self._want_cell = None
            self.model_sched = Schedule(self.app.session.dag_obj,
                                        self.app.session.model())
            self.model_note = "generating…"
            self.model_repairs = []
            self.view = "model"
            self._mark_view()
            self._draw_model_grid()
            return
        if isinstance(ev, Note):
            if con is not None:
                con.note("  " + ev.text, ev.level)
            return
        if self.model_sched is None:
            return
        if isinstance(ev, Placed):
            p = ev.placement
            self.model_sched.place(p.instr, p.cycle, p.channel)
            self._want_cell = (p.cycle, p.channel)
            self._draw_model_grid()
            self._draw_detail()
            self._draw_numbers()
            return
        if isinstance(ev, Repaired):
            self.model_repairs.append((ev.instr, ev.frm, ev.to))
            return
        if isinstance(ev, Failed):
            self.model_note = "failed to start"
            self._draw_model_grid()
            return
        if isinstance(ev, Done):
            self._model_done(ev.result)

    def _first_illegal_cell(self) -> tuple[int, int] | None:
        """Return `(cycle, port)` of the earliest illegal model placement."""
        illegal = self._model_illegal()
        if not illegal or self.model_sched is None:
            return None
        p = min((self.model_sched.placements[i] for i in illegal),
                key=lambda pl: (pl.cycle, pl.channel))
        return p.cycle, p.channel

    def _model_done(self, res) -> None:
        illegal = self._model_illegal()
        placed = len(self.model_sched.placements) if self.model_sched else 0
        total = len(self.app.session.dag_obj)
        if placed < total:
            self.model_note = f"unplaced {total - placed}"
        elif illegal:
            self.model_note = ""      # illegal count is already in the title
        else:
            self.model_note = f"legal, {self.model_sched.makespan} cyc"
        self._draw_model_grid()

        cell = self._first_illegal_cell()
        con = self.console
        if cell is not None:
            self._want_cell = cell
            self._draw_model_grid()
            if con is not None:
                machine = self.app.session.model()
                con.note(f"  illegal channels: {len(illegal)}  ·  first: "
                         f"cycle {cell[0]}, port {machine.port_label(cell[1])}"
                         f"  —  cursor moved there", "warning")
        self._draw_detail()
        if con is not None and self.model_repairs:
            con.note("  repair channels without changing cycles:  /repair",
                     "warning")

    def panel_facts(self, topic: str) -> list[str]:
        """Collect grounded facts for the active maximized panel."""
        s = self.app.session
        base = [f"Block {s.scenario}, {len(s.dag_obj)} ops, "
                f"machine {s.model().name}."]
        if topic == "grid":
            return base + self._grid_facts()
        if topic == "diag":
            return base + self._diag_facts()
        if topic == "numbers":
            return base + self._numbers_facts()
        if topic == "machine":
            return base + self._machine_facts()
        if topic == "detail":
            return base + self._detail_facts()
        if topic == "scen":
            return base + [
                f"Available blocks: {len(SCENARIOS)}.",
                "List: " + ", ".join(sorted(SCENARIOS)) + ".",
                f"Currently open: {s.scenario}: "
                + (SCENARIOS[s.scenario].lesson or SCENARIOS[s.scenario].note
                   or "")]
        if topic == "console":
            con = self.query_one("#console", Console)
            return base + [f"Session git commits: {len(con.runs)}."] + \
                [f"Ran {r['cmd']} ({len(r['lines'])} output lines)."
                 for r in con.runs[-6:]]
        return base

    def panel_chips(self, topic: str) -> list[str]:
        """Suggested questions tailored to each LAB panel."""
        return {
            "grid": ["why is there an idle gap here?",
                     "which op is holding up the schedule?",
                     "what is running on the exclusive port?"],
            "diag": ["which finding should I tackle first?",
                     "how many cycles are actually recoverable?",
                     "why is this not a hardware limit?"],
            "numbers": ["why is the lower bound this value?",
                        "what holds up the critical path?",
                        "is this bound by resources or dependencies?"],
            "machine": ["how does this profile differ from default?",
                        "what does exclusive port mean?",
                        "why is div so expensive?"],
            "detail": ["why can't this op issue earlier?",
                       "which ops depend on it?",
                       "what happens if we remove it?"],
            "scen": ["which block should I inspect next?",
                     "how does this block differ from its neighbor?",
                     "what breaks in this block?"],
            "console": ["summarize the last report",
                        "how does /doctor differ from /compare?",
                        "what command should I run next?"],
        }.get(topic, [])

    def _diag_facts(self) -> list[str]:
        out = []
        for f in self._findings()[:6]:
            out.append(f"Finding: {f.title} ({f.where}), loses "
                       f"{f.cycles_lost} cyc, "
                       f"{'recoverable' if f.recoverable else 'machine bound'}.")
        return out or ["No findings: baseline hits the lower bound."]

    def _numbers_facts(self) -> list[str]:
        if self.base is None or self.met is None:
            return ["Schedule not computed yet."]
        m = self.met
        out = [f"baseline {self.base.schedule.makespan} cyc, "
               f"oracle {self.orc.schedule.makespan} cyc, "
               f"lower bound {m.lower_bound} cyc ({m.binding}).",
               f"Critical path {m.critical_path_bound} cyc, "
               f"resource bound {m.resource_bound} cyc."]
        dag = self.app.session.dag_obj
        chain = self._critical_chain()
        if chain:
            out.append("Critical path passes through: "
                       + ", ".join(dag[i].name for i in chain[:8]) + ".")
        return out

    def _machine_facts(self) -> list[str]:
        model = self.app.session.model()
        out = [f"Profile {model.name}: {model.width} ports. "
               f"Matrix source: {model.matrix_source}."]
        for port, ops in sorted(model.sole_host_ops().items()):
            out.append(f"Port {model.port_label(port)} is the sole "
                       f"executor for {', '.join(ops)}.")
        for name in sorted(model.ops):
            op = model.ops[name]
            out.append(f"{name}: latency {op.latency} cyc"
                       + (f", occupies port {op.occupancy} cyc" if
                          op.blocks_channel() else "")
                       + f" (source: {op.latency_source}).")
        return out[:10]

    def _detail_facts(self) -> list[str]:
        target = self._cursor_target()
        if target is None or target[0] != "cycle" or target[3] is None:
            return ["Cursor is not on an operation."]
        instr = target[3]
        dag, model = self.app.session.dag_obj, self.app.session.model()
        ins = dag[instr]
        out = [f"Op {ins.name}: {ins.text}, class {ins.op}, "
               f"latency {model.latency(ins.op)} cyc."]
        if self.met is not None:
            alap = self.met.critical_path_bound - self.met.height[instr]
            out.append(f"Earliest cycle {self.met.asap[instr]} "
                       f"(dependencies), latest {alap} without "
                       f"lengthening the schedule.")
        if self.base is not None:
            pl = self.base.schedule.placements.get(instr)
            if pl:
                out.append(f"Placed at cycle {pl.cycle} on port "
                           f"{model.port_label(pl.channel)}.")
        out.append("Waited for: " + (", ".join(dag[i].name for i in ins.preds)
                                     or "none"))
        out.append("Blocks: " + (", ".join(dag[i].name
                                           for i in dag.succs[instr])
                                 or "none"))
        return out

    def _grid_facts(self) -> list[str]:
        s = self.app.session
        out = [f"Grid shows '{VIEWS.get(self.view, self.view)}' view: "
               f"cycles vertically, channels (ports) horizontally."]
        if self.view == "model" and self.model_sched is not None:
            illegal = self._model_illegal()
            out.append(f"RAW trained-model output, placed "
                       f"{len(self.model_sched.placements)} of {len(s.dag_obj)}.")
            if illegal:
                dag, machine = s.dag_obj, s.model()
                out.append(f"Illegal placements: {len(illegal)} "
                           f"(channel does not support op).")
                for i in sorted(illegal)[:4]:
                    p = self.model_sched.placements[i]
                    ok = ", ".join(machine.port_label(c)
                                   for c in machine.channels_for(dag[i].op))
                    out.append(f"  {dag[i].op} #{i} placed on "
                               f"{machine.port_label(p.channel)}, valid ports: "
                               f"{ok}.")
            else:
                out.append("No illegal placements.")
            return out
        res = self._result
        if res is None:
            return out + ["Schedule not computed yet — run /run."]
        sch = res.schedule
        out.append(f"Issue spans {sch.span_cycles} cycles, completes at "
                   f"cycle {sch.makespan}, slot utilization "
                   f"{sch.slot_utilization:.0%}.")
        empty = [c for c in range(sch.span_cycles)
                 if not any(p.cycle == c for p in sch.placements.values())]
        if empty:
            out.append(f"Completely empty cycles: {len(empty)} "
                       f"(e.g., {', '.join('c' + str(c) for c in empty[:6])}).")
        return out

    def _cursor_facts(self) -> list[str]:
        """Collect concise facts about the cell or gap under the cursor."""
        s = self.app.session
        target = self._cursor_target()
        if target is None:
            return []
        machine, dag = s.model(), s.dag_obj
        if target[0] == "gap":
            f = self._gap_finding(target[1], target[2])
            if f is None:
                return []
            return [f"Idle gap {f.cycles_lost} cyc, {f.where}.", f.why, f.fix]
        _kind, cycle, port, instr = target
        head = (f"Cursor at cycle {cycle}, port "
                f"{machine.port_label(port)} ('{VIEWS.get(self.view, self.view)}' view).")
        if instr is None:
            return [head, "Nothing issued in this slot."]
        ins = dag[instr]
        allowed = ", ".join(machine.port_label(c)
                            for c in machine.channels_for(ins.op))
        out = [head,
               f"Op {ins.op} '{ins.name}' (#{instr}).",
               f"{ins.op} runs on ports: {allowed}.",
               f"{ins.op} latency: {machine.latency(ins.op)} cyc."]
        if self.view == "model" and instr in self._model_illegal():
            out.append("ILLEGAL PLACEMENT: channel does not execute this op.")
        preds = list(dag[instr].preds)
        if preds:
            out.append("Depends on: "
                       + ", ".join(f"{dag[p].op} '{dag[p].name}'" for p in preds[:5]))
        return out

    def after_command(self) -> None:
        self._draw_journal()
        self.recompute()

    def redraw(self) -> None:
        if self.base is None:
            return
        self._mark_view()
        self._draw_grid()
        self._draw_numbers()
        self._draw_diag()
        self._draw_machine()
        self._draw_detail()
        self._draw_grid_link()

    def action_swap_focus(self) -> None:
        grid = self.query_one("#grid", ScheduleGrid)
        bar = self.query_one("#prompt", PromptBar)
        if grid.has_focus:
            bar.focus_input()
        else:
            if bar.palette_widget.display:
                bar.set_value("")
                return
            grid.focus()

    # --- scheduling worker ------------------------------------------------

    def recompute(self) -> None:
        """Recompute schedules for the current block on a background thread."""
        self.set_busy(True)
        self._blank_grid("computing schedule…")
        self.run_worker(self._compute, thread=True, exclusive=True, group="lab")

    def _compute(self) -> None:
        try:
            base, orc, met = self.app.session.results()
        except Exception as e:
            self.app.call_from_thread(self._compute_failed, str(e))
            return
        try:
            from ... import ai_hints
            hints = ai_hints.collect(self.app.session, base, orc)
        except Exception:
            hints = None
        self.app.call_from_thread(self._compute_done, base, orc, met, hints)

    def _compute_failed(self, msg: str) -> None:
        self.set_busy(False)
        self._blank_grid(f"failed: {msg}")

    def _compute_done(self, base, orc, met, hints=None) -> None:
        self.base, self.orc, self.met = base, orc, met
        self.hints = hints
        self.diverged = {
            i for i in base.schedule.placements
            if i in orc.schedule.placements
            and base.schedule.placements[i].cycle != orc.schedule.placements[i].cycle
        }
        self.set_busy(False)
        self._find_pos = -1
        self._mark_view()
        self._draw_grid()
        self._draw_numbers()
        self._draw_ai()
        self._draw_diag()
        self._draw_machine()
        self._draw_detail()
        self._draw_grid_link()
        self.refresh_context()

    # --- schedule grid ----------------------------------------------------

    @property
    def _result(self):
        if self.view == "model":
            return None
        return self.orc if self.view == "oracle" else self.base

    def _blank_grid(self, note: str) -> None:
        grid = self.query_one("#grid", ScheduleGrid)
        grid.clear(columns=True)
        grid.add_column(note, width=40)
        self.query_one("#p-grid", Panel).set_title("SCHEDULE")
        try:
            self.query_one("#grid-hud", Static).update(Text("", justify="right"))
        except Exception:
            pass
        self._draw_side()

    def _draw_grid(self) -> None:
        if self.view == "model":
            self._draw_model_grid()
            return
        res = self._result
        if res is None:
            return
        sched = res.schedule
        span = max(sched.span_cycles, 1)
        if span == sched.makespan:
            title = (f"SCHEDULE   {VIEWS[self.view]}   "
                     f"{sched.makespan} {_takt(sched.makespan)}")
        else:
            title = (f"SCHEDULE   {VIEWS[self.view]}   issue {span} cyc"
                     f"   ·   ready at c{sched.makespan}")
        if self.view == "oracle" and res.optimal:
            title += "   ·   optimum proven"
        self._render_grid(sched, title)

    def _model_illegal(self) -> frozenset[int]:
        """Return instruction IDs placed on channels that cannot execute them."""
        sched = self.model_sched
        if sched is None:
            return frozenset()
        dag = self.app.session.dag_obj
        machine = self.app.session.model()
        return frozenset(
            i for i, p in sched.placements.items()
            if p.channel not in machine.channels_for(dag[i].op))

    def _draw_model_grid(self) -> None:
        sched = self.model_sched
        if sched is None or not sched.placements:
            self._blank_grid(self.model_note
                             or "model has not run yet  —  /learned")
            return
        dag = self.app.session.dag_obj
        illegal = self._model_illegal()
        title = (f"SCHEDULE   model   "
                 f"placed {len(sched.placements)}/{len(dag)}")
        if illegal:
            title += f"   ·   illegal {len(illegal)}"
        if self.model_note:
            title += f"   ·   {self.model_note}"
        if len(sched.placements) == len(dag) and not illegal and not self.model_note:
            title += f"   ·   {sched.makespan} {_takt(sched.makespan)}"
        self._render_grid(sched, title, illegal)

    MIN_GAP = 3
    """Minimum consecutive empty cycles collapsed into one gap row (matches
    doctor's `_rule_idle_stretches` threshold)."""

    def _gaps(self, sched) -> list[tuple[int, int]]:
        """Return contiguous idle stretches `[(start, end), ...]` >= MIN_GAP."""
        used = {p.cycle for p in sched.placements.values()}
        out: list[tuple[int, int]] = []
        span = max(sched.span_cycles, 1)
        t = 0
        while t < span:
            if t in used:
                t += 1
                continue
            start = t
            while t < span and t not in used:
                t += 1
            if t - start >= self.MIN_GAP:
                out.append((start, t - 1))
        return out

    def _gap_finding(self, start: int, end: int):
        """Return the doctor idle-stall finding matching `[start, end]`."""
        for f in self._findings():
            if f.code == "idle-stall" and f.where in (
                    f"такты {start}–{end}", f"cycles {start}–{end}", f"cycles {start}-{end}"):
                return f
        return None

    def _findings(self):
        if self.base is None or self.met is None:
            return []
        try:
            from ...core.doctor import diagnose

            return diagnose(self.app.session.dag_obj, self.app.session.model(),
                            self.base.schedule, self.met).findings
        except Exception:
            return []

    SEVERITIES = ("all", "high", "medium", "low", "limit")

    def _filtered_findings(self):
        findings = self._findings()
        if self._diag_filter == "all":
            return findings
        if self._diag_filter == "limit":
            return [f for f in findings if f.kind == "limit"]
        return [f for f in findings
                if f.kind != "limit" and f.severity == self._diag_filter]

    def _cmd_find(self, arg: str) -> None:
        """`/find` — jump to next/prev finding, or `filter <severity>`."""
        parts = arg.split()
        con = self.console
        if parts and parts[0] == "filter":
            sev = parts[1] if len(parts) > 1 else "all"
            if sev not in self.SEVERITIES:
                if con is not None:
                    con.note(f"  filter: {', '.join(self.SEVERITIES)}", "warning")
                return
            self._diag_filter = sev
            self._find_pos = -1
            self._draw_diag()
            return
        findings = self._filtered_findings()
        if not findings:
            if con is not None:
                con.note("  no findings — /find filter all", "dim")
            return
        delta = -1 if parts and parts[0] == "prev" else 1
        self._find_pos = (self._find_pos + delta) % len(findings)
        self._jump_to_finding(findings[self._find_pos])

    def _jump_to_finding(self, f) -> None:
        """Move the grid cursor to the cell or gap referenced by finding `f`."""
        if f.code == "idle-stall":
            raw = f.where.replace("такты ", "").replace("cycles ", "")
            start = int(raw.replace("–", "-").split("-")[0])
            row, col = self._row_of_cycle(start), 0
        elif f.instrs:
            pos = next((rc for rc, i in self._cells.items() if i == f.instrs[0]),
                       None)
            if pos is None:
                return
            row, col = pos
        else:
            return
        width = max(self.app.session.model().width, 1)
        grid = self.query_one("#grid", ScheduleGrid)
        grid.move_cursor(row=min(row, max(len(self._rows) - 1, 0)),
                         column=min(col, width - 1))
        self._draw_detail()
        self._draw_diag()
        self._draw_grid_link()

    def _render_grid(self, sched, title: str,
                     illegal: frozenset[int] = frozenset()) -> None:
        model = self.app.session.model()
        dag = self.app.session.dag_obj
        grid = self.query_one("#grid", ScheduleGrid)
        grid.clear(columns=True)
        busy = sched.busy_map()
        used_ports = {p.channel for p in sched.placements.values()}
        cw = self._cell_w
        for p in range(model.width):
            idle = p not in used_ports
            role = "faint" if idle else "dim"
            label = Text(model.port_label(p), style=palette.role_hex(role))
            grid.add_column(label, width=4 if idle else cw, key=str(p))

        crit = self._critical_set() if self._crit_on else set()
        rels = self._cursor_relatives() if self._deps_on else None
        self._cells = {}
        self._rows = []
        span = max(sched.span_cycles, 1)
        if self._all_cycles:
            gaps = {}
        else:
            gaps = {a: b for a, b in self._gaps(sched)
                    if (a, b) not in self._expanded_gaps}

        cycle = 0
        while cycle < span:
            if cycle in gaps:
                end = gaps[cycle]
                grid.add_row(*self._gap_cells(cycle, end, model.width),
                             label=self._gap_label(cycle, end))
                self._rows.append(("gap", cycle, end))
                cycle = end + 1
                continue
            row = len(self._rows)
            cells = []
            issued = 0
            for port in range(model.width):
                slot = busy.get((cycle, port))
                if slot is None:
                    cells.append(Text(f" {EMPTY}", style=palette.role_hex("faint")))
                    continue
                instr, head = slot
                self._cells[(row, port)] = instr
                rel = None if rels is None else instr in rels
                if not head:
                    style = palette.op_style(dag[instr].op)
                    if rel is False:
                        style = palette.role_hex("faint")
                    cells.append(Text(f" {CONT}", style=style))
                    continue
                issued += 1
                cells.append(self._cell_text(dag, instr, crit,
                                             instr in illegal, related=rel))
            grid.add_row(*cells, label=self._row_label(cycle, issued, model.width))
            self._rows.append(("cycle", cycle))
            cycle += 1

        self.query_one("#p-grid", Panel).set_title(title)
        if self._rows:
            want = self._want_cell or (0, 0)
            grid.move_cursor(row=min(self._row_of_cycle(want[0]), len(self._rows) - 1),
                             column=min(want[1], model.width - 1))
        self._update_grid_hud()
        self._draw_side()

    def _update_grid_hud(self) -> None:
        """Live makespan, slot utilization, and cursor coordinate readout."""
        try:
            hud = self.query_one("#grid-hud", Static)
        except Exception:
            return
        dim = palette.role_hex("dim")
        faint = palette.role_hex("faint")
        warn = palette.role_hex("warning")
        t = Text()
        if self.view == "model" and self.model_sched is not None \
                and self.model_sched.placements:
            dag = self.app.session.dag_obj
            illegal = self._model_illegal()
            t.append(f"{len(self.model_sched.placements)}/{len(dag)} ops",
                     style=dim)
            if illegal:
                t.append(f"   illegal {len(illegal)}",
                         style=palette.role_hex("error"))
        elif self.base is not None:
            sched = (self.orc if self.view == "oracle" else self.base).schedule
            util = sched.slot_utilization
            t.append(f"{sched.makespan} {_takt(sched.makespan)}"
                     f"   ·   slots {util:.0%}", style=dim)
        target = self._cursor_target()
        if target is not None and target[0] == "cycle":
            cell = f"c{target[1]} ,{target[2]}"
            name = self.app.session.dag_obj[target[3]].name \
                if target[3] is not None else ""
            t.append(f"   ·   {cell}"
                     + (f"  {name}" if name else ""),
                     style=warn if name else faint)
        elif self.view == "model":
            t.append("   ·   model not run — /learned", style=faint)
        hud.update(t)

    # --- maximized grid right-side inspector ------------------------------

    def _draw_side(self) -> None:
        try:
            cursor = self.query_one("#side-cursor", Static)
            finding = self.query_one("#side-finding", Static)
            ports = self.query_one("#side-ports", Static)
            legend = self.query_one("#side-legend", Static)
        except Exception:
            return
        dim = palette.role_hex("dim")
        faint = palette.role_hex("faint")
        title = palette.role_hex("title")
        accent = palette.role_hex("accent")

        def mark(on: bool) -> Text:
            return Text("on" if on else "off",
                        style=palette.role_hex("success" if on else "faint"))

        # --- layers + cursor ---
        t = Text()
        t.append_text(self._section("cursor"))
        t.append("\n")
        t.append("z deps   ", style=dim); t.append_text(mark(self._deps_on))
        t.append("  ·  x cycles ", style=dim); t.append_text(mark(self._all_cycles))
        t.append("\n")
        t.append("p path   ", style=dim); t.append_text(mark(self._crit_on))
        t.append("  ·  w wide   ", style=dim); t.append_text(mark(self._wide_cells))
        t.append("\n\n")
        facts = self._cursor_facts()
        if not facts:
            t.append("grid is empty", style=faint)
        for i, line in enumerate(facts):
            if i:
                t.append("\n")
            t.append(_wrapped(line, 40, 2) if i == 0
                     else "  " + _wrapped(line, 38, 2), style=title if i == 0
                     else dim)
        cursor.update(t)

        # --- finding ---
        f = self._active_finding()
        tf = Text()
        tf.append_text(self._section("finding",
                                     "" if f is not None else "clean"))
        tf.append("\n\n")
        if f is None:
            tf.append("no doctor findings under cursor", style=faint)
        else:
            head = f"-{f.cycles_lost} cyc "
            tf.append(head, style=palette.role_hex(
                "dim" if f.kind == "limit" else "error"))
            tf.append(_wrapped(f.title, 36, len(head)),
                      style=f"{title} bold")
            tf.append("\n  " + _wrapped(f.where, 34, 2),
                      style=palette.role_hex("accent_soft"))
            tf.append("\n  " + _wrapped(f.why, 34, 2), style=dim)
            if getattr(f, "fix", ""):
                tf.append("\n  " + _wrapped(f.fix, 34, 2),
                          style=palette.role_hex("success"))
        finding.update(tf)

        # --- channel utilization ---
        tp = Text()
        tp.append_text(self._section("channels"))
        tp.append("\n\n")
        model = self.app.session.model()
        res = None if self.view == "model" else self._result
        if res is None:
            tp.append("model view — computed after run finishes", style=faint)
        else:
            busy = res.schedule.busy_map()
            span = max(res.schedule.makespan, 1)
            per: dict[int, int] = {}
            for (_c, port) in busy:
                per[port] = per.get(port, 0) + 1
            worst = max(per.values(), default=0)
            for port in model.ports:
                held = per.get(port.index, 0)
                bar_w = max(0, min(14, round(14 * held / span)))
                tp.append(port.label.ljust(4), style=dim)
                tp.append("─" * bar_w,
                          style=accent if held == worst and held
                          else palette.role_hex("success"))
                tp.append("·" * (14 - bar_w), style=faint)
                tp.append(f" {held:>3}", style=title if held else faint)
                if held == worst and held:
                    tp.append(" bottle", style=accent)
                tp.append("\n")
        ports.update(tp)

        # --- keys + legend ---
        tl = Text()
        tl.append_text(self._section("keys"))
        tl.append("\n\n")
        for key, what in (
                ("n / N", "next / prev finding"),
                ("[ / ]", "prev / next op"),
                ("c", "next critical-path op"),
                ("v", "view: baseline <> oracle"),
                ("z x p w", "layers — toggled above"),
                ("d", "diagnosis: full findings list"),
                ("o", "maximize session git"),
        ):
            tl.append("  ")
            tl.append(key.ljust(8), style=f"{accent} bold")
            tl.append(what, style=dim)
            tl.append("\n")
        tl.append("\n")
        tl.append_text(self._section("marks"))
        tl.append("\n\n")
        tl.append("  > differs from oracle\n", style=palette.role_hex("diverge"))
        tl.append("  bold name — critical path\n",
                  style=f"{title} bold")
        tl.append("  - channel cannot run op\n",
                  style=palette.role_hex("error"))
        tl.append("  ─── idle gap >= 3 cycles\n", style=faint)
        tl.append("  _▄█ cycle slot load", style=dim)
        legend.update(tl)

    def _row_of_cycle(self, cycle: int) -> int:
        """Return grid row index displaying `cycle` (or its collapsed gap)."""
        for i, r in enumerate(self._rows):
            if r[0] == "cycle" and r[1] == cycle:
                return i
            if r[0] == "gap" and r[1] <= cycle <= r[2]:
                return i
        return 0

    def _gap_cells(self, start: int, end: int, width: int) -> list[Text]:
        """Collapsed idle-gap row: solid rule instead of empty-slot dots."""
        style = palette.role_hex("faint")
        line = " " + "─" * (self._cell_w - 2)
        return [Text(line, style=style) for _ in range(width)]

    def _active_finding(self):
        """Return the doctor finding associated with the cell under cursor."""
        target = self._cursor_target()
        if target is None:
            return None
        if target[0] == "gap":
            return self._gap_finding(target[1], target[2])
        instr = target[3]
        if instr is None:
            return None
        for f in self._findings():
            if instr in f.instrs:
                return f
        return None

    def _gap_label(self, start: int, end: int) -> Text:
        f = self._gap_finding(start, end)
        role = "error" if (f is not None and f.recoverable) else "dim"
        t = Text()
        t.append(f"c{start}–{end}", style=palette.role_hex(role))
        t.append(f" v{end - start + 1}", style=palette.role_hex("faint"))
        return t

    def _cell_text(self, dag, instr: int, crit: set[int],
                   illegal: bool = False, related: bool | None = None) -> Text:
        """Format a single scheduled operation cell."""
        ins = dag[instr]
        t = Text()
        if illegal:
            t.append("-", style=palette.role_hex("error") + " bold")
        else:
            moved = instr in self.diverged
            mark_style = palette.role_hex("diverge") if moved \
                else palette.role_hex("faint") if related is False else ""
            t.append(">" if moved else " ", style=mark_style)
        op_style = palette.op_style(ins.op)
        if related is False:
            op_style = palette.role_hex("faint")
        t.append(ins.op.lower()[:3].ljust(4), style=op_style)
        name_w = 12 if self._wide_cells else 7
        if illegal:
            style = palette.role_hex("error") + " bold"
        elif instr in crit:
            style = palette.role_hex("crit") + " bold"
        elif related is False:
            style = palette.role_hex("faint")
        else:
            style = palette.role_hex("text")
        t.append(ins.name[:name_w], style=style)
        return t

    def _row_label(self, cycle: int, issued: int, width: int) -> Text:
        """Cycle label plus single-width slot occupancy glyph."""
        t = Text()
        if issued == 0:
            role, mark = "error", "_"
        elif issued == width:
            role, mark = "success", "█"
        else:
            role, mark = "dim", "▄"
        t.append(f"c{cycle:<3}", style=palette.role_hex(role))
        t.append(mark, style=palette.role_hex(role))
        return t

    def _critical_set(self) -> set[int]:
        if self.met is None:
            return set()
        from ...ui.schedule_view import critical_set

        return critical_set(self.app.session.dag_obj, self.met)

    # --- WHY HERE ---------------------------------------------------------

    def on_data_table_cell_highlighted(self, event) -> None:
        event.stop()
        target = self._cursor_target()
        instr = target[3] if target and target[0] == "cycle" else None
        if self._deps_on and instr != self._last_deps_instr:
            self._last_deps_instr = instr
            self._redraw_grid_keep_cursor()
            return
        self._draw_detail()
        self._draw_diag()
        self._draw_grid_link()
        self._update_grid_hud()
        self._draw_side()
        self._cell_ai_restart()

    # --- panel maximize/collapse ------------------------------------------

    def on_panel_expanded(self, event) -> None:
        event.stop()
        topic = getattr(event.panel, "topic", "")
        if topic == "diag":
            self._diag_expanded = True
            self._find_pos = -1
            self._draw_diag()
        elif topic == "grid":
            self._grid_expanded = True
            self._draw_side()
            self.refresh_hints()
            self._draw_grid_link()
        elif topic == "numbers":
            self._numbers_expanded = True
            self._draw_numbers()
        elif topic == "machine":
            self._machine_expanded = True
            self._draw_machine()
        elif topic == "detail":
            self._detail_expanded = True
            self._draw_detail()
        elif topic == "console":
            self._console_expanded = True
            self._draw_journal()
        elif topic == "scen":
            self._scen_expanded = True
            self._draw_scen_catalog()

    def on_panel_collapsed(self, event) -> None:
        event.stop()
        self._diag_expanded = False
        self._grid_expanded = False
        self._numbers_expanded = False
        self._machine_expanded = False
        self._detail_expanded = False
        self._console_expanded = False
        self._scen_expanded = False
        self._draw_journal()
        self._draw_scen_catalog()
        self._draw_diag()
        self._draw_grid_link()
        self._draw_numbers()
        self._draw_machine()
        self._draw_detail()

    SCEN_SORT_DEFAULT_REV = {"key": False, "family": False, "binding": False}

    def _scen_sort_value(self, key: str, sort_key: str, dag, met):
        if sort_key == "key":
            return key
        if sort_key == "family":
            return (dag.family or "other", key)
        if sort_key == "ops":
            return len(dag)
        if sort_key == "lb":
            return met.lower_bound if met else -1
        if sort_key == "binding":
            return (met.binding if met else "", key)
        return key

    def on_input_changed(self, event) -> None:
        if event.input.id == "machine-filter":
            event.stop()
            self._matrix_filter = event.value.strip().lower()
            self._draw_machine_matrix()
        elif event.input.id == "scen-filter":
            event.stop()
            self._scen_filter = event.value.strip().lower()
            self._draw_scen_catalog()

    def on_data_table_row_selected(self, event) -> None:
        if event.data_table.id not in ("machine-matrix", "scen-table"):
            return
        event.stop()
        if event.data_table.id == "machine-matrix":
            idx = event.cursor_row
            if not (0 <= idx < len(self._matrix_ops)):
                return
            op = self._matrix_ops[idx]
            dag = self.app.session.dag_obj
            first = next((i.id for i in dag if i.op == op), None)
            if first is None:
                return
            self._show_instr(first)
        elif event.data_table.id == "scen-table":
            idx = event.cursor_row
            if not (0 <= idx < len(self._scen_keys)):
                return
            key = self._scen_keys[idx]
            if key != self.app.session.scenario:
                self.run_core(f"/run {key}")

    def _draw_scen_catalog(self) -> None:
        """Maximized BLOCK panel: sortable, filterable scenario catalog."""
        wide = self._scen_expanded
        self.query_one("#scen-wide").display = wide
        panel = self.query_one("#p-scen", Panel)
        if not wide:
            panel.set_title("BLOCK")
            return
        from ...core.dag import compute_metrics

        head = self.query_one("#scen-head", Static)
        foot = self.query_one("#scen-foot", Static)
        table = self.query_one("#scen-table", DataTable)
        model = self.app.session.model()
        cur = self.app.session.scenario
        dim, faint = palette.role_hex("dim"), palette.role_hex("faint")
        title, accent = palette.role_hex("title"), palette.role_hex("accent")
        panel.set_title(f"BLOCK   ·   catalog   ·   {len(SCENARIOS)} blocks")

        h = Text()
        h.append_text(self._section("available blocks",
                                    "> current · click to switch"))
        head.update(h)

        def col(label: str, key: str) -> Text:
            t = Text(label, style=dim)
            if key == self._scen_sort_key:
                t.append(" v" if self._scen_sort_rev else " ^",
                        style=palette.role_hex("accent_soft"))
            return t

        table.clear(columns=True)
        table.add_column(col("block", "key"), width=14, key="key")
        table.add_column(col("ops", "ops"), width=5, key="ops")
        table.add_column(col("bound", "lb"), width=9, key="lb")
        table.add_column(col("bound by", "binding"), width=20, key="binding")
        table.add_column(col("family", "family"), width=16, key="family")
        width = max(24, self.app.size.width - 78)
        table.add_column(Text("what it tests", style=dim), width=width,
                         key="lesson")

        metrics: dict[str, tuple] = {}
        for key, dag in SCENARIOS.items():
            try:
                met = compute_metrics(dag, model)
            except Exception:
                met = None
            metrics[key] = (dag, met)

        pool = [k for k in SCENARIOS
                if not self._scen_filter or self._scen_filter in
                (k + " " + (SCENARIOS[k].family or "") + " "
                 + (SCENARIOS[k].lesson or SCENARIOS[k].note or "")).lower()]
        self._scen_keys = sorted(
            pool,
            key=lambda k: self._scen_sort_value(k, self._scen_sort_key,
                                                *metrics[k]),
            reverse=self._scen_sort_rev)

        if not self._scen_keys:
            foot.update(Text(f"    no matches for '{self._scen_filter}'",
                             style=faint))
            table.clear()
            return

        for key in self._scen_keys:
            dag, met = metrics[key]
            lb, binding = (met.lower_bound, met.binding) if met else (0, "—")
            here = key == cur
            row_style = (title + " bold") if here else palette.role_hex("text")
            row = [
                Text(("> " if here else "  ") + key, style=row_style),
                Text(str(len(dag)), style=dim),
                Text(f"{lb} cyc", style=title if here else dim),
                Text(binding, style=palette.role_hex("warning")
                     if binding in ("ресурсы", "resources") else faint),
                Text(dag.family or "other", style=faint),
                Text((dag.lesson or dag.note or dag.title)[:width],
                     style=faint),
            ]
            table.add_row(*row)

        f = Text()
        f.append_text(self._section("how to read"))
        f.append("\n\n")
        f.append("    'bound' is the fewest cycles any scheduler can achieve.\n"
                 "    'bound by' shows whether the limit is dependency depth\n"
                 "    (critical path) or port scarcity (resources). Wider\n"
                 "    hardware fixes resources; only code rewrites fix depth.",
                 style=faint)
        foot.update(f)

    def _draw_journal(self) -> None:
        """Maximized GIT panel: full session history and command catalog."""
        journal = self.query_one("#journal", ConsoleJournal)
        con = self.query_one("#console", Console)
        panel = self.query_one("#p-console", Panel)
        self.query_one("#prompt", PromptBar).display = not self._console_expanded
        journal.display = self._console_expanded
        con.display = not self._console_expanded
        if not self._console_expanded:
            panel.set_title("GIT")
            return
        n = len(con.runs)
        panel.set_title(f"GIT   ·   session history   ·   "
                        f"{n} {plural(n, 'run', 'runs', 'runs')}")
        journal.load(con.runs, self.mode, list(self.app.commands),
                     self.app.session.journal_events)

    def _jump_to_instr(self, instr: int) -> bool:
        """Move grid cursor to `instr`. Return False if not placed."""
        pos = next((rc for rc, i in self._cells.items() if i == instr), None)
        if pos is None:
            return False
        grid = self.query_one("#grid", ScheduleGrid)
        grid.move_cursor(row=pos[0], column=pos[1])
        self._draw_detail()
        self._draw_diag()
        self._draw_grid_link()
        return True

    def _show_instr(self, instr: int) -> None:
        if not self._jump_to_instr(instr):
            return
        self._open_panel("#p-grid", "grid")

    def on_instr_link_picked(self, event) -> None:
        event.stop()
        self._show_instr(event.instr)

    def _draw_grid_link(self) -> None:
        try:
            link = self.query_one("#grid-link", GridLink)
        except Exception:
            return
        link.set_class(self._grid_expanded, "on")
        if not self._grid_expanded:
            link.active = False
            link.update("")
            return
        f = self._active_finding()
        if f is None:
            link.active = False
            link.tooltip = "hint bar: cursor and /find work at any time"
            link.update(Text("cursor — move cells   ·   /find — step findings",
                             style=palette.role_hex("faint")))
            return
        link.active = True
        link.tooltip = (f"{f.title}\n{f.why}\nclick — full list in DIAGNOSIS")
        t = Text()
        t.append("> ", style=palette.role_hex("accent"))
        t.append(f.title, style=palette.role_hex("title") + " bold")
        t.append("   ·   click — all findings in DIAGNOSIS",
                 style=palette.role_hex("accent_soft"))
        link.update(t)

    def on_finding_item_picked(self, event) -> None:
        event.stop()
        findings = self._filtered_findings()
        if not (0 <= event.index < len(findings)):
            return
        self._find_pos = event.index
        self._jump_to_finding(findings[event.index])
        self._open_panel("#p-grid", "grid")

    def on_grid_link_picked(self, event) -> None:
        event.stop()
        f = self._active_finding()
        if f is None:
            return
        findings = self._filtered_findings()
        if f not in findings:
            self._diag_filter = "all"
            findings = self._filtered_findings()
        self._find_pos = findings.index(f) if f in findings else -1
        self._open_panel("#p-diag", "diag")
        self._draw_diag()

    # --- cursor-triggered AI summary --------------------------------------

    CELL_AI_DELAY = 1.5

    CELL_AI_QUESTION = "Rephrase this in one plain-language sentence."

    def _cell_ai_restart(self) -> None:
        self._cell_ai_token += 1
        self._cell_ai_text = ""
        self._cell_ai_state = ""
        self._render_detail()
        if not self._cell_ai_on or self.view == "model" and self.model_sched is None:
            return
        if not self._cell_has_a_story():
            return
        tok = self._cell_ai_token
        self.set_timer(self.CELL_AI_DELAY, lambda: self._cell_ai_start(tok))

    def _cell_has_a_story(self) -> bool:
        """Only invoke cursor AI on noteworthy cells (gaps, empty slots,
        illegal placements, oracle divergences, or critical-path ops)."""
        target = self._cursor_target()
        if target is None:
            return False
        if target[0] == "gap":
            return True
        instr = target[3]
        if instr is None:
            return True
        if self.view == "model":
            return instr in self._model_illegal()
        return instr in self.diverged or instr in self._critical_set()

    def _cell_ai_start(self, tok: int) -> None:
        if tok != self._cell_ai_token:
            return
        base = self._detail_base
        facts = [l for l in (base.plain.split("\n") if base else []) if l.strip()]
        if len(facts) < 2:
            return
        self._cell_ai_state = "waiting"
        self._cell_ai_facts = facts
        self._render_detail()
        self._cell_ai_worker(tok, facts)

    @work(thread=True, group="cellai")
    def _cell_ai_worker(self, tok: int, facts: list[str]) -> None:
        from ...agent import context, llm

        system = context.cell_prompt(facts)
        gen = llm.stream(system, self.CELL_AI_QUESTION, None, nudge=False)
        try:
            for piece in gen:
                if tok != self._cell_ai_token:
                    break
                self.app.call_from_thread(self._cell_ai_piece, tok, piece)
        except Exception as e:
            self.app.call_from_thread(self._cell_ai_failed, tok, str(e))
        finally:
            closer = getattr(gen, "close", None)
            if closer is not None:
                closer()
        self.app.call_from_thread(self._cell_ai_done, tok)

    def _cell_ai_piece(self, tok: int, piece: str) -> None:
        if tok != self._cell_ai_token:
            return
        self._cell_ai_state = "ready"
        self._cell_ai_text += piece
        self._render_detail()

    def _cell_ai_done(self, tok: int) -> None:
        if tok != self._cell_ai_token:
            return
        if self._cell_ai_state == "waiting":
            self._cell_ai_state = ""
            self._render_detail()
            return
        from ...agent import context

        if not context.cell_answer_is_grounded(self._cell_ai_text,
                                               self._cell_ai_facts):
            self._cell_ai_text = ""
            self._cell_ai_state = "NEX invented numbers — reply hidden"
            self._render_detail()

    def _cell_ai_failed(self, tok: int, msg: str) -> None:
        if tok != self._cell_ai_token:
            return
        self._cell_ai_state = "no model"
        self._render_detail()

    def on_data_table_cell_selected(self, event) -> None:
        event.stop()
        target = self._cursor_target()
        if target is not None and target[0] == "gap":
            key = (target[1], target[2])
            if key in self._expanded_gaps:
                self._expanded_gaps.discard(key)
            else:
                self._expanded_gaps.add(key)
            self._want_cell = (target[1], event.coordinate.column)
            self._draw_grid()
            self._draw_detail()
            return
        if target is not None:
            self.run_core(f"/explain {target[1]}")

    def _cursor_target(self):
        """Return `("cycle", cycle, port, instr)` or `("gap", start, end)`."""
        grid = self.query_one("#grid", ScheduleGrid)
        coord = grid.cursor_coordinate
        row, port = coord.row, coord.column
        if not (0 <= row < len(self._rows)):
            return None
        r = self._rows[row]
        if r[0] == "gap":
            return ("gap", r[1], r[2])
        return ("cycle", r[1], port, self._cells.get((row, port)))

    def _render_detail(self) -> None:
        """Render exact core analysis followed by optional AI paraphrase."""
        target = self.query("#detail").first(Static) if self.query("#detail") else None
        base = self._detail_base
        if target is None or base is None:
            return
        t = base.copy()
        faint = palette.role_hex("faint")
        if self._cell_ai_state == "waiting":
            t.append("\n\n" + "─" * 3 + " NEX analyzing…", style=faint)
        elif self._cell_ai_state == "ready":
            t.append("\n\n" + "─" * 3 + " NEX\n", style=faint)
            t.append(self._cell_ai_text.strip(), style=palette.role_hex("dim"))
        elif self._cell_ai_state:
            t.append("\n\n" + "─" * 3 + " " + self._cell_ai_state, style=faint)
        target.update(t)

    def _set_detail(self, text: Text) -> None:
        self._detail_base = text
        self._render_detail()

    # --- maximized WHY HERE: scheduling window and dependency cones -------

    def _draw_detail_graph(self) -> None:
        preds_box = self.query_one("#detail-preds", Vertical)
        succs_box = self.query_one("#detail-succs", Vertical)
        graph = self.query_one("#detail-graph", Horizontal)
        graph.display = self._detail_expanded
        if not self._detail_expanded:
            return
        preds_box.remove_children()
        succs_box.remove_children()
        dim = palette.role_hex("dim")
        faint = palette.role_hex("faint")
        title = palette.role_hex("title")
        target = self._cursor_target()
        instr = target[3] if (target and target[0] == "cycle") else None
        if instr is None:
            preds_box.mount(Static(Text("move cursor onto an operation",
                                        style=faint)))
            return
        dag = self.app.session.dag_obj
        placed = self.base.schedule.placements if self.base else {}
        model = self.app.session.model()

        def cone(seed: int, step) -> dict[int, int]:
            """Collect all reachable dependency nodes with shortest depth."""
            out: dict[int, int] = {}
            frontier = [(seed, 0)]
            while frontier:
                node, d = frontier.pop()
                for nxt in step(node):
                    if nxt in out and out[nxt] <= d + 1:
                        continue
                    out[nxt] = d + 1
                    frontier.append((nxt, d + 1))
            return out

        def column(box, head: str, cone_map: dict[int, int], direct: int,
                   phrase) -> None:
            h = Text()
            h.append(head + "   ", style=palette.role_hex("accent"))
            h.append(f"{direct} direct", style=title)
            if len(cone_map) > direct:
                h.append(f",  {len(cone_map)} total in chain", style=dim)
            h.append("\n", style=dim)
            box.mount(Static(h))
            if not cone_map:
                box.mount(Static(Text("   none — block boundary\n",
                                      style=faint)))
                return
            for i, depth in sorted(cone_map.items(),
                                   key=lambda kv: (kv[1], placed[kv[0]].cycle
                                                   if kv[0] in placed else 0)):
                ins = dag[i]
                row = Text()
                row.append("  " + "· " * (depth - 1), style=faint)
                row.append(ins.name[:5].ljust(6), style=title if depth == 1
                           else dim)
                row.append(ins.op.lower()[:3].ljust(4),
                           style=palette.op_style(ins.op))
                pl = placed.get(i)
                row.append((f"c{pl.cycle}" if pl else "—").rjust(5), style=dim)
                row.append("  " + phrase(i, depth), style=faint)
                link = InstrLink(i, row, classes="instr-link")
                pl = placed.get(i)
                link.tooltip = (f"grid cell: {ins.name} (c{pl.cycle})"
                                if pl else f"op {ins.name} — jump to grid")
                box.mount(link)

        up = cone(instr, lambda n: dag[n].preds)
        down = cone(instr, lambda n: dag.succs[n])
        own = placed.get(instr)
        own_ready = (own.cycle + model.latency(dag[instr].op)) if own else None

        def up_note(i: int, depth: int) -> str:
            pl = placed.get(i)
            if pl is None:
                return ""
            ready = pl.cycle + model.latency(dag[i].op)
            if depth > 1:
                return f"ready at c{ready}"
            return f"ready at c{ready} — earliest start"

        def down_note(i: int, depth: int) -> str:
            if depth > 1 or own_ready is None:
                return ""
            return f"cannot start before c{own_ready}"

        column(preds_box, "WAITED FOR", up, len(dag[instr].preds), up_note)
        column(succs_box, "BLOCKS", down, len(dag.succs[instr]), down_note)

    def _detail_window(self, instr: int) -> Text:
        """Render ASAP..ALAP scheduling window and slack for `instr`."""
        met, dag = self.met, self.app.session.dag_obj
        t = Text()
        if met is None or self.base is None:
            return t
        dim = palette.role_hex("dim")
        title = palette.role_hex("title")
        asap = met.asap[instr]
        alap = met.critical_path_bound - met.height[instr]
        pl = self.base.schedule.placements.get(instr)
        slack = alap - asap
        t.append("\n\n")
        t.append("window  ", style=dim)
        t.append(f"c{asap}", style=title)
        t.append(" … ", style=dim)
        t.append(f"c{alap}", style=title)
        t.append("      placed  ", style=dim)
        t.append(f"c{pl.cycle}" if pl else "—", style=title)
        t.append("      slack  ", style=dim)
        if slack <= 0:
            t.append("0 — on critical path",
                     style=palette.role_hex("error"))
        else:
            t.append(f"{slack} cyc", style=palette.role_hex("success"))
        return t

    def _draw_detail(self) -> None:
        panel = self.query_one("#p-detail", Panel)
        if self._detail_expanded:
            target = self._cursor_target()
            instr = target[3] if (target and target[0] == "cycle") else None
            dag = self.app.session.dag_obj
            name = dag[instr].name if instr is not None else "—"
            panel.set_title(f"WHY HERE   ·   {name}   ·   graph walk")
        else:
            panel.set_title("WHY HERE")
        self._draw_detail_graph()
        if self.view == "model":
            self._set_detail(self._detail_model())
            return
        res = self._result
        if res is None:
            self._set_detail(Text("schedule not computed yet",
                                  style=palette.role_hex("faint")))
            return
        target = self._cursor_target()
        if target is None:
            return
        if target[0] == "gap":
            self._set_detail(self._detail_gap(target[1], target[2]))
            return
        _kind, cycle, port, instr = target
        if instr is None:
            self._set_detail(self._detail_empty(cycle, port))
        else:
            t = self._detail_instr(cycle, port, instr)
            if self._detail_expanded:
                t = t.copy()
                t.append_text(self._detail_window(instr))
            self._set_detail(t)

    def _detail_model(self) -> Text:
        """Explain legality of a model-placed cell under the cursor."""
        faint = palette.role_hex("faint")
        sched = self.model_sched
        if sched is None or not sched.placements:
            return Text("model has not run yet  —  /learned", style=faint)

        grid = self.query_one("#grid", ScheduleGrid)
        coord = grid.cursor_coordinate
        cycle, port = coord.row, coord.column
        instr = self._cells.get((cycle, port))
        machine, dag = self.app.session.model(), self.app.session.dag_obj

        t = Text()
        if instr is None:
            t.append("cycle ", style=faint)
            t.append(f"{cycle}", style=palette.role_hex("title"))
            t.append(f", port {machine.port_label(port)} — ", style=faint)
            t.append("model placed nothing here", style=faint)
            return t

        ins = dag[instr]
        allowed = machine.channels_for(ins.op)
        ok = port in allowed
        t.append(f"{ins.op.lower()} {ins.name}", style=palette.op_style(ins.op))
        t.append(f"  #{instr}\n", style=faint)
        t.append("model placed: ", style=faint)
        t.append(f"cycle {cycle}, port {machine.port_label(port)}\n",
                 style=palette.role_hex("title"))

        if ok:
            t.append("channel supports op — legal placement",
                     style=palette.role_hex("success"))
            return t

        labels = ", ".join(machine.port_label(c) for c in allowed) or "none"
        t.append("- this channel does NOT execute this op\n",
                 style=palette.role_hex("error") + " bold")
        t.append(f"{ins.op} runs only on: ", style=faint)
        t.append(f"{labels}\n", style=palette.role_hex("success"))
        t.append(f"port matrix source: {machine.matrix_source}\n",
                 style=faint)
        if self.model_repairs:
            t.append("repair channels without changing cycles:  /repair",
                     style=palette.role_hex("warning"))
        return t

    def _detail_gap(self, start: int, end: int) -> Text:
        """Explain a collapsed idle gap using doctor's finding."""
        dim, title = palette.role_hex("dim"), palette.role_hex("title")
        t = Text()
        t.append(f"idle gap {end - start + 1} cyc", style=f"{title} bold")
        t.append(f"   cycles {start}–{end}\n", style=dim)
        f = self._gap_finding(start, end)
        if f is None:
            t.append("short gap — below doctor finding threshold",
                     style=palette.role_hex("faint"))
            return t
        if f.recoverable:
            t.append(f"-{f.cycles_lost} cyc recoverable\n",
                     style=palette.role_hex("error") + " bold")
        else:
            t.append("block bound, not a scheduling miss\n",
                     style=palette.role_hex("success"))
        t.append(_wrapped(f.why, 70, 0) + "\n", style=dim)
        t.append(_wrapped(f.fix, 70, 0) + "\n", style=palette.role_hex("faint"))
        t.append("\nEnter — expand cycles individually",
                 style=palette.role_hex("faint"))
        return t

    def _detail_empty(self, cycle: int, port: int) -> Text:
        """Explain why an empty slot was left unused."""
        s = self.app.session
        model, dag = s.model(), s.dag_obj
        sched = self._result.schedule
        dim = palette.role_hex("dim")
        t = Text()
        t.append(f"cycle {cycle}", style=f"{palette.role_hex('lab')} bold")
        t.append(f"   channel {model.port_label(port)}", style=dim)
        t.append("   slot empty\n", style=palette.role_hex("faint"))

        ops = [op for op in sorted({i.op for i in dag})
               if port in model.channels_for(op)]
        t.append("channel accepts: ", style=dim)
        if ops:
            for i, op in enumerate(ops):
                if i:
                    t.append("  ", style=dim)
                t.append(op, style=palette.op_style(op))
        else:
            t.append("nothing in this block", style=palette.role_hex("warning"))
        t.append("\n\n")

        pending = [i for i in range(len(dag))
                   if i in sched.placements and sched.cycle_of(i) > cycle]
        if not pending:
            t.append("all ops already issued — draining in-flight latencies",
                     style=dim)
            return t
        ready_at = {i: max((sched.ready_at(p) for p in dag[i].preds), default=0)
                    for i in pending}
        able = [i for i in pending if ready_at[i] <= cycle
                and port in model.channels_for(dag[i].op)]
        if able:
            i = min(able, key=lambda k: sched.cycle_of(k))
            t.append("operands ready for ", style=dim)
            t.append(dag[i].name, style=palette.op_style(dag[i].op))
            t.append(", but scheduler issued it at c", style=dim)
            t.append(str(sched.cycle_of(i)), style=palette.role_hex("warning"))
            t.append("\nlost cycle — compare with oracle",
                     style=palette.role_hex("warning"))
            return t
        soonest = min(pending, key=lambda k: ready_at[k])
        t.append("waiting for operands: next ", style=dim)
        t.append(dag[soonest].name, style=palette.op_style(dag[soonest].op))
        t.append(" ready at c", style=dim)
        t.append(str(ready_at[soonest]), style=palette.role_hex("title"))
        blockers = sorted(
            {p for p in dag[soonest].preds if sched.ready_at(p) == ready_at[soonest]})
        if blockers:
            t.append("\nblocked by: ", style=dim)
            for k, p in enumerate(blockers):
                if k:
                    t.append(", ", style=dim)
                t.append(dag[p].name, style=palette.op_style(dag[p].op))
                t.append(f" ({dag[p].op}, lat {model.latency(dag[p].op)},"
                         f" issued c{sched.cycle_of(p)})", style=dim)
        return t

    def _detail_instr(self, cycle: int, port: int, instr: int) -> Text:
        s = self.app.session
        model, dag = s.model(), s.dag_obj
        sched = self._result.schedule
        ins = dag[instr]
        dim = palette.role_hex("dim")
        title = palette.role_hex("title")
        t = Text()

        t.append(ins.name, style=f"{title} bold")
        t.append("   ")
        t.append(ins.op, style=palette.op_style(ins.op))
        t.append(f"   {ins.text}", style=dim)
        t.append(f"     channel {model.port_label(port)}\n", style=dim)

        lat = model.latency(ins.op)
        occ = model.occupancy(ins.op)
        place = sched.placements[instr]
        t.append("issued at c", style=dim)
        t.append(str(place.cycle), style=title)
        t.append(", ready at c", style=dim)
        t.append(str(place.cycle + lat), style=title)
        t.append(f"   latency {lat}", style=dim)
        if occ > 1:
            t.append(f", holds channel {occ} cyc", style=palette.role_hex("warning"))
        t.append("\n")

        if ins.preds:
            t.append("waited for: ", style=dim)
            for k, p in enumerate(ins.preds):
                if k:
                    t.append(", ", style=dim)
                t.append(dag[p].name, style=palette.op_style(dag[p].op))
                t.append(f" ready c{sched.ready_at(p)}", style=dim)
            t.append("\n")
        else:
            t.append("no operand dependencies — eligible from c0\n", style=dim)

        if self.met is not None:
            t.append("earliest c", style=dim)
            t.append(str(self.met.asap[instr]), style=title)
            t.append("; remaining height ", style=dim)
            t.append(str(self.met.height[instr]), style=title)
            t.append(" cyc", style=dim)
            if self.met.asap[instr] + self.met.height[instr] == self.met.critical_path_bound:
                t.append("   on critical path", style=palette.role_hex("crit"))
            t.append("\n")

        other = self.orc if self.view == "baseline" else self.base
        who = "oracle" if self.view == "baseline" else "baseline"
        if other is not None and instr in other.schedule.placements:
            oc = other.schedule.placements[instr].cycle
            if oc != place.cycle:
                t.append(f"{who} places it at c", style=palette.role_hex("diverge"))
                t.append(str(oc), style=f"{palette.role_hex('diverge')} bold")
                t.append(f"  ({oc - place.cycle:+d})", style=dim)
            else:
                t.append(f"{who} places it identically", style=palette.role_hex("success"))
        return t

    # --- maximized NUMBERS: lower-bound derivation ------------------------

    def _critical_chain(self) -> list[int]:
        """Reconstruct one critical-path chain from ASAP/height metrics."""
        met = self.met
        if met is None:
            return []
        dag = self.app.session.dag_obj
        model = self.app.session.model()
        cp = met.critical_path_bound
        on = [i for i in range(len(dag)) if met.asap[i] + met.height[i] == cp]
        if not on:
            return []
        cur = min(on, key=lambda i: met.asap[i])
        chain = [cur]
        seen = {cur}
        while True:
            lat = model.latency(dag[cur].op)
            nxt = [x for x in dag.succs[cur]
                   if x not in seen
                   and met.asap[x] == met.asap[cur] + lat
                   and met.asap[x] + met.height[x] == cp]
            if not nxt:
                break
            cur = nxt[0]
            seen.add(cur)
            chain.append(cur)
        return chain

    def _resource_groups(self):
        """Break down the resource bound into `(ports, ops, slots, cycles)`."""
        dag = self.app.session.dag_obj
        model = self.app.session.model()
        groups: dict[tuple[int, ...], int] = {}
        names: dict[tuple[int, ...], set[str]] = {}
        for ins in dag:
            chans = model.channels_for(ins.op)
            groups[chans] = groups.get(chans, 0) + model.occupancy(ins.op)
            names.setdefault(chans, set()).add(ins.op)
        out = []
        for chans in groups:
            if not chans:
                continue
            total = sum(v for other, v in groups.items()
                        if set(other) <= set(chans))
            ops = sorted({o for other, ns in names.items()
                          if set(other) <= set(chans) for o in ns})
            out.append((chans, ops, total, -(-total // len(chans))))
        out.sort(key=lambda r: (-r[3], len(r[0])))
        return out

    SCALE_LEFT = 22
    """Left label width for timeline charts: name, op, issue cycle."""

    def _section(self, label: str, note: str = "") -> Text:
        """Section rule: lowercase label with horizontal line to the edge."""
        width = max(40, self.app.size.width - 8)
        t = Text()
        t.append("  " + label + "  ", style=palette.role_hex("title") + " bold")
        used = len(label) + 4
        if note:
            t.append(note + "  ", style=palette.role_hex("faint"))
            used += len(note) + 2
        t.append("─" * max(0, width - used), style=palette.role_hex("line"))
        return t

    def _scale(self) -> tuple[int, int]:
        """Return `(chars_per_cycle, left_margin)` scaled to screen width."""
        w = max(60, self.app.size.width - 6)
        span = max(self.base.schedule.makespan, 1) if self.base else 1
        room = max(20, w - self.SCALE_LEFT - 18)
        return max(1, room // span), self.SCALE_LEFT

    def _ruler(self, cpc: int) -> Text:
        """Cycle ruler above the critical-path Gantt chart."""
        span = max(self.base.schedule.makespan, 1) if self.base else 1
        step = 5 if cpc * 5 >= 6 else 10
        line = ""
        for c in range(0, span + 1, step):
            mark = f"c{c}" if c == 0 else str(c)
            pad = c * cpc - len(line)
            if pad < 0:
                continue
            line += " " * pad + mark
        return Text("    cycle".ljust(self.SCALE_LEFT) + line,
                    style=palette.role_hex("faint"))

    def _draw_numbers_why(self) -> None:
        head = self.query_one("#numbers-head", Static)
        chain_box = self.query_one("#numbers-chain", Vertical)
        res = self.query_one("#numbers-res", Static)
        chain_box.remove_children()
        if self.base is None or self.met is None:
            head.update(Text("schedule not computed yet",
                             style=palette.role_hex("faint")))
            res.update("")
            return
        dag = self.app.session.dag_obj
        model = self.app.session.model()
        met = self.met
        dim = palette.role_hex("dim")
        faint = palette.role_hex("faint")
        title = palette.role_hex("title")
        b = self.base.schedule.makespan
        o = self.orc.schedule.makespan
        lb = met.lower_bound
        cp, rb = met.critical_path_bound, met.resource_bound
        cpc, left = self._scale()

        t = Text()
        t.append_text(self._section("results"))
        t.append("\n\n")
        top_w = max(b, o, lb) * cpc
        for name, val, style in (
                ("baseline", b, title),
                ("oracle", o, palette.role_hex("success")),
                ("bound", lb, dim),
        ):
            t.append(("    " + name).ljust(left), style=dim)
            body = min(val, lb) * cpc
            tail = max(0, val - lb) * cpc
            t.append("─" * body, style=style)
            if tail:
                t.append("─" * tail, style=palette.role_hex("error"))
            t.append(" " * (top_w - body - tail), style=faint)
            t.append(f"{val:>4}", style=style)
            if tail:
                t.append(f"   +{val - lb} cyc over bound",
                         style=palette.role_hex("error"))
            elif name == "bound":
                t.append(f"   {met.binding}", style=faint)
            t.append("\n")
        head.update(t)

        chain = self._critical_chain()
        placed = self.base.schedule.placements
        note = f"{cp} cyc"
        if cp >= rb:
            note += "  ·  sets the bound"
        hdr = Text("\n")
        hdr.append_text(self._section("critical path", note))
        chain_box.mount(Static(hdr))
        chain_box.mount(Static(self._ruler(cpc)))
        if not chain:
            chain_box.mount(Static(Text("  chain could not be reconstructed",
                                        style=faint)))
        else:
            for i in chain:
                ins = dag[i]
                lat = model.latency(ins.op)
                pl = placed.get(i)
                row = Text()
                row.append("    ")
                row.append(ins.name[:5].ljust(4), style=title)
                row.append(ins.op.lower()[:3].ljust(4),
                           style=palette.op_style(ins.op))
                row.append((f"c{pl.cycle}" if pl else "—").rjust(6) + "    ",
                           style=dim)
                row.append(" " * (met.asap[i] * cpc))
                row.append("─" * max(1, lat * cpc),
                           style=palette.op_style(ins.op))
                row.append(f" {lat}", style=faint)
                link = InstrLink(i, row, classes="instr-link")
                link.tooltip = f"{ins.name}: latency {lat} cyc — jump to grid"
                chain_box.mount(link)

        note = f"{rb} cyc"
        if rb > cp:
            note += "  ·  sets the bound"
        r = Text("\n")
        r.append_text(self._section("resources", note))
        r.append("\n\n")
        for chans, ops, slots, need in self._resource_groups():
            label = " ".join(model.port_label(c) for c in chans)
            r.append("    " + label.ljust(22)[:22], style=dim)
            r.append(f"{slots:>3}", style=title)
            r.append(" slots / ", style=faint)
            r.append(f"{len(chans)}", style=title)
            r.append(" ports = ", style=faint)
            r.append(f"{need:>2} cyc", style=title)
            r.append("   " + "/".join(o.lower() for o in ops)[:26],
                     style=palette.op_style(ops[0]) if ops else dim)
            r.append("\n")
        r.append("\n    click any path row to jump to that op in the grid",
                 style=faint)
        res.update(r)

    def _draw_ai(self) -> None:
        """NEURAL NETS: TINY Flash schedule results (computed automatically)."""
        body = self.query_one("#ai-body", Static)
        h = getattr(self, "hints", None)
        dim = palette.role_hex("dim")
        faint = palette.role_hex("faint")
        title = palette.role_hex("title")
        accent = palette.role_hex("accent")
        t = Text()
        if h is None or h.tiny is None:
            t.append("TINY unavailable (missing weights?) — tool works fine without it",
                     style=faint)
            body.update(t)
            return
        tn = h.tiny
        t.append("TINY Flash", style=accent)
        t.append("  schedules", style=dim)
        if tn.через_ядро:
            t.append("  · scheduler block, NEX core", style=faint)
        t.append("\n")
        gain = tn.baseline - tn.tiny
        t.append(f"  baseline {tn.baseline} → TINY {tn.tiny} cyc", style=title)
        if gain > 0:
            t.append(f"  (-{gain})", style=palette.role_hex("success"))
        elif gain == 0:
            t.append("  (tied)", style=dim)
        t.append(f"\n  {tn.winner} · {tn.ms:.0f} ms", style=faint)
        if tn.oracle is not None:
            t.append(f" · oracle {tn.oracle}", style=faint)
        t.append("\n")
        if h.blocks:
            t.append("\nFILE BLOCKS", style=accent)
            t.append(f"  {len(h.blocks)} of {h.blocks_total}\n", style=dim)
            for r in h.blocks:
                t.append(f"  #{r.index:<3} n={r.n:<4} ", style=dim)
                t.append(f"{r.baseline}→{r.tiny}", style=title)
                if r.baseline > r.tiny:
                    t.append(f" -{r.baseline - r.tiny}", style=palette.role_hex("success"))
                t.append("\n")
        body.update(t)

    def _draw_numbers(self) -> None:
        why = self.query_one("#numbers-why", VerticalScroll)
        short = self.query_one("#numbers", Static)
        why.display = self._numbers_expanded
        short.display = not self._numbers_expanded
        panel = self.query_one("#p-numbers", Panel)
        if self._numbers_expanded:
            panel.set_title("NUMBERS   ·   bound breakdown")
            self._draw_numbers_why()
            return
        panel.set_title("NUMBERS")
        target = self.query_one("#numbers", Static)
        if self.base is None:
            return
        b = self.base.schedule.makespan
        o = self.orc.schedule.makespan
        lb = self.met.lower_bound
        dim = palette.role_hex("dim")
        title = palette.role_hex("title")
        t = Text()

        def row(key: str, value: str, style: str, note: str = "") -> None:
            t.append(key.ljust(11), style=dim)
            t.append(value.rjust(5), style=style)
            if note:
                t.append("  " + note, style=dim)
            t.append("\n")

        row("baseline", str(b), title)
        row("oracle", str(o), f"{palette.role_hex('success')} bold")
        self._row_model(row, b, o)
        row("bound", str(lb), title, self.met.binding)
        gap = b - o
        row("gain", f"-{gap}" if gap else "none",
            palette.role_hex("success") if gap else dim,
            f"{100 * gap // b}%" if gap and b else "")
        t.append("\n")
        t.append("optimum proven" if self.orc.optimal else "optimum not proven",
                 style=palette.role_hex("success") if self.orc.optimal
                 else palette.role_hex("warning"))
        t.append("\n")
        util = self.base.schedule.slot_utilization
        t.append(f"baseline slots used {util:.0%}", style=dim)
        target.update(t)

    def _row_model(self, row, base_t: int, orc_t: int) -> None:
        """Render the trained model's makespan alongside baseline and oracle."""
        sched = self.model_sched
        if sched is None or not sched.placements:
            return
        dim = palette.role_hex("dim")
        total = len(self.app.session.dag_obj)
        illegal = self._model_illegal()
        if len(sched.placements) < total:
            row("model", f"{len(sched.placements)}/{total}", dim, "generating…")
            return
        if illegal:
            row("model", "—", palette.role_hex("error"),
                f"illegal: {len(illegal)} ch")
            return
        m = sched.makespan
        if m < orc_t:
            note = "below oracle — verify"
            style = palette.role_hex("warning")
        elif m == orc_t:
            note = "optimal"
            style = f"{palette.role_hex('success')} bold"
        elif m < base_t:
            note = "beats baseline"
            style = palette.role_hex("success")
        elif m == base_t:
            note = "ties baseline"
            style = palette.role_hex("title")
        else:
            note = "worse than baseline"
            style = palette.role_hex("warning")
        row("model", str(m), style, note)

    _SEV_MARKS = {"high": ("!!", "error"), "medium": ("!", "warning"),
                  "low": ("·", "dim")}

    def _finding_mark(self, f) -> tuple[str, str]:
        return ("=", "dim") if f.kind == "limit" \
            else self._SEV_MARKS.get(f.severity, ("·", "dim"))

    def _draw_diag(self) -> None:
        scroll = self.query_one("#diag-scroll", VerticalScroll)
        if self.base is None:
            return
        if self._diag_expanded:
            self._draw_diag_full(scroll)
            return
        self.query_one("#diag-filter", Horizontal).remove_children()
        scroll.remove_children()
        from ...core.doctor import diagnose

        s = self.app.session
        try:
            diag = diagnose(s.dag_obj, s.model(), self.base.schedule, self.met)
        except Exception as e:
            scroll.mount(Static(Text(str(e), style=palette.role_hex("error"))))
            return
        t = Text()
        if diag.clean:
            t.append("no findings — baseline hits the bound",
                     style=palette.role_hex("success"))
            scroll.mount(Static(t))
            return
        worst = diag.top[0]
        n = len(diag.top)
        t.append(f"{n} ", style=palette.role_hex("title") + " bold")
        t.append(plural(n, "finding", "findings", "findings") + "  ·  worst ",
                 style=palette.role_hex("dim"))
        t.append(f"-{worst.cycles_lost} cyc", style=palette.role_hex("error"))
        t.append(" ")
        width = max(20, self.query_one("#p-diag", Panel).size.width - 4)
        t.append(_wrapped(worst.title, width - 24, 0)[:width],
                 style=palette.role_hex("text"))
        t.append("\n")
        t.append("d or 2xclick — all findings & jump",
                 style=palette.role_hex("accent_soft"))
        scroll.mount(Static(t))

    def _fill_diag_filter(self, row: Horizontal) -> None:
        row.remove_children()
        counts = {"all": 0, "high": 0, "medium": 0, "low": 0, "limit": 0}
        for f in self._findings():
            counts["all"] += 1
            counts["limit" if f.kind == "limit" else f.severity] += 1
        labels = {"all": "all", "high": "high", "medium": "medium",
                  "low": "low", "limit": "bound"}
        for key in self.SEVERITIES:
            n = counts.get(key, 0)
            chip = Chip(f"{labels[key]} {n}", f"/find filter {key}",
                        classes="chip diag-sev")
            chip.set_class(key == self._diag_filter, "chip-on")
            row.mount(chip)

    def _draw_diag_full(self, scroll: VerticalScroll) -> None:
        """Maximized DIAGNOSIS: full filterable list of clickable findings."""
        self._fill_diag_filter(self.query_one("#diag-filter", Horizontal))
        scroll.remove_children()
        findings = self._filtered_findings()
        if not findings:
            scroll.mount(Static(Text("no findings match this filter",
                                     style=palette.role_hex("faint"))))
            return
        active = self._active_finding()
        dim = palette.role_hex("dim")
        panel = self.query_one("#p-diag", Panel)
        if self.maximized is panel:
            width = max(30, min(self.app.size.width - 8, 120))
        else:
            width = max(30, min(panel.size.width - 6, 120))
        for i, f in enumerate(findings):
            here = active is not None and f == active
            mark, role = self._finding_mark(f)
            t = Text()
            head = f"{'>' if here else mark:<3}-{f.cycles_lost} cyc "
            t.append(head, style=palette.role_hex("accent" if here else role))
            t.append(_wrapped(f.title, width, len(head)),
                     style=(palette.role_hex("title") + " bold") if here
                     else palette.role_hex("text"))
            t.append("\n     " + _wrapped(f.where, width, 5),
                     style=palette.role_hex("accent_soft") if here else dim)
            t.append("\n     " + _wrapped(f.why, width, 5), style=dim)
            row = FindingItem(i, t, classes="finding-row" + (" here" if here else ""))
            row.tooltip = (f"{f.title}\n{f.where}\n{f.why}\n"
                           "click — jump grid cursor to this cell")
            scroll.mount(row)

    # --- maximized MACHINE: port capability matrix ------------------------

    MATRIX_SORT_DEFAULT_REV = {"op": False}

    def _matrix_sort_value(self, name: str, key: str, model, counts):
        op = model.ops[name]
        if key == "op":
            return name
        if key == "lat":
            return op.latency
        if key == "cnt":
            return counts.get(name, 0)
        if key == "occ":
            return op.occupancy if op.blocks_channel() else 0
        if key.startswith("p"):
            idx = int(key[1:])
            return 1 if any(p.index == idx and name in p.ops
                            for p in model.ports) else 0
        return 0

    def on_data_table_header_selected(self, event) -> None:
        table_id = event.data_table.id
        if table_id not in ("machine-matrix", "scen-table"):
            return
        event.stop()
        key = event.column_key.value
        if table_id == "machine-matrix":
            if key == self._matrix_sort_key:
                self._matrix_sort_rev = not self._matrix_sort_rev
            else:
                self._matrix_sort_key = key
                self._matrix_sort_rev = self.MATRIX_SORT_DEFAULT_REV.get(key, True)
            self._draw_machine_matrix()
        else:
            if key == self._scen_sort_key:
                self._scen_sort_rev = not self._scen_sort_rev
            else:
                self._scen_sort_key = key
                self._scen_sort_rev = self.SCEN_SORT_DEFAULT_REV.get(key, True)
            self._draw_scen_catalog()

    def _draw_machine_matrix(self) -> None:
        table = self.query_one("#machine-matrix", DataTable)
        foot = self.query_one("#machine-foot", Static)
        model = self.app.session.model()
        dag = self.app.session.dag_obj
        counts = dag.op_counts() if dag is not None else {}
        sole = model.sole_host_ops()
        mono = {op for ops in sole.values() for op in ops}
        dim = palette.role_hex("dim")
        faint = palette.role_hex("faint")
        title = palette.role_hex("title")
        accent = palette.role_hex("accent")

        def head(label: str, key: str) -> Text:
            t = Text(label, style=dim)
            if key == self._matrix_sort_key:
                t.append(" v" if self._matrix_sort_rev else " ^",
                        style=palette.role_hex("accent_soft"))
            return t

        table.clear(columns=True)
        table.add_column(head("op", "op"), width=10, key="op")
        for port in model.ports:
            table.add_column(head(port.label, f"p{port.index}"), width=4,
                             key=f"p{port.index}")
        table.add_column(head("lat", "lat"), width=7, key="lat")
        table.add_column(head("holds port", "occ"), width=13, key="occ")
        table.add_column(head("in block", "cnt"), width=11, key="cnt")

        pool = [n for n in model.ops
                if not self._matrix_filter or self._matrix_filter in n.lower()]
        self._matrix_ops = sorted(
            pool,
            key=lambda n: self._matrix_sort_value(n, self._matrix_sort_key,
                                                  model, counts),
            reverse=self._matrix_sort_rev)
        if not self._matrix_ops:
            foot.update(Text(f"    no matches for '{self._matrix_filter}'",
                             style=faint))
            return
        for name in self._matrix_ops:
            op = model.ops[name]
            n = counts.get(name, 0)
            row = [Text(name.lower(), style=palette.op_style(name)
                        if n else faint)]
            for port in model.ports:
                if name not in port.ops:
                    row.append(Text("  ·", style=faint))
                elif name in mono:
                    row.append(Text("  *", style=accent))
                else:
                    row.append(Text("  *", style=palette.op_style(name)))
            row.append(Text(f"{op.latency} cyc".rjust(6),
                            style=title if n else faint))
            row.append(Text((f"{op.occupancy} cyc" if op.blocks_channel()
                             else "—").rjust(11),
                            style=palette.role_hex("warning")
                            if op.blocks_channel() else faint))
            row.append(Text((str(n) if n else "—").rjust(9),
                            style=title if n else faint))
            table.add_row(*row)

        t = Text()
        if self.base is not None:
            busy = self.base.schedule.busy_map()
            span = max(self.base.schedule.makespan, 1)
            per: dict[int, int] = {}
            for (_c, port) in busy:
                per[port] = per.get(port, 0) + 1
            worst = max(per.values(), default=0)
            t.append("\n")
            t.append_text(self._section("port utilization",
                                        f"block runs in {span} cyc"))
            t.append("\n\n")
            for port in model.ports:
                held = per.get(port.index, 0)
                t.append("    " + port.label.ljust(5), style=dim)
                bar_w = max(0, min(44, round(44 * held / span)))
                t.append("─" * bar_w, style=accent if held == worst and held
                         else palette.role_hex("success"))
                t.append("·" * (44 - bar_w), style=faint)
                t.append(f"  {held:>3} cyc", style=title if held else faint)
                t.append(f"{held * 100 // span:>5}%", style=dim if held
                         else faint)
                if held == worst and held:
                    t.append("   bottleneck", style=accent)
                elif not held:
                    t.append("   unused", style=faint)
                t.append("\n")
            t.append("\n")
        t.append("    * ", style=accent)
        t.append("sole executor", style=dim)
        t.append("      * supported      · no\n", style=faint)
        srcs = {model.matrix_source}
        srcs |= {o.latency_source for o in model.ops.values()}
        t.append("    source: " + ", ".join(sorted(srcs)) + "\n", style=faint)
        t.append("    click any table row to jump to that op in the grid",
                 style=faint)
        foot.update(t)

    def _draw_machine(self) -> None:
        matrix = self.query_one("#machine-matrix", DataTable)
        foot = self.query_one("#machine-foot", Static)
        short = self.query_one("#machine", Static)
        filt = self.query_one("#machine-filter-row")
        panel = self.query_one("#p-machine", Panel)
        matrix.display = self._machine_expanded
        foot.display = self._machine_expanded
        filt.display = self._machine_expanded
        short.display = not self._machine_expanded
        if self._machine_expanded:
            model = self.app.session.model()
            panel.set_title(f"MACHINE   ·   {model.name}   ·   "
                            f"{model.width} ports   ·   capability matrix")
            self._draw_machine_matrix()
            return
        panel.set_title("MACHINE")
        target = self.query_one("#machine", Static)
        model = self.app.session.model()
        dim = palette.role_hex("dim")
        t = Text()
        t.append("profile".ljust(11), style=dim)
        t.append(model.name, style=palette.role_hex("text"))
        t.append("\n")
        t.append("channels".ljust(11), style=dim)
        t.append(str(model.width), style=palette.role_hex("text"))
        t.append("\n")
        for port, ops in sorted(model.sole_host_ops().items()):
            t.append("  " + "/".join(ops), style=palette.op_style(ops[0]))
            t.append(f" → only {model.port_label(port)}", style=dim)
            t.append("\n")
        t.append("/model — full matrix", style=palette.role_hex("accent_soft"))
        target.update(t)
