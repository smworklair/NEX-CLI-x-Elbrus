"""Общие детали интерфейса: шапка, панели, док ввода, палитра команд.

Раскладки у трёх режимов разные — общими остаются только эти детали, чтобы
инструмент читался как одна вещь: одинаковая шапка, одинаковый способ
набирать команду, одинаковый язык панелей.
"""

from __future__ import annotations

import time

from rich.text import Text
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import Input, OptionList, RichLog, Static
from textual.widgets.option_list import Option

from . import palette

MARK = "▍"
ARROW = "▸"


# --------------------------------------------------------------------------
# Шапка
# --------------------------------------------------------------------------


class TopBar(Static):
    """Полоса режима: марка, имя режима, живой контекст, подсказка справа."""

    context = reactive("", layout=False)

    def __init__(self, mode: str, title: str, subtitle: str, **kw) -> None:
        super().__init__("", **kw)
        self.mode = mode
        self.title_text = title
        self.subtitle = subtitle

    def watch_context(self) -> None:
        self.refresh_bar()

    def on_mount(self) -> None:
        self.refresh_bar()

    def refresh_bar(self) -> None:
        accent = palette.role_hex(palette.MODE_ROLE.get(self.mode, "accent"))
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
        self.update(line)


# --------------------------------------------------------------------------
# Панель с заголовком
# --------------------------------------------------------------------------


class Panel(Vertical):
    """Рамка с подписью. Подпись — часть рамки, а не строка внутри.

    Двойной клик разворачивает панель на весь экран (Esc — обратно). Панелей
    на экране шесть-семь, и в каждой либо решётка тактов, либо длинный отчёт;
    в своей трети экрана они читаются с трудом, а развёрнутая — целиком.

    Двойной клик определяется по времени вручную: у Textual 8.2 в событии
    Click нет поля `chain` (счётчика кликов подряд), есть только `time`.
    """

    #: Максимальный зазор между кликами, чтобы счесть их двойным.
    DOUBLE_CLICK_S = 0.4

    #: Без этого Textual разворачивать не даёт: по умолчанию `allow_maximize`
    #: равен `can_focus`, а Panel — контейнер и фокус не принимает.
    ALLOW_MAXIMIZE = True

    def __init__(self, *children, title: str = "", accent: str = "", **kw) -> None:
        super().__init__(*children, **kw)
        self._title = title
        self._accent = accent
        self._last_click = 0.0

    def on_mount(self) -> None:
        if self._title:
            self.border_title = self._title
        if self._accent:
            self.styles.border_title_color = palette.role_hex(self._accent)

    def set_title(self, title: str) -> None:
        self._title = title
        self.border_title = title

    def on_click(self, event) -> None:
        """Двойной клик — развернуть/свернуть эту панель."""
        now = getattr(event, "time", 0.0) or time.monotonic()
        double = (now - self._last_click) <= self.DOUBLE_CLICK_S
        self._last_click = now
        if not double:
            return
        event.stop()
        self._last_click = 0.0        # третий клик подряд не считаем четвёртым
        screen = self.screen
        if screen.maximized is self:
            screen.minimize()
        else:
            screen.maximize(self, container=False)


# --------------------------------------------------------------------------
# Лог: вывод команд ядра как есть
# --------------------------------------------------------------------------


class Console(RichLog):
    """Отчёты команд. Принимает ANSI-строки ядра без изменений."""

    def __init__(self, **kw) -> None:
        kw.setdefault("highlight", False)
        kw.setdefault("markup", False)
        kw.setdefault("wrap", False)
        kw.setdefault("auto_scroll", True)
        super().__init__(**kw)

    def echo(self, line: str, mode: str = "lab") -> None:
        """Отметка о поданной команде — чтобы лог не был безадресным."""
        accent = palette.role_hex(palette.MODE_ROLE.get(mode, "accent"))
        t = Text()
        t.append(f"{ARROW} ", style=accent)
        t.append(line, style=palette.role_hex("title"))
        self.write(t)

    def ansi(self, text: str) -> None:
        for line in text.split("\n"):
            self.write(Text.from_ansi(line))

    def note(self, text: str, role: str = "dim") -> None:
        self.write(Text(text, style=palette.role_hex(role)))


# --------------------------------------------------------------------------
# Палитра команд («/»)
# --------------------------------------------------------------------------


