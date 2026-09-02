"""Список экранов — не главное меню, а развилка, на которую уходят.

Инструмент открывается КОДОМ и в него же возвращается. Этот экран стал
тем, чем и должен был быть: списком мест, куда можно уйти из работы. Пока
он был первым, что видит человек, все четыре экрана были равны — а раз
равны, каждый обязан быть самодостаточным приложением, и в каждом сидели
редактор, расписание, разбор, git и консоль разом. Отсюда и теснота.

Открывается по `/clear` (или ^O). Цифры работают как клавиши только здесь:
во всех остальных местах они принадлежат тексту.
"""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Center, Vertical
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Static

from .. import palette

#: Порядок — по тому, чем на самом деле пользуются. КОД первым не из
#: вежливости: это единственный экран, куда человек приносит СВОЁ — вывод
#: lcc, который надо разобрать. Остальные три смотрят на то, что он принёс.
MODES = [
    {
        "id": "code",
        "key": "1",
        "title": "КОД",
        "subtitle": "рабочее место",
        "about": "редактор .s, расписание, разбор, замечания и ядро — "
                 "вкладками одного дока",
        "examples": "F5 — прогнать   ·   F6 — переписать по оракулу   ·   /example",
    },
    {
        "id": "lab",
        "key": "2",
        "title": "РАЗБОР",
        "subtitle": "весь граф целиком",
        "about": "участок без исходника: матрица машины, диагноз, сценарии",
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
        "id": "work",
        "key": "4",
        "title": "ЯДРО",
        "subtitle": "интерпретатор целиком",
        "about": "лента, коммиты и снимки машины; короткая консоль есть "
                 "вкладкой в КОДЕ",
        "examples": "sum 8   ·   a=load 0   ·   t=a*2   ·   go",
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
    """Знак NEX и карточки экранов, на которые уходят из работы."""

    BINDINGS = [
        ("up", "move(-1)", "выше"),
        ("down", "move(1)", "ниже"),
        # Четвёртой цифры раньше не было вовсе: карточек стало четыре, а
        # биндингов осталось три, и ЯДРО с клавиатуры не открывалось.
        ("1", "pick(0)", "код"),
        ("2", "pick(1)", "разбор"),
        ("3", "pick(2)", "агент"),
        ("4", "pick(3)", "ядро"),
        ("enter", "open", "открыть"),
        # Esc возвращает В РАБОТУ, а не выходит из инструмента. Пока этот
        # экран был стартовым, «назад» отсюда действительно значило «выйти»;
        # теперь сюда приходят из КОДА, и Esc обязан возвращать туда же —
        # иначе передумавший закрывает весь инструмент.
        ("escape", "home", "назад в код"),
        ("q", "quit_app", "выход"),
    ]

    # Пороги высоты. Экран складывается из фиксированных кусков: знак
    # (8 строк), подпись с отступом (3), четыре карточки по 6 плюс отступ
    # (28), подсказка (2) — 41 строка. Ниже нижняя карточка уезжала за край,
    # и человек не видел, что режимов четыре.
    #
    # ПОРЯДОК ЖЕРТВ — от самой дешёвой. Первая версия этой правки прятала
    # знак сразу, на высоте 40: чтобы освободить ДВЕ строки, убиралось
    # ВОСЕМЬ, и внизу оставалась дыра в восемь строк пустоты. Ужиматься надо
    # ровно настолько, насколько не хватает:
    #
    #   snug   (< 41)  убрать отступы между карточками      −4
    #   short  (< 36)  карточки 6 → 5 строк                 −4
    #   tiny   (< 32)  спрятать знак NEX                    −8
    #   micro  (< 24)  спрятать подпись, карточки в 3 строки
    #
    # Карточки не прячутся никогда: без них экран теряет смысл.
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
        tag.append("рабочее место — КОД; остальное открывается отсюда",
                   style=palette.role_hex("dim"))
        self.query_one("#picker-tagline", Static).update(tag)

        hint = Text()
        for key, label in (("↑↓ / 1-4", "выбрать"), ("Enter", "открыть"),
                           ("Esc", "назад в код"), ("q", "выход")):
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
