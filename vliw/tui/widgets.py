"""Shared UI primitives: top bar, panels, input dock, command palette.

Each mode has its own layout, sharing only these building blocks so the whole
tool feels cohesive: a uniform top bar, input line, and panel chrome.
"""

from __future__ import annotations

import time

from rich.text import Text
from textual.binding import Binding
from textual.containers import Horizontal, ItemGrid, Vertical, VerticalScroll
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import Input, OptionList, RichLog, Static
from textual.widgets.option_list import Option

from . import palette

MARK = "▌"
ARROW = ">"


# --------------------------------------------------------------------------
# Top bar
# --------------------------------------------------------------------------


class SleepChip(Static):
    """Single dormant-mode fact on the second line of the top bar.

    Clicking opens that mode via `app.open_mode`. Styled like IDE status-bar
    text with hover feedback.
    """

    class Goto(Message):
        """Open mode `mode` (work | mind | code)."""

        def __init__(self, mode: str) -> None:
            super().__init__()
            self.mode = mode

    def __init__(self, label: str, body: str, mode: str, **kw) -> None:
        t = Text()
        t.append(f"{label}: ", style=f"{palette.mode_hex(mode)} bold")
        t.append(body, style=palette.role_hex("dim"))
        super().__init__(t, **kw)
        self.mode = mode

    def on_click(self, event) -> None:
        event.stop()
        self.post_message(self.Goto(self.mode))


class TopBar(Vertical):
    """Mode header: mark, mode title, live context, and optional sleeper row."""

    context = reactive("", layout=False)

    #: [(label, text, mode)] — one short fact per dormant mode; hidden if empty.
    sleepers = reactive((), layout=False)

    def __init__(self, mode: str, title: str, subtitle: str, **kw) -> None:
        super().__init__(**kw)
        self.mode = mode
        self.title_text = title
        self.subtitle = subtitle
        self._sleep_gen = 0          # generation counter to drop stale mounts

    def compose(self):
        yield Static("", id="topbar-line")
        yield Horizontal(id="topbar-sleep")

    def watch_context(self) -> None:
        self.refresh_bar()

    def watch_sleepers(self) -> None:
        self.refresh_bar()

    def on_mount(self) -> None:
        self.refresh_bar()

    def refresh_bar(self) -> None:
        accent = palette.mode_hex(self.mode)
        dim = palette.role_hex("dim")
        line = Text()
        line.append(f"{MARK} ", style=accent)
        line.append("NEX", style=f"{accent} bold")
        line.append("   ")
        line.append(self.title_text, style=f"{accent} bold")
        line.append("   ")
        line.append(self.subtitle, style=dim)
        if self.context:
            line.append("      ")
            line.append(self.context, style=dim)
        try:
            self.query_one("#topbar-line", Static).update(line)
        except Exception:
            pass        # watcher may fire before children are mounted
        self._render_sleepers()

    def _render_sleepers(self) -> None:
        try:
            row = self.query_one("#topbar-sleep", Horizontal)
        except Exception:
            return
        row.remove_children()
        row.set_class(bool(self.sleepers), "on")
        if not self.sleepers:
            return
        faint = palette.role_hex("faint")
        parts = []
        for i, (label, body, mode) in enumerate(self.sleepers):
            if i:
                parts.append(Static(Text("   ·   ", style=faint),
                                    classes="sleep-sep"))
            parts.append(SleepChip(label, body, mode, classes="sleep-chip",
                                   id=f"sleep-{mode}"))
        # Defer mounting to the next refresh so synchronous mount inside
        # on_mount -> reactive chains does not deadlock Textual message tracking.
        self._sleep_gen += 1
        gen = self._sleep_gen

        def flush() -> None:
            if gen != self._sleep_gen:
                return
            try:
                row.mount(*parts)
            except Exception:
                pass

        self.call_after_refresh(flush)


# --------------------------------------------------------------------------
# Titled panel
# --------------------------------------------------------------------------


class PanelHead(Static):
    """Single-row panel header: title on the left, live summary on the right."""

    def set_head(self, title: str, note: str = "", accent: str = "") -> None:
        """Set header title and optional muted trailing note."""
        t = Text()
        t.append(title, style=palette.role_hex(accent or "title"))
        if note:
            t.append("   " + note, style=palette.role_hex("faint"))
        self.update(t)


#: Max interval between clicks to count as a double-click (matches Textual's
#: `App.CLICK_CHAIN_TIME_THRESHOLD`).
DOUBLE_CLICK_S = 0.5


def double_click(event, last: float) -> tuple[bool, float]:
    """Return `(is_double, next_timestamp)` for a mouse click event."""
    now = getattr(event, "time", 0.0) or time.monotonic()
    if getattr(event, "chain", 1) >= 2:
        return True, 0.0
    if last and now - last <= DOUBLE_CLICK_S:
        return True, 0.0
    return False, now


