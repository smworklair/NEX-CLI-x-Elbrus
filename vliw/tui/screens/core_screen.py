"""CORE — interpreter workbench.

Previously the interpreter was a plain text log where names, memory, and the
accumulated block graph had to be queried manually (`names`, `mem`, `list`).
Here they stay visible at all times and update on every line.

Layout:
    left    TAPE — calculation sheet: each user line with its result (value,
            +ops, names) and `go` verdict; the embedded console only shows
            slash-command reports
    right   NAMES, MEMORY, PROGRAM — live machine state
    bottom  OPERATIONS (kernels and verbs) + input bar with live preview

Key links:
    - sheet row <> graph ops: clicking an op highlights the line that emitted
      it; clicking a line highlights its ops in PROGRAM;
    - every line that mutates machine state commits to the shared git journal
      with a full machine snapshot so "restore" recovers names, memory, and
      graph from any mode.

Live preview evaluates expressions on a copy of the workspace as you type,
leaving real state untouched while showing the result before pressing Enter.
"""

from __future__ import annotations

import copy

from rich.text import Text
from textual.containers import Horizontal, ItemGrid, Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import Static

from ...core import InterpError, kernel_help
from ...core.interp import MEM_SIZE
from .. import palette
from ..widgets import (Chip, Console, ConsoleJournal, Panel, PanelToolbar,
                        PromptBar, plural)
from .base import ModeScreen

MEM_MINI_W = 8
MEM_MINI_ROWS = 4


class MemCell(Static):
    """Memory cell in the map. Clicking inserts `load <addr>` into input."""

    class Picked(Message):
        def __init__(self, addr: int) -> None:
            super().__init__()
            self.addr = addr

    def __init__(self, addr: int, *args, **kw) -> None:
        super().__init__(*args, **kw)
        self.addr = addr

    def on_click(self, event) -> None:
        event.stop()
        self.post_message(self.Picked(self.addr))


class TapeRow(Static):
    """TAPE sheet row. Clicking highlights the ops it emitted in PROGRAM."""

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


class ProgramItem(Static):
    """Operation in PROGRAM. Clicking highlights the TAPE row that created it."""

    class Picked(Message):
        def __init__(self, node: int) -> None:
            super().__init__()
            self.node = node

    def __init__(self, node: int, *args, **kw) -> None:
        super().__init__(*args, **kw)
        self.node = node

    def on_click(self, event) -> None:
        event.stop()
        self.post_message(self.Picked(self.node))