class Palette(OptionList):
    """Список команд под курсором ввода. Открыт, пока строка начинается с «/»."""

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self.items: list[dict] = []
        self.can_focus = False

    def load(self, items: list[dict]) -> None:
        self.items = items
        self.clear_options()
        if not items:
            self.add_option(Option(Text("  ничего не подходит",
                                        style=palette.role_hex("warning"))))
            self.highlighted = None
            return
        key = palette.role_hex("accent")
        dim = palette.role_hex("dim")
        val = palette.role_hex("text")
        for it in items:
            row = Text()
            name = it["name"] if it.get("kind") == "arg" else "/" + it["name"]
            row.append(f" {name:<14}", style=f"{key} bold")
            row.append(f"{(it.get('arg') or ''):<14}", style=val)
            row.append(it.get("help") or "", style=dim)
            self.add_option(Option(row))
        self.highlighted = 0

    @property
    def selected(self) -> dict | None:
        if not self.items or self.highlighted is None:
            return None
        return self.items[min(self.highlighted, len(self.items) - 1)]

    def step(self, delta: int) -> None:
        if not self.items:
            return
        cur = self.highlighted or 0
        self.highlighted = max(0, min(len(self.items) - 1, cur + delta))


# --------------------------------------------------------------------------
# Док ввода
# --------------------------------------------------------------------------


class NexInput(Input):
    """Поле ввода: цифры остаются цифрами, стрелки — истории и палитре."""

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

    def action_nex_up(self) -> None:
        self.post_message(self.Nav("up"))

    def action_nex_down(self) -> None:
        self.post_message(self.Nav("down"))

    def action_nex_tab(self) -> None:
        self.post_message(self.Nav("tab"))

    def action_nex_escape(self) -> None:
        self.post_message(self.Nav("escape"))


class PromptBar(Vertical):
    """Строка ввода с палитрой команд, историей и правой подсказкой.

    Клавиши 1/2/3 здесь — обычные символы: режимы больше никуда не прыгают,
    выход из режима один и тот же во всех трёх экранах — `/clear`.
    """

    class Submitted(Message):
        def __init__(self, value: str) -> None:
            super().__init__()
            self.value = value

    class Changed(Message):
        def __init__(self, value: str) -> None:
            super().__init__()
            self.value = value

    class Escaped(Message):
        """Esc при закрытой палитре — экран решает, что это значит."""

    def __init__(self, mode: str, placeholder: str, commands: list[dict],
                 **kw) -> None:
        super().__init__(**kw)
        self.mode = mode
        self.placeholder = placeholder
        self.commands = commands
        self.history: list[str] = []
        self._hist_pos: int | None = None

    def compose(self):
        yield Palette(id="palette")
        # Поле ввода — именно поле: рамка, своя подложка, видимая граница.
        # Голая строка на общем фоне читалась как часть вывода, а не как то,
        # куда вообще можно печатать.
        with Horizontal(id="prompt-field"):
            yield Static("", id="prompt-mark")
            yield NexInput(placeholder=self.placeholder, id="prompt-input")
            yield Static("", id="prompt-side")

    def on_mount(self) -> None:
        self.repaint()
        self.query_one("#palette", Palette).display = False

    def repaint(self) -> None:
        accent = palette.role_hex(palette.MODE_ROLE.get(self.mode, "accent"))
        mark = Text()
        mark.append("nex ", style=f"{accent} bold")
        mark.append(ARROW, style=palette.role_hex("dim"))
        self.query_one("#prompt-mark", Static).update(mark)

    # --- доступ -----------------------------------------------------------

    @property
    def input(self) -> NexInput:
        return self.query_one("#prompt-input", NexInput)

    @property
    def palette_widget(self) -> Palette:
        return self.query_one("#palette", Palette)

    def focus_input(self) -> None:
        self.input.focus()

    def set_side(self, text: str | Text) -> None:
        self.query_one("#prompt-side", Static).update(text)

    def set_value(self, value: str) -> None:
        inp = self.input
        inp.value = value
        inp.cursor_position = len(value)
        self._sync_palette(value)

    # --- палитра ----------------------------------------------------------

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
# Мелочи
# --------------------------------------------------------------------------


class Chip(Static):
    """Кликабельная подсказка: подставляет свой текст в строку ввода."""

    class Picked(Message):
        def __init__(self, value: str) -> None:
            super().__init__()
            self.value = value

    def __init__(self, label: str, value: str | None = None, **kw) -> None:
        super().__init__(label, **kw)
        self.value = value if value is not None else label

    def on_click(self) -> None:
        self.post_message(self.Picked(self.value))


class HintBar(Static):
    """Нижняя строка подсказок — одна на все экраны, меняется по состоянию."""

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