class Panel(Vertical):
    """Window with a single-line header strip and double-click maximize."""

    DOUBLE_CLICK_S = DOUBLE_CLICK_S

    #: Required so Textual allows maximizing a non-focusable container.
    ALLOW_MAXIMIZE = True

    #: Topic key used by the screen to collect AI helper facts for this panel.
    topic: str = ""

    #: True if this panel has its own input line (side chat opens on the left).
    has_own_input: bool = False

    class Expanded(Message):
        """Panel was maximized."""

        def __init__(self, panel: "Panel") -> None:
            super().__init__()
            self.panel = panel

    class Collapsed(Message):
        """Panel was restored to normal size."""

    #: Soft maximize: emit Expanded without invoking Textual's built-in
    #: maximize, letting the screen rearrange its own layout.
    soft: bool = False

    def __init__(self, *children, title: str = "", accent: str = "",
                 topic: str = "", has_own_input: bool = False,
                 soft: bool = False, **kw) -> None:
        super().__init__(*children, **kw)
        self._title = title
        self._accent = accent
        self._last_click = 0.0
        self.topic = topic
        self.has_own_input = has_own_input
        self.soft = soft

    def on_mount(self) -> None:
        self._head = PanelHead(classes="panel-head")
        self.mount(self._head, before=0)
        self._head.set_head(self._title, accent=self._accent)

    def set_title(self, title: str) -> None:
        self._title = title
        head = getattr(self, "_head", None)
        if head is not None:
            head.set_head(title, accent=self._accent)

    def on_mouse_down(self, event) -> None:
        """Double-click toggles maximize/restore (tracked on MouseDown so
        inner widgets like DataTable or Chips that stop Click don't block it)."""
        if isinstance(event.widget, Input):
            event.stop()
            return
        now = getattr(event, "time", 0.0) or time.monotonic()
        double = (now - self._last_click) <= self.DOUBLE_CLICK_S
        self._last_click = now
        if not double:
            return
        event.stop()
        self._last_click = 0.0        # prevent triple-click from re-triggering
        screen = self.screen
        if self.soft:
            self.post_message(self.Expanded(self))
            return
        if screen.maximized is self:
            screen.minimize()
            self.post_message(self.Collapsed())
        else:
            screen.maximize(self, container=False)
            self.post_message(self.Expanded(self))


# --------------------------------------------------------------------------
# Console: raw core command output
# --------------------------------------------------------------------------


class Console(RichLog):
    """Command output log that accepts ANSI strings and records per-run history."""

    def __init__(self, runs: list | None = None, **kw) -> None:
        kw.setdefault("highlight", False)
        kw.setdefault("markup", False)
        kw.setdefault("wrap", False)
        kw.setdefault("auto_scroll", True)
        super().__init__(**kw)
        self.runs: list[dict] = runs if runs is not None else []

    def _record(self, line) -> None:
        """Append a rendered line to the active run record."""
        if self.runs:
            self.runs[-1]["lines"].append(line)

    def echo(self, line: str, mode: str = "lab") -> None:
        """Record and display a submitted command with mode and timestamp."""
        accent = palette.mode_hex(mode)
        self.runs.append({"cmd": line, "lines": [], "error": False,
                          "mode": mode,
                          "time": time.strftime("%H:%M")})
        t = Text()
        t.append(f"{ARROW} ", style=accent)
        t.append(line, style=palette.role_hex("title"))
        self.write(t)
        self._record(t)

    def commit(self, line: str, mode: str = "lab") -> dict:
        """Create a new journal run entry without writing to the RichLog."""
        self.runs.append({"cmd": line, "lines": [], "error": False,
                          "mode": mode,
                          "time": time.strftime("%H:%M")})
        return self.runs[-1]

    def ansi(self, text: str) -> None:
        for line in text.split("\n"):
            t = Text.from_ansi(line)
            self._record(t)
            self.write(t)

    def note(self, text: str, role: str = "dim") -> None:
        t = Text(text, style=palette.role_hex(role))
        if role == "error" and self.runs:
            self.runs[-1]["error"] = True
        self._record(t)
        self.write(t)


def plural(n: int, one: str, few: str, many: str) -> str:
    """Return singular (`one`) when `n == 1`, otherwise plural (`many`)."""
    return one if n == 1 else many


class RunItem(Static):
    """Single run entry in the journal. Click shows its output on the right."""

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


class CommandItem(Static):
    """Command in the journal catalog. Click inserts it into the input line."""

    class Picked(Message):
        def __init__(self, line: str) -> None:
            super().__init__()
            self.line = line

    def __init__(self, line: str, *args, **kw) -> None:
        super().__init__(*args, **kw)
        self.line = line

    def on_click(self, event) -> None:
        event.stop()
        self.post_message(self.Picked(self.line))


class JournalInput(Input):
    """Terminal input where Up/Down step through command history."""

    BINDINGS = [
        Binding("up", "hist(-1)", "", show=False),
        Binding("down", "hist(1)", "", show=False),
    ]

    class Hist(Message):
        def __init__(self, delta: int) -> None:
            super().__init__()
            self.delta = delta

    def action_hist(self, delta: int) -> None:
        self.post_message(self.Hist(delta))


