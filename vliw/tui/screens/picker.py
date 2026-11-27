"""Screen picker — a branch point you switch to from your workspace.

The tool opens into CODE and returns to it. This screen lists the other places
you can jump to from work. While it used to be the landing screen, making all
four screens co-equal forced every screen to act as a standalone app (packing
editor, schedule, inspect, git, and console together) and made layouts cramped.

Opened via `/clear` (or ^O). Digits act as shortcuts only here; everywhere else
they belong to text input.
"""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Center, Vertical
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Static

from .. import palette

#: Ordered by actual usage. CODE comes first because it is the one screen where
#: users bring their own input (lcc assembly); the other three inspect it.
MODES = [
    {
        "id": "code",
        "key": "1",
        "title": "CODE",
        "subtitle": "workspace",
        "about": ".s editor, schedule, inspect, issues, and core — "
                 "all as tabs in one dock",
        "examples": "F5 — run   ·   F6 — rewrite via oracle   ·   /example",
    },
    {
        "id": "lab",
        "key": "2",
        "title": "LAB",
        "subtitle": "full graph view",
        "about": "block without source: machine matrix, diagnosis, scenarios",
        "examples": "/run slotclash   ·   /doctor   ·   /load examples/probe.s",
    },
    {
        "id": "mind",
        "key": "3",
        "title": "AGENT",
        "subtitle": "dialog",
        "about": "ask in plain language, answered from computed numbers",
        "examples": "why is this block slow?   ·   what should I change?",
    },
    {
        "id": "work",
        "key": "4",
        "title": "CORE",
        "subtitle": "full interpreter",
        "about": "tape, commits, and machine snapshots; compact console is "
                 "also a tab in CODE",
        "examples": "sum 8   ·   a=load 0   ·   t=a*2   ·   go",
    },
]


class ModeCard(Static):
    """Mode card: click opens, hover selects."""

    class Chosen(Message):
        def __init__(self, index: int) -> None:
            super().__init__()
            self.index = index

    class Hovered(Message):
        def __init__(self, index: int) -> None:
            super().__init__()
            self.index = index

    def __init__(self, meta: dict, index: int, **kw) -> None:
        super().__init__("", **kw)
        self.meta = meta
        self.index = index
        self.selected = False

    def on_mount(self) -> None:
        self.redraw()

    def set_selected(self, value: bool) -> None:
        if value != self.selected:
            self.selected = value
            self.set_class(value, "selected")
            self.redraw()

    def redraw(self) -> None:
        m = self.meta
        accent = palette.mode_hex(m["id"])
        dim = palette.role_hex("dim")
        faint = palette.role_hex("faint")
        title_color = palette.role_hex("title") if self.selected else dim

        head = Text()
        # Render the shortcut digit as a badge: this is the only screen where
        # digits act as direct hotkeys.
        if self.selected:
            head.append(f" {m['key']} ",
                        style=f"{palette.SURFACES['canvas']} on {accent} bold")
        else:
            head.append(f" {m['key']} ", style=f"{faint} on {palette.SURFACES['line']}")
        head.append("   ")
        head.append(m["title"], style=f"{accent} bold" if self.selected
                    else f"{title_color} bold")
        head.append("   ")
        head.append(m["subtitle"], style=dim if self.selected else faint)

        body = Text()
        body.append(m["about"], style=palette.role_hex("text") if self.selected
                    else dim)
        ex = Text(m["examples"], style=dim if self.selected else faint)

        card = Text()
        card.append_text(head)
        card.append("\n\n")
        card.append_text(body)
        card.append("\n")
        card.append_text(ex)
        self.update(card)
        if self.selected:
            self.styles.border = ("solid", accent)
        else:
            self.styles.border = ("solid", palette.SURFACES["line"])

    def on_click(self) -> None:
        self.post_message(self.Chosen(self.index))

    def on_enter(self) -> None:
        self.post_message(self.Hovered(self.index))


