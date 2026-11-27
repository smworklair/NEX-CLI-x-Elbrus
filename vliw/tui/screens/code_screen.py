"""CODE — e2k assembly editor that overlays scheduling directly on source.

The editor parses the buffer live on every keystroke to answer three questions:
  * **which cycle each line issues in** — left gutter (`c7 ,0`);
  * **machine hazards** — `^` marker and ISSUES pane (illegal channel, busy
    port, or read-before-latency hazard);
  * **recoverable slack** — after F5, the gutter shows `c7→1` for where exact
    search places the same op.

Expensive passes (exact search, doctor) run only on F5. The active buffer is
stored in `session.code_text` so `/code run`, `/code save`, and multi-line
pastes from other modes share it.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

from rich.segment import Segment
from rich.style import Style as RichStyle
from rich.text import Text
from textual import work
from textual.binding import Binding
from textual.containers import Horizontal, ItemGrid, Vertical, VerticalScroll
from textual.message import Message
from textual.strip import Strip
from textual.widgets import DataTable, Input, RichLog, Static, TextArea
from textual.widgets.text_area import TextAreaTheme

from ...core import asm_parser, doctor
from .. import palette
from ..widgets import (BridgeRow, Chip, Console, ConsoleJournal, HintBar,
                       PanelPrompt, PromptBar, Tool, double_click, plural)
from .base import ModeScreen

#: Example catalog stored under `examples/code/*.s` and loaded via `/example <name>`.
EXAMPLES = [
    ("slots", "idle slots",
     "eight multiplies one per cycle instead of four in one"),
    ("divport", "divider monopoly",
     "while sole ,5 is busy, five channels sit idle"),
    ("loads", "loads on one channel",
     "four independent ldw queued unnecessarily"),
    ("latency", "chain bound",
     "no slack left — and that is the right answer, not silence"),
    ("broken", "hazards the assembler misses",
     "illegal channel, busy port, and read-before-ready"),
]

#: Fallback buffer when `examples/` is missing so the editor still opens cleanly.
FALLBACK = """\
! e2k assembly: { } is one wide bundle, ,N is the channel.
! Edit and press F5.
{
  muls,0 %r10, %r11, %r20
  adds,1 %r12, %r13, %r21
}
"""


def examples_dir():
    from pathlib import Path

    return Path(__file__).resolve().parents[3] / "examples" / "code"


def example_text(name: str) -> str | None:
    """Return example source by name, or None if not found."""
    try:
        return (examples_dir() / f"{name}.s").read_text(encoding="utf-8")
    except OSError:
        return None


def example_title(name: str) -> str:
    for key, title, _ in EXAMPLES:
        if key == name:
            return title
    return name


_FILE_LINE_RE = re.compile(
    r"(?:line\s*(\d+)|(\d+)\s*line)", re.I)
"""Line number referenced in a question: e.g. 'line 12'."""


def excerpt_center(question: str, cursor: int, n_lines: int) -> int:
    """Center line for file window: from question, else cursor. Always in [1, n]."""
    m = _FILE_LINE_RE.search(question or "")
    if m:
        try:
            num = next(int(g) for g in m.groups() if g is not None)
            return min(max(num, 1), max(n_lines, 1))
        except (ValueError, StopIteration):
            pass
    return min(max(cursor, 1), max(n_lines, 1))


def file_excerpt(name: str, text: str, center: int, window: int = 15) -> list[str]:
    """Numbered window of an open non-asm file for the agent.

    Pure function (testable without UI). Lines are truncated to 160 chars;
    the center line is marked with `>>>`.
    """
    lines = text.splitlines()
    n = len(lines)
    if not n or not any(s.strip() for s in lines):
        return [f"open file {name}: empty"]
    center = min(max(center, 1), n)
    lo = max(1, center - window)
    hi = min(n, center + window)
    out = [f"open file {name} (not e2k, not parsed), total lines: {n}, "
           f"showing {lo}–{hi}"]
    width = len(str(hi))
    for i in range(lo, hi + 1):
        mark = ">>>" if i == center else "   "
        out.append(f"{mark} {str(i).rjust(width)}: {lines[i - 1][:160]}")
    return out


CONT = "─"        # cell occupied by multi-cycle op continuation
                  # (extends right when grid is horizontal; see _fill_grid)
EMPTY = "·"


# --- e2k assembly syntax highlighting ---

_COMMENT_RE = re.compile(r"(//|!|;)")
_MNEM_RE = re.compile(r"(?P<mn>[a-z][a-z0-9_]*)(?P<ch>,\d+)?")
_REG_RE = re.compile(r"%[a-z]+\d*(\[\d+\])?")
_NUM_RE = re.compile(r"(?<![\w%])\d+")

#: Non-scheduled directives (`nop 4`, `return`) skipped by both parser and highlighter.
META = {"nop", "return", "ct", "ibranch", "call", "disp"}


def _line_tokens(line: str) -> list[tuple[int, int, str]]:
    """Highlight spans for a single line: [(start, end, style_name)]."""
    out: list[tuple[int, int, str]] = []

    m = _COMMENT_RE.search(line)
    code = line[:m.start()] if m else line
    if m:
        out.append((m.start(), len(line), "comment"))

    for i, ch in enumerate(code):
        if ch in "{}":
            out.append((i, i + 1, "brace"))

    body = code.strip()
    if body.startswith("."):
        out.append((code.index("."), len(code.rstrip()), "meta"))
        return out
    if body.endswith(":") and " " not in body:
        out.append((len(code) - len(code.lstrip()), len(code.rstrip()), "label"))
        return out

    for rm in _REG_RE.finditer(code):
        out.append((rm.start(), rm.end(), "reg"))
    for nm in _NUM_RE.finditer(code):
        out.append((nm.start(), nm.end(), "num"))

    # Mnemonic is the first word after `{`/spaces; applied after registers/numbers.
    tail = code.lstrip(" \t{")
    if tail:
        off = len(code) - len(tail)
        mm = _MNEM_RE.match(tail)
        if mm:
            mn = mm.group("mn").lower()
            if mn in META:
                name = "meta"
            else:
                cls = asm_parser.MNEMONICS.get(mn)
                name = f"op.{cls}" if cls else "unknown"
            out.append((off + mm.start("mn"), off + mm.end("mn"), name))
            if mm.group("ch"):
                out.append((off + mm.start("ch"), off + mm.end("ch"), "channel"))
    return out


def _asm_theme() -> TextAreaTheme:
    """Build editor theme from project palette so `/theme` recolors code too.

    Operations are colored by their execution class (div, mul, load, ...) to
    match the schedule grid and legend.
    """
    def st(role: str, **kw) -> RichStyle:
        return RichStyle(color=palette.role_hex(role), **kw)

    styles = {
        "comment": st("faint", italic=True),
        "brace": st("border"),
        "meta": st("faint"),
        "label": st("title", bold=True),
        # Channel suffix is the key e2k scheduling token (port assignment).
        "channel": st("accent", bold=True),
        "reg": st("dim"),
        "num": st("accent2_soft"),
        "unknown": st("warning", underline=True),
    }
    for op in ("ADD", "SUB", "MUL", "DIV", "LOAD", "STORE", "SHL", "AND"):
        color = palette.op_hex(op)
        styles[f"op.{op}"] = RichStyle(color=color, bold=True)

    return TextAreaTheme(
        name="nex-asm",
        base_style=RichStyle(color=palette.role_hex("text")),
        gutter_style=RichStyle(color=palette.role_hex("faint")),
        cursor_style=RichStyle(color=palette.SURFACES["canvas"],
                               bgcolor=palette.role_hex("accent2")),
        cursor_line_gutter_style=RichStyle(color=palette.role_hex("accent2")),
        bracket_matching_style=RichStyle(bgcolor=palette.SURFACES["raised"],
                                         bold=True),
        selection_style=RichStyle(bgcolor=palette.SURFACES["raised"]),
        syntax_styles=styles,
    )


class AsmArea(TextArea):
    """Assembly editor with syntax highlighting and live schedule gutter."""

    #: Draw line numbers ourselves inside the widened schedule gutter.
    MIN_MARK_W = 3
    MAX_MARK_W = 10

    #: Gutter action column: `>` on the cursor line runs the buffer (F5).
    RUN_W = 2

    #: Class-level defaults needed because `TextArea.__init__` queries `gutter_width`.
    _marks: dict[int, tuple[str, RichStyle]] = {}

    #: Whether the active buffer can be scheduled (hides run arrow on notes/scripts).
    runnable: bool = True

    def __init__(self, **kw) -> None:
        kw.setdefault("soft_wrap", False)
        kw.setdefault("tab_behavior", "indent")
        kw.setdefault("show_line_numbers", False)
        super().__init__(**kw)
        # 0-based line -> (label, style)
        self._marks: dict[int, tuple[str, RichStyle]] = {}
        self.register_theme(_asm_theme())
        self.theme = "nex-asm"

    # --- highlighting -----------------------------------------------------

    def _build_highlight_map(self) -> None:
        """Custom highlighting instead of tree-sitter; runs on every edit."""
        self._line_cache.clear()
        highlights = self._highlights
        highlights.clear()
        for row, line in enumerate(self.document.lines):
            tokens = _line_tokens(line)
            if not tokens:
                continue
            # Highlight spans use UTF-8 byte offsets so non-ASCII comments stay aligned.
            prefix = [0] * (len(line) + 1)
            total = 0
            for i, ch in enumerate(line):
                prefix[i] = total
                total += len(ch.encode("utf-8"))
            prefix[len(line)] = total
            for start, end, name in tokens:
                highlights[row].append((prefix[min(start, len(line))],
                                        prefix[min(end, len(line))], name))

    def refresh_theme(self) -> None:
        """Reload editor colors after `/theme`."""
        self.register_theme(_asm_theme())
        self._set_theme("nex-asm")
        self._line_cache.clear()
        self.refresh()

    # --- schedule gutter --------------------------------------------------

    @property
    def NUM_W(self) -> int:
        return len(str(max(1, self.document.line_count))) + 2

    @property
    def MARK_W(self) -> int:
        if not self._marks:
            return 0
        widest = max(len(text) for text, _ in self._marks.values())
        return min(self.MAX_MARK_W, max(self.MIN_MARK_W, widest + 1))

    @property
    def BADGE_W(self) -> int:
        return self.NUM_W + self.MARK_W

    def set_marks(self, marks: dict[int, tuple[str, RichStyle]]) -> None:
        self._marks = marks
        self._line_cache.clear()
        # layout=True so gutter width changes reflow editor text width.
        self.refresh(layout=True)

    @property
    def gutter_width(self) -> int:
        # Gutter stays fixed during horizontal scroll; TextArea deducts its width automatically.
        return self.RUN_W + self.BADGE_W

    class RunHere(Message):
        """Run arrow in the gutter was clicked."""

    def on_click(self, event) -> None:
        """Click on the gutter run arrow runs the buffer; other gutter clicks edit."""
        if event.x < self.RUN_W:
            event.stop()
            if self.runnable:
                self.post_message(self.RunHere())

    def render_line(self, y: int) -> Strip:
        strip = super().render_line(y)
        row = self.scroll_offset.y + y
        if row >= self.document.line_count:
            return strip
        badge, style = self._marks.get(row, ("", None))
        if style is None:
            style = RichStyle(color=palette.role_hex("faint"))
        cursor = row == self.cursor_location[0]
        num_style = RichStyle(color=palette.role_hex(
            "accent2" if cursor else "faint"), bold=cursor)
        mark_w = self.MARK_W
        head = Strip([
            # Show run arrow only on the cursor line.
            Segment("> " if (cursor and self.runnable) else "  ",
                    RichStyle(color=palette.role_hex("success"), bold=True)
                    if cursor else num_style),
            Segment(f"{row + 1:>{self.NUM_W - 1}} ", num_style),
            Segment((f"{badge:>{mark_w - 1}} " if badge else " " * mark_w)
                    if mark_w else "", style),
        ], cell_length=self.gutter_width)
        # Reuse parent `_render_line` for syntax, cursor, and selection rendering.
        return Strip.join([head, strip])

    # --- cursor (tracked via TextArea.SelectionChanged) -------------------

    def goto_line(self, line: int) -> None:
        """Move cursor to 1-based line and scroll it into view."""
        row = max(0, min(line - 1, self.document.line_count - 1))
        self.move_cursor((row, 0))
        self.scroll_cursor_visible(center=True)


class SuggestItem(Static):
    """Single completion item in the typing popup."""

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


class Suggest(Vertical):
    """Machine-aware completion popup for e2k assembly.

    Suggests only legal channels after a mnemonic (marking channels busy in the
    current bundle) and buffer-defined registers with their ready cycles.
    """

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self.items: list[tuple[str, str, str, str]] = []
        self.index = 0

    def show(self, items: list[tuple[str, str, str, str]]) -> None:
        """items: (insert_text, label, detail, color_role)."""
        self.items = items[:8]
        self.index = 0
        self.remove_children()
        if not self.items:
            self.display = False
            return
        # Size description column dynamically to the widest label in this popup.
        pad = min(34, max(len(label) for _i, label, _n, _r in self.items) + 2)
        rows = []
        for i, (_ins, label, note, role) in enumerate(self.items):
            rows.append(SuggestItem(i, self._row(label, note, role, pad),
                                    classes="suggest-item"))
        self.mount(*rows)
        self.display = True
        self.call_after_refresh(self._mark)

    def _row(self, label: str, note: str, role: str, pad: int = 10) -> Text:
        t = Text()
        t.append(" " + label.ljust(pad), style=palette.role_hex(role) + " bold")
        t.append(note, style=palette.role_hex("dim"))
        return t

    def _mark(self) -> None:
        for i, row in enumerate(self.query(SuggestItem)):
            row.set_class(i == self.index, "suggest-on")

    def step(self, delta: int) -> None:
        if not self.items:
            return
        self.index = (self.index + delta) % len(self.items)
        self._mark()

    def current(self) -> str:
        return self.items[self.index][0] if self.items else ""

    def hide(self) -> None:
        self.display = False
        self.items = []


class LineChip(Static):
    """Cursor readout in the status bar; clicking opens the INSPECT tab."""

    class Picked(Message):
        pass

    def on_click(self, event) -> None:
        event.stop()
        self.post_message(self.Picked())


class DrawerChip(Static):
    """Status bar button that opens a specific bottom dock tab."""

    class Picked(Message):
        def __init__(self, target: str) -> None:
            super().__init__()
            self.target = target

    def __init__(self, target: str, label: str = "", tip: str = "",
                 **kw) -> None:
        super().__init__(label, **kw)
        self.target = target
        self._label = label
        if tip:
            self.tooltip = tip

    def set_label(self, label: str) -> None:
        self._label = label
        self.update(label)

    def on_click(self, event) -> None:
        event.stop()
        self.post_message(self.Picked(self.target))


class FileStrip(Static):
    """Open buffer tab strip: click switches, x closes, double-click maximizes."""

    class Picked(Message):
        def __init__(self, index: int) -> None:
            super().__init__()
            self.index = index

    class Closed(Message):
        def __init__(self, index: int) -> None:
            super().__init__()
            self.index = index

    class Toggled(Message):
        """Panel toggle button on the right end of the tab strip was clicked."""

        def __init__(self, which: str) -> None:
            super().__init__()
            self.which = which

    class Maximized(Message):
        """Double-click on a file tab toggles full-screen editor mode."""

    def __init__(self, *args, **kw) -> None:
        super().__init__(*args, **kw)
        #: [(start, end, tab_index, has_close_x)] in character cells.
        self.spans: list[tuple[int, int, int, bool]] = []
        #: [(start, end, panel_key)] — right-side panel toggle buttons.
        self.toggles: list[tuple[int, int, str]] = []
        self._last_click = 0.0

    def on_click(self, event) -> None:
        # Check right-side panel buttons before tab hit zones.
        for start, end, which in self.toggles:
            if start <= event.x < end:
                event.stop()
                self.post_message(self.Toggled(which))
                return
        double, self._last_click = double_click(event, self._last_click)

        for start, end, index, closable in self.spans:
            if not (start <= event.x < end):
                continue
            event.stop()
            # Close `x` occupies the last two cells of a tab.
            if closable and event.x >= end - 2:
                self.post_message(self.Closed(index))
            elif double:
                self.post_message(self.Maximized())
            else:
                self.post_message(self.Picked(index))
            return


class SideItem(Static):
    """Explorer list row: click opens file/dir, trailing x deletes file."""

    class Picked(Message):
        def __init__(self, key: str, at_x: int = -1) -> None:
            super().__init__()
            self.key = key
            self.at_x = at_x

    def __init__(self, key: str, *args, **kw) -> None:
        super().__init__(*args, **kw)
        self.key = key

    def on_click(self, event) -> None:
        event.stop()
        self.post_message(self.Picked(self.key, getattr(event, "x", -1)))


class DockSplitter(Static):
    """Draggable hairline splitter between editor and bottom dock."""

    class Grabbed(Message):
        """Drag started on the dock splitter."""

    class Dragged(Message):
        """Splitter dragged vertically by `delta` rows."""

        def __init__(self, delta: int) -> None:
            super().__init__()
            self.delta = delta

    def __init__(self, *args, **kw) -> None:
        super().__init__(*args, **kw)
        self._from = 0

    def on_mount(self) -> None:
        # Explicit tooltip because terminals cannot change mouse cursor shape.
        self.tooltip = ("drag — resize bottom dock\n"
                        "F11 — maximize dock\n"
                        "F12 — hide dock")

    def render(self):
        # Thin hairline with centered grip handle.
        w = self.size.width or 0
        if w < 9:
            return Text("─" * w, style=palette.role_hex("border"))
        left = (w - 3) // 2
        t = Text()
        t.append("─" * left, style=palette.role_hex("border"))
        t.append("───", style=palette.role_hex("dim"))
        t.append("─" * (w - left - 3), style=palette.role_hex("border"))
        return t

    def on_mouse_down(self, event) -> None:
        event.stop()
        self._from = event.screen_y
        self.capture_mouse()
        # Signal drag start separately because MouseUp is consumed while captured.
        self.post_message(self.Grabbed())

    def on_mouse_move(self, event) -> None:
        if self.app.mouse_captured is not self:
            return
        event.stop()
        self.post_message(self.Dragged(event.screen_y - self._from))

    def on_mouse_up(self, event) -> None:
        if self.app.mouse_captured is self:
            event.stop()
            self.release_mouse()


class DockTabs(Horizontal):
    """Bottom dock tab strip; double-click maximizes/restores the dock."""

    class Zoom(Message):
        pass

    def __init__(self, *children, **kw) -> None:
        super().__init__(*children, **kw)
        self._last_click = 0.0

    def on_click(self, event) -> None:
        double, self._last_click = double_click(event, self._last_click)
        if double:
            event.stop()
            self.post_message(self.Zoom())


class LintItem(Static):
    """Issue row; clicking jumps the editor cursor to that source line."""

    class Picked(Message):
        def __init__(self, line: int) -> None:
            super().__init__()
            self.line = line

    def __init__(self, line: int, *args, **kw) -> None:
        super().__init__(*args, **kw)
        self.line = line

    def on_click(self, event) -> None:
        event.stop()
        self.post_message(self.Picked(self.line))


# --- CodeScreen -------------------------------------------------------


class CodeScreen(ModeScreen):
    mode = "code"
    mode_title = "CODE"
    mode_subtitle = "editor"
    placeholder = "/doctor   ·   /code save my.s   ·   /example"
    hint = "'/' catalog   ·   ↑ history"
    # Left sidebar toggles via ^B; hint bar stays visible so F5 stays discoverable.
    SIDE_ID = "#code-side"
    TIPS_ID = ""

    BINDINGS = ModeScreen.BINDINGS + [
        Binding("f5", "run_code", "run", priority=True),
        ("ctrl+s", "save_code", "save"),
        # F6 sits next to F5 (run then rewrite); ^R is reserved for ConsoleJournal repeat.
        Binding("f6", "rewrite", "rewrite via oracle", priority=True),
        # F12 toggles bottom dock visibility.
        Binding("f12", "toggle_drawer", "bottom dock", priority=True),
        # F11 toggles full-screen dock zoom (paired with F12).
        Binding("f11", "zoom_dock", "maximize dock", priority=True),
        Binding("f2", "rename_buffer", "rename tab", priority=True),
        # ^P opens OUTPUT command prompt without stealing `/` or `:` from assembly.
        Binding("ctrl+p", "command", "command", priority=True),
        # `/` stays a quick command trigger when focus is outside text inputs.
        Binding("slash", "slash", "command", priority=True),
        # ^G opens the contextual AGENT dock tab.
        Binding("ctrl+g", "explain", "explain", priority=True),
        # ^E toggles the right-side file explorer.
        Binding("ctrl+e", "toggle_explorer", "explorer", priority=True),
        # Popup arrow/Enter bindings activate via `check_action` only while popup is visible.
        Binding("up", "suggest_up", "up", priority=True),
        Binding("down", "suggest_down", "down", priority=True),
        Binding("enter", "suggest_take", "insert", priority=True),
    ]

    #: Actions active only while the completion popup is open.
    SUGGEST_ACTIONS = ("suggest_up", "suggest_down", "suggest_take")

    #: Bottom dock tabs: key -> (label, body_id, button_id, ai_topic).
    TABS = {
        "term": ("output", "#dock-term", "#tab-term", "console"),
        "lint": ("issues", "#dock-lint", "#tab-lint", "lint"),
        "line": ("inspect", "#dock-line", "#tab-line", "code"),
        "sched": ("schedule", "#dock-sched", "#tab-sched", "sched"),
        "core": ("core", "#dock-core", "#tab-core", "core"),
        "agent": ("agent", "#dock-agent", "#tab-agent", "code"),
    }

    #: Assembly snippet templates inserted via `/` using fresh unused registers.
    SNIPPETS = (
        ("bundle", "empty wide bundle — one cycle", "bundle"),
        ("par4", "four multiplies in one cycle: ,0 ,1 ,3 ,4", "par"),
        ("queue", "same work on one channel — unnecessary queue",
         "queue"),
        ("chain", "dependent chain: stalled by multiply latency",
         "chain"),
        ("div", "division: sole channel ,5 and its latency", "div"),
        ("load", "load and consumer: stalled by load latency", "load"),
        ("store", "store — channels ,2 and ,5 only", "store"),
    )

    def _free_regs(self, count: int) -> list[str]:
        """Allocate fresh register names not already used in the buffer."""
        busy: set[str] = set()
        if self.parsed is not None:
            for op in self.parsed.ops:
                if op.dst:
                    busy.add(op.dst.lower())
                for src in getattr(op, "srcs", ()) or ():
                    busy.add(str(src).lower())
        # Also scan raw text in case the buffer did not parse.
        text = self.query_one("#code-edit", AsmArea).text.lower()
        out: list[str] = []
        n = 0
        while len(out) < count and n < 200:
            name = f"r{n}"
            n += 1
            if name in busy or f"%{name}," in text or f"%{name} " in text:
                continue
            out.append(name)
        return out or [f"r{i}" for i in range(count)]

    def _pause_for(self, op_class: str) -> int:
        """Return op latency from the active machine model."""
        return max(0, self.app.session.model().latency(op_class) - 1)

    def _snippet_text(self, kind: str) -> str:
        """Build an assembly snippet tailored to the buffer and machine model."""
        model = self.app.session.model()

        def bundle(*lines: str) -> str:
            return "{\n" + "".join(f"  {l}\n" for l in lines) + "}\n"

        if kind == "bundle":
            return "{\n  \n}\n"

        if kind == "par":
            # One legal multiply channel per operation.
            chans = model.channels_for("MUL")[:4]
            regs = self._free_regs(len(chans) * 3)
            lines = []
            for i, ch in enumerate(chans):
                a, b, d = regs[i * 3:i * 3 + 3]
                lines.append(f"muls,{ch} %{a}, %{b}, %{d}")
            return bundle(*lines)

        if kind == "queue":
            ch = model.channels_for("MUL")[0]
            regs = self._free_regs(12)
            out = []
            for i in range(4):
                a, b, d = regs[i * 3:i * 3 + 3]
                out.append(bundle(f"muls,{ch} %{a}, %{b}, %{d}"))
            return "".join(out)

        if kind == "chain":
            ch = model.channels_for("MUL")[0]
            a, b, d, e, f = self._free_regs(5)
            pause = self._pause_for("MUL")
            first = bundle(f"nop {pause}", f"muls,{ch} %{a}, %{b}, %{d}") \
                if pause else bundle(f"muls,{ch} %{a}, %{b}, %{d}")
            return first + bundle(f"muls,{ch} %{d}, %{e}, %{f}")

        if kind == "div":
            ch = model.channels_for("DIV")[0]
            add_ch = model.channels_for("ADD")[0]
            a, b, d, e, f = self._free_regs(5)
            pause = self._pause_for("DIV")
            first = bundle(f"nop {pause}", f"sdivs,{ch} %{a}, %{b}, %{d}") \
                if pause else bundle(f"sdivs,{ch} %{a}, %{b}, %{d}")
            return first + bundle(f"adds,{add_ch} %{d}, %{e}, %{f}")

        if kind == "load":
            ch = model.channels_for("LOAD")[0]
            add_ch = model.channels_for("ADD")[0]
            a, d, e, f = self._free_regs(4)
            pause = self._pause_for("LOAD")
            first = bundle(f"nop {pause}", f"ldw,{ch} %{a}, %{d}") \
                if pause else bundle(f"ldw,{ch} %{a}, %{d}")
            return first + bundle(f"adds,{add_ch} %{d}, %{e}, %{f}")

        if kind == "store":
            ch = model.channels_for("STORE")[0]
            a, b = self._free_regs(2)
            return bundle(f"stw,{ch} %{a}, %{b}")
        return ""

    #: New file types creatable from the sidebar: (ext, label, template, note).
    FILE_KINDS = (
        ("s", "e2k block", "block",
         "! new block — F5 to run, '/' for commands\n"),
        ("md", "note", "note",
         "# notes and experiments\n"),
    )

    #: File extensions parsed as e2k assembly.
    ASM_SUFFIXES = (".s", ".asm")

    #: Default dock height per tab until manually resized.
    TAB_HEIGHT = {
        "sched": 8,    # tab bar, cycle header, six channels
        "line": 15,    # cursor cycle breakdown and cycle catalog
        "lint": 10,    # issues with hints
        "term": 15,    # command output and input line
        "core": 15,    # interpreter console and names sidebar
        "agent": 12,   # dialog transcript, chips, and question input
    }

    #: Tooltips for bottom dock tab buttons.
    TAB_TIPS = {
        "sched": "where ops landed: channels as rows, cycles as columns",
        "line": "cycle under cursor, dependency chain, and buffer cycle catalog",
        "lint": "machine hazards and where cycles are lost",
        "term": "command results, session history, and slash commands",
        "core": "interpreter console: build a graph without writing "
                "assembly",
        "agent": "full agent dialog: 2xclick to maximize",
    }

    #: Widgets kept visible during Textual maximize.
    ALLOW_IN_MAXIMIZED_VIEW = ("PanelChat, PanelPrompt, PromptBar, HintBar, "
                               "Footer, TopBar, #code-foot, #code-dock")

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        # Left catalog starts closed (^B toggles).
        self.side_shown = False
        # Live parse results (recomputed on every edit).
        self.parsed = None
        self.local_dag = None
        self.comp = None              # schedule reconstructed from source
        self.comp_problem = None      # (title, detail) when source schedule is illegal
        self.unknown_share = 0.0      # fraction of ops unknown to machine model
        self.problems: list = []
        # Exact-search and doctor results (computed on F5).
        self.base = None
        self.orc = None
        self.met = None
        self.findings: list = []
        self.findings_from = "buffer"
        self.run_text = ""            # buffer text at last F5 run
        self._grid_cells: dict[tuple[str, int, int], int] = {}
        self._sched_left = None       # schedule currently shown in the grid
        self._sched_which = "src"
        self._lint_lines: list[int] = []
        self._code_expanded = False
        self._sched_expanded = False
        self._lint_expanded = False
        self._console_expanded = False
        self._debounce = None
        self.sched_view = "src"     # active schedule view ('source' or 'oracle')
        self._cursor_line = 0
        self._example = ""          # active example name if loaded from catalog
        # Open buffer tabs: [{name, path, text, example}] and active index.
        self.files: list[dict] = []
        self.file_i = 0
        # Bottom dock starts open on the schedule tab.
        self.drawer_open = True
        #: Saved layout state before editor full-screen zoom; None if not zoomed.
        self._maximized: tuple[bool, bool] | None = None
        self.drawer_tab = "sched"   # sched | line | lint | term
        # Dock zoom state: '' or 'dock'.
        self.zoom = ""
        #: User-dragged dock height in rows (persisted for session); None uses default.
        self.dock_h: int | None = None
        #: Dock height at drag start.
        self._drag_h: int | None = None
        #: Agent action trace for the maximized AGENT tab.
        self.ai_actions: list[str] = []
        #: Right-side file explorer state (open flag, cwd, search query).
        self.explorer_shown = False
        #: User's intended sidebar visibility independent of narrow-window auto-hide.
        self._want_explorer = False
        self._want_side = False
        self.explorer_dir = Path.cwd()
        self.explorer_query = ""
        #: Highlighted row index in explorer list.
        self._explorer_at = 0
        #: Recently visited explorer directories.
        self._explorer_hist: list[str] = []
        #: Debounce timer handle for explorer search.
        self._find_timer = None
        #: Truncation reason if explorer search hit a limit.
        self._find_cut = ""
        #: Dock tab that was active before switching to AGENT.
        self._prev_tab = ""
        #: Topic snapshot captured when opening AGENT.
        self._ai_from = "code"
        #: Pending switch to oracle grid view once F5 completes.
        self._want_orc = False
        #: Explorer file pending inline delete confirmation.
        self._to_delete: str = ""


    # --- layout -----------------------------------------------------------

    def compose(self):
        # Single top bar: mark, open file tabs, right-aligned metrics, and panel toggles.
        yield FileStrip(id="code-head")
        with Horizontal(id="code-body"):
            # Left files/examples sidebar (closed by default; ^B toggles).
            with Vertical(id="code-side"):
                # Fixed sidebar header above scrollable list.
                yield Static(id="side-head", classes="panel-head")
                yield VerticalScroll(id="code-side-list", can_focus=False)
            yield AsmArea(id="code-edit")
            # Welcome overlay shown on empty buffers until first e2k op is typed.
            yield Static(id="code-hello")
            # Right file explorer sidebar (closed by default; ^E toggles).
            with Vertical(id="code-explorer"):
                yield Static(id="explorer-head", classes="panel-head")
                yield Horizontal(Static(" / ", id="explorer-mark"),
                                 Input(placeholder="file or folder name",
                                       id="explorer-find"),
                                 id="explorer-search")
                # can_focus=False so explorer list rebuilds never steal focus from search input.
                yield VerticalScroll(id="explorer-list", can_focus=False)

            # Agent lives in the bottom dock tab rather than a duplicate right column.

        # --- bottom dock (draggable splitter above tab bar) -------------------
        yield DockSplitter(id="dock-split")

        with Vertical(id="code-dock"):
            with DockTabs(id="dock-tabs"):
                for key, (label, _box, tool_id, _topic) in self.TABS.items():
                    yield Tool(label, f"dock-{key}", self.TAB_TIPS[key],
                               id=tool_id.lstrip("#"))
                # Live per-tab summary on the right of the dock tab strip.
                yield Static(id="dock-note")
                # Divider between live summary and schedule view toggle.
                yield Static("│", id="dock-sep")
                # Schedule view toggle buttons on the right of the dock tab strip.
                yield Tool("as written", "sched-src",
                           "schedule parsed from the buffer", id="tab-src")
                yield Tool("oracle", "sched-orc",
                           "exact-search schedule (F5)", id="tab-orc")

            yield Horizontal(
                # cell_padding=0 so all six channels fit without clipping channel ,5.
                Vertical(DataTable(id="code-grid", cursor_type="cell",
                                   zebra_stripes=False, cell_padding=0,
                                   fixed_columns=1),
                         id="code-grid-wrap"),
                Vertical(Static(id="code-grid-orc-head"),
                         DataTable(id="code-grid-orc", cursor_type="cell",
                                   zebra_stripes=False, cell_padding=0,
                                   fixed_columns=1),
                         id="code-grid-orc-wrap"),
                # Grid breakdown sidebar shown only when dock is maximized (F11).
                VerticalScroll(Static(id="sched-side-body"), id="sched-side"),
                # Empty-grid explanation pane shown when buffer has no valid schedule.
                Static(id="sched-empty"),
                id="dock-sched")

            # INSPECT tab: cursor cycle breakdown, dependency chain, and cycle catalog.
            yield Horizontal(
                VerticalScroll(Static(id="code-line-info"),
                               Static(id="code-chain-body"),
                               id="dock-line-col"),
                VerticalScroll(id="dock-bundles"),
                # Third column (NUMBERS & MACHINE) shown only when INSPECT is maximized.
                VerticalScroll(Static(id="line-side-body"), id="line-side"),
                id="dock-line")

            yield VerticalScroll(id="dock-lint")

            yield Vertical(
                # Bridge action row directly inside the OUTPUT tab.
                BridgeRow(prefix="dbridge", id="drawer-bridge"),
                Console(id="console", runs=self.app.session.journal_runs),
                ConsoleJournal(id="journal"),
                PromptBar(self.mode, self.placeholder,
                          list(self.app.commands) + self.extra_commands(),
                          hint=self.hint, id="prompt"),
                id="dock-term")

            # CORE tab: compact interpreter console and live machine state.
            yield Horizontal(
                Vertical(
                    Horizontal(
                        Tool("~ repeat", "agent-repeat",
                             "ask the last question again"),
                        Tool("clear", "agent-clear",
                             "clear conversation across all views"),
                        Tool("agent context", "agent-facts",
                             "refresh buffer facts in the right column"),
                        id="agent-tools"),
                    VerticalScroll(Static(id="agent-log"), id="agent-log-box"),
                    ItemGrid(id="agent-asks", min_column_width=36),
                    Horizontal(Static(" > ", id="agent-mark"),
                               Input(placeholder="ask in plain language — "
                                     "agent answers from computed numbers",
                                     id="agent-input"),
                               id="agent-prompt"),
                    id="agent-main"),
                VerticalScroll(
                    Static("  agent context", classes="panel-head"),
                    Static(id="agent-seen"),
                    Static("  trace", classes="panel-head"),
                    Static(id="agent-trace"),
                    id="agent-side"),
                id="dock-agent")

            yield Horizontal(
                Vertical(
                    RichLog(id="core-log", wrap=False, markup=False,
                            highlight=False, auto_scroll=True),
                    # Kernel/verb chips placed above input when maximized so they don't hide output.
                    ItemGrid(id="core-chips", min_column_width=9),
                    Horizontal(Static(" > ", id="core-mark"),
                               Input(placeholder="a = 10   ·   t = a*2   "
                                     "·   sum 8   ·   go", id="core-input"),
                               id="core-prompt"),
                    id="core-log-box"),
                VerticalScroll(Static(id="core-state"), id="core-state-col"),
                id="dock-core")

        # --- footer: single status bar at the very bottom ---------------------
        with Vertical(id="code-foot"):
            with Horizontal(id="code-status-row"):
                yield LineChip(id="code-line-chip")
                # Key hints share the single status bar to preserve vertical space.
                yield Static(id="code-keys")
                yield Static(id="code-status")
                yield DrawerChip(
                    "lint", "^ 0",
                    "machine issues: click — ISSUES tab",
                    id="status-lint")
                yield DrawerChip(
                    "term", "git 0",
                    "session git — run history and mode bridge: "
                    "click — OUTPUT tab",
                    id="status-term")

        yield Suggest(id="suggest")

    def on_ready(self) -> None:
        self._load_layout()
        # Apply loaded layout state to widgets immediately.
        self._draw_drawer()
        self._fit_columns(self.size.width or 120)
        edit = self.query_one("#code-edit", AsmArea)
        if not self.app.session.code_text:
            self.app.session.code_text = example_text("slots") or FALLBACK
            self._example = "slots"
        # Seed first tab from the active session buffer.
        self.files = [{"name": self._buffer_name(),
                       "path": self.app.session.code_path,
                       "text": self.app.session.code_text,
                       "example": self._example}]
        self.file_i = 0
        edit.text = self.app.session.code_text
        # Tooltip advertising click-to-inspect on the status bar cursor readout.
        self.query_one("#code-line-chip", LineChip).tooltip = (
            "line under cursor: cycle, channels, issues\n"
            "click — full breakdown (INSPECT tab below)")
        edit.tooltip = ("> next to cursor line — run buffer (F5)\n"
                        "cN in gutter — cycle where op issues\n"
                        "cN→M — exact search places it at cycle M")
        self._draw_side()
        self._seed_console()
        self._seed_core()
        self._take_pending_note()
        self.reparse()
        edit.focus()

    # --- open file tabs ---------------------------------------------------

    def _buffer_name(self, rec: dict | None = None) -> str:
        """Derive display name for a buffer tab from its path, example, or record."""
        path = self.app.session.code_path
        if path:
            return path.rsplit("/", 1)[-1]
        if self._example:
            return self._example + ".s"
        if rec is not None and rec.get("name"):
            return rec["name"]
        return "buffer"

    def _stash_current(self) -> None:
        """Persist active tab text and name before switching tabs."""
        if not self.files:
            return
        rec = self.files[self.file_i]
        rec["text"] = self.query_one("#code-edit", AsmArea).text
        rec["path"] = self.app.session.code_path
        rec["example"] = self._example
        rec["name"] = self._buffer_name(rec)

    def open_file(self, text: str, name: str, path: str = "",
                  example: str = "") -> None:
        """Open text in a new tab, or focus the existing tab if already open."""
        self._stash_current()
        for i, rec in enumerate(self.files):
            if rec["name"] == name:
                self.select_file(i)
                return
        self.files.append({"name": name, "path": path, "text": text,
                           "example": example})
        self.select_file(len(self.files) - 1, stash=False)

    def select_file(self, index: int, stash: bool = True) -> None:
        if not (0 <= index < len(self.files)):
            return
        if stash:
            self._stash_current()
        self.file_i = index
        rec = self.files[index]
        edit = self.query_one("#code-edit", AsmArea)
        edit.replace(rec["text"], (0, 0), edit.document.end)
        self.app.session.code_text = rec["text"]
        self.app.session.code_path = rec["path"]
        self._example = rec["example"]
        # Discard stale oracle results when switching to another buffer.
        self.base = self.orc = self.met = None
        self.findings = []
        self.run_text = ""
        self.reparse()
        edit.focus()

    def close_file(self, index: int) -> None:
        """Close a tab; always keeps at least one tab open."""
        if len(self.files) <= 1 or not (0 <= index < len(self.files)):
            return
        if index == self.file_i:
            self._stash_current()
        self.files.pop(index)
        self.select_file(min(self.file_i if index > self.file_i
                             else self.file_i - 1, len(self.files) - 1),
                         stash=False)

    def on_file_strip_picked(self, event) -> None:
        event.stop()
        self.select_file(event.index)

    def on_file_strip_closed(self, event) -> None:
        event.stop()
        self.close_file(event.index)

    def on_side_item_picked(self, event) -> None:
        """Open a file picked from the left catalog as a tab."""
        event.stop()
        key = event.key
        if key.startswith("hist:"):
            self.explorer_dir = Path(key[5:])
            self.explorer_query = ""
            self._explorer_at = 0
            try:
                self.query_one("#explorer-find", Input).value = ""
            except Exception:
                pass
            self._draw_explorer()
            return
        if key.startswith("dir:"):
            # Reset search filter when navigating into a folder.
            self._remember_dir(self.explorer_dir)
            self.explorer_dir = Path(key[4:])
            self.explorer_query = ""
            self._explorer_at = 0
            try:
                self.query_one("#explorer-find", Input).value = ""
            except Exception:
                pass
            self._draw_explorer()
            return
        if key.startswith("new:"):
            self._new_buffer(key[4:])
            return
        if key == "del:no":
            self._to_delete = ""
            self._draw_explorer()
            return
        if key == "del:yes":
            self._delete_file(self._to_delete)
            return
        if key == self._to_delete:
            # Second click on the same pending-delete file cancels deletion.
            self._to_delete = ""
            self._draw_explorer()
            return
        if key == "buf:new":
            self._new_buffer()
            return
        if key.startswith("buf:"):
            self.select_file(int(key[4:]))
            self._draw_side()
            return
        if key.startswith("ex:"):
            name = key[3:]
            text = example_text(name)
            if text is not None:
                self.open_file(text, f"{name}.s", example=name)
            return
        # Clicking trailing `x` prompts inline delete confirmation.
        if getattr(event, "at_x", -1) >= self.DELETE_X and self._deletable(key):
            self._to_delete = key
            self._draw_explorer()
            return
        # Remember path for local files so ^S saves back in place.
        try:
            text = Path(key).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            con = self.console
            if con is not None:
                con.note(f"  {key}: {exc}", "error")
            return
        # Use basename only so Windows backslashes never leak into tab titles.
        self.open_file(text, Path(key).name, path=key)

    def _new_buffer(self, kind: str = "s") -> None:
        """Create a new empty tab with an auto-numbered name (F2 renames)."""
        suffix, _label, base, seed = next(
            (k for k in self.FILE_KINDS if k[0] == kind), self.FILE_KINDS[0])
        n = 1
        used = {rec["name"] for rec in self.files}
        while f"{base} {n}.{suffix}" in used:
            n += 1
        self.open_file(seed, f"{base} {n}.{suffix}")
        self._draw_side()
        self.query_one("#code-edit", AsmArea).focus()

    def _is_asm(self, name: str = "") -> bool:
        """Return whether this buffer should be parsed as e2k assembly (by extension)."""
        if not name:
            name = self.files[self.file_i]["name"] if self.files else ""
        low = name.lower()
        return (not low) or low.endswith(self.ASM_SUFFIXES)

    def action_rename_buffer(self) -> None:
        """F2 — rename the active tab inline."""
        if not self.files:
            return
        # F2 prefills `/rename ` in the command prompt instead of a modal dialog.
        self.open_drawer("term")
        bar = self.query_one("#prompt", PromptBar)
        bar.focus_input()
        bar.set_value("/rename " + self.files[self.file_i]["name"])

    def _rename_buffer(self, name: str) -> None:
        name = (name or "").strip()
        if not name or not self.files:
            return
        if any(i != self.file_i and rec["name"] == name
               for i, rec in enumerate(self.files)):
            con = self.console
            if con is not None:
                con.note(f"  tab '{name}' already exists", "error")
            return
        rec = self.files[self.file_i]
        was = rec["name"]
        rec["name"] = name
        # Clear path and example tag on rename so ^S does not overwrite the old file.
        rec["path"] = rec["example"] = ""
        self._example = ""
        self.app.session.code_path = ""
        self.refresh_context()
        self._draw_side()
        con = self.console
        if con is not None:
            con.note(f"  tab '{was}' → '{name}'", "success")

    def _take_pending_note(self) -> None:
        """Record a bridge note ("to CODE") in the output log."""
        note = getattr(self.app.session, "pending_note", "")
        if not note:
            return
        self.app.session.pending_note = ""
        con = self.console
        if con is not None:
            con.note("  " + note, "accent2")

    def _seed_console(self) -> None:
        con = self.console
        if con is None:
            return
        dim = palette.role_hex("dim")
        accent = palette.role_hex("accent2")
        con.write(Text("what F5 does", style=dim))
        for cmd, note in (
            ("parse", "lines of .s → register dependency DAG"),
            ("schedule", "how the buffer executes as written"),
            ("exact search", "minimum cycles achievable"),
            ("diagnosis", "where cycles are lost"),
        ):
            row = Text()
            row.append("  " + cmd.ljust(14), style=accent)
            row.append(note, style=dim)
            con.write(row)

    # --- typing completion popup ------------------------------------------

    def check_action(self, action: str, parameters) -> bool:
        """Activate popup navigation keys only while the completion popup is visible."""
        if action in self.SUGGEST_ACTIONS:
            # Keep arrows and Enter active in explorer search.
            if self._explorer_has_focus():
                return True
            sug = self.suggest
            return bool(sug is not None and sug.display)
        return True

    @property
    def suggest(self):
        try:
            return self.query_one("#suggest", Suggest)
        except Exception:
            return None

    def _focus_find(self) -> None:
        """Focus the explorer search input if visible."""
        try:
            self.query_one("#explorer-find", Input).focus()
        except Exception:
            pass

    def _explorer_has_focus(self) -> bool:
        try:
            return self.query_one("#explorer-find", Input).has_focus
        except Exception:
            return False

    def action_suggest_up(self) -> None:
        # Route arrow keys to explorer search or editor completion popup.
        if self._explorer_has_focus():
            self._explorer_step(-1)
            return
        self.suggest.step(-1)

    def action_suggest_down(self) -> None:
        if self._explorer_has_focus():
            self._explorer_step(1)
            return
        self.suggest.step(1)

    def action_suggest_take(self) -> None:
        # Priority binding forwards Enter to explorer search when focused there.
        if self._explorer_has_focus():
            self._open_selected()
            return
        self._accept_suggest()

    #: Determine completion context at cursor.
    _MNEM_TAIL = re.compile(r"(?:^|[{\s])([a-z][a-z0-9_]*)$")
    _CHAN_TAIL = re.compile(r"\b([a-z][a-z0-9_]+),(\d*)$")
    _REG_TAIL = re.compile(r"%([a-z]*\d*)$")

    def _update_suggest(self) -> None:
        """Rebuild completion items for the text left of the cursor."""
        sug = self.query_one("#suggest", Suggest)
        edit = self.query_one("#code-edit", AsmArea)
        if not edit.has_focus:
            sug.hide()
            return
        row, col = edit.cursor_location
        line = edit.document.get_line(row)[:col]
        # No completions inside comments.
        if _COMMENT_RE.search(line):
            sug.hide()
            return

        items = self._suggest_items(line, row)
        if not items:
            sug.hide()
            return
        sug.show(items)
        # Position popup below cursor, flipping above if near the bottom edge.
        try:
            x, y = edit.cursor_screen_offset
            height = min(len(sug.items), 8) + 2      # + border
            width = int(sug.styles.width.value or 52)
            below = y + 1
            if below + height > self.size.height - 1:
                below = max(0, y - height)
            sug.styles.offset = (max(0, min(x - 2, self.size.width - width)),
                                 below)
        except Exception:
            pass

    #: Leading `/` starts a command/snippet (comments use `!` in e2k).
    _CMD_TAIL = re.compile(r"^\s*/([a-z0-9_]*)$", re.I)

    def _suggest_items(self, line: str, row: int):
        model = self.app.session.model()

        # List commands first when typing `/` in the editor.
        m = self._CMD_TAIL.match(line)
        if m:
            return self._cmd_items(m.group(1))

        m = self._CHAN_TAIL.search(line)
        if m:
            return self._chan_items(m.group(1), m.group(2), row, model)
        m = self._REG_TAIL.search(line)
        if m:
            return self._reg_items(m.group(1), row, model)
        m = self._MNEM_TAIL.search(line)
        if m:
            return self._mnem_items(m.group(1), model)
        return []

    #: Buffer-writing commands offered in editor `/` popup.
    WRITES_BUFFER = ("gen", "fill", "example", "rewrite", "load", "code")

    def _cmd_items(self, prefix: str):
        """Suggest snippets and buffer-writing commands after `/` in the editor."""
        low = prefix.lower()
        rows: list[tuple[str, str, str, str]] = []
        for name, note, kind in self.SNIPPETS:
            if name.startswith(low):
                # Build snippet bodies on demand using currently unused registers.
                rows.append((self._snippet_text(kind), "/" + name, note,
                             "accent2"))
        # Cap unfiltered snippets so commands remain visible in the popup.
        if not low:
            rows = rows[:5]

        cmds = list(self.app.commands) + self.extra_commands()
        seen: set[str] = set()
        order = self.WRITES_BUFFER
        for cmd in sorted(cmds, key=lambda c: (
                order.index(c["name"]) if c["name"] in order else 99,
                c["name"])):
            name = cmd["name"]
            if name not in order or name in seen or not name.startswith(low):
                continue
            seen.add(name)
            arg = cmd.get("arg", "")
            rows.append((name[len(prefix):] + (" " if arg else ""),
                         "/" + name + (" " + arg if arg else ""),
                         cmd.get("help", ""), "text"))
        return rows[:12]

    def _mnem_items(self, prefix: str, model):
        """Suggest e2k mnemonics with latency and legal channels."""
        out = []
        for mn in sorted(asm_parser.MNEMONICS):
            if not mn.startswith(prefix) or mn == prefix:
                continue
            cls = asm_parser.MNEMONICS[mn]
            chans = " ".join(model.port_label(p)
                             for p in model.channels_for(cls))
            out.append((mn[len(prefix):], mn,
                        f"{cls}  lat {model.latency(cls)}  {chans}",
                        "text"))
        return out[:8]

    def _chan_items(self, mnemonic: str, typed: str, row: int, model):
        """Suggest only legal channels for the op, marking busy channels in this bundle."""
        cls = asm_parser.MNEMONICS.get(mnemonic.lower())
        if cls is None:
            return []
        busy = self._busy_channels(row)
        out = []
        for port in model.channels_for(cls):
            label = str(port)
            if typed and not label.startswith(typed):
                continue
            if port in busy:
                note = f"busy: {busy[port]}"
                role = "warning"
            else:
                note = "free in this bundle"
                role = "success"
            out.append((label[len(typed):], f",{port}", note, role))
        return out

    def _busy_channels(self, row: int) -> dict[int, str]:
        """Return map of channel -> mnemonic already used in the bundle at `row`."""
        edit = self.query_one("#code-edit", AsmArea)
        lines = edit.document.lines
        start = row
        while start > 0 and "{" not in lines[start]:
            start -= 1
        busy: dict[int, str] = {}
        for i in range(start, min(len(lines), start + 12)):
            if i == row:
                continue
            if i > start and "}" in lines[i]:
                break
            m = _MNEM_RE.match(lines[i].lstrip(" \t{"))
            if m and m.group("ch"):
                busy[int(m.group("ch")[1:])] = m.group("mn")
        return busy

    def _reg_items(self, prefix: str, row: int, model):
        """Suggest registers defined earlier in the buffer with their ready cycle."""
        if self.parsed is None:
            return []
        seen: dict[str, tuple[int, str]] = {}
        for op in self.parsed.ops:
            if op.line - 1 >= row:
                break
            if op.dst:
                seen[op.dst] = (op.cycle + model.latency(op.op), op.mnemonic)
        here = self._op_at_line(row + 1)
        out = []
        for reg, (ready, who) in sorted(seen.items()):
            if prefix and not reg.startswith(prefix):
                continue
            role = "text"
            note = f"ready at c{ready}   ← {who}"
            if here is not None and here.cycle < ready:
                role = "error"
                note = f"NOT ready: c{ready}, line is at c{here.cycle}"
            out.append((reg[len(prefix):], "%" + reg, note, role))
        return out[:8]

    def on_suggest_item_picked(self, event) -> None:
        event.stop()
        sug = self.query_one("#suggest", Suggest)
        sug.index = event.index
        self._accept_suggest()

    def _accept_suggest(self) -> bool:
        sug = self.query_one("#suggest", Suggest)
        if not sug.display or not sug.items:
            return False
        edit = self.query_one("#code-edit", AsmArea)
        insert, _label, _note, role = sug.items[sug.index]
        if role == "accent2" and insert.startswith("{"):
            # Replace typed `/name` trigger with the generated snippet.
            row, col = edit.cursor_location
            line = edit.document.get_line(row)[:col]
            slash = line.rfind("/")
            if slash >= 0:
                edit.replace("", (row, slash), (row, col))
            edit.insert(insert)
        else:
            edit.insert(insert)
        sug.hide()
        return True

    # --- bottom dock ------------------------------------------------------

    def action_toggle_drawer(self) -> None:
        if self.drawer_open:
            self.close_drawer()
        else:
            self.open_drawer(self.drawer_tab)

    def action_slash(self) -> None:
        """Handle `/` in editor (opens command popup) or pass through to focused Input."""
        edit = self.query_one("#code-edit", AsmArea)
        if edit.has_focus:
            # Typing `/` in editor inserts it and opens the inline command popup.
            edit.insert("/")
            return
        # Typing `/` inside an Input appends `/` instead of resetting the command.
        try:
            focused = self.app.focused
        except Exception:
            focused = None
        if isinstance(focused, Input):
            try:
                self._clear_selection(focused)
                focused.insert_text_at_cursor("/")
            except Exception:
                try:
                    pos = focused.cursor_position or len(focused.value or "")
                    val = focused.value or ""
                    focused.value = val[:pos] + "/" + val[pos:]
                    focused.cursor_position = pos + 1
                except Exception:
                    pass
            return
        # Outside text inputs, `/` opens the OUTPUT command prompt.
        self.open_drawer("term")
        bar = self.query_one("#prompt", PromptBar)
        bar.focus_input()
        try:
            cur = bar.input.value or ""
        except Exception:
            cur = ""
        if not cur:
            bar.set_value("/")
            self._clear_selection(bar.input)
            # Textual selects all text on focus asynchronously; clear selection after refresh.
            try:
                self.call_after_refresh(self._clear_selection, bar.input)
            except Exception:
                pass
        else:
            try:
                self._clear_selection(bar.input)
                bar.input.insert_text_at_cursor("/")
            except Exception:
                bar.set_value(cur + "/")

    @staticmethod
    def _clear_selection(inp) -> None:
        """Clear text selection after focusing so typing does not overwrite `/`."""
        try:
            from textual.widgets._input import Selection

            pos = inp.cursor_position or len(inp.value or "")
            inp.selection = Selection(pos, pos)
        except Exception:
            pass

    def action_command(self) -> None:
        """^P — open OUTPUT tab with `/` prefilled in the command prompt."""
        self.open_drawer("term")
        bar = self.query_one("#prompt", PromptBar)
        bar.focus_input()
        try:
            cur = bar.input.value or ""
        except Exception:
            cur = ""
        if not cur:
            bar.set_value("/")
            self._clear_selection(bar.input)
            # Same async selection clear after focusing the command prompt.
            try:
                self.call_after_refresh(self._clear_selection, bar.input)
            except Exception:
                pass
        else:
            # Preserve existing text in the prompt when pressing ^P.
            self._clear_selection(bar.input)
            try:
                self.call_after_refresh(self._clear_selection, bar.input)
            except Exception:
                pass

    def open_drawer(self, tab: str) -> None:
        tab = tab if tab in self.TABS else "sched"
        # Capture the tab/context active before opening AGENT.
        if tab == "agent" and self.drawer_tab != "agent":
            # Snapshot topic before moving focus to the AGENT question input.
            self._prev_tab = self.drawer_tab
            try:
                in_code = self.query_one("#code-edit", AsmArea).has_focus
            except Exception:
                in_code = True
            self._ai_from = ("code" if in_code
                             else self.TABS[self.drawer_tab][3])
        self.drawer_tab = tab
        self._save_layout()
        self.drawer_open = True
        self._draw_drawer()
        if self.drawer_tab == "term":
            self.query_one("#prompt", PromptBar).focus_input()
        elif self.drawer_tab == "core":
            self.query_one("#core-input", Input).focus()
        elif self.drawer_tab == "agent":
            self.query_one("#agent-input", Input).focus()

    def close_drawer(self) -> None:
        self.drawer_open = False
        self._save_layout()
        self._draw_drawer()
        self.query_one("#code-edit", AsmArea).focus()

    def _draw_drawer(self) -> None:
        """Switch active dock tab and update zoom flags."""
        self._sched_expanded = bool(self.zoom) and self.drawer_tab == "sched"
        self._lint_expanded = bool(self.zoom) and self.drawer_tab == "lint"
        self._console_expanded = bool(self.zoom) and self.drawer_tab == "term"
        dock = self.query_one("#code-dock", Vertical)
        dock.display = self.drawer_open
        self._apply_dock_height(dock)
        # Hide splitter whenever the dock is hidden.
        self.query_one("#dock-split", DockSplitter).display = self.drawer_open
        # Toggle dock-open class for responsive height rules.
        self.set_class(self.drawer_open, "drawer")
        for key, (_label, box, tool, _t) in self.TABS.items():
            self.query_one(box).display = key == self.drawer_tab
            self.query_one(tool, Tool).set_on(key == self.drawer_tab)
        # Show schedule view switcher only on the SCHEDULE tab.
        on_sched = self.drawer_tab == "sched"
        for tool_id in ("#tab-src", "#tab-orc"):
            self.query_one(tool_id, Tool).display = on_sched
        self.query_one("#dock-sep", Static).display = on_sched
        self._draw_journal()
        if self.drawer_tab == "sched":
            # Rebuild grid when switching to SCHEDULE while zoomed so orientation matches.
            self._draw_grids()
            if self.zoom:
                self.call_after_refresh(self._draw_grids)
        if self.drawer_tab == "lint":
            self._draw_lint()
        elif self.drawer_tab == "line":
            # Update all three INSPECT panes.
            line = self._cursor_line or 1
            self._draw_line_info(line)
            self._draw_chain(line)
            self._draw_bundles()
            self._draw_line_side()
        elif self.drawer_tab == "core":
            self._seed_core_chips()
            self._draw_core_state()
        elif self.drawer_tab == "agent":
            self._draw_dialog()
            self._draw_agent_extras()
        self._draw_dock_note()
        self.refresh_hints()

    def _draw_dock_note(self) -> None:
        """Right-aligned live summary for the active dock tab."""
        try:
            note = self.query_one("#dock-note", Static)
        except Exception:
            return
        t = Text()
        dim = palette.role_hex("dim")
        if self.drawer_tab == "sched":
            t = self._sched_note()
        elif self.drawer_tab == "lint":
            errs = sum(1 for p in self.problems if p.severity == "error")
            if errs:
                t.append(f"{errs} {plural(errs, 'error', 'errors', 'errors')} ",
                         style=palette.role_hex("error"))
            elif self.findings and not self._stale():
                k = len(self.findings)
                t.append(f"{k} {plural(k, 'finding', 'findings', 'findings')} ",
                         style=palette.role_hex("warning"))
            else:
                t.append("clean ", style=palette.role_hex("success"))
        elif self.drawer_tab == "term":
            n = len(self.query_one("#console", Console).runs)
            if n:
                t.append(f"{n} {plural(n, 'commit', 'commits', 'commits')} ",
                         style=dim)
            else:
                t.append("empty — F5 becomes commit #1 ", style=dim)
        elif self.drawer_tab == "agent":
            t = self._dialog_note()
        elif self.drawer_tab == "core":
            ws = self.app.session.workspace()
            n = ws.graph_size()
            t.append(f"{len(ws.regs)} names   ·   {n} "
                     f"{plural(n, 'op', 'ops', 'ops')} "
                     f"in graph ", style=dim)
        else:
            n = self.parsed.bundles if self.parsed is not None else 0
            t.append(f"{n} {plural(n, 'bundle', 'bundles', 'bundles')}"
                     f"   ·   ln.{self._cursor_line or 1} ", style=dim)
        note.update(t)

    # --- AGENT dock tab ---------------------------------------------------

    class _Subject:
        """Lightweight panel descriptor passed to `open_panel_prompt`."""

        def __init__(self, topic: str, title: str) -> None:
            self.topic = topic
            self._title = title

    #: Search result and depth limits for the file explorer.
    FIND_LIMIT = 60
    FIND_DEPTH = 4

    #: Max filesystem entries scanned per search.
    FIND_SCAN = 4000

    #: Directories skipped during explorer search (e.g. `.venv`, `.git`).
    SKIP_DIRS = frozenset({"__pycache__", "node_modules", "site-packages",
                           "dist-info", "egg-info"})

    #: Max entries displayed in an unfiltered folder listing.
    LIST_LIMIT = 300

    #: Debounce delay before starting explorer search.
    FIND_DEBOUNCE = 0.2

    #: Column threshold for the inline delete `x` button.
    DELETE_X = 24

    #: Minimum columns reserved for the editor.
    EDIT_MIN_W = 60

    def action_toggle_explorer(self) -> None:
        """^E — toggle right file explorer via `_fit_columns`."""
        self._want_explorer = not self.explorer_shown
        self._fit_columns(self.size.width or 120)
        self._save_layout()
        if self.explorer_shown:
            self._draw_explorer()
            # Focus explorer search both immediately and after refresh once visible.
            self._focus_find()
            self.call_after_refresh(self._focus_find)
        else:
            self.query_one("#code-edit", AsmArea).focus()
            self._say_no_room("explorer", 30, self._want_explorer)
        self.refresh_context()
        self.refresh_hints()

    def action_toggle_side(self) -> None:
        """^B — toggle left tabs sidebar, remembering user intent across resizes."""
        self._want_side = not self.side_shown
        self._fit_columns(self.size.width or 120)
        self._save_layout()
        if not self.side_shown:
            self._say_no_room("tabs sidebar", 22, self._want_side)
        self.refresh_hints()
        self.refresh_context()

    def _say_no_room(self, what: str, need: int, wanted: bool) -> None:
        """Explain in output why a sidebar could not open on a narrow window."""
        if not wanted:
            return
        con = self.console
        if con is None:
            return
        width = self.size.width or 120
        con.note(f"  {what} needs {need} cols, window has "
                 f"{width}: {self.EDIT_MIN_W} reserved for editor", "warning")

    #: Layout persistence path alongside `~/.config/nex/key`.
    LAYOUT_FILE = Path.home() / ".config" / "nex" / "layout.json"

    def _save_layout(self) -> None:
        """Persist layout preferences (dock height, sidebars, active tab)."""
        import json

        try:
            self.LAYOUT_FILE.parent.mkdir(parents=True, exist_ok=True)
            self.LAYOUT_FILE.write_text(json.dumps({
                "dock_h": self.dock_h,
                "drawer_open": self.drawer_open,
                "drawer_tab": self.drawer_tab,
                "side": self._want_side,
                "explorer": self._want_explorer,
                "dirs": self._explorer_hist,
            }, ensure_ascii=False), encoding="utf-8")
        except OSError:
            # Ignore layout save errors; defaults remain usable.
            pass

    def _load_layout(self) -> None:
        """Restore saved layout preferences from previous session."""
        import json

        try:
            data = json.loads(self.LAYOUT_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(data, dict):
            return
        height = data.get("dock_h")
        if isinstance(height, int) and self.DOCK_MIN <= height <= 60:
            self.dock_h = height
        tab = data.get("drawer_tab")
        if tab in self.TABS:
            self.drawer_tab = tab
        if isinstance(data.get("drawer_open"), bool):
            self.drawer_open = data["drawer_open"]
        self._want_side = bool(data.get("side"))
        self._want_explorer = bool(data.get("explorer"))
        dirs = data.get("dirs")
        if isinstance(dirs, list):
            self._explorer_hist = [str(d) for d in dirs[:5]
                                   if isinstance(d, str)]

    def _fit_columns(self, width: int) -> None:
        """Fit sidebars within current width while keeping >= EDIT_MIN_W for editor."""
        room = width - (22 if self._want_side else 0) \
            - (30 if self._want_explorer else 0)
        show_explorer = self._want_explorer
        show_side = self._want_side
        if room < self.EDIT_MIN_W and show_explorer:
            show_explorer = False
            room += 30
        if room < self.EDIT_MIN_W and show_side:
            show_side = False
        for selector, want, attr in (("#code-explorer", show_explorer,
                                      "explorer_shown"),
                                     ("#code-side", show_side, "side_shown")):
            if getattr(self, attr) == want:
                continue
            try:
                self.query_one(selector).display = want
            except Exception:
                continue
            setattr(self, attr, want)

    def _apply_width(self, width: int) -> None:
        super()._apply_width(width)
        self._fit_columns(width)

    def _explorer_rows(self) -> list[tuple[str, str, bool]]:
        """List entries for explorer: [(key, label, is_dir)] for current dir or search."""
        folder = self.explorer_dir
        query = self.explorer_query.strip().lower()
        rows: list[tuple[str, str, bool]] = []
        if query:
            return self._find_rows(folder, query)

        import os

        self._find_cut = ""
        if folder.parent != folder:
            rows.append((str(folder.parent), "..", True))
        # Show recently visited folders right under `..`.
        for path in self._explorer_hist[:3]:
            if path == str(folder):
                continue
            name = Path(path).name or path
            rows.append(("hist:" + path, "← " + name, True))
        try:
            with os.scandir(folder) as it:
                entries = list(it)
        except OSError as exc:
            self._find_cut = f"cannot read directory: {exc.strerror}"
            return rows
        # Cap directory listing to keep large folders responsive.
        if len(entries) > self.LIST_LIMIT:
            self._find_cut = (f"{len(entries)} files in folder, showing "
                              f"first {self.LIST_LIMIT} — search by name")
        def sort_key(entry):
            try:
                return (not entry.is_dir(follow_symlinks=False),
                        entry.name.lower())
            except OSError:
                return (True, entry.name.lower())

        for entry in sorted(entries, key=sort_key)[:self.LIST_LIMIT]:
            if entry.name.startswith(".") or entry.name in self.SKIP_DIRS:
                continue
            try:
                is_dir = entry.is_dir(follow_symlinks=False)
            except OSError:
                continue
            rows.append((entry.path,
                         entry.name + "/" if is_dir else entry.name, is_dir))
        return rows

    def _remember_dir(self, folder) -> None:
        """Remember last visited directory for quick return."""
        path = str(folder)
        hist = [p for p in self._explorer_hist if p != path]
        hist.insert(0, path)
        self._explorer_hist = hist[:5]
        self._save_layout()

    @staticmethod
    def _find_hit(query: str, name: str, rel: str) -> bool:
        """Match search query against filename or relative path (normalizing slashes)."""
        q = query.replace("\\", "/").strip().lower()
        if not q:
            return False
        if "/" in q:
            return q.strip("/") in rel.replace("\\", "/").lower()
        return q in name.lower()

    def _find_rows(self, folder, query: str) -> list[tuple[str, str, bool]]:
        """Breadth-first filename search with depth, scan, and result caps."""
        import os

        rows: list[tuple[str, str, bool]] = []
        seen = 0
        self._find_cut = ""
        queue: list[tuple[str, int]] = [(str(folder), 0)]
        base = str(folder)
        while queue and len(rows) < self.FIND_LIMIT and seen < self.FIND_SCAN:
            here, depth = queue.pop(0)
            try:
                with os.scandir(here) as it:
                    entries = sorted(it, key=lambda e: e.name.lower())
            except OSError:
                continue
            for entry in entries:
                seen += 1
                if seen >= self.FIND_SCAN:
                    break
                name = entry.name
                if name.startswith(".") or name in self.SKIP_DIRS:
                    continue
                try:
                    is_dir = entry.is_dir(follow_symlinks=False)
                except OSError:
                    continue
                # Descend into subfolders even when the folder name itself does not match.
                if is_dir and depth + 1 < self.FIND_DEPTH:
                    queue.append((entry.path, depth + 1))

                shown = entry.path[len(base) + 1:] or name
                if not self._find_hit(query, name, shown):
                    continue
                # Include matching folders in search results.
                rows.append((entry.path, shown + "/" if is_dir else shown,
                             is_dir))
                if len(rows) >= self.FIND_LIMIT:
                    break
        # Note if search hit result, scan, or depth cap.
        if len(rows) >= self.FIND_LIMIT:
            self._find_cut = f"showing first {self.FIND_LIMIT}"
        elif seen >= self.FIND_SCAN:
            self._find_cut = (f"scanned {self.FIND_SCAN} files — "
                              "narrow query or enter a folder")
        elif queue:
            self._find_cut = f"stopped at depth {self.FIND_DEPTH}"
        return rows

    def _draw_explorer(self) -> None:
        """Redraw the file explorer column."""
        try:
            head = self.query_one("#explorer-head", Static)
            box = self.query_one("#explorer-list", VerticalScroll)
        except Exception:
            return
        dim = palette.role_hex("dim")
        faint = palette.role_hex("faint")
        rows = self._explorer_rows()

        where = self._rel(self.explorer_dir)
        if where in ("", "."):
            where = self.explorer_dir.name or str(self.explorer_dir)
        t = Text()
        t.append("FOLDERS", style=palette.role_hex("title"))
        if self.explorer_query:
            # Show match count in header during active search.
            n = len(rows)
            t.append(f"   {n} " + plural(n, "match", "matches", "matches"),
                     style=palette.role_hex("dim" if n else "faint"))
        else:
            # Truncate long folder names on the right to keep distinctive prefix visible.
            t.append("   " + (where if len(where) <= 17
                              else where[:16] + "…"), style=faint)
        head.update(t)
        head.tooltip = f"{self.explorer_dir}\n^E — hide sidebar"

        # Preserve search input focus while rebuilding explorer rows.
        keep_focus = self._explorer_has_focus()
        box.remove_children()
        items: list = []
        if not rows:
            items.append(Static(Text(
                "  no matches" if self.explorer_query
                else "  folder is empty", style=faint)))
        if self._find_cut:
            items.append(Static(self._wrapped(self._find_cut, 28,
                                              style=faint)))
        for key, label, is_dir in rows[:200]:
            rel = self._rel(Path(key))
            mine = (not is_dir) and self._deletable(rel)
            t = Text()
            t.append("  " + ("> " if is_dir else "  "),
                     style=palette.role_hex("accent2" if is_dir else "faint"))
            short = label if len(label) <= 19 else "…" + label[-18:]
            t.append(short, style=palette.role_hex("text") if is_dir else dim)
            # Mark the obsolete hand-drawn illustration file clearly in the list.
            if "OBSOLETE" in Path(key).name.upper():
                t.append("  sample", style=palette.role_hex("warning"))
            if mine:
                # Show delete `x` only for files inside the working directory.
                t.append(" " * max(1, self.DELETE_X - t.cell_len), style=faint)
                # Keep `x` visible (dimmed normally, red while confirming delete).
                t.append("x", style=palette.role_hex(
                    "error" if self._to_delete == rel else "faint"))
            cls = "side-item"
            if len(items) - (1 if not rows else 0) == self._explorer_at:
                cls += " side-item-on"
            item = SideItem(("dir:" + key) if is_dir else (rel if mine else key),
                            t, classes=cls)
            item.tooltip = (f"{key}\n" + ("click — open folder" if is_dir
                                          else "click — open in tab"
                                          + ("\nx on right — delete file"
                                             if mine else "")))
            items.append(item)
        if self._to_delete:
            t = Text()
            t.append("  delete ", style=palette.role_hex("error"))
            t.append(self._to_delete.rsplit("/", 1)[-1][:14],
                     style=palette.role_hex("title"))
            t.append("?", style=palette.role_hex("error"))
            items.append(Static(t))
            row = Text()
            row.append("   yes, delete", style=palette.role_hex("error"))
            item = SideItem("del:yes", row, classes="side-item")
            item.tooltip = "file will be permanently deleted from disk"
            items.append(item)
            row = Text()
            row.append("   cancel", style=dim)
            items.append(SideItem("del:no", row, classes="side-item"))
        if items:
            box.mount(*items)
        if keep_focus:
            try:
                self.query_one("#explorer-find", Input).focus()
            except Exception:
                pass

    def action_toggle_ai(self) -> None:
        """Toggle the AGENT dock tab (^G)."""
        if self.drawer_open and self.drawer_tab == "agent":
            self.close_drawer()
            return
        self.open_drawer("agent")

    @property
    def ai_shown(self) -> bool:
        """Return whether the AGENT dock tab is currently visible."""
        return self.drawer_open and self.drawer_tab == "agent"

    def _answer_in_ai(self, question: str) -> None:
        """Send a question to the shared session agent from the AGENT dock tab."""
        facts = self.panel_facts(self._ai_topic(), question)
        dialog = self.app.session.dialog
        dialog.append({"role": "you", "text": question, "facts": facts})
        dialog.append({"role": "nex", "text": "", "facts": [],
                       "waiting": True})
        self._draw_dialog()
        self._ai_worker(question, facts)

    def _dialog_note(self) -> Text:
        """Summary note for the AGENT dock tab."""
        n = sum(1 for m in self.app.session.dialog if m["role"] == "you")
        t = Text()
        if not n:
            t.append("no questions yet ", style=palette.role_hex("faint"))
        else:
            t.append(f"{n} ", style=palette.role_hex("text"))
            t.append(plural(n, "question", "questions", "questions") + " ",
                     style=palette.role_hex("dim"))
        return t

    #: Buffer-specific suggested questions for the AGENT dock tab.
    ASKS = (
        "why is this cycle empty?",
        "where are cycles lost?",
        "what prevents moving this earlier?",
        "why is the latency this high?",
        "explain the buffer issues",
        "what will F6 change?",
    )

    def _draw_agent_extras(self) -> None:
        """Update sidebar content shown when the AGENT dock tab is maximized."""
        try:
            seen = self.query_one("#agent-seen", Static)
            trace = self.query_one("#agent-trace", Static)
        except Exception:
            return
        dim = palette.role_hex("dim")
        faint = palette.role_hex("faint")
        # Wrap facts to actual sidebar width (fallback 34 before layout).
        width = (self.query_one("#agent-side").size.width or 46) - 3

        t = Text()
        for fact in self.panel_facts(self._ai_topic()):
            t.append_text(self._wrapped(fact, width, style=dim))
        seen.update(t)

        t = Text()
        if not self.ai_actions:
            t.append_text(self._wrapped("no agent actions yet", width,
                                        style=faint))
            t.append_text(self._wrapped("actions and commands the agent ran "
                                        "before answering will appear here",
                                        width, style=faint))
        else:
            for act in self.ai_actions[-12:]:
                t.append_text(self._wrapped("* " + act, width,
                                            style=palette.role_hex("accent2")))
        trace.update(t)

        # Mount question chips once to avoid flicker on redraw.
        try:
            grid = self.query_one("#agent-asks", ItemGrid)
        except Exception:
            return
        if not list(grid.children):
            for q in self.ASKS:
                grid.mount(Chip("> " + q, q, classes="chip chip-question"))

    def _ai_topic(self) -> str:
        """Determine which topic (code or active tab) the agent should explain."""
        if self.drawer_tab != "agent":
            # When invoked outside AGENT, inspect the active view.
            return self.TABS[self.drawer_tab][3]
        return self._ai_from or "code"

    @staticmethod
    def _wrapped(text: str, width: int, style: str = "",
                 indent: int = 2) -> Text:
        """Word-wrap text with a hanging indent."""
        limit = max(8, width - indent)
        out = Text()
        line = ""
        for word in text.split():
            if line and len(line) + 1 + len(word) > limit:
                out.append(" " * indent + line + "\n", style=style)
                line = word
                indent = max(indent, 4)
                limit = max(8, width - indent)
            else:
                line = f"{line} {word}".strip()
        if line:
            out.append(" " * indent + line + "\n", style=style)
        return out

    def on_chip_picked(self, event) -> None:
        """Handle clicks on suggested question chips or CORE kernel chips."""
        event.stop()
        if self.drawer_tab == "core":
            self._exec_core(event.value)
            return
        self._answer_in_ai(event.value)

    def _draw_dialog(self) -> None:
        """Redraw the shared dialog transcript in the AGENT dock tab."""
        self._draw_agent_extras()
        for target_id in ("#agent-log",):
            try:
                target = self.query_one(target_id, Static)
            except Exception:
                continue
            target.update(self._dialog_text())
        try:
            box = self.query_one("#agent-log-box", VerticalScroll)
            box.scroll_end(animate=False)
        except Exception:
            pass

    def _dialog_text(self) -> Text:
        """Format the dialog transcript including waiting/warmup status."""
        dim = palette.role_hex("dim")
        faint = palette.role_hex("faint")
        mind = palette.role_hex("accent2")
        t = Text()
        if not self.app.session.dialog:
            t.append("\nagent explains the COMPUTED numbers above\n", style=dim)
            t.append("exact search computes the numbers; the model writes the prose.\n",
                     style=faint)
            t.append("verify any answer with /doctor, "
                     "/compare, /bounds.\n", style=faint)
            # Show live agent context even when transcript is empty.
            facts = self.panel_facts(self._ai_topic())
            if facts:
                t.append("\nagent currently sees:\n", style=dim)
                for fact in facts[:4]:
                    t.append(f"  {fact}\n", style=faint)
            return t
        for msg in self.app.session.dialog:
            if msg["role"] == "you":
                t.append("\n▌ you\n", style=dim)
                t.append(msg["text"] + "\n", style=palette.role_hex("title"))
                continue
            t.append("\n▌ nex", style=mind)
            t.append("   from numbers above\n", style=faint)
            if msg["text"]:
                t.append(msg["text"] + "\n", style=palette.role_hex("text"))
            elif msg.get("waiting"):
                t.append(self._waiting_text())
        return t

    def _waiting_text(self) -> Text:
        """Render honest model warmup/offline status while awaiting first token."""
        from ...agent import local as agent_local

        t = Text()
        state, note = agent_local.warm_state()
        if state == "ready":
            t.append("  computing…\n", style=palette.role_hex("dim"))
        elif state == "failed":
            t.append(f"  model unavailable: {note}\n",
                     style=palette.role_hex("error"))
            t.append("  numbers above were computed without it and remain valid.\n",
                     style=palette.role_hex("dim"))
        else:
            t.append("  model is warming up — starting server and\n",
                     style=palette.role_hex("warning"))
            t.append("  evaluating system prompt. First reply takes\n",
                     style=palette.role_hex("warning"))
            t.append("  about a minute; subsequent replies take seconds.\n",
                     style=palette.role_hex("warning"))
            t.append("\n  Numbers above are already computed.\n",
                     style=palette.role_hex("dim"))
        return t

    @work(thread=True, exclusive=True, group="ai-side")
    def _ai_worker(self, question: str, facts: list[str]) -> None:
        """Run the full session agent with current screen facts attached."""
        agent = self.app.session.agent()
        try:
            for kind, value in agent.ask_stream(question,
                                                panel=("code", facts)):
                if kind == "text":
                    self.app.call_from_thread(self._ai_piece, value)
                elif kind == "action":
                    # Record executed agent actions in the trace pane.
                    self.app.call_from_thread(self._ai_action, value)
                elif kind == "error":
                    self.app.call_from_thread(self._ai_piece, "\n" + value)
        except Exception as e:
            self.app.call_from_thread(self._ai_piece, f"\nfailed: {e}")

    def _ai_action(self, act: str) -> None:
        """Record an executed agent action in the trace."""
        self.ai_actions.append(act)
        self._draw_agent_extras()

    def _ai_piece(self, piece: str) -> None:
        """Append a streamed answer chunk to the last dialog entry."""
        dialog = self.app.session.dialog
        if not dialog or dialog[-1]["role"] != "nex":
            dialog.append({"role": "nex", "text": "", "facts": []})
        dialog[-1]["text"] += piece
        dialog[-1]["waiting"] = False
        self._draw_dialog()

    def action_explain(self) -> None:
        """^G — open AGENT tab and focus question input (press again to close)."""
        if self.ai_shown:
            self.action_toggle_ai()
            return
        self.action_toggle_ai()
        try:
            self.query_one("#agent-input", Input).focus()
        except Exception:
            pass

    def action_ai_or_complete(self) -> None:
        """Tab inserts indentation in the editor; AI helper lives on ^G."""
        if self._accept_suggest():
            return
        edit = self.query_one("#code-edit", AsmArea)
        if edit.has_focus:
            edit.insert("\t")
            return
        try:
            self.query_one("#prompt", PromptBar).tab()
        except Exception:
            pass

    # --- CORE dock tab: interpreter console -------------------------------

    def _seed_core_chips(self) -> None:
        """Populate built-in kernel and verb chips for the CORE dock tab."""
        from ...core.interp import kernel_help

        try:
            row = self.query_one("#core-chips", ItemGrid)
        except Exception:
            return
        if list(row.children):
            return
        row.mount(Static("kernels", classes="chip-label"))
        for name, default, hint in kernel_help():
            chip = Chip(name, f"{name} {default}", classes="chip chip-kernel")
            chip.tooltip = f"{hint}  ·  default {default}"
            row.mount(chip)
        row.mount(Static("verbs", classes="chip-label"))
        for word, hint in (("names", "show names and values"),
                           ("mem", "show memory"),
                           ("list", "show accumulated graph"),
                           ("reset", "clear names and memory"),
                           ("go", "schedule accumulated graph with exact search")):
            chip = Chip(word, classes="chip chip-verb")
            chip.tooltip = hint
            row.mount(chip)

    def _seed_core(self) -> None:
        log = self.query_one("#core-log", RichLog)
        dim = palette.role_hex("dim")
        log.write(Text("expressions build a graph — like a Python Console",
                       style=dim))
        for line, note in (
            ("a = 10", "assign a value"),
            ("t = a*2 + 3", "expression: each op becomes a graph node"),
            ("sum 8", "built-in kernel: sum of 8 numbers"),
            ("go", "schedule accumulated graph with exact search"),
        ):
            row = Text()
            row.append("  " + line.ljust(14), style=palette.role_hex("accent2"))
            row.append(note, style=dim)
            log.write(row)

    def on_input_changed(self, event) -> None:
        """Debounce explorer directory search while typing."""
        if getattr(event.input, "id", "") != "explorer-find":
            return
        event.stop()
        self.explorer_query = event.value
        self._explorer_at = 0
        if self._find_timer is not None:
            self._find_timer.stop()
        self._find_timer = self.set_timer(self.FIND_DEBOUNCE,
                                          self._draw_explorer)

    def _explorer_step(self, delta: int) -> None:
        """Move selection in explorer list with arrow keys."""
        rows = self._explorer_rows()
        if not rows:
            return
        self._explorer_at = max(0, min(len(rows) - 1,
                                       self._explorer_at + delta))
        self._draw_explorer()
        try:
            box = self.query_one("#explorer-list", VerticalScroll)
            items = list(box.query(SideItem))
            if self._explorer_at < len(items):
                box.scroll_to_widget(items[self._explorer_at], animate=False)
        except Exception:
            pass

    def _open_selected(self) -> None:
        """Open the highlighted item in the explorer."""
        rows = self._explorer_rows()
        if not rows:
            return
        at = min(self._explorer_at, len(rows) - 1)
        key, _label, is_dir = rows[at]
        self.post_message(SideItem.Picked(("dir:" + key) if is_dir else key))

    def _open_first_found(self) -> None:
        """Open the first search match on Enter in the explorer search box."""
        rows = [r for r in self._explorer_rows() if not r[2]]
        if not rows:
            return
        key = rows[0][0]
        self.post_message(SideItem.Picked(key))

    def on_input_submitted(self, event) -> None:
        """Single Input.Submitted dispatcher routing by widget ID."""
        which = getattr(event.input, "id", "")
        if which == "explorer-find":
            event.stop()
            self._open_selected()
            return
        if which == "core-input":
            event.stop()
            line = event.value.strip()
            event.input.value = ""
            if line:
                self._exec_core(line)
            return
        if which == "agent-input":
            event.stop()
            question = event.value.strip()
            event.input.value = ""
            if question:
                self._answer_in_ai(question)
            return

    def _exec_core(self, line: str) -> None:
        """Execute an interpreter line in the CORE dock tab."""
        from ...core.interp import InterpError
        from ...ui import interp_view

        log = self.query_one("#core-log", RichLog)
        ws = self.app.session.workspace()
        echo = Text()
        echo.append("> ", style=palette.role_hex("faint"))
        echo.append(line, style=palette.role_hex("title"))
        log.write(echo)
        try:
            result = ws.exec(line)
        except InterpError as exc:
            log.write(Text("  " + str(exc), style=palette.role_hex("error")))
            return
        except Exception as exc:
            log.write(Text(f"  {type(exc).__name__}: {exc}",
                           style=palette.role_hex("error")))
            return

        width = max(24, self.query_one("#core-log-box").size.width - 2)
        for out in interp_view.render_result(ws, result, width=width):
            log.write(Text.from_ansi(out))
        # Promote interpreter graph to the active session block for LAB and AGENT.
        if result.kind != "reset" and not ws.empty():
            self.app.session.set_dag(ws.snapshot(), "interp")
        self._draw_core_state()
        self._draw_dock_note()
        self.refresh_context()
        if result.kind == "go":
            self._core_handoff()

    def _core_handoff(self) -> None:
        """`go` — schedule the accumulated interpreter graph with exact search."""
        ws = self.app.session.workspace()
        log = self.query_one("#core-log", RichLog)
        if ws.empty():
            log.write(Text("  no graph yet — evaluated without emitting ops",
                           style=palette.role_hex("warning")))
            return
        self.set_busy(True)
        self.run_worker(self._core_go_worker, thread=True, exclusive=True,
                        group="core")

    def _core_go_worker(self) -> None:
        """Run exact search on a background thread."""
        try:
            base, orc, met = self.app.session.results()
        except Exception as exc:
            self.app.call_from_thread(self._core_go_done, None, None, str(exc))
            return
        self.app.call_from_thread(self._core_go_done, base, orc, met, "")

    def _core_go_done(self, base, orc, met, err: str = "") -> None:
        self.set_busy(False)
        log = self.query_one("#core-log", RichLog)
        if err or base is None:
            log.write(Text(f"  failed: {err}",
                           style=palette.role_hex("error")))
            return
        b, o = base.schedule.makespan, orc.schedule.makespan
        t = Text()
        t.append("  greedy ", style=palette.role_hex("dim"))
        t.append(f"{b} cyc", style=palette.role_hex("text"))
        t.append("   exact search ", style=palette.role_hex("dim"))
        t.append(f"{o} cyc", style=palette.role_hex("accent"))
        t.append("   lower bound ", style=palette.role_hex("dim"))
        t.append(f"{met.lower_bound} cyc", style=palette.role_hex("dim"))
        log.write(t)
        if o == met.lower_bound:
            log.write(Text("  optimum proven: no shorter schedule exists",
                           style=palette.role_hex("success")))
        log.write(Text("  session block updated: LAB and AGENT now "
                       "show this graph", style=palette.role_hex("faint")))
        self.refresh_context()

    def _draw_core_state(self) -> None:
        """Render compact NAMES / GRAPH / MEMORY sidebar in the CORE dock tab."""
        try:
            target = self.query_one("#core-state", Static)
        except Exception:
            return
        ws = self.app.session.workspace()
        title = palette.role_hex("title")
        dim = palette.role_hex("dim")
        faint = palette.role_hex("faint")
        # Show full machine state when CORE tab is maximized.
        wide = bool(self.zoom)
        n_names = 100 if wide else 12
        t = Text()
        t.append("NAMES", style=title)
        t.append(f"  {len(ws.regs)}\n", style=dim)
        if not ws.regs:
            t.append("  empty — type  a = 10\n", style=faint)
        for name, value in list(ws.regs.items())[:n_names]:
            t.append(f"  {name[:12]:<13}", style=palette.role_hex("text"))
            t.append(f"{value}\n", style=palette.role_hex("accent2"))
        if len(ws.regs) > n_names:
            t.append(f"  +{len(ws.regs) - n_names} more\n", style=faint)

        n = ws.graph_size()
        t.append("\nGRAPH", style=title)
        t.append(f"  {n} {plural(n, 'op', 'ops', 'ops')}\n",
                 style=dim)
        t.append("  go — schedule\n" if n else "  empty\n", style=faint)
        if wide:
            # List accumulated graph ops line by line when maximized.
            for line in ws.log[-12:]:
                t.append(f"  {line}\n", style=dim)

        used = [(i, v) for i, v in enumerate(ws.mem) if v]
        t.append("\nMEMORY", style=title)
        t.append(f"  {len(used)} of {len(ws.mem)} non-zero\n", style=dim)
        if not used:
            t.append("  empty — store 0 42\n", style=faint)
        elif wide:
            # Render memory as a compact grid when maximized.
            row = ""
            for i, v in used[:32]:
                row += f"{i}:{v}".ljust(9)
                if len(row) >= 36:
                    t.append(f"  {row}\n", style=palette.role_hex("accent2"))
                    row = ""
            if row:
                t.append(f"  {row}\n", style=palette.role_hex("accent2"))
            if len(used) > 32:
                t.append(f"  +{len(used) - 32} more\n", style=faint)
        else:
            for i, v in used[:8]:
                t.append(f"  cell {i:<7}", style=faint)
                t.append(f"{v}\n", style=palette.role_hex("accent2"))
            if len(used) > 8:
                t.append(f"  +{len(used) - 8} more\n", style=faint)
        target.update(t)

    def _draw_line_side(self) -> None:
        """Render NUMBERS and MACHINE summary in the maximized INSPECT tab."""
        try:
            target = self.query_one("#line-side-body", Static)
        except Exception:
            return
        model = self.app.session.model()
        dim = palette.role_hex("dim")
        faint = palette.role_hex("faint")
        title = palette.role_hex("title")
        t = Text()

        t.append("NUMBERS\n", style=title)
        if self.comp is not None:
            t.append("as written".ljust(15), style=dim)
            t.append(f"{self.comp.makespan} cyc\n",
                     style=palette.role_hex("text"))
            t.append("slots".ljust(15), style=dim)
            t.append(f"{self.comp.slot_utilization * 100:.0f}%\n",
                     style=palette.role_hex("text"))
        else:
            t.append("  buffer schedule could not be built\n", style=faint)
        if self._have_orc():
            orc = self.orc.schedule.makespan
            t.append("oracle".ljust(15), style=dim)
            t.append(f"{orc} cyc\n", style=palette.role_hex("success"))
            if self.comp is not None and self.comp.makespan > orc:
                gap = self.comp.makespan - orc
                t.append("slack".ljust(15), style=dim)
                t.append(f"-{gap} cyc  "
                         f"({100 * gap / self.comp.makespan:.0f}%)\n",
                         style=palette.role_hex("success"))
        else:
            t.append("oracle".ljust(15), style=dim)
            t.append("F5 — compute\n", style=faint)

        t.append("\nMACHINE\n", style=title)
        t.append("profile".ljust(15), style=dim)
        t.append(f"{model.name}\n", style=palette.role_hex("text"))
        t.append("channels".ljust(15), style=dim)
        t.append(f"{model.width}\n", style=palette.role_hex("text"))
        for port, ops in sorted(model.sole_host_ops().items()):
            t.append("  " + "/".join(ops), style=palette.op_style(ops[0]))
            t.append(f" → only {model.port_label(port)}\n", style=dim)
        t.append("/model — full matrix\n",
                 style=palette.role_hex("accent_soft"))
        target.update(t)

    def _sched_note(self) -> Text:
        """Summary note for the SCHEDULE dock tab."""
        t = Text()
        left = self._sched_left
        if self.parsed is None or not self.parsed.ops:
            t.append("empty ", style=palette.role_hex("faint"))
        elif left is None:
            t.append("invalid ", style=palette.role_hex("warning"))
        elif self._sched_which == "src":
            t.append(f"{left.makespan} cyc ", style=palette.role_hex("text"))
            if self._have_orc():
                gap = left.makespan - self.orc.schedule.makespan
                if gap > 0:
                    t.append(f" -{gap} ", style=palette.role_hex("success"))
        else:
            t.append(f"{left.makespan} cyc ", style=palette.role_hex("accent"))
        return t

    #: Min/max dock height constraints while dragging.
    DOCK_MIN = 5
    EDIT_MIN = 8

    def _apply_dock_height(self, dock) -> None:
        """Compute dock height from manual drag or per-tab default."""
        if self.zoom:
            return
        want = self.dock_h
        if want is None:
            want = self.TAB_HEIGHT.get(self.drawer_tab, 12)
        # Always keep at least 8 rows for the editor.
        room = max(self.DOCK_MIN, (self.size.height or 40) - self.EDIT_MIN - 4)
        dock.styles.height = max(self.DOCK_MIN, min(want, room))

    def on_dock_splitter_grabbed(self, event) -> None:
        """Record starting dock height when drag begins."""
        event.stop()
        self._drag_h = self.query_one("#code-dock", Vertical).size.height

    def on_dock_splitter_dragged(self, event) -> None:
        """Resize dock height while dragging the splitter."""
        event.stop()
        if self.zoom or not self.drawer_open or self._drag_h is None:
            return
        dock = self.query_one("#code-dock", Vertical)
        # Clamp dragged height to keep both dock and editor usable.
        room = max(self.DOCK_MIN, self.size.height - self.EDIT_MIN - 4)
        want = max(self.DOCK_MIN, min(self._drag_h - event.delta, room))
        if want == self.dock_h:
            return
        self.dock_h = want
        dock.styles.height = want
        self._draw_grids()
        self._save_layout()

    def on_dock_tabs_zoom(self, event) -> None:
        """Double-clicking the dock tab bar toggles dock zoom."""
        event.stop()
        self.open_block(self.drawer_tab)

    def on_line_chip_picked(self, event) -> None:
        event.stop()
        self.open_drawer("line")

    def on_drawer_chip_picked(self, event) -> None:
        """Open the dock tab corresponding to a clicked status-bar launcher."""
        event.stop()
        if self.drawer_open and self.drawer_tab == event.target:
            self.close_drawer()
            return
        self.open_drawer(event.target)

    def refresh_status(self) -> None:
        """Update live error and git commit counters in the status bar."""
        try:
            lint = self.query_one("#status-lint", DrawerChip)
            errs = sum(1 for p in self.problems if p.severity == "error")
            warns = len(self.problems) - errs
            if errs:
                lint.set_label(f"^ {errs}"
                               + (f" ~{warns}" if warns else ""))
            elif warns:
                lint.set_label(f"~ {warns}")
            else:
                lint.set_label("+ clean")
            term = self.query_one("#status-term", DrawerChip)
            n = len(self.app.session.journal_runs)
            term.set_label(f"git {n}" if n else "git")
        except Exception:
            pass

    # --- buffer & top bar -------------------------------------------------

    def _sync_buffer(self) -> None:
        """Sync editor text to session and active tab record."""
        self.app.session.code_text = self.query_one("#code-edit", AsmArea).text
        if self.files:
            self.files[self.file_i]["text"] = self.app.session.code_text

    def on_asm_area_run_here(self, event) -> None:
        """Clicking the gutter run arrow triggers F5."""
        event.stop()
        self.action_run_code()

    def context_bits(self) -> str:
        return "   ·   ".join(self.context_parts())

    #: Top-right panel toggle buttons: (key, icon, label).
    TOGGLES = (
        ("side", "▌", "files", "^B"),
        ("dock", "▄", "dock", "F12"),
        ("explorer", "▐", "folders", "^E"),
    )

    def _toggles_wide(self) -> bool:
        """Decide whether the top bar has room for button text labels or icons only."""
        width = self.size.width or 120
        labels = sum(4 + len(label) for _w, _g, label, _k in self.TOGGLES)
        tail = len("   ·   ".join(self.context_parts()))
        return width - labels - tail - 6 >= self.TAB_ROOM

    #: Minimum width reserved for file tabs.
    TAB_ROOM = 18

    def _toggles_width(self) -> int:
        """Return total width of window-toggle buttons on the right of the top bar."""
        if not self._toggles_wide():
            return len(self.TOGGLES) * 3
        return sum(4 + len(label) for _w, _g, label, _k in self.TOGGLES)

    def _append_toggles(self, line) -> list[tuple[int, int, str]]:
        """Append panel toggle buttons to the top bar and return their hit zones."""
        zones: list[tuple[int, int, str]] = []
        wide = self._toggles_wide()
        for which, glyph, label, _key in self.TOGGLES:
            shown = {"side": self.side_shown, "dock": self.drawer_open,
                     "explorer": self.explorer_shown}[which]
            begin = line.cell_len
            line.append("  " + glyph,
                        style=palette.role_hex("accent2" if shown else "faint"))
            if wide:
                line.append(" " + label, style=palette.role_hex(
                    "dim" if shown else "faint"))
            zones.append((begin, line.cell_len, which))
        return zones

    def _toggle_tip(self) -> str:
        """Tooltip describing the panel toggle buttons and shortcuts."""
        return "   ·   ".join(f"{label} — {key}"
                              for _w, _g, label, key in self.TOGGLES)

    def on_file_strip_maximized(self, event) -> None:
        """Toggle full-screen editor mode, restoring prior sidebar/dock state."""
        event.stop()
        if self._maximized is None:
            self._maximized = (self.side_shown, self.drawer_open)
            if self.side_shown:
                self.action_toggle_side()
            if self.drawer_open:
                self.action_toggle_drawer()
        else:
            side, drawer = self._maximized
            self._maximized = None
            if side and not self.side_shown:
                self.action_toggle_side()
            if drawer and not self.drawer_open:
                self.action_toggle_drawer()
        self.refresh_context()
        self.refresh_hints()

    def on_file_strip_toggled(self, event) -> None:
        """Handle click on a top-bar panel toggle button."""
        event.stop()
        if event.which == "side":
            self.action_toggle_side()
        elif event.which == "explorer":
            self.action_toggle_explorer()
        else:
            self.action_toggle_drawer()
        self.refresh_context()

    def context_parts(self) -> list[str]:
        """Build prioritized metric chips for the right side of the top bar."""
        s = self.app.session
        bits = []
        if not self._is_asm():
            # Omit e2k block metrics for non-assembly files.
            name = self.files[self.file_i]["name"] if self.files else ""
            n = len(self.query_one("#code-edit", AsmArea).text.splitlines())
            bits.append(f"{n} {plural(n, 'line', 'lines', 'lines')}")
            bits.append("not e2k")
            if s.code_path:
                bits.append(s.code_path)
            return bits
        if self.parsed is not None and self.parsed.ops:
            src = self.comp.makespan if self.comp is not None else None
            orc = (self.orc.schedule.makespan
                   if self.orc is not None and not self._stale() else None)
            if src is not None and orc is not None:
                bits.append(f"{src}→{orc} cyc")
            elif src is not None:
                bits.append(f"{src} cyc")
            bits.append(f"{len(self.parsed.ops)} ops")
        else:
            bits.append("empty buffer")
        errs = sum(1 for p in self.problems if p.severity == "error")
        if errs:
            bits.append(f"^ {errs} {plural(errs, 'error', 'errors', 'errors')}")
        if self.app.session.code_path:
            bits.append(self.app.session.code_path)
        bits.append(s.model().name)
        return bits

    #: Max key-hint pairs shown in the status bar.
    MAX_HINTS = 5

    def refresh_hints(self) -> None:
        """Render key hints into the status bar, dropping trailing pairs if narrow."""
        try:
            keys = self.query_one("#code-keys", Static)
        except Exception:
            return
        # Drop trailing key hints first on narrow windows so metrics stay intact.
        width = self.size.width or 120
        room = 12 if width < 110 else width // 2 - 10
        key_c = palette.role_hex("accent_soft")
        dim = palette.role_hex("faint")
        t = Text()
        used = 0
        for k, v in self.hint_pairs():
            piece = len(k) + len(v) + 1
            if used + piece + (3 if used else 0) > room:
                break
            if used:
                t.append("   ")
                used += 3
            t.append(k, style=key_c)
            t.append(" " + v, style=dim)
            used += piece
        keys.update(t)

    def hint_pairs(self) -> list[tuple[str, str]]:
        """Return prioritized key-hint pairs for the status bar."""
        # Show F5/F6 hints only for `.s` buffers.
        pairs = [("F5", "run")] if self._is_asm() else []
        if self._is_asm() and self._have_orc():
            pairs.append(("F6", "rewrite"))
        # Panel toggles live in the top bar; keep dock zoom and mode picker here.
        pairs.append(("F11", "restore" if self.zoom else "maximize"))
        # Surface F12 dock hide shortcut in the status bar.
        pairs.append(("F12", "hide dock" if self.drawer_open else "show dock"))
        # Surface double-click tab maximize gesture.
        pairs.append(("2xclick", "maximize pane"))
        pairs.append(("^P", "command"))
        pairs.append(("^O", "modes"))
        return pairs[:self.MAX_HINTS]

    def toggle_hints(self) -> list[tuple[str, str]]:
        """Toggle hints are already merged into hint_pairs."""
        return []

    def extra_commands(self) -> list[dict]:
        return [
            {"name": "rewrite", "arg": "",
             "help": "rewrite buffer using exact-search schedule (F6)",
             "local": True},
            {"name": "example", "arg": "[" + "|".join(
                k for k, _, _ in EXAMPLES) + "]",
             "help": "example catalog: list all, or open by name in a tab",
             "local": True},
            {"name": "gen", "arg": "<count> <op> [packed]",
             "help": "generate test block: /gen 8 muls · /gen chain 5 fmul",
             "local": True},
            {"name": "fill", "arg": "<cycles>",
             "help": "generate N-cycle filler: /fill 20",
             "local": True},
            {"name": "rename", "arg": "<name>",
             "help": "rename active tab (F2)",
             "local": True},
        ]

    # --- live parsing -----------------------------------------------------

    def on_text_area_changed(self, event) -> None:
        """Debounce live buffer parsing by 250ms while typing."""
        event.stop()
        if self._debounce is not None:
            self._debounce.stop()
        self._debounce = self.set_timer(0.25, self.reparse)
        # Update completion popup immediately without debounce.
        self._update_suggest()

    def on_text_area_selection_changed(self, event) -> None:
        """Sync line inspector and schedule grid highlight when editor cursor moves."""
        event.stop()
        line = event.selection.end[0] + 1
        if line == self._cursor_line:
            return
        self._cursor_line = line
        self._update_suggest()
        self._draw_line_chip(line)
        self._sync_grid_cursor(line)
        # Only redraw INSPECT when that tab is visible.
        if self.drawer_open and self.drawer_tab == "line":
            self._draw_line_info(line)
            self._draw_chain(line)
            self._draw_bundles()
            # Keep cursor line number fresh in the dock tab summary.
            self._draw_dock_note()

    def _stale(self) -> bool:
        """Return True if cached exact-search results belong to older buffer text."""
        edit = self.query_one("#code-edit", AsmArea)
        return bool(self.run_text) and edit.text != self.run_text

    def reparse(self) -> None:
        """Parse buffer and refresh all instant (non-oracle) views."""
        self._debounce = None
        edit = self.query_one("#code-edit", AsmArea)
        text = edit.text
        if self._example and text != example_text(self._example):
            self._example = ""      # edited manually — no longer verbatim example
        self.app.session.code_text = text
        model = self.app.session.model()
        # Skip e2k parsing for non-`.s` files.
        edit.runnable = self._is_asm()
        edit.refresh()
        if not self._is_asm():
            self.parsed = None
            self.local_dag = None
            self.comp = None
            self.comp_problem = None
            self.unknown_share = 0.0
            self.problems = []
            self.redraw()
            self.refresh_status()
            return
        try:
            parsed = asm_parser.parse_asm(text, source="<buffer>")
        except Exception:
            parsed = None
        self.parsed = parsed
        self.local_dag = None
        self.comp = None
        self.comp_problem = None
        self.unknown_share = 0.0
        # Show parse errors even when zero ops parsed; run model linter only when ops exist.
        self.problems = list(parsed.problems) if parsed is not None else []
        if parsed is not None and parsed.ops:
            self.local_dag = asm_parser.build_dag(parsed, key="asm:buffer",
                                                  title="buffer")
            # Reuse `/load` validation so CODE and `/load` agree on schedule legality.
            self.comp, self.comp_problem = asm_parser.compiler_schedule_checked(
                parsed, self.local_dag, model)
            self.unknown_share = asm_parser.unknown_share(parsed)
            self.problems += asm_parser.lint(parsed, model)
        self.redraw()
        self.refresh_status()

    # --- F5 run -----------------------------------------------------------

    def _refuse_non_asm(self) -> bool:
        """Reject running non-e2k buffers with an explanatory note. True if rejected."""
        if self._is_asm():
            return False
        con = self.console
        if con is not None:
            name = self.files[self.file_i]["name"] if self.files else "file"
            con.note(f"  {name} is not e2k: scheduler reads wide bundles "
                     "in .s from lcc", "warning")
            self.open_drawer("term")
        return True

    def action_run_code(self) -> None:
        if self._refuse_non_asm():
            return
        self._sync_buffer()
        if not self.app.session.code_text.strip():
            con = self.console
            if con is not None:
                con.note("  buffer is empty — nothing to run", "error")
            return
        self.run_core("/code run")

    def after_command(self) -> None:
        """Pick up computed results after a core command finishes."""
        cached = self.app.session.peek()
        first = self.orc is None
        if cached is not None:
            self.base, self.orc, self.met = cached
            self.run_text = self.query_one("#code-edit", AsmArea).text
            self.findings = self._diagnose()
            # Fulfill deferred switch to oracle view once F5 completes.
            if self._want_orc:
                self._want_orc = False
                self.sched_view = "orc"
                self.open_drawer("sched")
            # Announce once per session that the buffer is now the active block in LAB/AGENT.
            con = self.console
            if first and con is not None:
                # Three short lines so wrap=False in OUTPUT does not clip.
                con.note("  buffer is now the active block", "accent2")
                con.note("  LAB (^O → 2): cycle-by-cycle view", "dim")
                con.note("  AGENT (3): grounded in these numbers", "dim")
                # Show one-time project support note after first successful optimization run.
                con.note("  found this useful? star/support the author: "
                         "pay.cloudtips.ru/p/7809ff65", "accent2_soft")
        # Sync editor text and tab name if `/code load` replaced the buffer.
        edit = self.query_one("#code-edit", AsmArea)
        if self.app.session.code_text != edit.text:
            edit.text = self.app.session.code_text
            self._example = ""
            if self.files:
                rec = self.files[self.file_i]
                rec["path"] = self.app.session.code_path
                rec["example"] = ""
                rec["name"] = self._buffer_name(rec)
        self.reparse()
        # Refresh status bar git commit count.
        self.refresh_status()
        # Refresh OUTPUT bridge buttons for the new run.
        self._sync_drawer_bridge()
        # Attach buffer source to the journal run so 'to CODE' can restore it.
        con = self.console
        if con is not None and con.runs:
            rec = con.runs[-1]
            if rec.get("cmd", "").lstrip("/").startswith("code"):
                rec["code"] = self.app.session.code_text

    def _diagnose(self) -> list:
        """Run doctor on the buffer schedule (falling back to baseline if illegal)."""
        sched = self.app.session.compiler_sched
        self.findings_from = "buffer"
        if sched is None:
            # Buffer schedule failed validation; diagnose greedy baseline instead.
            sched = self.base.schedule if self.base is not None else None
            self.findings_from = "greedy scheduler"
        if sched is None or self.met is None:
            return []
        try:
            d = doctor.diagnose(self.app.session.dag_obj, self.app.session.model(),
                                sched, self.met)
        except Exception:
            return []
        return list(d.findings)

    # --- rendering --------------------------------------------------------

    def refresh_context(self) -> None:
        """Top bar displays block metrics directly (no separate mode header)."""
        self._draw_title()

    def on_resize(self, event) -> None:
        """Re-align right-justified metrics and status hints on terminal resize."""
        super().on_resize(event)
        self._draw_title()
        self.refresh_hints()
        # Reflow status bar and cursor readout for the new terminal width.
        self._draw_status()
        self._draw_line_chip(self._cursor_line or 1)
        try:
            self._apply_dock_height(self.query_one("#code-dock", Vertical))
        except Exception:
            pass

    def _draw_title(self) -> None:
        """Render top file-tab strip with right-aligned metrics and panel toggles."""
        try:
            strip = self.query_one("#code-head", FileStrip)
        except Exception:
            return
        raised = palette.SURFACES["raised"]
        dim = palette.role_hex("dim")
        faint = palette.role_hex("faint")
        title = palette.role_hex("title")
        mark_c = palette.mode_hex(self.mode)

        head = Text()
        head.append(" ▌", style=mark_c)
        head.append("NEX ", style=f"{mark_c} bold")
        width = strip.size.width or 120
        # Drop lower-priority metric chips until metrics fit within half the top bar.
        parts = self.context_parts()
        tail = "   ·   ".join(parts)
        while len(parts) > 1 and len(tail) > width // 2:
            parts.pop()
            tail = "   ·   ".join(parts)
        # Reserve room for right-side panel toggle buttons before laying out tabs.
        room = width - head.cell_len - len(tail) - self._toggles_width() - 3

        n = len(self.files)
        if not n:
            # `refresh_context` may run during on_mount before the first tab is created.
            head.append(" " * max(1, width - head.cell_len - len(tail)
                                  - self._toggles_width() - 1))
            head.append(tail, style=dim)
            strip.spans = []
            strip.toggles = self._append_toggles(head)
            strip.tooltip = self._toggle_tip()
            strip.update(head)
            return
        # Never allow closing the last open tab.
        closable = n > 1
        chunks: list[Text] = []
        for i, rec in enumerate(self.files):
            on = i == self.file_i
            base = f"{title} bold on {raised}" if on else dim
            t = Text()
            t.append(f" {rec['name'][:22]}", style=base)
            # Mark dirty buffers directly on their tab.
            t.append(" *" if (on and self._stale()) else "  ",
                     style=(f"{palette.role_hex('warning')} on {raised}"
                            if on else faint))
            t.append(" x " if closable else " ",
                     style=(f"{dim} on {raised}" if on else faint))
            chunks.append(t)

        # Window open tabs around the active tab so it always stays visible.
        lo = hi = self.file_i
        used = chunks[self.file_i].cell_len
        while True:
            grew = False
            if hi + 1 < n and used + chunks[hi + 1].cell_len + 1 <= room:
                hi += 1
                used += chunks[hi].cell_len + 1
                grew = True
            if lo - 1 >= 0 and used + chunks[lo - 1].cell_len + 1 <= room:
                lo -= 1
                used += chunks[lo].cell_len + 1
                grew = True
            if not grew:
                break

        line = head
        spans: list[tuple[int, int, int, bool]] = []
        if lo:
            line.append(f" <{lo} ", style=faint)
        for i in range(lo, hi + 1):
            begin = line.cell_len
            line.append_text(chunks[i])
            spans.append((begin, line.cell_len, i, closable))
            line.append(" ", style=faint)
        if hi < n - 1:
            line.append(f"> {n - 1 - hi} ", style=faint)

        pad = max(1, width - line.cell_len - len(tail)
                  - self._toggles_width() - 2)
        line.append(" " * pad)
        line.append(tail, style=dim)
        strip.spans = spans
        strip.toggles = self._append_toggles(line)
        strip.tooltip = self._toggle_tip()
        strip.update(line)

    def _draw_side(self) -> None:
        """Render left catalog of machine examples and repository `.s` files."""
        try:
            box = self.query_one("#code-side-list", VerticalScroll)
        except Exception:
            return
        try:
            head = self.query_one("#side-head", Static)
            t = Text()
            t.append("FILES", style=palette.role_hex("title"))
            n = len(self.files)
            # Show tab count only when multiple tabs are open.
            if n > 1:
                t.append(f"   {n} "
                         f"{plural(n, 'tab', 'tabs', 'tabs')}",
                         style=palette.role_hex("faint"))
            head.update(t)
        except Exception:
            pass
        box.remove_children()
        rows: list = []
        title = palette.role_hex("title")
        dim = palette.role_hex("dim")
        faint = palette.role_hex("faint")

        # List open tabs first in the left sidebar.
        for i, rec in enumerate(self.files):
            t = Text()
            here = i == self.file_i
            t.append("  " + ("> " if here else "  "),
                     style=palette.role_hex("accent2" if here else "faint"))
            nm = rec["name"]
            t.append(nm if len(nm) <= 16 else nm[:15] + "…",
                     style=title if here else dim)
            item = SideItem(f"buf:{i}", t, classes="side-item")
            item.tooltip = (f"{rec['name']}\nclick — switch"
                            "\ndouble-click — rename")
            rows.append(item)


        # Allow creating `.s` blocks or `.md` notes from the sidebar.
        rows.append(Static(Text("\n new", style=title)))
        for suffix, label, _base, _seed in self.FILE_KINDS:
            t = Text()
            t.append("  + " + label, style=palette.role_hex("accent2"))
            item = SideItem(f"new:{suffix}", t, classes="side-item")
            item.tooltip = (f"new .{suffix} tab"
                            + ("" if suffix in ("s", "asm")
                               else "\nparsing and F5 apply only to .s"))
            rows.append(item)

        # Local file browsing lives in the right-side explorer (^E).

        # Keep sidebar shortcut labels within 20 columns.
        for key, what in (("^B ", "hide sidebar"),
                          ("F12", "hide dock"),
                          ("F2 ", "rename")):
            t = Text()
            t.append(" " + key + " ", style=palette.role_hex("accent_soft"))
            t.append(what, style=faint)
            rows.append(Static(t))
        box.mount(*rows)

    def _deletable(self, rel: str) -> bool:
        """Check whether `path` is inside the working directory and safe to delete."""
        if not rel or rel.startswith("new:") or rel.startswith("buf:"):
            return False
        path = Path(rel)
        if path.is_absolute():
            return False
        try:
            path.resolve().relative_to(Path.cwd().resolve())
        except (ValueError, OSError):
            return False
        return True

    def _delete_file(self, rel: str) -> None:
        """Delete a file from disk and close its open tab if present."""
        self._to_delete = ""
        if not self._deletable(rel):
            return
        con = self.console
        try:
            Path(rel).unlink()
        except OSError as exc:
            if con is not None:
                con.note(f"  failed to delete {rel}: {exc}", "error")
            self._draw_side()
            return
        if con is not None:
            con.note(f"  deleted {rel}", "warning")
        for i, rec in list(enumerate(self.files)):
            if rec.get("path") == rel and len(self.files) > 1:
                self.close_file(i)
                break
        else:
            for rec in self.files:
                if rec.get("path") == rel:
                    rec["path"] = ""
                    if self.app.session.code_path == rel:
                        self.app.session.code_path = ""
        self._draw_side()
        self._draw_explorer()
        self.refresh_context()

    def _rel(self, path) -> str:
        """Return path relative to working directory, or None if outside."""
        try:
            return str(path.relative_to(Path.cwd()))
        except ValueError:
            return str(path)

    def redraw(self) -> None:
        self._draw_hello()
        self._draw_title()
        self._draw_marks()
        self._draw_status()
        self._draw_grids()
        line = self.query_one("#code-edit", AsmArea).cursor_location[0] + 1
        self._draw_line_chip(line)
        # Skip dock tab redraws when the dock is closed.
        if self.drawer_open:
            self._draw_drawer()
        self.refresh_context()
        self.refresh_hints()

    def _draw_line_chip(self, line: int) -> None:
        """Left side of status bar: one-line summary of the op under cursor."""
        chip = self.query_one("#code-line-chip", LineChip)
        model = self.app.session.model()
        op = self._op_at_line(line)
        t = Text()
        t.append(f" ln.{line}", style=palette.role_hex("accent2"))
        if op is not None:
            t.append(f"  {op.op}", style=palette.op_style(op.op))
            t.append(f"  lat {model.latency(op.op)}",
                     style=palette.role_hex("dim"))
            t.append(f"  cyc {op.cycle}", style=palette.role_hex("dim"))
            orc = self._orc_cycle(op.index)
            if orc is not None and orc != op.cycle:
                # Spell out the gutter oracle arrow in the status bar.
                role = "success" if orc < op.cycle else "warning"
                t.append(f" → c{orc} oracle", style=palette.role_hex(role))
        else:
            t.append("  not an op", style=palette.role_hex("faint"))
        mine = [x for x in self.problems if x.line == line]
        if mine:
            t.append(f"  ^{len(mine)}", style=palette.role_hex("error"))
        # Show 'inspect >' cue on wider windows.
        if (self.size.width or 120) >= 120:
            t.append("  inspect >", style=palette.role_hex("faint"))
        else:
            t.append("  >", style=palette.role_hex("faint"))
        chip.tooltip = ("under cursor: line, op class, "
                        "latency, issue cycle\n"
                        "'→ cN oracle' — where exact search "
                        "places it (gutter c1→0 shows the same)\n"
                        "click — open INSPECT tab")
        chip.update(t)

    def repaint(self) -> None:
        self.query_one("#code-edit", AsmArea).refresh_theme()
        super().repaint()

    def _op_at_line(self, line: int):
        if self.parsed is None:
            return None
        for o in self.parsed.ops:
            if o.line == line:
                return o
        return None

    def _orc_cycle(self, instr: int) -> int | None:
        """Return exact-search cycle for `op_index` if results match current buffer."""
        if self.orc is None or self._stale():
            return None
        p = self.orc.schedule.placements.get(instr)
        return None if p is None else p.cycle

    def _draw_marks(self) -> None:
        """Populate the editor schedule gutter."""
        edit = self.query_one("#code-edit", AsmArea)
        marks: dict[int, tuple[str, RichStyle]] = {}
        bad = {p.line for p in self.problems if p.severity == "error"}
        warn = {p.line for p in self.problems if p.severity == "warn"}
        if self.parsed is not None:
            for o in self.parsed.ops:
                orc = self._orc_cycle(o.index)
                if orc is None:
                    # Omit channel in gutter label since it is already written on the line.
                    label = f"c{o.cycle}"
                    role = "dim"
                elif orc < o.cycle:
                    label = f"c{o.cycle}→{orc}"
                    role = "success"
                elif orc > o.cycle:
                    # Oracle scheduled op later than written (hazard in buffer).
                    label = f"c{o.cycle}→{orc}"
                    role = "warning"
                else:
                    # Omit `=` when oracle matches written cycle to avoid gutter clutter.
                    label = f"c{o.cycle}"
                    role = "faint"
                if o.line in bad:
                    label = "^ " + label
                    role = "error"
                elif o.line in warn:
                    label = "^ " + label
                    role = "warning"
                style = RichStyle(color=palette.role_hex(role),
                                  bold=role in ("success", "error"))
                marks[o.line - 1] = (label, style)
        for line in sorted(bad | warn):
            if line - 1 not in marks:
                role = "error" if line in bad else "warning"
                marks[line - 1] = ("^", RichStyle(color=palette.role_hex(role),
                                                  bold=True))
        edit.set_marks(marks)

    def _draw_hello(self) -> None:
        """Show welcome overlay on empty buffers; hide as soon as e2k ops appear."""
        try:
            hello = self.query_one("#code-hello", Static)
        except Exception:
            return
        has_ops = self.parsed is not None and bool(self.parsed.ops)
        text = self.query_one("#code-edit", AsmArea).text
        # Hide welcome overlay once the user starts typing.
        hello.display = (not has_ops) and len(text.strip()) < 200
        if not hello.display:
            return
        # Offset overlay past the left sidebar if open.
        try:
            edit = self.query_one("#code-edit", AsmArea)
            hello.styles.offset = (edit.region.x + 6, 2)
            hello.styles.width = max(40, min(64, edit.region.width - 8))
        except Exception:
            pass
        title = palette.role_hex("title")
        dim = palette.role_hex("dim")
        faint = palette.role_hex("faint")
        key = palette.role_hex("accent2")
        t = Text()
        t.append("\n  NEX · CODE", style=title)
        t.append("   Elbrus e2k wide-instruction scheduler\n\n", style=dim)
        # Keep welcome lines under 60 columns for clean wrapping.
        t.append("  bring your ", style=dim)
        t.append(".s from lcc -O3", style=palette.role_hex("accent"))
        t.append(",\n  to see where cycles are lost\n\n", style=dim)

        for k, what in (("^E", "explorer — find your .s on disk"),
                        ("F5", "run: compare compiler output vs oracle"),
                        ("2xclick", "on a dock tab — maximize pane")):
            t.append(f"  {k:<8}", style=key)
            t.append(what + "\n", style=dim)

        t.append("\n  no .s handy? ", style=faint)
        t.append("/example slots", style=key)
        t.append("  — sample block\n", style=faint)
        hello.update(t)

    def _draw_status(self) -> None:
        """Right side of status bar: slot utilization and recoverable cycles."""
        line = Text()
        dim = palette.role_hex("dim")
        # Clearly label non-e2k files in the status bar.
        if not self._is_asm():
            name = self.files[self.file_i]["name"] if self.files else ""
            suffix = name.rsplit(".", 1)[-1] if "." in name else "?"
            line.append(f".{suffix} — not e2k", style=palette.role_hex("warning"))
            line.append("   ·   parsing and F5 are for .s only", style=dim)
            self.query_one("#code-status", Static).update(line)
            return
        if self.parsed is None or not self.parsed.ops:
            if self.problems:
                bad = len(self.problems)
                line.append(f"no valid ops: {bad} "
                            f"{plural(bad, 'line', 'lines', 'lines')} "
                            f"unparsed", style=palette.role_hex("warning"))
            else:
                line.append("empty buffer", style=dim)
            self.query_one("#code-status", Static).update(line)
            return
        if self.comp is not None:
            slots = self.comp.slot_utilization
            line.append(f"slots {slots * 100:.0f}%", style=dim)
            if self._have_orc():
                line.append(f" → {self.orc.schedule.slot_utilization * 100:.0f}%",
                            style=palette.role_hex("success"))
        else:
            # Stop here when buffer schedule is invalid.
            line.append("invalid", style=palette.role_hex("warning"))
            self.query_one("#code-status", Static).update(line)
            return
        if self._have_orc():
            orc = self.orc.schedule.makespan
            src = self.comp.makespan if self.comp is not None else None
            # Suppress slack claim when unknown ops dominate (placeholder latency 1).
            if src is not None and self.unknown_share >= asm_parser.UNKNOWN_SHARE_LIMIT:
                line.append(f"   ·   cannot compare: "
                            f"{self.unknown_share:.0%} of ops unknown to model",
                            style=palette.role_hex("warning"))
            elif src is not None and src > orc:
                gap = src - orc
                line.append(f"   ·   gain {gap} cyc "
                            f"({100 * gap / src:.0f}%)",
                            style=palette.role_hex("success"))
            elif src is not None:
                line.append("   ·   no slack", style=dim)
        elif self._stale():
            line.append("   ·   edited — press F5",
                        style=palette.role_hex("warning"))
        elif (self.size.width or 120) >= 110:
            # Show F5 hint only when it fits without truncation.
            line.append("   ·   F5 — compute bound",
                        style=palette.role_hex("accent2"))
        self.query_one("#code-status", Static).update(line)

    # --- schedule grid ----------------------------------------------------

    def _cell_w(self) -> int:
        """Compute cell width dynamically so all six channels always stay visible."""
        # Horizontal grid scrolls cycles sideways, so cells keep comfortable width.
        return 8

    def _have_orc(self) -> bool:
        return self.orc is not None and not self._stale()

    def _draw_grids(self) -> None:
        """Render schedule grid: single toggleable view in dock, side-by-side when zoomed."""
        self._grid_cells = {}
        both = self._sched_expanded and self._have_orc()
        if self.sched_view == "orc" and not self._have_orc():
            self.sched_view = "src"
        # Fall back to oracle grid when buffer schedule is illegal.
        if self.comp is None and self._have_orc():
            self.sched_view = "orc"
            both = False
        left = (self.comp if (both or self.sched_view == "src")
                else self.orc.schedule)
        which = "src" if (both or self.sched_view == "src") else "orc"
        self._fill_grid("code-grid", left, which)

        for tool, name in (("#tab-src", "src"), ("#tab-orc", "orc")):
            self.query_one(tool, Tool).set_on(
                both or self.sched_view == name)

        self._sched_left = left
        self._sched_which = which
        if self.drawer_tab == "sched":
            self._draw_dock_note()
        self._draw_sched_side()
        self._draw_sched_empty(left)

        wrap = self.query_one("#code-grid-orc-wrap")
        # Reserve second-grid slot when maximized so grid width does not jump on F5.
        wrap.display = both or bool(self.zoom and self.drawer_tab == "sched")
        head = self.query_one("#code-grid-orc-head", Static)
        if both:
            head.update(
                Text(f"  exact search   ·   {self.orc.schedule.makespan} cyc",
                     style=palette.role_hex("accent")))
            self._fill_grid("code-grid-orc", self.orc.schedule, "orc")
        elif wrap.display:
            t = Text()
            t.append("  exact search\n", style=palette.role_hex("faint"))
            if self.parsed is None or not self.parsed.ops:
                t.append("  nothing to compute: no e2k ops in buffer\n",
                         style=palette.role_hex("faint"))
            else:
                t.append("  F5", style=palette.role_hex("accent2"))
                t.append("  compute how tightly this graph can pack\n",
                         style=palette.role_hex("dim"))
                t.append("  the second grid will appear here — cycle by cycle "
                         "next to the first\n", style=palette.role_hex("faint"))
            head.update(t)
            self.query_one("#code-grid-orc", DataTable).clear(columns=True)

    def _draw_sched_empty(self, left) -> None:
        """Explain why the schedule grid is empty and what to do next."""
        try:
            note = self.query_one("#sched-empty", Static)
            wrap = self.query_one("#code-grid-wrap")
        except Exception:
            return
        t = Text()
        if self.parsed is None or not self.parsed.ops:
            t.append("  no e2k operations in buffer.\n\n",
                     style=palette.role_hex("dim"))
            t.append("  ^B", style=palette.role_hex("accent2"))
            t.append("  open catalog to load an example or real .s\n",
                     style=palette.role_hex("dim"))
            if self.problems:
                bad = len(self.problems)
                t.append(f"  ISSUES tab  why "
                         f"{bad} "
                         f"{plural(bad, 'line', 'lines', 'lines')} failed to parse\n",
                         style=palette.role_hex("warning"))
        elif left is None:
            t.append("  buffer schedule could not be built: "
                     "channel assignment conflicts with machine model.\n\n",
                     style=palette.role_hex("warning"))
            t.append("  ISSUES tab", style=palette.role_hex("accent2"))
            t.append("  see what conflicted\n",
                     style=palette.role_hex("dim"))
            t.append("  F5", style=palette.role_hex("accent2"))
            t.append("  exact search can still run: it builds "
                     "a fresh schedule from dependencies\n",
                     style=palette.role_hex("dim"))
        else:
            note.display = False
            wrap.display = True
            return
        note.update(t)
        note.display = True
        # Hide empty DataTable while showing the empty-state explanation.
        wrap.display = False

    def _draw_sched_side(self) -> None:
        """Render port utilization and suggested moves sidebar for maximized grid."""
        try:
            target = self.query_one("#sched-side-body", Static)
        except Exception:
            return
        model = self.app.session.model()
        t = Text()
        dim = palette.role_hex("dim")
        if self.comp is None and not self._have_orc():
            target.update(Text("no schedule yet — F5", style=dim))
            return

        # Compact single-line port summary in the low dock.
        try:
            avail = max(4, self.query_one("#sched-side").size.height - 1)
        except Exception:
            avail = 9

        t.append("PORTS  ", style=palette.role_hex("title"))
        for port in range(model.width):
            src = self._port_load(self.comp, port)
            t.append(f"{model.port_label(port)}:", style=palette.role_hex("faint"))
            t.append(f"{src} ", style=palette.role_hex("text" if src else "faint"))
        t.append("\n")
        if self._have_orc():
            t.append("oracle  ", style=palette.role_hex("faint"))
            for port in range(model.width):
                src = self._port_load(self.comp, port)
                orc = self._port_load(self.orc.schedule, port)
                role = "success" if orc > src else ("dim" if orc == src
                                                    else "warning")
                t.append(f"{model.port_label(port)}:",
                         style=palette.role_hex("faint"))
                t.append(f"{orc} ", style=palette.role_hex(role))
            t.append("\n")
        if self.comp is not None:
            t.append(f"slots {self.comp.slot_utilization * 100:.0f}%", style=dim)
            if self._have_orc():
                t.append(f"  →  "
                         f"{self.orc.schedule.slot_utilization * 100:.0f}%",
                         style=palette.role_hex("success"))
            t.append("\n")

        # Show cursor cell details above suggested moves.
        if self.zoom:
            t.append_text(self._sched_cursor_text())

        moves = self._moves()
        if moves:
            # Cap suggested moves to remaining sidebar height.
            room = max(1, avail - (4 if self._have_orc() else 3)
                       - (12 if self.zoom else 0))
            t.append(f"\nMOVE   {len(moves)}\n",
                     style=palette.role_hex("title"))
            shown = moves[:room]
            for line, text in shown:
                t.append_text(text)
                t.append("\n")
            if len(moves) > len(shown):
                t.append(f"      +{len(moves) - len(shown)} more"
                         f"  —  F12 to expand\n",
                         style=palette.role_hex("faint"))
            t.append("\nF6 applies this schedule to the buffer\n",
                     style=palette.role_hex("accent2"))
        elif self._have_orc():
            t.append("\nnothing to move: buffer already matches "
                     "the exact-search schedule\n",
                     style=palette.role_hex("success"))
        else:
            t.append("\nF5 — compute suggested moves\n", style=dim)
        target.update(t)

    def _sched_cursor_text(self) -> Text:
        """Render cursor cell details and channel counts in maximized grid."""
        dim = palette.role_hex("dim")
        faint = palette.role_hex("faint")
        t = Text()
        sched = self._sched_left
        if sched is None:
            return t
        model = self.app.session.model()
        try:
            table = self.query_one("#code-grid", DataTable)
            row, col = table.cursor_coordinate
        except Exception:
            return t
        # Default to first cycle/port when cursor is on the frozen label column.
        col = max(col, 1)
        cycle, port = ((row, col - 1) if self._tall_grid()
                       else (col - 1, row))

        t.append("\nCURSOR\n", style=palette.role_hex("title"))
        t.append(f"cycle {cycle}   channel {model.port_label(port)}\n",
                 style=dim)
        instr = self._grid_cells.get((self._sched_which, cycle, port))
        if instr is not None and self.parsed is not None \
                and instr < len(self.parsed.ops):
            op = self.parsed.ops[instr]
            t.append(f"  {op.mnemonic}", style=palette.op_style(op.op))
            t.append(f"   ln.{op.line}\n", style=dim)
            t.append(f"  {op.op} · latency {model.latency(op.op)} cyc",
                     style=dim)
            if model.occupancy(op.op) > 1:
                t.append(f" · holds port {model.occupancy(op.op)} cyc",
                         style=dim)
            t.append("\n")
        else:
            t.append("  slot empty\n", style=faint)
            takes = [n for n in model.ops if port in model.channels_for(n)]
            if takes:
                t.append("  channel accepts: ", style=faint)
                t.append(" ".join(sorted({n for n in takes})[:6]), style=dim)
                t.append("\n")

        t.append("\nCHANNELS\n", style=palette.role_hex("title"))
        span = max(sched.span_cycles, 1)
        for p_i in range(model.width):
            load = self._port_load(sched, p_i)
            filled = round(10 * load / span) if span else 0
            t.append(f"{model.port_label(p_i)} ", style=faint)
            t.append("█" * filled, style=palette.role_hex(
                "warning" if filled >= 8 else "accent2"))
            t.append("·" * (10 - filled), style=faint)
            t.append(f" {load}\n", style=dim if load else faint)
        return t

    def _port_load(self, sched, port: int) -> int:
        """Count operations issued on `port` across the schedule."""
        if sched is None:
            return 0
        return sum(1 for p in sched.placements.values() if p.channel == port)

    def _tall_cell_w(self, channels: int) -> int:
        """Compute cell width for the maximized grid based on available screen width."""
        side = 40 if self.zoom else 0
        # Always split maximized grid width in two to prevent layout jumps.
        grids = 2 if self._sched_expanded else 1
        room = max(24, ((self.size.width or 120) - side) // grids)
        return max(6, min(11, (room - 10) // max(1, channels)))

    def _tall_grid(self) -> bool:
        """Choose vertical (cycles as rows) when maximized, horizontal in compact dock."""
        return bool(self.zoom) and self.drawer_tab == "sched"

    def _fill_grid(self, table_id: str, sched, which: str) -> None:
        table = self.query_one("#" + table_id, DataTable)
        table.clear(columns=True)
        if sched is None or self.parsed is None:
            return
        if self._tall_grid():
            self._fill_grid_tall(table, sched, which)
            return
        model = self.app.session.model()
        dag = sched.dag
        busy = sched.busy_map()
        used = {p.channel for p in sched.placements.values()}
        cw = self._cell_w()
        span = max(sched.span_cycles, 1)

        # Pin channel label as a frozen first column so it stays visible while scrolling.
        table.add_column(Text(""), width=3, key="chan")

        # Compact dock uses horizontal layout (cycles as columns, 6 channels as rows).
        for cycle in range(span):
            head = Text(f"c{cycle}", style=palette.role_hex("dim"))
            table.add_column(head, width=cw, key=str(cycle))

        # Highlight illegal cells only in the as-written schedule (oracle is always legal).
        bad = ({p.op for p in self.problems
                if p.severity == "error" and p.op >= 0}
               if which == "src" else set())

        for port in range(model.width):
            cells = []
            for cycle in range(span):
                slot = busy.get((cycle, port))
                if slot is None:
                    cells.append(Text(f" {EMPTY}",
                                      style=palette.role_hex("faint")))
                    continue
                instr, head_cell = slot
                self._grid_cells[(which, cycle, port)] = instr
                style = palette.op_style(dag[instr].op)
                if not head_cell:
                    # Multi-cycle continuation extends right in horizontal layout.
                    cells.append(Text(" " + CONT * max(1, cw - 2), style=style))
                    continue
                cells.append(self._cell_text(instr, cw, instr in bad))
            idle = port not in used
            head = Text(model.port_label(port),
                        style=palette.role_hex("faint" if idle else "dim"))
            table.add_row(head, *cells)

    def _fill_grid_tall(self, table, sched, which: str) -> None:
        """Fill vertical schedule grid: cycles as rows, channels as columns."""
        model = self.app.session.model()
        dag = sched.dag
        busy = sched.busy_map()
        span = max(sched.span_cycles, 1)
        # Size columns dynamically so all six channels (including ,5) fit.
        cw = self._tall_cell_w(model.width)

        table.add_column(Text(""), width=8, key="cycle")
        for port in range(model.width):
            table.add_column(Text(model.port_label(port),
                                  style=palette.role_hex("dim")),
                             width=cw, key=f"p{port}")

        bad = ({p.op for p in self.problems
                if p.severity == "error" and p.op >= 0}
               if which == "src" else set())

        for cycle in range(span):
            cells = []
            taken = 0
            for port in range(model.width):
                slot = busy.get((cycle, port))
                if slot is None:
                    cells.append(Text(f" {EMPTY}",
                                      style=palette.role_hex("faint")))
                    continue
                taken += 1
                instr, head_cell = slot
                self._grid_cells[(which, cycle, port)] = instr
                style = palette.op_style(dag[instr].op)
                if not head_cell:
                    # Multi-cycle continuation extends down in vertical layout.
                    cells.append(Text(" │", style=style))
                    continue
                cells.append(self._cell_text(instr, cw, instr in bad))
            head = Text(f"c{cycle}".ljust(4),
                        style=palette.role_hex("dim" if taken else "faint"))
            head.append(f"{taken}/{model.width}",
                        style=palette.role_hex(
                            "warning" if taken * 2 <= model.width else "text")
                        if taken else palette.role_hex("faint"))
            table.add_row(head, *cells)

    def _cell_text(self, instr: int, width: int, bad: bool) -> Text:
        """Render a grid cell using the source mnemonic rather than an internal ID."""
        op = None
        if self.parsed is not None and instr < len(self.parsed.ops):
            op = self.parsed.ops[instr]
        name = op.mnemonic if op is not None else f"i{instr}"
        style = palette.op_style(op.op if op is not None else "ADD")
        if bad:
            style = palette.role_hex("error") + " bold"
        t = Text(" ")
        t.append(name[:width - 1], style=style)
        return t

    # Row label carries cycle and slot load in vertical layout.

    def _sync_grid_cursor(self, line: int) -> None:
        """Sync editor cursor line to the corresponding schedule grid cell."""
        op = self._op_at_line(line)
        if op is None:
            return
        for (which, cycle, port), instr in self._grid_cells.items():
            if which != "src" or instr != op.index:
                continue
            table = self.query_one("#code-grid", DataTable)
            # Map grid coordinates based on orientation (+1 for frozen label column).
            row, col = ((cycle, port) if self._tall_grid() else (port, cycle))
            if row < table.row_count and col + 1 < len(table.columns):
                table.move_cursor(row=row, column=col + 1)
            return

    def on_data_table_cell_highlighted(self, event) -> None:
        """Refresh cursor cell inspector when moving inside the schedule grid."""
        if self.zoom and self.drawer_tab == "sched":
            self._draw_sched_side()

    def on_data_table_cell_selected(self, event) -> None:
        """Clicking a grid cell jumps the editor cursor to that op's source line."""
        event.stop()
        which = "orc" if event.data_table.id == "code-grid-orc" else "src"
        # Ignore clicks on the frozen label column (col 0).
        if self._tall_grid():
            cycle, port = event.coordinate.row, event.coordinate.column - 1
        else:
            cycle, port = event.coordinate.column - 1, event.coordinate.row
        instr = self._grid_cells.get((which, cycle, port))
        if instr is None or self.parsed is None or instr >= len(self.parsed.ops):
            return
        self._goto_line(self.parsed.ops[instr].line)

    # --- issues -----------------------------------------------------------

    def _draw_lint(self) -> None:
        """Render ISSUES tab: machine linter hazards first, then cycle-loss findings."""
        scroll = self.query_one("#dock-lint", VerticalScroll)
        scroll.remove_children()
        self._lint_lines = []
        limit = None if self._lint_expanded else 4

        errs = [p for p in self.problems if p.severity == "error"]
        warns = [p for p in self.problems if p.severity == "warn"]
        infos = [p for p in self.problems if p.severity == "info"]
        shown = (errs + warns + infos)[:limit]

        widgets: list = []
        if shown:
            widgets.append(Static(self._section(
                "machine", f"{len(errs)} errors · {len(warns)} warnings"
                if (errs or warns) else "", first=True)))
            for p in shown:
                item = LintItem(p.line, self._lint_text(p),
                                classes="lint-item")
                # Full issue text and fix hint in tooltip.
                item.tooltip = f"ln.{p.line}  ·  {p.text}\nclick — jump here"
                widgets.append(item)
                self._lint_lines.append(p.line)
        elif self.parsed is not None and self.parsed.ops:
            widgets.append(Static(Text("  no machine hazards",
                                       style=palette.role_hex("success"))))
            widgets.append(Static(self._checked_text()))

        if self.findings and not self._stale():
            widgets.append(Static(self._section(
                "cycle losses",
                "from buffer schedule" if self.findings_from == "buffer"
                else "buffer conflicts with model — showing greedy")))
            for f in (self.findings if self._lint_expanded
                      else self.findings[:3]):
                line = self._finding_line(f)
                item = LintItem(line, self._finding_text(f),
                                classes="lint-item")
                item.tooltip = (f"{f.title}: {f.why}\nclick — jump to "
                                f"ln.{line}")
                widgets.append(item)
                self._lint_lines.append(line)
        elif self.orc is None:
            widgets.append(Static(Text("\n  F5 — find where cycles "
                                       "are lost",
                                       style=palette.role_hex("dim"))))

        # Actionable move list (applied automatically by F6).
        moves = self._moves()
        if moves:
            widgets.append(Static(self._section(
                "suggested moves", "F6 applies automatically")))
            for line, text in (moves if self._lint_expanded else moves[:4]):
                item = LintItem(line, text, classes="lint-item")
                item.tooltip = f"click — jump to ln.{line}"
                widgets.append(item)
                self._lint_lines.append(line)
            if not self._lint_expanded and len(moves) > 4:
                widgets.append(Static(Text(
                    f"      +{len(moves) - 4} more ops",
                    style=palette.role_hex("faint"))))
        if not self._lint_expanded and len(self.problems) > 4:
            widgets.append(Static(Text(
                f"\n  +{len(self.problems) - 4} more — 2xclick tab",
                style=palette.role_hex("faint"))))
        if widgets:
            scroll.mount(*widgets)
        # Dock tab header is owned by `_draw_drawer`.

    def _checked_text(self) -> Text:
        """Show what the live linter verified when there are zero hazards."""
        dim = palette.role_hex("dim")
        faint = palette.role_hex("faint")
        model = self.app.session.model()
        parsed = self.parsed
        t = Text()
        n = len(parsed.ops)
        t.append(f"\n  {n} ", style=palette.role_hex("text"))
        t.append(f"{plural(n, 'op', 'ops', 'ops')} "
                 f"in {parsed.bundles} "
                 f"{plural(parsed.bundles, 'wide bundle', 'wide bundles', 'wide bundles')}\n",
                 style=dim)
        t.append("  channels legal, operands ready on time\n", style=dim)

        # Show op classes and latencies verified by the live linter.
        heavy: dict[str, int] = {}
        for op in parsed.ops:
            if model.latency(op.op) > 1:
                heavy[op.op] = heavy.get(op.op, 0) + 1
        for cls, count in sorted(heavy.items(), key=lambda kv: -kv[1])[:3]:
            chans = ",".join(str(c) for c in model.channels_for(cls))
            t.append(f"  {cls}", style=palette.op_style(cls))
            t.append(f" x{count}   lat {model.latency(cls)} cyc   "
                     f"channels {chans}\n", style=faint)
        if self.comp is not None:
            free = model.width - round(
                self.comp.slot_utilization * model.width)
            t.append(f"  slot utilization "
                     f"{self.comp.slot_utilization * 100:.0f}% — "
                     f"{free} of {model.width} channels idle\n",
                     style=palette.role_hex(
                         "warning" if free >= 4 else "dim"))
        return t

    def _moves(self) -> list[tuple[int, Text]]:
        """List ops that exact search schedules earlier, sorted by cycle gain."""
        if not self._have_orc() or self.parsed is None:
            return []
        out = []
        for o in self.parsed.ops:
            pl = self.orc.schedule.placements.get(o.index)
            if pl is None or pl.cycle >= o.cycle:
                continue
            t = Text()
            t.append(f" ↑ ", style=palette.role_hex("success"))
            t.append(f"ln.{o.line}", style=palette.role_hex("accent2"))
            t.append(f"  {o.mnemonic}", style=palette.op_style(o.op))
            t.append(f"  c{o.cycle} → c{pl.cycle}",
                     style=palette.role_hex("text"))
            t.append(f", ch ,{pl.channel}", style=palette.role_hex("dim"))
            out.append((o.cycle - pl.cycle, o.line, t))
        out.sort(key=lambda x: (-x[0], x[1]))
        return [(line, t) for _, line, t in out]

    def _section(self, label: str, note: str = "", first: bool = False) -> Text:
        t = Text()
        if not first:
            t.append("\n")
        t.append("  " + label.upper(), style=palette.role_hex("title"))
        # Omit section subtitle when narrow so it does not wrap.
        if note and len(label) + len(note) + 5 <= self._lint_width():
            t.append("   " + note, style=palette.role_hex("faint"))
        return t

    def _lint_width(self) -> int:
        try:
            return self.query_one("#code-dock", Vertical).size.width - 4
        except Exception:
            return 40

    #: Severity badge matching doctor findings.
    MARKS = {"error": ("^", "error"), "warn": ("^", "warning"),
             "info": ("·", "dim")}

    def _lint_text(self, p) -> Text:
        mark, role = self.MARKS.get(p.severity, ("·", "dim"))
        t = Text()
        t.append(f" {mark} ", style=palette.role_hex(role))
        t.append(f"ln.{p.line}", style=palette.role_hex("accent2"))
        t.append("  " + p.text, style=palette.role_hex("text"))
        if p.hint and self._lint_expanded:
            t.append("\n      " + p.hint, style=palette.role_hex("dim"))
        return t

    def _finding_line(self, f) -> int:
        """Return source line number associated with a doctor finding."""
        if not f.instrs or self.parsed is None:
            return 0
        instr = f.instrs[0]
        if instr < len(self.parsed.ops):
            return self.parsed.ops[instr].line
        return 0

    def _finding_text(self, f) -> Text:
        role = {"high": "error", "medium": "warning"}.get(f.severity, "dim")
        if f.kind == "limit":
            role = "accent"
        t = Text()
        t.append(f" {f.mark():>2} ", style=palette.role_hex(role))
        t.append(f.title, style=palette.role_hex("text"))
        if f.cycles_lost:
            t.append(f"  -{f.cycles_lost} cyc", style=palette.role_hex(role))
        if self._lint_expanded:
            t.append("\n      " + f.why, style=palette.role_hex("dim"))
            t.append("\n      " + f.fix, style=palette.role_hex("faint"))
        return t

    def on_lint_item_picked(self, event) -> None:
        event.stop()
        if event.line:
            self._goto_line(event.line)

    def _goto_line(self, line: int) -> None:
        edit = self.query_one("#code-edit", AsmArea)
        # Unzoom dock when jumping to a source line so the code is visible.
        if self.zoom:
            self.set_zoom("")
        edit.goto_line(line)
        edit.focus()

    # --- cursor cycle inspector -------------------------------------------

    def _bundle_at(self, line: int):
        """Return `(cycle, [ops])` for the wide bundle containing the cursor."""
        if self.parsed is None or not self.parsed.ops:
            return None, []
        edit = self.query_one("#code-edit", AsmArea)
        lines = edit.document.lines
        row = max(0, min(line - 1, len(lines) - 1))
        # Scan upward to `{` and downward to `}`.
        start = row
        while start > 0 and "{" not in lines[start]:
            if "}" in lines[start] and start != row:
                break
            start -= 1
        end = row
        while end < len(lines) - 1 and "}" not in lines[end]:
            if "{" in lines[end] and end != row:
                break
            end += 1
        inside = [o for o in self.parsed.ops if start + 1 <= o.line <= end + 1]
        if not inside:
            # If cursor is outside bundles (file header), pick the next bundle.
            later = [o for o in self.parsed.ops if o.line > line]
            if not later:
                return None, []
            cycle = later[0].cycle
            return cycle, [o for o in self.parsed.ops if o.cycle == cycle]
        return inside[0].cycle, inside

    def _draw_bundles(self) -> None:
        """Render buffer-wide cycle catalog showing slot occupancy bars."""
        box = self.query_one("#dock-bundles", VerticalScroll)
        box.remove_children()
        if self.parsed is None or not self.parsed.ops:
            box.mount(Static(Text("  empty buffer",
                                  style=palette.role_hex("dim"))))
            return
        model = self.app.session.model()
        width = model.width
        by_cycle: dict[int, list] = {}
        for o in self.parsed.ops:
            by_cycle.setdefault(o.cycle, []).append(o)

        rows = []
        head = Text()
        head.append("  cyc    slots      ops", style=palette.role_hex("dim"))
        rows.append(Static(head))
        span = max(by_cycle) + 1 if by_cycle else 0
        for cycle in range(span):
            ops = by_cycle.get(cycle, [])
            k = len(ops)
            t = Text()
            t.append(f"  c{cycle:<5}", style=palette.role_hex("accent2"))
            role = "success" if k >= width - 1 else (
                "error" if k <= 1 else "warning")
            # Slot occupancy bar for each cycle.
            t.append("█" * k, style=palette.role_hex(role))
            t.append("·" * (width - k), style=palette.role_hex("faint"))
            t.append(f" {k}/{width}  ", style=palette.role_hex(role))
            if ops:
                t.append("  ".join(f"{o.mnemonic},{o.channel}"
                                   if o.channel is not None else o.mnemonic
                                   for o in ops[:4]),
                         style=palette.op_style(ops[0].op))
            else:
                t.append("idle", style=palette.role_hex("faint"))
            line = ops[0].line if ops else 0
            rows.append(LintItem(line, t, classes="lint-item"))
        box.mount(*rows)

    def _draw_line_info(self, line: int, target_id: str = "#code-line-info") -> None:
        """Render INSPECT breakdown for the cycle/bundle under the cursor."""
        target = self.query_one(target_id, Static)
        model = self.app.session.model()
        cycle, ops = self._bundle_at(line)
        t = Text()
        if cycle is None:
            t.append("empty buffer — type an e2k operation\n",
                     style=palette.role_hex("dim"))
            target.update(t)
            return

        # Show cursor op details above the full cycle summary.
        op = self._op_at_line(line)
        if op is not None:
            t.append(f"ln.{op.line}  ", style=palette.role_hex("accent2"))
            t.append(op.mnemonic, style=palette.op_style(op.op))
            t.append(f"   latency {model.latency(op.op)}",
                     style=palette.role_hex("dim"))
            orc = self._orc_cycle(op.index)
            if orc is not None and orc != op.cycle:
                t.append(f"   oracle: c{orc}", style=palette.role_hex("success"))
            t.append("\n\n")

        used = {o.channel: o for o in ops if o.channel is not None}
        width = model.width
        t.append(f"CYCLE {cycle}", style=palette.role_hex("title"))
        k = len(ops)
        role = "success" if k >= width - 1 else ("error" if k <= 1 else "warning")
        t.append(f"   used {k} of {width}\n\n", style=palette.role_hex(role))

        # List occupied and free channels for this cycle in order.
        for port in range(width):
            op = used.get(port)
            t.append(f" {model.port_label(port):>3} ", style=palette.role_hex("dim"))
            if op is not None:
                t.append(f"{op.mnemonic:<8}", style=palette.op_style(op.op))
                t.append(f"ln.{op.line}", style=palette.role_hex("accent2"))
                orc = self._orc_cycle(op.index)
                if orc is not None and orc != op.cycle:
                    t.append(f"  → c{orc}", style=palette.role_hex("success"))
            else:
                # Show op classes accepted by each idle channel.
                t.append("empty ", style=palette.role_hex("faint"))
                for cls in ("ADD", "MUL", "LOAD", "STORE", "DIV"):
                    if port in model.channels_for(cls):
                        t.append(cls + " ", style=palette.op_style(cls))
            t.append("\n")

        # Summarize how exact search treats this cycle.
        if ops and self.orc is not None and not self._stale():
            moved = [o for o in ops if (self._orc_cycle(o.index) or o.cycle) != o.cycle]
            t.append("\n")
            if moved:
                t.append(f"exact search moves {len(moved)} of {k} ops out\n",
                         style=palette.role_hex("success"))
            else:
                t.append("exact search keeps this cycle as is\n",
                         style=palette.role_hex("dim"))

        mine = [p for p in self.problems
                if any(o.line == p.line for o in ops) or p.line == line]
        if mine:
            t.append("\nissues\n", style=palette.role_hex("title"))
            for p in mine[:4]:
                mark, role = self.MARKS.get(p.severity, ("·", "dim"))
                t.append(f" {mark} ln.{p.line} {p.text}\n",
                         style=palette.role_hex(role))
        target.update(t)

    # --- dock zoom --------------------------------------------------------

    def open_block(self, tab: str) -> None:
        """Maximize a dock tab in place inside CODE."""
        # Double-clicking the zoomed tab restores; double-clicking another switches.
        same = self.zoom and self.drawer_open and self.drawer_tab == tab
        self.open_drawer(tab)
        self.set_zoom("" if same else "dock")

    def action_zoom_dock(self) -> None:
        """Toggle full-screen dock mode (F11 or double-clicking a dock tab)."""
        self.set_zoom("" if self.zoom else "dock")

    def set_zoom(self, zoom: str) -> None:
        self.zoom = zoom
        self.set_class(bool(zoom), "zoom-dock")
        # Clear manual inline height during full-screen zoom and restore afterward.
        try:
            dock = self.query_one("#code-dock", Vertical)
            dock.styles.height = None if zoom else self.dock_h
        except Exception:
            pass
        # Ensure dock is visible when zoomed.
        if zoom and not self.drawer_open:
            self.open_drawer(self.drawer_tab)
        if self.drawer_tab == "core":
            self._draw_core_state()
        if zoom and self.drawer_tab == "agent":
            # Reflow AGENT facts after layout width is computed.
            self.call_after_refresh(self._draw_agent_extras)
        if zoom and self.drawer_tab == "sched":
            # Refill maximized schedule grid once final table width is known.
            self.call_after_refresh(self._draw_grids)
        self._sched_expanded = bool(zoom) and self.drawer_tab == "sched"
        self._lint_expanded = bool(zoom) and self.drawer_tab == "lint"
        self._console_expanded = bool(zoom) and self.drawer_tab == "term"
        self._draw_grids()
        if self.drawer_open:
            self._draw_drawer()
        self.refresh_hints()

    def _draw_chain(self, line: int) -> None:
        """Render dependency chain (producers and consumers) for the cursor op."""
        target = self.query_one("#code-chain-body", Static)
        t = Text()
        if self.local_dag is None or self.parsed is None:
            target.update(t)
            return
        op = self._op_at_line(line)
        if op is None:
            # Fall back to first op in bundle when cursor is on a brace or comment.
            _cycle, ops = self._bundle_at(line)
            op = ops[0] if ops else None
        if op is None:
            target.update(t)
            return
        model = self.app.session.model()
        dag = self.local_dag
        t.append("CHAIN\n\n", style=palette.role_hex("title"))

        preds = dag[op.index].preds if op.index < len(dag) else ()
        t.append("producers\n", style=palette.role_hex("dim"))
        if not preds:
            t.append("  none — operands already ready\n",
                     style=palette.role_hex("faint"))
        for pid in preds:
            src = self.parsed.ops[pid]
            ready = src.cycle + model.latency(src.op)
            role = "error" if ready > op.cycle else "text"
            t.append(f"  ln.{src.line:<4}", style=palette.role_hex("accent2"))
            t.append(f"{src.mnemonic:<8}", style=palette.op_style(src.op))
            t.append(f"c{src.cycle} → ready c{ready}\n",
                     style=palette.role_hex(role))

        succs = [i for i in range(len(dag)) if op.index in dag[i].preds]
        t.append("\nconsumers\n", style=palette.role_hex("dim"))
        if not succs:
            t.append("  none — result unused\n",
                     style=palette.role_hex("faint"))
        for sid in succs:
            dst = self.parsed.ops[sid]
            t.append(f"  ln.{dst.line:<4}", style=palette.role_hex("accent2"))
            t.append(f"{dst.mnemonic:<8}", style=palette.op_style(dst.op))
            t.append(f"c{dst.cycle}\n", style=palette.role_hex("text"))

        ready = op.cycle + model.latency(op.op)
        t.append(f"\nresult ready at cycle {ready}\n",
                 style=palette.role_hex("dim"))
        target.update(t)

    def _draw_journal(self) -> None:
        """Maximize OUTPUT tab into the full session journal and command catalog."""
        journal = self.query_one("#journal", ConsoleJournal)
        con = self.query_one("#console", Console)
        deep = self._console_expanded and self.drawer_tab == "term"
        journal.display = deep
        con.display = not deep
        # Hide compact prompt while maximized journal is visible.
        self.query_one("#prompt", PromptBar).display = not deep
        # Sync shared bridge row with selected/latest run.
        self.query_one("#drawer-bridge", BridgeRow).display = not deep
        if deep:
            journal.load(con.runs, self.mode,
                         list(self.app.commands) + self.extra_commands(),
                         self.app.session.journal_events)
        self._sync_drawer_bridge()

    def _sync_drawer_bridge(self) -> None:
        """Sync bridge action bar in the OUTPUT tab."""
        try:
            row = self.query_one("#drawer-bridge", BridgeRow)
            journal = self.query_one("#journal", ConsoleJournal)
        except Exception:
            return
        row.sync(self.app.session.journal_runs, journal.pos)

    # --- panel tools ------------------------------------------------------

    def on_tool_twice(self, event) -> None:
        """Double-clicking a dock tab toggles full-screen dock zoom."""
        event.stop()
        if event.tool.startswith("dock-"):
            self.open_block(event.tool.split("-", 1)[1])

    def panel_tool(self, tool: str) -> None:
        if tool.startswith("dock-"):
            # Single click switches tab; double click arrives via `on_tool_twice`.
            self.open_drawer(tool.split("-", 1)[1])
        elif tool == "agent-repeat":
            last = next((m["text"] for m in reversed(self.app.session.dialog)
                         if m["role"] == "you"), "")
            if last:
                self._answer_in_ai(last)
        elif tool == "agent-clear":
            self.app.session.dialog.clear()
            self.ai_actions.clear()
            self._draw_dialog()
        elif tool == "agent-facts":
            self._draw_agent_extras()
        elif tool == "code-save":
            self.action_save_code()
        elif tool == "code-rewrite":
            self.action_rewrite()
        elif tool == "code-broken":
            self._load_example_named("broken")
        elif tool == "sched-src":
            self._sched_view("src")
        elif tool == "sched-orc":
            self._sched_view("orc")
        elif tool == "sched-to-code":
            self._cell_to_code()
        elif tool == "lint-first":
            if self._lint_lines:
                self._goto_line(next((l for l in self._lint_lines if l), 0))
        else:
            super().panel_tool(tool)

    def _load_example_named(self, name: str) -> None:
        """`/example <name>` — open an example in a tab, or list all examples."""
        name = (name or "").strip().lower()
        if not name:
            self._list_examples()
            return
        text = example_text(name)
        if text is None:
            con = self.console
            if con is not None:
                con.note(f"  unknown example '{name}'", "error")
            self._list_examples()
            return
        self._load_example(text, name)

    def _generate(self, kind: str, arg: str) -> None:
        """`/gen` and `/fill` — generate legal e2k test blocks on demand.

            /gen 8 muls          eight independent ops, one per cycle
            /gen 8 muls packed   same ops packed across all legal channels
            /gen chain 5 fmul    five dependent ops in a chain
            /fill 20             twenty cycles of filler
        """
        from ...core import asmgen

        model = self.app.session.model()
        con = self.console
        words = arg.split()

        def fail(text: str) -> None:
            if con is not None:
                con.note("  " + text, "error")

        try:
            if kind == "fill":
                cycles = int(words[0]) if words else 10
                text = asmgen.filler(model, max(1, min(cycles, 200)))
                name = f"filler {cycles}"
            else:
                chain_mode = bool(words) and words[0] in ("chain", "chain")
                if chain_mode:
                    words = words[1:]
                packed = any(w in ("packed", "packed") for w in words)
                words = [w for w in words if w not in ("packed", "packed")]
                if len(words) < 2:
                    fail("usage: /gen <count> <op>   ·   "
                         "e.g. /gen 8 muls")
                    fail("ops: " + ", ".join(asmgen.known_names()).lower())
                    return
                count = max(1, min(int(words[0]), 200))
                op = asmgen.resolve(words[1])
                if op is None:
                    fail(f"unknown op '{words[1]}'")
                    fail("known: " + ", ".join(asmgen.known_names()).lower())
                    return
                if chain_mode:
                    text = asmgen.chain(model, op, count)
                    name = f"chain {count} {words[1]}"
                else:
                    text = asmgen.independent(model, op, count, packed=packed)
                    name = f"{count} {words[1]}" + (" packed" if packed else "")
        except ValueError as e:
            fail(str(e) if str(e) else "invalid count")
            return

        # Open generated block in its own tab.
        self.open_file(text, f"{name}.s")
        if con is not None:
            con.note(f"  generated: {name} — press F5 to run", "success")

    def _list_examples(self) -> None:
        con = self.console
        if con is None:
            return
        con.note("  examples: /example <name>", "accent2")
        for key, title, note in EXAMPLES:
            row = Text()
            row.append("  " + key.ljust(9), style=palette.role_hex("accent2"))
            row.append(title, style=palette.role_hex("text"))
            con.write(row)
            con.note("           " + note, "dim")

    def _load_example(self, text: str, name: str = "") -> None:
        """Open an example in its own tab without overwriting the active buffer."""
        self.open_file(text, f"{name or 'example'}.s", example=name)
        con = self.console
        if con is not None:
            con.note(f"  example '{name or 'untitled'}' opened in tab — F5",
                     "accent2")

    # --- rewrite via oracle (F6) ------------------------------------------

    def action_rewrite(self) -> None:
        """F6: rewrite buffer bundles to match the exact-search schedule (undoable via ^Z)."""
        if self._refuse_non_asm():
            return
        if not self._have_orc():
            con = self.console
            if con is not None:
                con.note("  press F5 first: run exact search before "
                         "rewriting", "warning")
            return
        text = self._rewrite_by_oracle()
        edit = self.query_one("#code-edit", AsmArea)
        edit.replace(text, (0, 0), edit.document.end)
        self.app.session.code_text = text
        src = self.comp.makespan if self.comp is not None else None
        self.reparse()
        con = self.console
        if con is not None:
            gain = f"{src} → {self.orc.schedule.makespan} cyc" if src else ""
            # Re-lint rewritten code to warn if anti/output register hazards need renaming.
            bad = len(self.problems)
            if bad:
                con.note(f"  buffer rewritten   {gain}   ·   check "
                         f"found {bad}: legal for dependency graph, "
                         f"but register names were not "
                         f"renamed   ·   ^Z to undo",
                         "warning")
            else:
                con.note(f"  buffer rewritten via oracle   {gain}"
                         f"   ·   ^Z to undo", "success")
        edit.focus()

    def _rewrite_by_oracle(self) -> str:
        """Format buffer ops into e2k `.s` bundles following the exact-search schedule."""
        model = self.app.session.model()
        sched = self.orc.schedule
        src = self.comp.makespan if self.comp is not None else 0
        by_cycle: dict[int, list[tuple[int, int]]] = {}
        for pl in sched.placements.values():
            by_cycle.setdefault(pl.cycle, []).append((pl.channel, pl.instr))

        out = [f"! Rewritten by NEX via exact search: "
               f"{src} cyc  →  {sched.makespan} cyc",
               "! Your mnemonics and operands; updated channels and "
               "{ } bundles."]
        prev = None
        for cycle in sorted(by_cycle):
            if prev is not None and cycle > prev + 1:
                out.append(f"  nop {cycle - prev - 1}")
            out.append("{")
            for channel, instr in sorted(by_cycle[cycle]):
                op = self.parsed.ops[instr]
                args = self._operands(op)
                out.append(f"  {op.mnemonic},{channel}"
                           + (f" {args}" if args else ""))
            out.append("}")
            prev = cycle
        return "\n".join(out) + "\n"

    def _operands(self, op) -> str:
        """Extract raw operand text from a source line without mnemonic/channel."""
        text = op.text.strip()
        head = op.mnemonic + (f",{op.channel}" if op.channel is not None else "")
        if text.lower().startswith(head.lower()):
            return text[len(head):].strip()
        # Handle mnemonics without an explicit channel suffix.
        if text.lower().startswith(op.mnemonic):
            return text[len(op.mnemonic):].lstrip(" ,0123456789").strip()
        return text

    def _sched_view(self, which: str) -> None:
        """Switch schedule grid between as-written and oracle (running F5 if needed)."""
        if which == "orc" and not self._have_orc():
            if self.parsed is None or not self.parsed.ops:
                con = self.console
                if con is not None:
                    con.note("  nothing to run: no e2k ops in buffer",
                             "warning")
                return
            self._want_orc = True
            self.action_run_code()
            return
        self.sched_view = which
        self._draw_grids()

    def _cell_to_code(self) -> None:
        table = self.query_one("#code-grid", DataTable)
        instr = self._grid_cells.get(("src", table.cursor_column - 1,
                                      table.cursor_row))
        if instr is not None and self.parsed is not None:
            self._goto_line(self.parsed.ops[instr].line)

    # --- AI facts ---------------------------------------------------------

    def panel_facts(self, topic: str, question: str = "") -> list[str]:
        if topic == "code":
            return self._code_facts(question)
        if topic == "sched":
            return self._sched_facts()
        if topic == "lint":
            return self._lint_facts()
        if topic == "core":
            return self._core_facts()
        if topic == "console":
            runs = self.app.session.journal_runs
            return ([f"{r.get('cmd', '')} — block "
                     f"{r.get('scenario') or '—'}" for r in runs[-6:]]
                    or ["no runs in this session yet"])
        return []

    def _core_facts(self) -> list[str]:
        ws = self.app.session.workspace()
        out = [f"machine has {len(ws.regs)} names, graph has {ws.graph_size()} "
               "ops"]
        out += [f"{n} = {v}" for n, v in list(ws.regs.items())[:8]]
        return out

    def _code_facts(self, question: str = "") -> list[str]:
        if self.parsed is not None and self.parsed.ops:
            return self._asm_facts()
        # For non-asm files, send a numbered window around the requested/cursor line.
        try:
            rec = self.files[self.file_i]
            text = rec.get("text", "") or ""
            name = rec.get("name", "?")
        except Exception:
            return ["empty buffer"]
        if not text.strip():
            return ["empty buffer"]
        try:
            cursor = self.query_one("#code-edit", AsmArea).cursor_location[0] + 1
        except Exception:
            cursor = 1
        center = excerpt_center(question, cursor, len(text.splitlines()))
        return file_excerpt(name, text, center)

    def _asm_facts(self) -> list[str]:
        """Collect grounded facts from the parsed `.s` buffer for the agent."""
        model = self.app.session.model()
        line = self.query_one("#code-edit", AsmArea).cursor_location[0] + 1
        out = [f"buffer has {len(self.parsed.ops)} ops, "
               f"{self.parsed.bundles} wide bundles",
               f"buffer schedule: "
               f"{self.comp.makespan if self.comp else '—'} cycles"]
        op = self._op_at_line(line)
        if op is not None:
            out.append(f"cursor on line {line}: {op.text}")
            out.append(f"class {op.op}, latency {model.latency(op.op)} cyc, "
                       f"channels " + " ".join(model.port_label(p)
                                             for p in model.channels_for(op.op)))
            out.append(f"in buffer at cycle {op.cycle}")
            orc = self._orc_cycle(op.index)
            if orc is not None:
                out.append(f"exact search places it at cycle {orc}")
        return out

    def _sched_facts(self) -> list[str]:
        out = []
        if self.comp is not None:
            out.append(f"as written — {self.comp.makespan} cycles, "
                       f"slot utilization "
                       f"{self.comp.slot_utilization * 100:.0f}%")
        if self.orc is not None and not self._stale():
            out.append(f"exact search — {self.orc.schedule.makespan} cycles")
        if self.met is not None:
            out.append(f"lower bound — {self.met.lower_bound} cycles")
        return out

    def _lint_facts(self) -> list[str]:
        out = [f"ln.{p.line}: {p.text}" for p in self.problems[:8]]
        out += [f"{f.title}: {f.why}" for f in self.findings[:4]]
        return out or ["no issues"]

    def panel_chips(self, topic: str) -> list[str]:
        if topic == "code":
            return ["why is this line in this cycle?",
                    "how can I rewrite this block shorter?"]
        if topic == "sched":
            return ["why is exact search faster?",
                    "which port is the bottleneck here?"]
        if topic == "lint":
            return ["how do I fix the first issue?",
                    "what is the most expensive part here?"]
        if topic == "core":
            return ["what is currently in the graph?",
                    "how would I write this in e2k assembly?"]
        if topic == "console":
            return ["what did the last run show?"]
        return []

    # --- input ------------------------------------------------------------

    def handle_line(self, line: str) -> None:
        head, _, arg = line.strip().lstrip("/").partition(" ")
        head = head.lower()
        if head == "code" and not arg.strip():
            # Bare `/code` returns focus to the editor.
            self.query_one("#code-edit", AsmArea).focus()
            return
        if head == "rewrite":
            self.action_rewrite()
            return
        if head == "example":
            self._load_example_named(arg.strip().lower())
            return
        if head in ("gen", "fill"):
            self._generate(head, arg.strip())
            return
        if head == "rename":
            self._rename_buffer(arg)
            return
        super().handle_line(line)

    def action_back(self) -> None:
        """Esc steps out one level: popup, dock zoom, focus editor, or mode picker."""
        sug = self.suggest
        if sug is not None and sug.display:
            sug.hide()
            return
        # Esc closes the right-side explorer before stepping further out.
        if self.explorer_shown:
            self.action_toggle_explorer()
            return
        # Esc from the AGENT tab returns focus to the editor without hiding the dock.
        if list(self.query(PanelPrompt)):
            self.close_panel_prompt()
            self.refresh_hints()
            return
        self._sync_buffer()
        if self.zoom:
            self.set_zoom("")
            return
        edit = self.query_one("#code-edit", AsmArea)
        if not edit.has_focus:
            edit.focus()
            return
        super().action_back()

    def action_save_code(self) -> None:
        """Ctrl+S: save active tab to disk (prompting if an untitled target exists)."""
        self._sync_buffer()
        last = getattr(self.app.session, "code_path", "")
        if last:
            self.handle_line(f"/code save {last}")
            return
        name = (self.files[self.file_i]["name"] if self.files else "").strip()
        # Replace spaces in tab names with underscores for clean filenames.
        name = name.replace(" ", "_")
        bar = self.query_one("#prompt", PromptBar)
        if not name:
            bar.focus_input()
            bar.set_value("/code save ")
            return
        if Path(name).exists():
            con = self.console
            if con is not None:
                con.note(f"  {name} already exists on disk — edit name or "
                         "confirm", "warning")
            self.open_drawer("term")
            bar.focus_input()
            bar.set_value(f"/code save {name}")
            return
        self.handle_line(f"/code save {name}")
        self._draw_side()