class ConsoleJournal(Horizontal):
    """Maximized command output journal: command catalog, run history,
    mode bridge, separate live events feed, and embedded terminal input."""

    BINDINGS = [
        Binding("ctrl+r", "repeat", "repeat run", show=False),
        Binding("ctrl+l", "wipe", "clear journal", show=False),
    ]

    #: Width of the left history/catalog column.
    SIDE_W = 32

    class RunRequested(Message):
        """Command submitted directly inside the maximized journal."""

        def __init__(self, line: str) -> None:
            super().__init__()
            self.line = line

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self.runs: list[dict] = []
        self.commands: list[dict] = []
        self.events: list = []
        self.pos = -1
        self._seen = 0
        self.mode = "lab"
        self._filter = ""
        self._hist_pos: int | None = None
        self._feed = "runs"    # runs | events — active right-pane stream

    def compose(self):
        with Vertical(id="journal-side"):
            yield Static("", id="journal-cmds-head")
            yield VerticalScroll(id="journal-cmds")
            yield Static("", id="journal-runs-head")
            yield VerticalScroll(id="journal-list")
        with Vertical(id="journal-right"):
            yield BridgeRow(prefix="bridge", id="run-actions")
            with Horizontal(id="feed-tabs"):
                yield Tool("command output", "feed-runs",
                           "reports from executed commands", id="feed-runs")
                yield Tool("events", "feed-events",
                           "live scheduler and model stream — separate "
                           "from reports", id="feed-events")
            yield RichLog(id="journal-out", highlight=False, markup=False,
                          wrap=False, auto_scroll=False)
            yield RichLog(id="events-out", highlight=False, markup=False,
                          wrap=True, auto_scroll=True)
            with Horizontal(id="journal-field"):
                yield Static("", id="journal-mark")
                yield JournalInput(placeholder="command", id="journal-input")
                yield Static("catalog left   ·   ↑↓ history   ·   ^R repeat",
                             id="journal-hint")

    def on_tool_picked(self, event) -> None:
        if event.tool in ("feed-runs", "feed-events"):
            event.stop()
            self.show_feed("runs" if event.tool == "feed-runs" else "events")

    def on_mount(self) -> None:
        self._repaint_mark()

    def _repaint_mark(self) -> None:
        accent = palette.mode_hex(self.mode)
        mark = Text("> ", style=f"{accent} bold")
        self.query_one("#journal-mark", Static).update(mark)

    # --- input ------------------------------------------------------------

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        line = event.value.strip()
        event.input.value = ""
        self._filter = ""
        self._hist_pos = None
        self._draw_commands()
        if line:
            self.post_message(self.RunRequested(line))

    def on_input_changed(self, event: Input.Changed) -> None:
        """Filter the left command catalog live by the first typed token."""
        event.stop()
        self._filter = event.value.strip().lstrip("/").split(" ")[0].lower()
        self._draw_commands()

    def on_journal_input_hist(self, event) -> None:
        event.stop()
        cmds = [r["cmd"] for r in self.runs]
        if not cmds:
            return
        if self._hist_pos is None:
            self._hist_pos = len(cmds)
        self._hist_pos = max(0, min(len(cmds), self._hist_pos + event.delta))
        inp = self.query_one("#journal-input", JournalInput)
        value = "" if self._hist_pos >= len(cmds) else cmds[self._hist_pos]
        inp.value = value
        inp.cursor_position = len(value)

    def on_command_item_picked(self, event) -> None:
        """Insert clicked command into input without immediately running it."""
        event.stop()
        inp = self.query_one("#journal-input", JournalInput)
        inp.value = event.line
        inp.cursor_position = len(event.line)
        inp.focus()

    def action_repeat(self) -> None:
        """^R — re-run the selected journal entry."""
        if 0 <= self.pos < len(self.runs):
            self.post_message(self.RunRequested(self.runs[self.pos]["cmd"]))

    def action_wipe(self) -> None:
        """^L — clear the journal history."""
        self.runs.clear()
        self.pos = -1
        self._seen = 0
        self.load(self.runs, self.mode, self.commands)

    # --- rendering --------------------------------------------------------

    def load(self, runs: list[dict], mode: str = "lab",
             commands: list[dict] | None = None,
             events: list | None = None) -> None:
        self.runs = runs
        if commands is not None:
            self.commands = commands
        if events is not None:
            self.events = events
        if mode != self.mode:
            self.mode = mode
            self._repaint_mark()
        self._draw_commands()
        self._draw_runs()
        self.show_feed(self._feed)

    # --- live events stream -----------------------------------------------

    def show_feed(self, feed: str) -> None:
        """Switch right pane between command reports and live events stream."""
        self._feed = feed if feed in ("runs", "events") else "runs"
        self.query_one("#journal-out").display = self._feed == "runs"
        self.query_one("#events-out").display = self._feed == "events"
        for key in ("feed-runs", "feed-events"):
            self.query_one(f"#{key}", Tool).set_on(
                (key == "feed-runs") == (self._feed == "runs"))
        head = self.query_one("#feed-events", Tool)
        n = len(self.events)
        label = f"events {n}" if n else "events"
        head.update(label)
        if self._feed == "events":
            out = self.query_one("#events-out", RichLog)
            out.clear()
            for line in self.events:
                out.write(line)

    def append_event(self, line) -> None:
        """Append a live stream line even when the events tab is inactive."""
        self.events.append(line)
        if self._feed == "events" and self.is_mounted:
            self.query_one("#events-out", RichLog).write(line)
        try:
            self.query_one("#feed-events", Tool).update(
                f"events {len(self.events)}")
        except Exception:
            pass

    def _draw_commands(self) -> None:
        box = self.query_one("#journal-cmds", VerticalScroll)
        head = self.query_one("#journal-cmds-head", Static)
        box.remove_children()
        accent = palette.mode_hex(self.mode)
        dim, faint = palette.role_hex("dim"), palette.role_hex("faint")
        shown = [c for c in self.commands
                 if not self._filter or self._filter in c["name"].lower()]
        if self._filter:
            shown.sort(key=lambda c: not c["name"].lower()
                       .startswith(self._filter))
        h = Text()
        h.append("COMMANDS ", style=f"{accent} bold")
        h.append(f" {len(shown)}", style=faint)
        if self._filter:
            h.append(f"  of {len(self.commands)}", style=faint)
        head.update(h)
        if not shown:
            box.mount(Static(Text("  no matches", style=faint)))
            return
        for c in shown:
            line = "/" + c["name"] + (" " + c["arg"] if c.get("arg") else "")
            t = Text()
            t.append("/" + c["name"], style=dim)
            if c.get("arg"):
                t.append(" " + c["arg"], style=faint)
            item = CommandItem(line, t, classes="cmd-item")
            item.tooltip = c.get("help") or ""
            box.mount(item)

    def _draw_runs(self) -> None:
        box = self.query_one("#journal-list", VerticalScroll)
        head = self.query_one("#journal-runs-head", Static)
        accent = palette.mode_hex(self.mode)
        faint = palette.role_hex("faint")
        box.remove_children()
        h = Text()
        h.append("HISTORY ", style=f"{accent} bold")
        h.append(f" {len(self.runs)}", style=faint)
        head.update(h)
        if not self.runs:
            box.mount(Static(Text(
                "  empty — your first command\n  becomes commit #1",
                style=faint)))
            self.query_one("#journal-out", RichLog).clear()
            self._seen = 0
            return
        grew = len(self.runs) > self._seen
        self._seen = len(self.runs)
        if grew or not 0 <= self.pos < len(self.runs):
            self.pos = len(self.runs) - 1
        for i, run in enumerate(self.runs):
            item = RunItem(i, self._row(i, run),
                           classes="run-item" + (" on" if i == self.pos
                                                 else ""))
            run_mode = run.get("mode") or "lab"
            where = {"lab": "LAB", "work": "CORE", "mind": "AGENT",
                     "code": "CODE"}.get(run_mode, run_mode)
            item.tooltip = (f"#{i + 1}  {run.get('time') or '--:--'}  "
                            f"{run['cmd']}\n{where}"
                            + (f"  ·  block {run['scenario']}"
                               if run.get("scenario") else "")
                            + f"  ·  {len(run['lines'])} output lines"
                            + ("  ·  error" if run.get("error") else "")
                            + "\nclick — show output\n"
                              "bridge — send to another mode\n"
                              "restore — revert session state here")
            box.mount(item)
        self.show(self.pos)

    #: Single-letter mode badge per run in its own mode color.
    MODE_MARKS = {"lab": "L", "work": "K", "mind": "A", "code": "C"}

    def _row(self, i: int, run: dict) -> Text:
        """Render a history entry as a two-line git-log commit."""
        accent = palette.mode_hex(getattr(self, "mode", "lab"))
        here = i == self.pos
        failed = run.get("error")
        run_mode = run.get("mode") or "lab"
        faint = palette.role_hex("faint")
        t = Text()
        t.append("* ", style=palette.mode_hex(run_mode))
        t.append(f"#{i + 1}".ljust(4),
                 style=palette.role_hex("title") if here else faint)
        t.append(f"{run.get('time') or '--:--'}  ", style=faint)
        mark = self.MODE_MARKS.get(run_mode, "·")
        t.append(mark + " ", style=palette.mode_hex(run_mode))
        name_style = (palette.role_hex("error") if failed
                      else (palette.role_hex("title") if here
                            else palette.role_hex("dim")))
        t.append(run["cmd"][:14], style=name_style)
        if failed:
            t.append(" -", style=palette.role_hex("error"))
        dag = run.get("dag")
        t.append("\n│  ", style=faint)
        if run.get("scenario"):
            t.append(str(run["scenario"])[:14],
                     style=palette.role_hex("dim"))
            if dag is not None:
                t.append(f" · {len(dag)} ops", style=palette.role_hex("dim"))
        t.append(f" · {len(run['lines'])} ln", style=faint)
        vw = run.get("verdict")
        if vw:
            b, o = vw
            t.append(f" · {b}→{o}" if b != o else f" · {b} cyc",
                     style=palette.role_hex("dim"))
        return t

    def show(self, index: int) -> None:
        if not (0 <= index < len(self.runs)):
            return
        self.pos = index
        rec = self.runs[index]
        out = self.query_one("#journal-out", RichLog)
        out.clear()
        for line in rec["lines"]:
            out.write(line)
        try:
            self.query_one(BridgeRow).sync(self.runs, self.pos)
        except Exception:
            pass
        for item in self.query(RunItem):
            item.set_class(item.index == index, "on")
            item.update(self._row(item.index, self.runs[item.index]))

    def on_run_item_picked(self, event) -> None:
        event.stop()
        self.show(event.index)