class PickerScreen(Screen):
    """NEX mark and cards for the screens you can switch to from work."""

    BINDINGS = [
        ("up", "move(-1)", "up"),
        ("down", "move(1)", "down"),
        ("1", "pick(0)", "code"),
        ("2", "pick(1)", "lab"),
        ("3", "pick(2)", "agent"),
        ("4", "pick(3)", "core"),
        ("enter", "open", "open"),
        # Esc returns to CODE rather than quitting the app, so changing your
        # mind does not close the entire tool.
        ("escape", "home", "back to code"),
        ("q", "quit_app", "quit"),
    ]

    # Height breakpoints. Full layout needs 41 rows: logo (8), tagline+margin
    # (3), four 6-row cards plus spacing (28), hint (2). Shrink progressively
    # from cheapest to heaviest so cards never clip off-screen:
    #
    #   snug   (< 41)  remove spacing between cards          -4
    #   short  (< 36)  shrink cards from 6 to 5 rows         -4
    #   tiny   (< 32)  hide the NEX logo                     -8
    #   micro  (< 24)  hide tagline, shrink cards to 3 rows
    #
    # Cards are never hidden: without them the screen has no purpose.
    SNUG = 41
    SHORT = 36
    TINY = 32
    MICRO = 24

    def __init__(self, selected: int = 0, **kw) -> None:
        super().__init__(**kw)
        self.selected = selected

    def on_resize(self, event) -> None:
        self._apply_height(event.size.height)

    def _apply_height(self, height: int) -> None:
        self.set_class(height < self.SNUG, "snug")
        self.set_class(height < self.SHORT, "short")
        self.set_class(height < self.TINY, "tiny")
        self.set_class(height < self.MICRO, "micro")

    def compose(self) -> ComposeResult:
        with Vertical(id="picker-wrap"):
            with Center():
                yield Static(id="picker-logo")
            with Center():
                yield Static(id="picker-tagline")
            with Center():
                with Vertical(id="picker-cards"):
                    for i, meta in enumerate(MODES):
                        yield ModeCard(meta, i, classes="mode-card")
            with Center():
                yield Static(id="picker-hint")

    def on_mount(self) -> None:
        self._apply_height(self.app.size.height)

        from ...ui import logo

        mark = Text()
        for i, line in enumerate(logo.render_mark(indent="")):
            if i:
                mark.append("\n")
            mark.append_text(Text.from_ansi(line))
        self.query_one("#picker-logo", Static).update(mark)

        from ... import VERSION_LABEL

        tag = Text()
        tag.append("NEX CLI", style=f"{palette.role_hex('title')} bold")
        tag.append("   ·   ", style=palette.role_hex("faint"))
        tag.append("Elbrus e2k", style=palette.role_hex("mountain"))
        tag.append("   ·   ", style=palette.role_hex("faint"))
        tag.append(VERSION_LABEL, style=palette.role_hex("warning"))
        tag.append("\n")
        tag.append("workspace is CODE; other views open from here",
                   style=palette.role_hex("dim"))
        self.query_one("#picker-tagline", Static).update(tag)

        hint = Text()
        for key, label in (("↑↓ / 1-4", "select"), ("Enter", "open"),
                           ("Esc", "back to code"), ("q", "quit")):
            hint.append(key, style=palette.role_hex("accent_soft"))
            hint.append(f" {label}    ", style=palette.role_hex("faint"))
        self.query_one("#picker-hint", Static).update(hint)
        self._sync()

    def _sync(self) -> None:
        for card in self.query(ModeCard):
            card.set_selected(card.index == self.selected)

    # --- actions ----------------------------------------------------------

    def action_move(self, delta: int) -> None:
        self.selected = (self.selected + delta) % len(MODES)
        self._sync()

    def action_pick(self, index: int) -> None:
        self.selected = index
        self._sync()
        self.action_open()

    def action_open(self) -> None:
        self.app.open_mode(MODES[self.selected]["id"])

    def action_home(self) -> None:
        self.app.open_mode(self.app.HOME)

    def action_quit_app(self) -> None:
        self.app.exit(0)

    def on_mode_card_chosen(self, event: ModeCard.Chosen) -> None:
        event.stop()
        self.selected = event.index
        self._sync()
        self.action_open()

    def on_mode_card_hovered(self, event: ModeCard.Hovered) -> None:
        event.stop()
        self.selected = event.index
        self._sync()