class CoreScreen(ModeScreen):
    """Interpreter workbench: evaluates expressions and builds a DAG live."""

    mode = "work"
    mode_title = "CORE"
    mode_subtitle = "interpreter"
    placeholder = "2+2   ·   a=10   ·   sum 8   ·   go"
    hint = "'/' command   ·   ↑ history"
    SIDE_ID = "#core-right"
    TIPS_ID = "#p-kernels"

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self._prev_regs: dict[str, int] = {}
        self._prev_mem: list[int] = []
        self._changed_regs: set[str] = set()
        self._changed_mem: set[int] = set()
        # TAPE sheet entries: append-only session log of lines, errors, notes,
        # `go` verdicts, and `names`/`mem`/`list` reports.
        self._rows: list[dict] = []
        self._line_seq = 0          # sequence number of last evaluation line
        self._sheet_drawn = 0       # number of mounted sheet rows
        self._sheet_theme = ""      # theme used when rows were mounted
        self._last_added = 0        # ops added by the last line
        self._link: tuple | None = None   # ("row", i) | ("op", node) | None
        self._report_on = False     # slash-command report console visible
        self._last_commit: dict | None = None   # journal entry for `go`
        # Session command journal inside TAPE: off by default, toggled via "git".
        self._tape_journal = False
        # Active maximized panel topic (names / memory / program / kernels / tape).
        self._wide = ""

    # --- layout -----------------------------------------------------------

    def compose_body(self):
        with Horizontal(id="core-body"):
            with Vertical(id="core-left"):
                yield Panel(
                    PanelToolbar(
                        ("names", "verb-names", "show names and values"),
                        ("mem", "verb-mem", "show memory"),
                        ("list", "verb-list", "show accumulated graph"),
                        ("go", "verb-go",
                         "send graph to LAB and schedule"),
                        ("reset", "verb-reset",
                         "clear names and memory"),
                        ("git", "tape-journal",
                         "session history and bridge to other modes"),
                    ),
                    VerticalScroll(id="tape-sheet"),
                    Console(id="console",
                            runs=self.app.session.journal_runs),
                    ConsoleJournal(id="journal"),
                    title="TAPE", id="p-tape", topic="tape")
                yield Panel(
                    Horizontal(id="kernel-chips"),
                    Horizontal(id="verb-chips"),
                    VerticalScroll(Static(id="kern-full"), id="kern-wide"),
                    title="OPERATIONS", id="p-kernels", topic="kernels",
                )
            with Vertical(id="core-right"):
                yield Panel(VerticalScroll(Static(id="names")),
                            VerticalScroll(Static(id="names-full"),
                                           id="names-wide"),
                            title="NAMES", id="p-names", topic="names")
                yield Panel(ItemGrid(id="mem-mini", min_column_width=8),
                            Static(id="mem-mini-foot"),
                            Vertical(Static(id="mem-head"),
                                     ItemGrid(id="mem-map", min_column_width=11),
                                     Static(id="mem-foot"),
                                     id="mem-wide"),
                            title="MEMORY", id="p-mem", topic="memory")
                yield Panel(
                    PanelToolbar(
                        ("go", "verb-go", "send graph to LAB and schedule"),
                        ("list", "verb-list", "show accumulated graph"),
                    ),
                    VerticalScroll(id="program"),
                    VerticalScroll(Static(id="prog-tiers"),
                                   id="prog-wide"),
                    title="PROGRAM", id="p-prog", topic="program")

    def panel_tool(self, tool: str) -> None:
        """Execute CORE panel toolbar verbs through `_exec_interp`."""
        verbs = {"verb-names": "names", "verb-mem": "mem",
                 "verb-list": "list", "verb-go": "go",
                 "verb-reset": "reset"}
        if tool in verbs:
            self._exec_interp(verbs[tool])
            return
        if tool == "tape-journal":
            self._toggle_tape_journal()
            return
        super().panel_tool(tool)

    # --- session journal inside TAPE --------------------------------------

    def _toggle_tape_journal(self) -> None:
        """Toggle the shared command journal inside the TAPE panel."""
        self._tape_journal = not self._tape_journal
        if self._tape_journal and self._wide != "tape":
            panel = self.query_one("#p-tape", Panel)
            self.maximize(panel, container=False)
            panel.post_message(Panel.Expanded(panel))
            return
        try:
            bar = self.query_one("#p-tape PanelToolbar", PanelToolbar)
            bar.mark("tape-journal", self._tape_journal)
        except Exception:
            pass
        self.refresh_state()

    def _load_journal(self) -> None:
        con = self.query_one("#console", Console)
        n = len(con.runs)
        self.query_one("#p-tape", Panel).set_title(
            f"TAPE   ·   git   ·   "
            f"{n} {plural(n, 'run', 'runs', 'runs')}")
        journal = self.query_one("#journal", ConsoleJournal)
        journal.load(con.runs, self.mode, list(self.app.commands),
                     self.app.session.journal_events)
        try:
            self.query_one("#p-tape PanelToolbar",
                           PanelToolbar).mark("tape-journal", True)
        except Exception:
            pass

    def _take_pending_note(self) -> None:
        """Append any bridge note ("to core") from the journal to the sheet."""
        note = getattr(self.app.session, "pending_note", "")
        if not note:
            return
        self.app.session.pending_note = ""
        self._rows.append({"kind": "note", "text": note})
        self._rows.append({"kind": "note",
                           "text": "build your graph variant here and run go"})
        self.refresh_state()

    def on_ready(self) -> None:
        self._fill_chips()
        self._take_pending_note()
        self.refresh_state()

    def run_core(self, line: str) -> None:
        """Show slash-command report in the console below the sheet."""
        self._report_on = True
        super().run_core(line)
        self.refresh_state()

    def hint_pairs(self):
        return [("Enter", "eval"), ("/", "commands"), ("go", "graph to LAB"),
                ("Esc", "mode picker")]

    def context_bits(self) -> str:
        """CORE header context: interpreter state rather than session scenario."""
        ws = self.app.session.workspace()
        graph = len(ws.snapshot())
        bits = [f"names {len(ws.regs)}", f"graph {graph} ops"]
        if ws.last is not None:
            bits.append(f"last {ws.last}")
        bits.append(self.app.session.model().name)
        return "   ·   ".join(bits)

    # --- chips ------------------------------------------------------------

    def _fill_chips(self) -> None:
        """Populate kernel and verb chips with tooltips."""
        row = self.query_one("#kernel-chips", Horizontal)
        row.mount(Static("kernels", classes="chip-label"))
        for name, default, hint in kernel_help():
            chip = Chip(name, f"{name} {default}", classes="chip chip-kernel")
            chip.tooltip = f"{hint}  ·  default {default}"
            row.mount(chip)
        row = self.query_one("#verb-chips", Horizontal)
        row.mount(Static("verbs", classes="chip-label"))
        for word, hint in (
            ("names", "show names and values"),
            ("mem", "show memory"),
            ("list", "show accumulated graph"),
            ("reset", "clear names and memory"),
            ("go", "send graph to LAB and schedule"),
        ):
            chip = Chip(word, classes="chip chip-verb")
            chip.tooltip = hint
            row.mount(chip)

    # --- input ------------------------------------------------------------

    def handle_line(self, line: str) -> None:
        if line.startswith("/"):
            self.run_core(line)
            return
        self._exec_interp(line)

    def _exec_interp(self, line: str) -> None:
        """Execute an interpreter line, update state, and commit if mutated."""
        from ...ui import interp_view

        con = self.console
        ws = self.app.session.workspace()
        self._snapshot_state()
        self._report_on = False     # user line restores the sheet view
        prev_graph = ws.graph_size()
        try:
            result = ws.exec(line)
        except InterpError as e:
            self._rows.append({"kind": "error", "line": line, "msg": str(e)})
            self.refresh_state()
            return
        except Exception as e:
            self._rows.append({"kind": "error", "line": line,
                               "msg": f"{type(e).__name__}: {e}"})
            self.refresh_state()
            return

        # Kernels rebuild the graph from scratch; ordinary expressions append.
        if result.kind == "kernel":
            created = list(range(ws.graph_size()))
        else:
            created = list(range(prev_graph, ws.graph_size()))
        self._last_added = len(created)
        names_changed = sorted(n for n, v in ws.regs.items()
                               if self._prev_regs.get(n) != v)
        mem_changed = {i for i, v in enumerate(ws.mem)
                       if i < len(self._prev_mem) and self._prev_mem[i] != v}

        # Utility views (names/mem/list) render as ANSI blocks; `mem 5 6` also
        # mutates memory and must record a journal commit.
        if result.kind in ("env", "mem", "list"):
            self._rows.append({
                "kind": "report",
                "ansi": interp_view.render_result(
                    ws, result, width=max(24, self.app.size.width - 8)),
            })
            if result.kind == "mem" and mem_changed:
                rec = con.commit(line, self.mode) if con is not None else {
                    "cmd": line, "lines": [], "error": False,
                    "mode": self.mode, "time": ""}
                rec["lines"] = [self._tape_text(len(self._rows) - 1)]
                rec["ws"] = ws.machine()
                self._last_commit = rec
            self.refresh_state()
            self.refresh_context()
            return

        self._line_seq += 1
        entry = {
            "kind": "line",
            "n": self._line_seq,
            "line": line,
            "value": result.value,
            "ops": len(created),
            "names": names_changed,
            "ids": created,
            "msg": (f"cell {result.message}" if result.kind == "store"
                    else result.message or ""),
        }
        self._rows.append(entry)

        changed = (bool(created) or bool(names_changed) or bool(mem_changed)
                   or result.kind == "reset")
        is_go = result.kind == "go" and not ws.empty()
        if changed or is_go:
            # Record a session commit only when machine state changes or on `go`.
            rec = con.commit(line, self.mode) if con is not None else {
                "cmd": line, "lines": [], "error": False, "mode": self.mode,
                "time": ""}
            rec["lines"] = [self._tape_text(len(self._rows) - 1)]
            rec["ws"] = ws.machine()
            if result.kind != "reset" and not ws.empty():
                self.app.session.set_dag(ws.snapshot(), "interp")
                rec["scenario"] = self.app.session.scenario
                rec["dag"] = self.app.session.dag_obj
                rec["profile"] = self.app.session.profile
            self._last_commit = rec
        self.refresh_state()
        self.refresh_context()
        if result.kind == "go":
            self._handoff()

    def _handoff(self) -> None:
        """`go`: schedule the accumulated graph and print a short verdict."""
        ws = self.app.session.workspace()
        if ws.empty():
            self._rows.append({"kind": "warn",
                               "text": "no graph yet — evaluated without "
                                       "emitting ops"})
            self.refresh_state()
            return
        self.set_busy(True)
        self.run_worker(self._go_worker, thread=True, exclusive=True, group="core")

    def _go_worker(self) -> None:
        """Run exact scheduling on a background thread so the UI stays fluid."""
        try:
            base, orc, met = self.app.session.results()
        except Exception as e:  # oracle timeout/error must not crash the screen
            self.app.call_from_thread(self._verdict_error, str(e))
            return
        self.app.call_from_thread(self._go_done, base, orc, met)

    def _go_done(self, base, orc, met) -> None:
        self.set_busy(False)
        self._verdict(base, orc, met)
        self.refresh_context()

    def _verdict_error(self, msg: str) -> None:
        self.set_busy(False)
        self._rows.append({"kind": "error", "line": "go",
                           "msg": f"scheduling failed: {msg}"})
        self.refresh_state()

    def _verdict(self, base, orc, met) -> None:
        """Record the `go` verdict in the sheet and in the journal commit."""
        b, o = base.schedule.makespan, orc.schedule.makespan
        self._rows.append({"kind": "verdict", "base": b, "oracle": o,
                           "bound": met.lower_bound})
        rec = self._last_commit
        if rec is not None:
            rec["verdict"] = (b, o)
            rec["lines"].append(self._verdict_text(b, o, met.lower_bound))
        self.refresh_state()

    def _verdict_text(self, b: int, o: int, bound: int) -> Text:
        t = Text()
        t.append("  *  graph sent to LAB",
                 style=f"{palette.role_hex('work')} bold")
        t.append("\n")
        t.append("     baseline ", style=palette.role_hex("dim"))
        t.append(str(b), style=palette.role_hex("title"))
        t.append("   oracle ", style=palette.role_hex("dim"))
        t.append(str(o), style=f"{palette.role_hex('success')} bold")
        t.append("   bound ", style=palette.role_hex("dim"))
        t.append(str(bound), style=palette.role_hex("title"))
        if b > o:
            t.append(f"   -{b - o} cyc", style=palette.role_hex("success"))
        return t

    # --- live preview -----------------------------------------------------

    def on_prompt_bar_changed(self, event: PromptBar.Changed) -> None:
        event.stop()
        self._preview(event.value.strip())

    def _preview(self, text: str) -> None:
        """Evaluate expression on a workspace copy before Enter is pressed."""
        bar = self.query_one("#prompt", PromptBar)
        if not text or text.startswith("/") or self.busy:
            bar.set_side("")
            return
        head = text.split()[0].lower()
        if head in ("go", "reset", "new", "names", "env", "list", "graph",
                    "ops", "mem") or "=" in text or text.startswith("store"):
            bar.set_side("")
            return
        try:
            ws = copy.deepcopy(self.app.session.workspace())
            result = ws.exec(text)
        except Exception:
            bar.set_side("")
            return
        if result.value is None:
            bar.set_side("")
            return
        t = Text()
        t.append("= ", style=palette.role_hex("faint"))
        t.append(str(result.value), style=palette.role_hex("work_soft"))
        bar.set_side(t)

    # --- machine state ----------------------------------------------------

    def redraw(self) -> None:
        self.refresh_state()

    def _snapshot_state(self) -> None:
        ws = self.app.session.workspace()
        self._prev_regs = dict(ws.regs)
        self._prev_mem = list(ws.mem)

    def refresh_state(self) -> None:
        ws = self.app.session.workspace()
        self._changed_regs = {k for k, v in ws.regs.items()
                              if self._prev_regs.get(k) != v}
        self._changed_mem = {i for i, v in enumerate(ws.mem)
                             if i < len(self._prev_mem) and self._prev_mem[i] != v}
        for wide_id, short_ids, topic in (
                ("#names-wide", ("#names",), "names"),
                ("#mem-wide", ("#mem-mini", "#mem-mini-foot"), "memory"),
                ("#prog-wide", ("#program",), "program"),
                ("#kern-wide", ("#kernel-chips", "#verb-chips"), "kernels")):
            self.query_one(wide_id).display = self._wide == topic
            for short_id in short_ids:
                self.query_one(short_id).display = self._wide != topic
        con = self.query_one("#console", Console)
        journal = self.query_one("#journal", ConsoleJournal)
        if self._wide == "tape" and self._tape_journal:
            self.query_one("#tape-sheet").display = False
            con.display = False
            journal.display = True
            self._load_journal()
        else:
            journal.display = False
            con.display = self._report_on
            sheet = self.query_one("#tape-sheet")
            sheet.display = True
            self._draw_tape()
        self._draw_names(ws)
        self._draw_memory(ws)
        self._draw_program(ws)
        # Render maximized views after compact views so their titles win.
        if self._wide == "names":
            self._draw_names_full(ws)
        elif self._wide == "memory":
            self._draw_mem_map(ws)
        elif self._wide == "program":
            self._draw_prog_tiers(ws)
        elif self._wide == "kernels":
            self._draw_kern_full()
        else:
            self.query_one("#p-kernels", Panel).set_title("OPERATIONS")

    # --- maximized CORE views ---------------------------------------------
    #
    # Each panel expands into a richer view rather than a scaled copy:
    #   NAMES   — value provenance (expression, subtree size, depth);
    #   MEMORY  — full 64-cell clickable map;
    #   PROGRAM — graph by ASAP tiers (parallelism available to LAB).

    def on_panel_expanded(self, event) -> None:
        event.stop()
        self._wide = getattr(event.panel, "topic", "")
        self.refresh_state()

    def on_panel_collapsed(self, event) -> None:
        event.stop()
        self._wide = ""
        self.refresh_state()

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

    def _subtree(self, dag, root: int) -> set[int]:
        """Return all graph op IDs contributing to `root`."""
        seen: set[int] = set()
        stack = [root]
        while stack:
            i = stack.pop()
            if i in seen:
                continue
            seen.add(i)
            stack.extend(dag[i].preds)
        return seen

    def panel_facts(self, topic: str) -> list[str]:
        ws = self.app.session.workspace()
        dag = ws.snapshot()
        base = [f"Interpreter: {len(ws.regs)} names, {len(dag)} graph ops, "
                f"machine {self.app.session.model().name}."]
        if topic == "names":
            return base + [f"{n} = {v}" for n, v in list(ws.regs.items())[:12]]
        if topic == "memory":
            filled = [(i, v) for i, v in enumerate(ws.mem) if v][:12]
            return base + [f"Cell {i} = {v}" for i, v in filled]
        if topic == "program":
            return base + [f"{i.name}: {i.text} ({i.op})"
                           for i in list(dag)[:12]]
        if topic == "tape":
            lines = [r for r in self._rows if r["kind"] == "line"]
            return base + [f"Line \"{h['line']}\" gave {h['value']}, "
                           f"+{h['ops']} ops." for h in lines[-8:]]
        if topic == "kernels":
            return base + [f"Kernel {n} {d}: {h}" for n, d, h in kernel_help()]
        return base

    def panel_chips(self, topic: str) -> list[str]:
        return {
            "names": ["which name is the most expensive here?",
                      "what does 'ops' mean in this table?"],
            "memory": ["what is in memory by default?",
                       "how does load differ from store?"],
            "program": ["what can run in parallel here?",
                        "why are the tiers so narrow?"],
            "tape": ["what have I computed so far?",
                     "which lines emitted ops to the graph?"],
            "kernels": ["which kernel is best to start with?",
                        "how does dot differ from saxpy?"],
        }.get(topic, [])

    # --- TAPE sheet -------------------------------------------------------

    def _draw_tape(self) -> None:
        """Render the TAPE sheet incrementally, rebuilding only on theme change."""
        from ...ui import render

        box = self.query_one("#tape-sheet", VerticalScroll)
        panel = self.query_one("#p-tape", Panel)
        if render.THEME.name != self._sheet_theme:
            box.remove_children()
            self._sheet_drawn = 0
            self._sheet_theme = render.THEME.name
        n = len([r for r in self._rows if r["kind"] == "line"])
        place = ("calculation sheet" if self._wide == "tape" else "sheet")
        panel.set_title(f"TAPE   ·   {place}   ·   "
                        f"{n} {plural(n, 'line', 'lines', 'lines')}")
        if not self._rows:
            if not box.children:
                box.mount(Static(Text(
                    "    every line lands here: input, result,\n"
                    "    and how many ops went into the graph.\n\n"
                    "    memory starts initialized to 1 2 3 4 …\n\n"
                    "    2+2   ·   a=10   ·   x=load 0   ·   sum 8   ·   go",
                    style=palette.role_hex("faint")),
                    classes="tape-empty"))
            return
        if self._sheet_drawn == 0:
            box.remove_children()   # replace empty state on first line
        fresh = False
        for i in range(self._sheet_drawn, len(self._rows)):
            box.mount(TapeRow(i, self._tape_text(i),
                              classes="tape-row tape-" + self._rows[i]["kind"]))
            fresh = True
        self._sheet_drawn = len(self._rows)
        if fresh and self._wide != "tape":
            box.scroll_end(animate=False)
        self._apply_link()

    def _tape_text(self, i: int) -> Text:
        """Format a sheet row (reused verbatim in git journal commit records)."""
        r = self._rows[i]
        faint = palette.role_hex("faint")
        dim = palette.role_hex("dim")
        title = palette.role_hex("title")
        work = palette.role_hex("work")
        kind = r["kind"]
        t = Text()
        if kind == "line":
            t.append(f"{r['n']:>3}  ", style=faint)
            t.append(r["line"][:26].ljust(26), style=title)
            val = "—" if r["value"] is None else str(r["value"])
            t.append(f"= {val}".ljust(12),
                     style=work if r["value"] is not None else faint)
            if r["ops"]:
                t.append(f"+{r['ops']} ops".ljust(9),
                         style=palette.role_hex("accent2"))
            else:
                t.append("·".ljust(9), style=faint)
            tail = ", ".join(r["names"]) if r["names"] else r.get("msg", "")
            if tail:
                t.append(tail[:32], style=dim)
        elif kind == "error":
            t.append("  -  ", style=palette.role_hex("error"))
            t.append(r["line"][:26], style=palette.role_hex("error"))
            t.append("   " + r["msg"], style=dim)
        elif kind == "warn":
            t.append("  !  ", style=palette.role_hex("warning"))
            t.append(r["text"], style=dim)
        elif kind == "note":
            t.append("  ·  ", style=palette.role_hex("accent2"))
            t.append(r["text"], style=dim)
        elif kind == "verdict":
            t.append_text(self._verdict_text(r["base"], r["oracle"],
                                             r["bound"]))
        elif kind == "report":
            return Text.from_ansi("\n".join(r["ansi"]))
        return t

    # --- row <> op cross-highlighting -------------------------------------

    def on_tape_row_picked(self, event: TapeRow.Picked) -> None:
        event.stop()
        if self._rows[event.index]["kind"] != "line":
            return
        self._set_link(None if self._link == ("row", event.index)
                       else ("row", event.index))

    def on_program_item_picked(self, event: ProgramItem.Picked) -> None:
        event.stop()
        self._set_link(None if self._link == ("op", event.node)
                       else ("op", event.node))
        if self._link is None:
            return
        i = self._row_of_node(event.node)
        if i is None:
            return
        sheet = self.query_one("#tape-sheet", VerticalScroll)
        for row in sheet.query(TapeRow):
            if row.index == i:
                sheet.scroll_to_widget(row, animate=False)
                break

    def _set_link(self, link: tuple | None) -> None:
        self._link = link
        self._apply_link()

    def _row_of_node(self, node: int) -> int | None:
        """Return the sheet row index that emitted graph node `node`."""
        for i, r in enumerate(self._rows):
            if r.get("kind") == "line" and node in r.get("ids", ()):
                return i
        return None

    def _apply_link(self) -> None:
        """Apply bidirectional row/op highlight without redrawing content."""
        link = self._link
        linked_ids: set[int] = set()
        if link is not None:
            if link[0] == "op":
                linked_ids.add(link[1])
            else:
                row = self._rows[link[1]]
                linked_ids = set(row.get("ids", ()))
        for row in self.query(TapeRow):
            on = False
            if link is not None:
                if link[0] == "row":
                    on = row.index == link[1]
                else:
                    r = self._rows[row.index]
                    on = r.get("kind") == "line" and link[1] in r.get("ids", ())
            row.set_class(on, "on")
        for item in self.query(ProgramItem):
            item.set_class(item.node in linked_ids, "hot")

    def _draw_kern_full(self) -> None:
        """Maximized OPERATIONS panel — full kernel and verb catalog."""
        target = self.query_one("#kern-full", Static)
        panel = self.query_one("#p-kernels", Panel)
        dim, faint = palette.role_hex("dim"), palette.role_hex("faint")
        work = palette.role_hex("work")
        rows = kernel_help()
        panel.set_title(f"OPERATIONS   ·   catalog   ·   {len(rows)} kernels")
        t = Text()
        t.append_text(self._section("kernels", "click a chip to run"))
        t.append("\n\n")
        t.append("      " + "call".ljust(18) + "what it computes\n", style=faint)
        for name, default, hint in rows:
            t.append("      ")
            t.append(f"{name} {default}".ljust(18), style=work)
            t.append(hint, style=dim)
            t.append("\n")
        t.append("\n")
        t.append_text(self._section("verbs"))
        t.append("\n\n")
        for word, hint in (("names", "show names and values"),
                           ("mem", "show memory"),
                           ("list", "show accumulated graph"),
                           ("reset", "clear names and memory"),
                           ("go", "send graph to LAB and schedule")):
            t.append("      " + word.ljust(18), style=palette.role_hex("text"))
            t.append(hint + "\n", style=faint)
        t.append("\n")
        t.append_text(self._section("syntax"))
        t.append("\n\n")
        t.append("      a0 = load [0]        read from memory\n"
                 "      s = a0 * b0          arithmetic on names\n"
                 "      store s 7            write back to memory\n\n", style=dim)
        t.append("      Use expressions here rather than e2k mnemonics:\n"
                 "      `mul m0 a0 b0` is assembly — load it with /load.",
                 style=faint)
        target.update(t)

    def _draw_names_full(self, ws) -> None:
        target = self.query_one("#names-full", Static)
        panel = self.query_one("#p-names", Panel)
        dim, faint = palette.role_hex("dim"), palette.role_hex("faint")
        title = palette.role_hex("title")
        panel.set_title(f"NAMES   ·   value origins   ·   "
                        f"{len(ws.regs)} {plural(len(ws.regs), 'name', 'names', 'names')}")
        t = Text()
        if not ws.regs:
            t.append("  empty so far. Type  a = 10  or  x = load 0",
                     style=faint)
            target.update(t)
            return
        dag = ws.snapshot()
        ids = getattr(ws, "_ids", {})
        t.append_text(self._section("values", "and how they were computed"))
        t.append("\n\n")
        t.append("    " + "name".ljust(12) + "value".rjust(12)
                 + "   " + "ops".rjust(9) + "   expression\n", style=faint)
        for name, value in ws.regs.items():
            hot = name in self._changed_regs
            t.append("    ")
            t.append(name[:11].ljust(12),
                     style=title if hot else palette.role_hex("text"))
            t.append(str(value).rjust(12),
                     style=(palette.role_hex("work") + " bold") if hot else dim)
            node = ids.get(name)
            if node is None or node >= len(dag):
                t.append("   " + "—".rjust(9) + "   ", style=faint)
                t.append("literal constant", style=faint)
            else:
                sub = self._subtree(dag, node)
                t.append("   " + str(len(sub)).rjust(9) + "   ", style=faint)
                t.append(dag[node].text, style=palette.op_style(dag[node].op))
            t.append("\n")
        t.append("\n")
        t.append_text(self._section("what this means"))
        t.append("\n\n")
        t.append("    'ops' is the number of graph nodes behind this name. A\n"
                 "    deep expression creates a long dependency chain that\n"
                 "    becomes the critical path in LAB.\n", style=faint)
        target.update(t)

    def _draw_mem_map(self, ws) -> None:
        head = self.query_one("#mem-head", Static)
        grid = self.query_one("#mem-map", ItemGrid)
        foot = self.query_one("#mem-foot", Static)
        panel = self.query_one("#p-mem", Panel)
        faint = palette.role_hex("faint")
        used = sum(1 for v in ws.mem if v)
        panel.set_title(f"MEMORY   ·   map   ·   {MEM_SIZE} cells, "
                        f"{used} non-zero")
        stores = self._store_cells(ws.snapshot())
        h = Text()
        h.append_text(self._section("cells", "click to insert load"))
        head.update(h)
        grid.remove_children()
        for addr in range(MEM_SIZE):
            grid.mount(MemCell(addr, self._mem_cell_text(addr, ws, stores),
                               classes="mem-cell"))
        f = Text()
        written = ", ".join(f"{a}←{n}" if n else str(a)
                            for a, n in sorted(stores.items())[:8])
        f.append("\n    > ", style=palette.role_hex("work"))
        f.append(f"written by store: {written}" if written
                 else "no store writes yet", faint)
        f.append("        bright = changed on last line", faint)
        foot.update(f)

    def on_mem_cell_picked(self, event) -> None:
        event.stop()
        bar = self.query_one("#prompt", PromptBar)
        bar.focus_input()
        bar.set_value(f"load {event.addr}")

    def _draw_prog_tiers(self, ws) -> None:
        target = self.query_one("#prog-tiers", Static)
        panel = self.query_one("#p-prog", Panel)
        dag = ws.snapshot()
        dim, faint = palette.role_hex("dim"), palette.role_hex("faint")
        title = palette.role_hex("title")
        panel.set_title(f"PROGRAM   ·   ASAP tiers   ·   {len(dag)} ops")
        t = Text()
        if not len(dag):
            t.append("  graph is empty. Try `x = load 0`, `s = x*2` to "
                     "start building it.", style=faint)
            target.update(t)
            return
        from ...core.dag import compute_metrics

        model = self.app.session.model()
        try:
            met = compute_metrics(dag, model)
        except Exception:
            met = None
        # Tier = earliest dependency-legal cycle (ASAP). Ops in the same tier
        # are mutually independent and show the raw ILP available to LAB.
        tiers: dict[int, list[int]] = {}
        for ins in dag:
            lvl = met.asap[ins.id] if met else 0
            tiers.setdefault(lvl, []).append(ins.id)
        widest = max((len(v) for v in tiers.values()), default=0)
        t.append_text(self._section(
            "tiers", f"{len(tiers)} {plural(len(tiers), 'tier', 'tiers', 'tiers')}"
            f"  ·  max width {widest}  ·  {model.width} ports"))
        t.append("\n\n")
        for lvl in sorted(tiers):
            t.append(f"    c{lvl:<4}", style=faint)
            row = tiers[lvl]
            over = len(row) > model.width
            for i in row:
                ins = dag[i]
                t.append(ins.name[:6].ljust(7), style=palette.op_style(ins.op))
            if over:
                t.append(f"   {len(row)} > {model.width} ports — "
                         "some will wait", style=palette.role_hex("warning"))
            t.append("\n")
        t.append("\n")
        t.append_text(self._section("next"))
        t.append("\n\n")
        if met:
            t.append(f"    dependency chain — {met.critical_path_bound} cyc, "
                     f"resources — {met.resource_bound} cyc\n", style=dim)
            t.append(f"    no scheduler can finish this graph faster than "
                     f"{met.lower_bound} cyc.\n", style=faint)
        t.append("    `go` — send graph to LAB and compute schedule.",
                 style=palette.role_hex("work"))
        target.update(t)

    def _draw_names(self, ws) -> None:
        target = self.query_one("#names", Static)
        panel = self.query_one("#p-names", Panel)
        dim = palette.role_hex("dim")
        badge = (f"   +{len(self._changed_regs)}"
                 if self._changed_regs else "")
        panel.set_title(f"NAMES   {len(ws.regs)}{badge}")
        if not ws.regs:
            target.update(Text("empty — try a=10", style=palette.role_hex("faint")))
            return
        width = max(20, panel.size.width - 4)
        key_w = max(6, width - 12)
        t = Text()
        for i, (name, value) in enumerate(ws.regs.items()):
            if i:
                t.append("\n")
            hot = name in self._changed_regs
            t.append(name[: key_w - 1].ljust(key_w),
                     style=palette.role_hex("title") if hot else palette.role_hex("text"))
            t.append(str(value).rjust(11),
                     style=(f"{palette.role_hex('work')} bold") if hot else dim)
        target.update(t)

    def _store_cells(self, dag) -> dict[int, str]:
        """Map memory address -> stored source name for STORE nodes."""
        stores: dict[int, str] = {}
        for ins in dag:
            if ins.op == "STORE" and ins.name.startswith("st"):
                digits = ins.name[2:].split(".")[0]
                if digits.isdigit():
                    parts = ins.text.split()
                    stores[int(digits)] = parts[1] if len(parts) > 1 else ""
        return stores

    def _mem_cell_text(self, addr: int, ws, stores: dict[int, str]) -> Text:
        """Render one memory cell without internal spaces so Static won't wrap."""
        value = ws.mem[addr] if addr < len(ws.mem) else 0
        faint = palette.role_hex("faint")
        cell = Text()
        cell.append(">" if addr in stores else "·",
                    style=palette.role_hex("work") if addr in stores else faint)
        cell.append(f"{addr:>2}", style=faint)
        cell.append("│", style=palette.role_hex("line"))
        if addr in self._changed_mem:
            style = f"{palette.role_hex('accent2')} bold"
        elif addr in stores:
            style = palette.role_hex("work")
        elif not value:
            style = faint
        else:
            style = palette.role_hex("dim")
        cell.append(str(value)[:4].rjust(4), style=style)
        return cell

    def _draw_memory(self, ws) -> None:
        """Compact MEMORY view: first rows of the same clickable cell map."""
        grid = self.query_one("#mem-mini", ItemGrid)
        foot = self.query_one("#mem-mini-foot", Static)
        panel = self.query_one("#p-mem", Panel)
        badge = (f"   +{len(self._changed_mem)}"
                 if self._changed_mem else "")
        panel.set_title(f"MEMORY{badge}")
        stores = self._store_cells(ws.snapshot())
        grid.remove_children()
        inner = max(16, panel.size.width - 4)
        cols = max(3, (inner - 4) // MEM_MINI_W)
        for addr in range(min(MEM_SIZE, cols * MEM_MINI_ROWS)):
            grid.mount(MemCell(addr, self._mem_cell_text(addr, ws, stores),
                               classes="mem-cell mini"))
        f = Text()
        written = ", ".join(f"{a}←{n}" if n else str(a)
                            for a, n in sorted(stores.items())[:6])
        f.append("> ", style=palette.role_hex("work"))
        if written:
            f.append(f"store: {written}", style=palette.role_hex("dim"))
            f.append("  ·  ", style=palette.role_hex("faint"))
        f.append("click — load · expand for full map",
                 style=palette.role_hex("faint"))
        foot.update(f)

    def _draw_program(self, ws) -> None:
        """PROGRAM — one clickable op per line, linked to the TAPE sheet."""
        box = self.query_one("#program", VerticalScroll)
        panel = self.query_one("#p-prog", Panel)
        dag = ws.snapshot()
        badge = (f"   +{self._last_added}" if self._last_added else "")
        panel.set_title(f"PROGRAM   {len(dag)} ops{badge}")
        box.remove_children()
        if not len(dag):
            box.mount(Static(Text(
                "graph is empty — load/store and arithmetic on names\n"
                "emit operations here",
                style=palette.role_hex("faint"))))
            return
        dim = palette.role_hex("dim")
        for ins in dag:
            t = Text()
            t.append(f"{ins.name:<7}", style=palette.role_hex("text"))
            t.append(f"{ins.op:<6}", style=palette.op_style(ins.op))
            t.append(ins.text, style=dim)
            box.mount(ProgramItem(ins.id, t, classes="prog-item"))
        self._apply_link()