class BridgeRow(Horizontal):
    """Action bar for sending the selected run to another mode or restoring it."""

    def __init__(self, prefix: str = "bridge", **kw) -> None:
        super().__init__(**kw)
        self.prefix = prefix
        self.runs: list[dict] = []
        self.pos = -1

    def on_mount(self) -> None:
        self.sync([], -1)

    def compose(self):
        yield Static("bridge >", classes="bridge-label")
        p = self.prefix
        yield Tool("to LAB", "@lab",
                   "open this run as the active block in LAB", id=f"{p}-lab")
        yield Tool("to AGENT", "@agent",
                   "ask AGENT about this run", id=f"{p}-agent")
        yield Tool("to CORE", "@work",
                   "open CORE with this run in context",
                   id=f"{p}-work")
        yield Tool("to CODE", "@code",
                   "open CODE with this run's source in buffer", id=f"{p}-code")
        yield Tool("restore", "@restore",
                   "restore session state from this run in place",
                   id=f"{p}-restore")
        yield Tool("~ repeat", "@repeat",
                   "re-run this command", id=f"{p}-repeat")

    def sync(self, runs: list[dict], pos: int) -> None:
        """Show only actions applicable to the selected (or latest) run."""
        self.runs = runs
        self.pos = pos if 0 <= pos < len(runs) else len(runs) - 1
        rec = self.runs[self.pos] if self.pos >= 0 else None
        has_dag = bool(rec and rec.get("dag") is not None)
        has_src = bool(rec and rec.get("code"))
        for suffix, need in (
            ("lab", has_dag),
            ("agent", has_dag),
            ("work", rec is not None),
            ("code", rec is not None),
            ("restore", has_dag or has_src),
            ("repeat", rec is not None),
        ):
            try:
                self.query_one(f"#{self.prefix}-{suffix}").display = need
            except Exception:
                pass

    def on_tool_picked(self, event) -> None:
        if event.tool != "@repeat":
            return
        event.stop()
        if 0 <= self.pos < len(self.runs):
            self.post_message(
                ConsoleJournal.RunRequested(self.runs[self.pos]["cmd"]))


