"""Выбор режима — единственный экран, где цифры работают как клавиши.

Отсюда открывается один из трёх инструментов. Обратно сюда возвращает
`/clear` (или ^O) из любого режима — это единственный способ сменить занятие,
и он намеренно явный: режимы не вкладки, между которыми скачут.
"""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Center, Vertical
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Static

from .. import palette

MODES = [
    {
        "id": "work",
        "key": "1",
        "title": "ЯДРО",
        "subtitle": "интерпретатор",
        "about": "считает выражения и копит из них граф участка",
        "examples": "sum 8   ·   a=load 0   ·   t=a*2   ·   go",
    },
    {
        "id": "lab",
        "key": "2",
        "title": "РАЗБОР",
        "subtitle": "исследование",
        "about": "расписание такт за тактом: где теряются такты и почему",
        "examples": "/run slotclash   ·   /doctor   ·   /load examples/probe.s",
    },
    {
        "id": "mind",
        "key": "3",
        "title": "АГЕНТ",
        "subtitle": "диалог",
        "about": "вопрос обычным языком, ответ по уже посчитанным числам",
        "examples": "почему этот участок медленный?   ·   что менять?",
    },
    {
        "id": "code",
        "key": "4",
        "title": "КОД",
        "subtitle": "редактор",
        "about": "пишешь ассемблер e2k — такт и канал стоят прямо на строке",
        "examples": "F5 — прогнать   ·   F6 — переписать по оракулу   ·   /example",
    },
]


class ModeCard(Static):
    """Карточка режима: клик открывает, наведение — выбирает."""

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
        # Клавиша — плашкой: на этом экране цифра действительно клавиша,
        # и это единственное место во всём инструменте, где она ею работает.
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
            self.styles.border = ("round", accent)
        else:
            self.styles.border = ("round", palette.SURFACES["line"])

    def on_click(self) -> None:
        self.post_message(self.Chosen(self.index))

    def on_enter(self) -> None:
        self.post_message(self.Hovered(self.index))


class PickerScreen(Screen):
    """Стартовый экран: знак NEX и три карточки."""

    BINDINGS = [
        ("up", "move(-1)", "выше"),
        ("down", "move(1)", "ниже"),
        ("1", "pick(0)", "ядро"),
        ("2", "pick(1)", "разбор"),
        ("3", "pick(2)", "агент"),
        ("enter", "open", "открыть"),
        ("q", "quit_app", "выход"),
        ("escape", "quit_app", "выход"),
    ]

    def __init__(self, selected: int = 1, **kw) -> None:
        super().__init__(**kw)
        self.selected = selected

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
        tag.append("четыре инструмента — у каждого свой экран",
                   style=palette.role_hex("dim"))
        self.query_one("#picker-tagline", Static).update(tag)

        hint = Text()
        for key, label in (("↑↓ / 1-4", "выбрать"), ("Enter", "открыть"),
                           ("q", "выход")):
            hint.append(key, style=palette.role_hex("accent_soft"))
            hint.append(f" {label}    ", style=palette.role_hex("faint"))
        self.query_one("#picker-hint", Static).update(hint)
        self._sync()

    def _sync(self) -> None:
        for card in self.query(ModeCard):
            card.set_selected(card.index == self.selected)

    # --- действия ---------------------------------------------------------

    def action_move(self, delta: int) -> None:
        self.selected = (self.selected + delta) % len(MODES)
        self._sync()

    def action_pick(self, index: int) -> None:
        self.selected = index
        self._sync()
        self.action_open()

    def action_open(self) -> None:
        self.app.open_mode(MODES[self.selected]["id"])

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
