"""Общие детали интерфейса: шапка, панели, док ввода, палитра команд.

Раскладки у трёх режимов разные — общими остаются только эти детали, чтобы
инструмент читался как одна вещь: одинаковая шапка, одинаковый способ
набирать команду, одинаковый язык панелей.
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

    #: Про что эта панель — ключ, по которому экран собирает ей факты для ИИ.
    #: Пусто — панель не о данных (подсказки, чипы), чат ей не нужен.
    topic: str = ""

    #: Есть ли у панели собственный ввод (лента ядра, вывод команд). У таких
    #: чат НЕ открывается сам: он отобрал бы место у того, ради чего панель и
    #: разворачивают. Открывается по клавише и встаёт слева.
    has_own_input: bool = False

    class Expanded(Message):
        """Панель развернули на весь экран."""

        def __init__(self, panel: "Panel") -> None:
            super().__init__()
            self.panel = panel

    class Collapsed(Message):
        """Панель свернули обратно."""

    def __init__(self, *children, title: str = "", accent: str = "",
                 topic: str = "", has_own_input: bool = False, **kw) -> None:
        super().__init__(*children, **kw)
        self._title = title
        self._accent = accent
        self._last_click = 0.0
        self.topic = topic
        self.has_own_input = has_own_input

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
            self.post_message(self.Collapsed())
        else:
            screen.maximize(self, container=False)
            self.post_message(self.Expanded(self))


# --------------------------------------------------------------------------
# Лог: вывод команд ядра как есть
# --------------------------------------------------------------------------


class Console(RichLog):
    """Отчёты команд. Принимает ANSI-строки ядра без изменений.

    Помимо ленты держит `runs` — вывод, разложенный по запускам. Лента
    отвечает на вопрос «что сейчас произошло», но не на «что показал
    /doctor три команды назад»: длинный отчёт уезжает вверх, и его
    перезапускают заново. Журнал (см. ConsoleJournal) строится из этого
    списка, поэтому запись идёт всегда, а не только когда журнал открыт.
    """

    def __init__(self, **kw) -> None:
        kw.setdefault("highlight", False)
        kw.setdefault("markup", False)
        kw.setdefault("wrap", False)
        kw.setdefault("auto_scroll", True)
        super().__init__(**kw)
        self.runs: list[dict] = []

    def _record(self, line) -> None:
        """Строку — в текущий запуск. Перехватывать `write` нельзя: RichLog
        переигрывает отложенный вывод на каждом ресайзе, и журнал двоился бы.
        Строки до первой команды (заставка панели) ничьи и не пишутся."""
        if self.runs:
            self.runs[-1]["lines"].append(line)

    def echo(self, line: str, mode: str = "lab") -> None:
        """Отметка о поданной команде — чтобы лог не был безадресным."""
        accent = palette.role_hex(palette.MODE_ROLE.get(mode, "accent"))
        self.runs.append({"cmd": line, "lines": []})
        t = Text()
        t.append(f"{ARROW} ", style=accent)
        t.append(line, style=palette.role_hex("title"))
        self.write(t)
        self._record(t)

    def ansi(self, text: str) -> None:
        for line in text.split("\n"):
            t = Text.from_ansi(line)
            self._record(t)
            self.write(t)

    def note(self, text: str, role: str = "dim") -> None:
        t = Text(text, style=palette.role_hex(role))
        self._record(t)
        self.write(t)


def plural(n: int, one: str, few: str, many: str) -> str:
    """Русское склонение по числу. «3 запусков» мозолит глаза в заголовке."""
    if 11 <= n % 100 <= 14:
        return many
    return {1: one, 2: few, 3: few, 4: few}.get(n % 10, many)


class RunItem(Static):
    """Один запуск в журнале. Клик — показать его вывод справа."""

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


class ConsoleJournal(Horizontal):
    """Развёрнутый ВЫВОД КОМАНД: слева запуски, справа вывод выбранного.

    Свёрнутая панель — лента: видно последнее, остальное уехало вверх.
    Развернуть её в ту же ленту подлиннее значило бы не решить ровно ту
    проблему, из-за которой её и разворачивают: /doctor на тринадцати
    строках и /compare на тридцати одной идут подряд, и чтобы вернуться к
    первому, его перезапускают. Журнал даёт вернуться, не запуская.

    Не универсальный виджет: у ЛЕНТЫ в ЯДРЕ развёрнутый вид свой, потому
    что там не запуски команд, а вычисления с значениями.
    """

    class RunRequested(Message):
        """Команда, набранная прямо в развёрнутом журнале — не в общем доке."""

        def __init__(self, line: str) -> None:
            super().__init__()
            self.line = line

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self.runs: list[dict] = []
        self.pos = -1
        self._seen = 0     # сколько запусков уже показывали (для терминала)
        self.mode = "lab"

    def compose(self):
        yield Vertical(id="journal-list")
        # Вывод и строка ввода — в одной колонке: журнал должен работать как
        # терминал сам по себе, а не подразумевать, что где-то далеко внизу
        # экрана есть общий док ввода, про который ещё нужно догадаться.
        with Vertical(id="journal-right"):
            yield RichLog(id="journal-out", highlight=False, markup=False,
                          wrap=False, auto_scroll=False)
            with Horizontal(id="journal-field"):
                yield Static("", id="journal-mark")
                yield Input(placeholder="команда прямо здесь — тот же ввод, "
                                        "что и внизу экрана",
                           id="journal-input")

    def on_mount(self) -> None:
        self._repaint_mark()

    def _repaint_mark(self) -> None:
        accent = palette.role_hex(palette.MODE_ROLE.get(self.mode, "accent"))
        mark = Text()
        mark.append("nex ", style=f"{accent} bold")
        mark.append(ARROW, style=palette.role_hex("dim"))
        mark.append(" ", style="")
        self.query_one("#journal-mark", Static).update(mark)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        line = event.value.strip()
        event.input.value = ""
        if line:
            self.post_message(self.RunRequested(line))

    def load(self, runs: list[dict], mode: str = "lab") -> None:
        self.runs = runs
        if mode != self.mode:
            self.mode = mode
            self._repaint_mark()
        box = self.query_one("#journal-list", Vertical)
        box.remove_children()
        dim = palette.role_hex("dim")
        if not runs:
            box.mount(Static(Text("  команд ещё не было", style=dim)))
            self.query_one("#journal-out", RichLog).clear()
            self._seen = 0
            return
        # Последний запуск открыт сразу на входе — а если появился НОВЫЙ
        # запуск с прошлой отрисовки, прыгаем на него всегда, даже если до
        # этого читали старый: журнал развёрнут поверх терминала (глобальный
        # ввод остаётся доступным при разворачивании панели), и набранная
        # команда должна показать СВОЙ вывод, а не оставить читателя на
        # чужом. Без этого разворот был терминалом только на словах: набрал
        # команду — а видишь по-прежнему то, что открыл до неё.
        grew = len(runs) > self._seen
        self._seen = len(runs)
        if grew or not 0 <= self.pos < len(runs):
            self.pos = len(runs) - 1
        for i, run in enumerate(runs):
            box.mount(RunItem(i, self._row(i, run),
                              classes="run-item" + (" on" if i == self.pos
                                                    else "")))
        self.show(self.pos)

    def _row(self, i: int, run: dict) -> Text:
        accent = palette.role_hex(palette.MODE_ROLE.get(
            getattr(self, "mode", "lab"), "accent"))
        here = i == self.pos
        t = Text()
        t.append("▸ " if here else "  ",
                 style=accent if here else palette.role_hex("faint"))
        t.append(run["cmd"][:26].ljust(27),
                 style=palette.role_hex("title") if here
                 else palette.role_hex("dim"))
        n = len(run["lines"])
        t.append(f"{n:>4} стр.", style=palette.role_hex("faint"))
        return t

    def show(self, index: int) -> None:
        if not (0 <= index < len(self.runs)):
            return
        self.pos = index
        out = self.query_one("#journal-out", RichLog)
        out.clear()
        for line in self.runs[index]["lines"]:
            out.write(line)
        for item in self.query(RunItem):
            item.set_class(item.index == index, "on")
            item.update(self._row(item.index, self.runs[item.index]))

    def on_run_item_picked(self, event) -> None:
        event.stop()
        self.show(event.index)


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

    def tab(self) -> None:
        """Дополнение по Tab. Публичный метод, потому что Tab теперь ловит
        экран (у него priority-биндинг ради справочника ИИ), а привычное
        дополнение вне разворота должно продолжать работать — экран зовёт
        этот метод сам."""
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




class PromptChip(Static):
    """Готовый вопрос во всплывающей строке. Клик — задать его."""

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
    """Крестик закрытия — кликабельная альтернатива Esc, не только клавиша."""

    class Picked(Message):
        pass

    def on_click(self, event) -> None:
        event.stop()
        self.post_message(self.Picked())


class PanelPrompt(Vertical):
    """Строка вопроса, всплывающая внизу развёрнутой панели.

    Заменяет колонку чата сбоку. Боковая панель отбирала треть ширины у того
    самого содержимого, ради которого панель и разворачивают, — а спросить
    хочется почти в любой из них. Всплывающая строка не отбирает ничего: она
    лежит поверх нижнего края, поднимается ответом вверх и уходит по Esc.

    Один виджет на все панели здесь уместен ровно потому, что это НЕ
    инструмент панели, а способ спросить: рамка одна, а начинка своя —
    готовые вопросы и факты каждая панель даёт сама.
    """

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
        # Заголовок — свой ряд внутри рамки, а не border_title: у
        # border_title нет клика, и крестик закрытия было бы некуда деть,
        # кроме как в отдельный виджет поверх линии рамки, что менее
        # надёжно, чем обычная строка.
        with Horizontal(id="pp-header"):
            yield Static("", id="pp-title")
            yield CloseBtn("✕", id="pp-close")
        yield VerticalScroll(id="pp-answer")
        yield ItemGrid(id="pp-chips", min_column_width=30)
        with Horizontal(id="pp-field"):
            yield Static("", id="pp-mark")
            yield Input(placeholder="спросить про эту панель…", id="pp-input")

    def on_mount(self) -> None:
        accent = palette.role_hex(palette.MODE_ROLE.get(self.mode, "accent"))
        self.styles.border_title_color = accent
        head = Text()
        head.append(f"NEX  ·  {self._title}", style=f"{accent} bold")
        self.query_one("#pp-title", Static).update(head)
        # Клавиша закрытия — ТЕКСТОМ рядом с крестиком, не только всплывающей
        # подсказкой по наведению: подсказка по hover не видна ни на
        # скриншоте, ни во многих терминалах без мыши, и тогда крестик без
        # подписи ничем не выдаёт, чем его закрыть.
        close = Text()
        close.append("✕ ", style=palette.role_hex("dim"))
        close.append("Esc", style=palette.role_hex("faint"))
        self.query_one("#pp-close", CloseBtn).update(close)
        self.query_one("#pp-close", CloseBtn).tooltip = "закрыть (Esc)"
        mark = Text()
        mark.append("? ", style=f"{accent} bold")
        self.query_one("#pp-mark", Static).update(mark)
        chips = self.query_one("#pp-chips", ItemGrid)
        for q in self._chips:
            chips.mount(PromptChip(q, "‹ " + q, classes="chip prompt-chip"))
        self.query_one("#pp-answer", VerticalScroll).display = False
        inp = self.query_one("#pp-input", Input)
        inp.placeholder = "спросить или сделать что-то с сессией  ·  /clear — очистить"
        inp.focus()

    # --- ответ ------------------------------------------------------------

    def start_answer(self) -> None:
        """Готовимся к ответу. Сам виджет ответа появится позже — в
        `first_piece()`, а не здесь, — потому что действия агента (переключил
        сценарий, посчитал расписание) приходят РАНЬШЕ текста и мысль должна
        идти ПОД ними, а не над: иначе порядок на экране лжёт про порядок
        событий — читатель видит вывод раньше причины.
        """
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
        t.append("вы  ", style=palette.role_hex("faint"))
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
        """Текст наконец пошёл — здесь и только здесь появляется его виджет.

        До этого момента на экране могли уже стоять строки действий (см.
        `action()`) и индикатор ожидания «…»; сам ответ встаёт ПОСЛЕ них,
        замещая «…», а не выше — порядок на экране обязан быть порядком
        событий.
        """
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
        # Сколько фактов ушло в модель и сколько она думала — на виду, а не в
        # отчёте: ответ локальной модели проверяют, а не принимают на веру.
        t.append(f"{seconds:.0f} с  ·  фактов {len(self.facts)}  ·  "
                 "посчитано ядром, пересказано моделью",
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
        """Действие, которое агент СДЕЛАЛ, а не сказал — своя строка и цвет.

        Иначе «переключился на mulclash» тонет в потоке того же цвета, что и
        пересказ модели, а это разные вещи: одно — факт (можно перепроверить
        командой), другое — формулировка (может быть неточной). Монтируется
        ПЕРЕД индикатором ожидания (`move_before`), который вставили первым в
        `start_answer()`, — действия старше «…» по времени и обязаны стоять
        выше него.
        """
        log = self.query_one("#pp-answer", VerticalScroll)
        log.display = True
        t = Text()
        t.append("⚙ ", style=palette.role_hex("accent"))
        t.append(note, style=palette.role_hex("accent_soft"))
        line = Static(t, classes="pp-line")
        if self._wait is not None and self._wait.is_mounted:
            log.mount(line, before=self._wait)
        else:
            log.mount(line)
        log.scroll_end(animate=False)

    def clear(self) -> None:
        """`/clear` — стереть только накопленный разговор, не факты и не чипы.

        Ответы копятся вниз и за несколько вопросов подряд съедают весь
        экран под них (max-height у панели — 60%). Закрывать панель ради
        этого не нужно — вопрос обычно ещё не закончен, нужно просто место.
        """
        log = self.query_one("#pp-answer", VerticalScroll)
        log.remove_children()
        log.display = False
        self._answer = None
        self._wait = None
        self._buf = ""

    # --- ввод -------------------------------------------------------------

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
# Чат по развёрнутой панели
# --------------------------------------------------------------------------


class PanelChat(Vertical):
    """Разговор про ОДНУ панель, рядом с ней.

    Идея не в том, чтобы завести ещё один чат. Она в том, что вопрос почти
    всегда возникает про то, на что человек сейчас смотрит: «почему эта
    клетка красная», «что значит этот диагноз», «откуда это число». Общий
    экран АГЕНТ на такой вопрос отвечает хуже — ему приходится угадывать, о
    чём речь, а модели на 3B угадывание даётся плохо и заканчивается
    выдумкой. Панель знает про себя точно, и её факты уходят в контекст.

    Проверяемость сохраняется тем же способом, что и на экране АГЕНТ: под
    строкой ввода видно, СКОЛЬКО фактов панель отдала модели, а сами факты
    показывает `/что` — ответ можно сверить с тем, из чего он сделан.
    """

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
        yield Input(placeholder="спросить про то, что выше…", id="pchat-input")

    def on_mount(self) -> None:
        # Заголовок рисуем здесь, а не сразу после mount() снаружи: на момент
        # возврата из mount() дети ещё не собраны, и query_one их не найдёт.
        self._greet()
        self.query_one("#pchat-input", Input).focus()

    def _greet(self) -> None:
        """Факты видно СРАЗУ, а не по команде.

        Это не подробность оформления, а единственная защита от выдумки.
        Локальная модель на 3B уверенно отвечает, когда факт один, и путает
        числа, когда их надо связать несколько, — проверено на панели
        ДИАГНОЗ. Прятать исходные строки за счётчиком «передано фактов: 5»
        значит предлагать верить на слово. Когда они висят прямо над ответом,
        неверный ответ виден сразу и без единой команды.
        """
        t = Text()
        t.append("NEX про панель ", style=palette.role_hex("dim"))
        t.append(self._panel_title + "\n\n", style=palette.role_hex("title"))
        t.append(f"модель видит ровно это ({len(self._facts)}):\n",
                 style=palette.role_hex("dim"))
        # По одной строке на факт, с обрезкой. Полный текст читать здесь
        # незачем — панель открыта слева, и она же источник. Смысл списка в
        # другом: видно, СКОЛЬКО и ЧЕГО досталось модели, и что лишнего она
        # не получала. Развёрнутый вид ничего не добавил бы, а ответ утопил
        # бы вниз — проверено, на панели ДИАГНОЗ факты длиннее самой панели.
        for f in self._facts:
            line = " ".join(f.split())
            if len(line) > 58:
                line = line[:57] + "…"
            t.append("  · " + line + "\n", style=palette.role_hex("faint"))
        t.append("\nспросите обычным языком; Esc — свернуть панель",
                 style=palette.role_hex("faint"))
        self._log().update(t)
        self._body = t.copy()

    def on_input_submitted(self, event) -> None:
        event.stop()
        text = event.value.strip()
        event.input.value = ""
        if text:
            self.post_message(self.Asked(text))

    # --- лента ------------------------------------------------------------

    def _log(self) -> Static:
        return self.query_one("#pchat-log", Static)

    def echo(self, question: str) -> None:
        self._body.append("\n\n› ", style=palette.role_hex("accent"))
        self._body.append(question, style=palette.role_hex("title"))
        self._body.append("\n")
        self._log().update(self._body)

    def note(self, text: str, role: str = "faint") -> None:
        self._body.append("\n" + text, style=palette.role_hex(role))
        self._log().update(self._body)

    def append(self, piece: str) -> None:
        self._body.append(piece)
        self._log().update(self._body)

    # --- состояние ответа -------------------------------------------------
    #
    # Наружу торчит `answering`: интерфейс по нему рисует «думает», а тест —
    # ждёт конца, не гадая по длине текста.

    answering = False

    def start_answer(self) -> None:
        self.answering = True
        self._answer_started = False
        # Позицию снимаем ДО метки, иначе срез по ней метку и оставляет.
        self._think_at = len(self._body)
        self.note("думает…", "warning")

    def first_piece(self) -> None:
        """Первый кусок ответа: убрать «думает…», дальше просто дописывать."""
        if self._answer_started:
            return
        self._answer_started = True
        self._body = self._body[:self._think_at]
        self._body.append("\n")
        self._log().update(self._body)

    def finish(self, seconds: float) -> None:
        self.answering = False
        self.note(f"\n({seconds:.1f} с)", "faint")