# --------------------------------------------------------------------------
# Command palette ('/')
# --------------------------------------------------------------------------


class Palette(OptionList):
    """Slash-command dropdown shown while the input starts with `/`."""

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self.items: list[dict] = []
        self.can_focus = False

    def load(self, items: list[dict]) -> None:
        self.items = items
        self.clear_options()
        if not items:
            self.add_option(Option(Text("  no matching commands",
                                        style=palette.role_hex("warning"))))
            self.highlighted = None
            return
        key = palette.role_hex("accent")
        dim = palette.role_hex("dim")
        faint = palette.role_hex("faint")
        val = palette.role_hex("text")
        for it in items:
            if it.get("kind") == "header":
                row = Text()
                row.append(" ─ ", style=faint)
                row.append(it.get("help") or "", style=f"{dim} bold")
                self.add_option(Option(row, disabled=True))
                continue
            row = Text()
            name = it["name"] if it.get("kind") == "arg" else "/" + it["name"]
            row.append(f" {name:<14}", style=f"{key} bold")
            row.append(f"{(it.get('arg') or ''):<14}", style=val)
            row.append(it.get("help") or "", style=dim)
            self.add_option(Option(row))
        self.highlighted = self._first_cmd()

    # --- header-aware indexing --------------------------------------------

    def _is_header(self, index: int) -> bool:
        return (0 <= index < len(self.items)
                and self.items[index].get("kind") == "header")

    def _first_cmd(self) -> int | None:
        for i, it in enumerate(self.items):
            if it.get("kind") != "header":
                return i
        return None

    @property
    def selected(self) -> dict | None:
        if not self.items or self.highlighted is None:
            return None
        i = min(self.highlighted, len(self.items) - 1)
        while i >= 0 and self._is_header(i):
            i -= 1
        return self.items[i] if i >= 0 else None

    def step(self, delta: int) -> None:
        if not self.items:
            return
        cur = self.highlighted if self.highlighted is not None else -1
        nxt = cur + delta
        while 0 <= nxt < len(self.items) and self._is_header(nxt):
            nxt += delta
        if 0 <= nxt < len(self.items):
            self.highlighted = nxt


# --------------------------------------------------------------------------
# Input dock
# --------------------------------------------------------------------------


class NexInput(Input):
    """Single-line input that forwards navigation keys and routes multi-line
    pastes directly to the CODE buffer."""

    BINDINGS = [
        Binding("up", "nex_up", "", show=False),
        Binding("down", "nex_down", "", show=False),
        Binding("tab", "nex_tab", "", show=False),
        Binding("escape", "nex_escape", "", show=False),
    ]

    class Nav(Message):
        def __init__(self, action: str) -> None:
            super().__init__()
            self.action = action

    class Pasted(Message):
        """Multi-line text pasted into the input — routed to CODE buffer."""

        def __init__(self, text: str) -> None:
            super().__init__()
            self.text = text

    def action_nex_up(self) -> None:
        self.post_message(self.Nav("up"))

    def action_nex_down(self) -> None:
        self.post_message(self.Nav("down"))

    def action_nex_tab(self) -> None:
        self.post_message(self.Nav("tab"))

    def action_nex_escape(self) -> None:
        self.post_message(self.Nav("escape"))

    def _on_paste(self, event) -> None:
        text = event.text or ""
        if "\n" in text.strip():
            event.stop()
            event.prevent_default()
            self.post_message(self.Pasted(text))
            return
        self.insert_text_at_cursor(text)


class PromptBar(Vertical):
    """Input line with `/` command palette, history, and right-aligned hint."""

    class Submitted(Message):
        def __init__(self, value: str) -> None:
            super().__init__()
            self.value = value

    class Changed(Message):
        def __init__(self, value: str) -> None:
            super().__init__()
            self.value = value

    class Escaped(Message):
        """Esc pressed while the palette is closed."""

    def __init__(self, mode: str, placeholder: str, commands: list[dict],
                 hint: str = "", **kw) -> None:
        super().__init__(**kw)
        self.mode = mode
        self.placeholder = placeholder
        self.hint = hint
        self.commands = commands
        self.history: list[str] = []
        self._hist_pos: int | None = None

    def compose(self):
        yield Palette(id="palette")
        with Horizontal(id="prompt-field"):
            yield Static("", id="prompt-mark")
            yield NexInput(placeholder=self.placeholder, id="prompt-input")
            yield Static("", id="prompt-side")

    def on_mount(self) -> None:
        self.repaint()
        self.set_side("")
        self.query_one("#palette", Palette).display = False

    def repaint(self) -> None:
        accent = palette.mode_hex(self.mode)
        mark = Text("> ", style=f"{accent} bold")
        self.query_one("#prompt-mark", Static).update(mark)

    # --- accessors --------------------------------------------------------

    @property
    def input(self) -> NexInput:
        return self.query_one("#prompt-input", NexInput)

    @property
    def palette_widget(self) -> Palette:
        return self.query_one("#palette", Palette)

    def focus_input(self) -> None:
        self.input.focus()

    def set_side(self, text: str | Text) -> None:
        """Set right-side status text; empty restores the persistent hint."""
        if not text and self.hint:
            text = Text(self.hint, style=palette.role_hex("faint"))
        self.query_one("#prompt-side", Static).update(text)

    def set_value(self, value: str) -> None:
        inp = self.input
        inp.value = value
        inp.cursor_position = len(value)
        self._sync_palette(value)

    # --- palette ----------------------------------------------------------

    def _sync_palette(self, value: str) -> None:
        from ..ui import slash

        pal = self.palette_widget
        if value.startswith("/"):
            pal.load(slash.items_for(value, self.commands))
            pal.display = True
        else:
            pal.display = False

    def on_input_changed(self, event: Input.Changed) -> None:
        event.stop()
        self._sync_palette(event.value)
        self.post_message(self.Changed(event.value))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        from ..ui import slash

        raw = event.value.strip()
        pal = self.palette_widget
        if raw.startswith("/") and pal.display:
            raw = slash.apply_enter(raw, pal.selected)
        self.input.value = ""
        pal.display = False
        self._hist_pos = None
        if not raw:
            return
        self.history.append(raw)
        self.post_message(self.Submitted(raw))

    def tab(self) -> None:
        """Complete from the command palette (called by ModeScreen on Tab)."""
        from ..ui import slash

        pal = self.palette_widget
        if pal.display:
            sel = pal.selected
            if sel:
                self.set_value(slash.apply_tab(self.input.value, sel))
            return
        self.set_value("/")

    def on_nex_input_nav(self, event: NexInput.Nav) -> None:
        event.stop()
        from ..ui import slash

        pal = self.palette_widget
        act = event.action
        if act == "escape":
            if pal.display:
                self.set_value("")
            else:
                self.post_message(self.Escaped())
            return
        if pal.display:
            if act == "up":
                pal.step(-1)
            elif act == "down":
                pal.step(1)
            elif act == "tab":
                sel = pal.selected
                if sel:
                    self.set_value(slash.apply_tab(self.input.value, sel))
            return
        if act == "tab":
            self.set_value("/")
            return
        self._history_step(-1 if act == "up" else 1)

    def _history_step(self, delta: int) -> None:
        if not self.history:
            return
        if self._hist_pos is None:
            self._hist_pos = len(self.history)
        self._hist_pos = max(0, min(len(self.history), self._hist_pos + delta))
        value = "" if self._hist_pos >= len(self.history) else self.history[self._hist_pos]
        self.set_value(value)


# --------------------------------------------------------------------------
# Small controls
# --------------------------------------------------------------------------


class Chip(Static):
    """Clickable suggestion chip that populates and submits its value."""

    class Picked(Message):
        def __init__(self, value: str) -> None:
            super().__init__()
            self.value = value

    def __init__(self, label: str, value: str | None = None, **kw) -> None:
        super().__init__(label, **kw)
        self.value = value if value is not None else label

    def on_click(self) -> None:
        self.post_message(self.Picked(self.value))


class Tool(Static):
    """Direct-action button in a panel toolbar or tab strip."""

    class Picked(Message):
        """Tool clicked. `at` records the original event timestamp."""

        def __init__(self, tool: str, at: float = 0.0) -> None:
            super().__init__()
            self.tool = tool
            self.at = at or time.monotonic()

    class Twice(Message):
        """Tool was double-clicked."""

        def __init__(self, tool: str) -> None:
            super().__init__()
            self.tool = tool

    def __init__(self, label: str, tool: str, tooltip: str = "", **kw) -> None:
        super().__init__(label, **kw)
        self.tool = tool
        self._last_click = 0.0
        if tooltip:
            self.tooltip = tooltip

    def on_click(self, event) -> None:
        event.stop()
        double, self._last_click = double_click(event, self._last_click)
        self.post_message(self.Picked(self.tool,
                                      getattr(event, "time", 0.0)))
        if double:
            self.post_message(self.Twice(self.tool))

    def set_on(self, on: bool) -> None:
        """Toggle active highlight for toggle-style buttons."""
        self.set_class(on, "tool-on")


class PanelToolbar(ItemGrid):
    """Wrapping toolbar strip at the top of a panel."""

    def __init__(self, *tools: tuple, **kw) -> None:
        kw.setdefault("min_column_width", 14)
        super().__init__(**kw)
        # Each tuple: (label, action_id, tooltip[, css_classes]).
        self._tools = tools

    def compose(self):
        for spec in self._tools:
            label, tool, tip = spec[0], spec[1], spec[2] if len(spec) > 2 else ""
            cls = spec[3] if len(spec) > 3 else None
            yield Tool(label, tool, tip, classes=cls)

    def mark(self, tool: str, on: bool) -> None:
        """Mark a toggle tool active/inactive; unknown ids are ignored."""
        for t in self.query(Tool):
            if t.tool == tool:
                t.set_on(on)


class HintBar(Static):
    """Bottom key-hint strip shared across screens."""

    def set_hint(self, pairs: list[tuple[str, str]]) -> None:
        key = palette.role_hex("accent_soft")
        dim = palette.role_hex("faint")
        t = Text()
        for i, (k, v) in enumerate(pairs):
            if i:
                t.append("    ")
            t.append(k, style=key)
            t.append(" ")
            t.append(v, style=dim)
        self.update(t)


class PromptChip(Static):
    """Suggested question chip inside the floating AI helper bar."""

    class Picked(Message):
        def __init__(self, question: str) -> None:
            super().__init__()
            self.question = question

    def __init__(self, question: str, *args, **kw) -> None:
        super().__init__(*args, **kw)
        self.question = question

    def on_click(self, event) -> None:
        event.stop()
        self.post_message(self.Picked(self.question))


class CloseBtn(Static):
    """Clickable close control (alternative to Esc)."""

    class Picked(Message):
        pass

    def on_click(self, event) -> None:
        event.stop()
        self.post_message(self.Picked())


class PanelPrompt(Vertical):
    """Floating bottom AI helper bar for a maximized panel."""

    class Asked(Message):
        def __init__(self, question: str) -> None:
            super().__init__()
            self.question = question

    class Closed(Message):
        pass

    def __init__(self, title: str = "", chips: list[str] | None = None,
                 facts: list[str] | None = None, mode: str = "lab",
                 **kw) -> None:
        super().__init__(**kw)
        self._title = title
        self._chips = chips or []
        self.facts = facts or []
        self.mode = mode
        self._answer: Static | None = None
        self._wait: Static | None = None
        self._buf = ""

    def compose(self):
        with Horizontal(id="pp-header"):
            yield Static("", id="pp-title")
            yield CloseBtn("x", id="pp-close")
        yield VerticalScroll(id="pp-answer")
        yield ItemGrid(id="pp-chips", min_column_width=30)
        with Horizontal(id="pp-field"):
            yield Static("", id="pp-mark")
            yield Input(placeholder="ask about this panel…", id="pp-input")

    def on_mount(self) -> None:
        accent = palette.mode_hex(self.mode)
        self.styles.border_title_color = accent
        head = Text()
        head.append(f"NEX  ·  {self._title}", style=f"{accent} bold")
        self.query_one("#pp-title", Static).update(head)
        close = Text()
        close.append("x ", style=palette.role_hex("dim"))
        close.append("Esc", style=palette.role_hex("faint"))
        self.query_one("#pp-close", CloseBtn).update(close)
        self.query_one("#pp-close", CloseBtn).tooltip = "close (Esc)"
        mark = Text("> ", style=f"{accent} bold")
        self.query_one("#pp-mark", Static).update(mark)
        chips = self.query_one("#pp-chips", ItemGrid)
        for q in self._chips:
            chips.mount(PromptChip(q, "< " + q, classes="chip prompt-chip"))
        self.query_one("#pp-answer", VerticalScroll).display = False
        inp = self.query_one("#pp-input", Input)
        inp.placeholder = "ask or run a session action  ·  /clear to clear"
        inp.focus()

    # --- answer streaming -------------------------------------------------

    def start_answer(self) -> None:
        """Prepare for streaming; answer widget mounts on `first_piece()` so
        agent actions appear above the prose in chronological order."""
        log = self.query_one("#pp-answer", VerticalScroll)
        log.display = True
        self._buf = ""
        self._answer = None
        self._wait = Static(Text("…", style=palette.role_hex("faint")),
                            classes="pp-line")
        log.mount(self._wait)
        log.scroll_end(animate=False)

    def echo(self, question: str) -> None:
        log = self.query_one("#pp-answer", VerticalScroll)
        log.display = True
        t = Text()
        t.append("you  ", style=palette.role_hex("faint"))
        t.append(question, style=palette.role_hex("title"))
        log.mount(Static(t, classes="pp-line"))

    def append(self, piece: str) -> None:
        self._buf += piece
        if self._answer is not None:
            self._answer.update(Text(self._buf.strip(),
                                     style=palette.role_hex("dim")))
            self.query_one("#pp-answer", VerticalScroll).scroll_end(
                animate=False)

    def first_piece(self) -> None:
        """Replace the waiting ellipsis with the live answer widget."""
        if self._answer is not None:
            return
        log = self.query_one("#pp-answer", VerticalScroll)
        if self._wait is not None:
            self._wait.remove()
            self._wait = None
        self._answer = Static(Text("", style=palette.role_hex("dim")),
                             classes="pp-line")
        log.mount(self._answer)

    def finish(self, seconds: float) -> None:
        if self._wait is not None:
            self._wait.remove()
            self._wait = None
        log = self.query_one("#pp-answer", VerticalScroll)
        t = Text()
        t.append(f"{seconds:.0f} s  ·  {len(self.facts)} facts  ·  "
                 "computed by core, explained by model",
                 style=palette.role_hex("faint"))
        log.mount(Static(t, classes="pp-line"))
        log.scroll_end(animate=False)

    def note(self, text: str, role: str = "dim") -> None:
        if self._wait is not None:
            self._wait.remove()
            self._wait = None
        log = self.query_one("#pp-answer", VerticalScroll)
        log.display = True
        log.mount(Static(Text(text, style=palette.role_hex(role)),
                         classes="pp-line"))

    def action(self, note: str) -> None:
        """Display an executed agent action above the waiting indicator."""
        log = self.query_one("#pp-answer", VerticalScroll)
        log.display = True
        t = Text()
        t.append("* ", style=palette.role_hex("accent"))
        t.append(note, style=palette.role_hex("accent_soft"))
        line = Static(t, classes="pp-line")
        if self._wait is not None and self._wait.is_mounted:
            log.mount(line, before=self._wait)
        else:
            log.mount(line)
        log.scroll_end(animate=False)

    def clear(self) -> None:
        """`/clear` — clear the conversation log while keeping facts and chips."""
        log = self.query_one("#pp-answer", VerticalScroll)
        log.remove_children()
        log.display = False
        self._answer = None
        self._wait = None
        self._buf = ""

    # --- input ------------------------------------------------------------

    def on_input_submitted(self, event) -> None:
        event.stop()
        q = event.value.strip()
        event.input.value = ""
        if not q:
            return
        if q.lstrip("/").lower() in ("clear", "cls"):
            self.clear()
            return
        self.post_message(self.Asked(q))

    def on_prompt_chip_picked(self, event) -> None:
        event.stop()
        self.post_message(self.Asked(event.question))

    def on_close_btn_picked(self, event) -> None:
        event.stop()
        self.post_message(self.Closed())


# --------------------------------------------------------------------------
# Side chat for a maximized panel
# --------------------------------------------------------------------------


class PanelChat(Vertical):
    """Focused side chat grounded in a single maximized panel's facts."""

    class Asked(Message):
        def __init__(self, question: str) -> None:
            super().__init__()
            self.question = question

    def __init__(self, title: str = "", facts: list[str] | None = None,
                 **kw) -> None:
        super().__init__(**kw)
        self._panel_title = title
        self._facts = list(facts or [])
        self._body = Text()

    def compose(self):
        yield Static(id="pchat-log")
        yield Input(placeholder="ask about the facts above…", id="pchat-input")

    def on_mount(self) -> None:
        self._greet()
        self.query_one("#pchat-input", Input).focus()

    def _greet(self) -> None:
        """Show the exact facts passed to the model upfront for transparency."""
        t = Text()
        t.append("NEX on panel ", style=palette.role_hex("dim"))
        t.append(self._panel_title + "\n\n", style=palette.role_hex("title"))
        t.append(f"model sees exactly ({len(self._facts)}):\n",
                 style=palette.role_hex("dim"))
        for f in self._facts:
            line = " ".join(f.split())
            if len(line) > 58:
                line = line[:57] + "…"
            t.append("  · " + line + "\n", style=palette.role_hex("faint"))
        t.append("\nask in plain language; Esc — restore panel",
                 style=palette.role_hex("faint"))
        self._log().update(t)
        self._body = t.copy()

    def on_input_submitted(self, event) -> None:
        event.stop()
        text = event.value.strip()
        event.input.value = ""
        if text:
            self.post_message(self.Asked(text))

    # --- transcript -------------------------------------------------------

    def _log(self) -> Static:
        return self.query_one("#pchat-log", Static)

    def echo(self, question: str) -> None:
        self._body.append("\n\n> ", style=palette.role_hex("accent"))
        self._body.append(question, style=palette.role_hex("title"))
        self._body.append("\n")
        self._log().update(self._body)

    def note(self, text: str, role: str = "faint") -> None:
        self._body.append("\n" + text, style=palette.role_hex(role))
        self._log().update(self._body)

    def append(self, piece: str) -> None:
        self._body.append(piece)
        self._log().update(self._body)

    # --- answer state -----------------------------------------------------

    answering = False

    def start_answer(self) -> None:
        self.answering = True
        self._answer_started = False
        self._think_at = len(self._body)
        self.note("thinking…", "warning")

    def first_piece(self) -> None:
        """First streamed chunk: clear 'thinking…' and start appending."""
        if self._answer_started:
            return
        self._answer_started = True
        self._body = self._body[:self._think_at]
        self._body.append("\n")
        self._log().update(self._body)

    def finish(self, seconds: float) -> None:
        self.answering = False
        self.note(f"\n({seconds:.1f} s)", "faint")
