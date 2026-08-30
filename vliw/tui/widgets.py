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


class SleepChip(Static):
    """Один факт спящего режима во второй строке шапки.

    Факт кликабелен целиком: клик открывает тот режим, про который он
    говорит, — тем же путём, каким мостик журнала переводит человека
    между режимами (`app.open_mode`). Вид — как у строки состояния в IDE:
    выглядит текстом, кликабельность проявляется наведением.
    """

    class Goto(Message):
        """Открыть режим `mode` (work | mind | code)."""

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
    """Полоса режима: марка, имя режима, живой контекст, подсказка справа.

    Под основной строкой может стоять ВТОРАЯ — факты спящих режимов
    (`sleepers`): три экрана читают одну сессию, но видеть чужое состояние
    из РАЗБОРА, никуда не переходя, до сих пор было негде. Пилот живёт
    только там, кто его наполнит; пустой список — второй строки нет вовсе,
    и шапка во всех остальных режимах остаётся однорядной.
    """

    context = reactive("", layout=False)

    #: [(метка, текст, режим)] — по одному короткому факту на спящий режим.
    #: Пусто — строки нет: место не пустует и не стоит прочерком.
    sleepers = reactive((), layout=False)

    def __init__(self, mode: str, title: str, subtitle: str, **kw) -> None:
        super().__init__(**kw)
        self.mode = mode
        self.title_text = title
        self.subtitle = subtitle
        self._sleep_gen = 0          # поколение фактов: устаревшие не встают

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
            pass        # watch срабатывает раньше, чем дети смонтированы
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
            # Разделитель — только МЕЖДУ показанными фактами: у скрытого
            # куска не остаётся ни места, ни висячей точки.
            if i:
                parts.append(Static(Text("   ·   ", style=faint),
                                    classes="sleep-sep"))
            parts.append(SleepChip(label, body, mode, classes="sleep-chip",
                                   id=f"sleep-{mode}"))
        # Монтирование — на следующий кадр, не из цепочки монтирования
        # экрана (on_mount → refresh_context → reactive): синхронный mount()
        # внутри неё подвешивал учёт сообщений у Textual, и run_test
        # отваливался по тайм-ауту. Поколение гасит устаревшие кадры:
        # пока removal предыдущих детей отложен, новый mount с теми же id
        # не должен успевать за ним.
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

    #: Мягкий разворот: панель НЕ отдаётся встроенному maximize, а только
    #: сообщает экрану «меня развернули», и он сам решает, как перестроить
    #: раскладку. Нужно там, где разворот должен ДОБАВЛЯТЬ на экран, а не
    #: прятать: встроенный maximize показывает ровно один виджет и убирает
    #: всех соседей (`Screen._arrange`, `get_maximize_widgets` смотрит только
    #: прямых детей экрана), поэтому у вложенных панелей вместе с соседями
    #: исчезало и то, чем в этот момент пользуются.
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
        if self.soft:
            # Экран сам знает, что показать шире, а что оставить на месте.
            self.post_message(self.Expanded(self))
            return
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

    def __init__(self, runs: list | None = None, **kw) -> None:
        kw.setdefault("highlight", False)
        kw.setdefault("markup", False)
        kw.setdefault("wrap", False)
        kw.setdefault("auto_scroll", True)
        super().__init__(**kw)
        # runs — общий журнал сессии (session.journal_runs): один и тот же
        # список у консолей всех экранов. Свой список остаётся только там,
        # где консоль вне сессии (тесты, служебные ленты).
        self.runs: list[dict] = runs if runs is not None else []

    def _record(self, line) -> None:
        """Строку — в текущий запуск. Перехватывать `write` нельзя: RichLog
        переигрывает отложенный вывод на каждом ресайзе, и журнал двоился бы.
        Строки до первой команды (заставка панели) ничьи и не пишутся."""
        if self.runs:
            self.runs[-1]["lines"].append(line)

    def echo(self, line: str, mode: str = "lab") -> None:
        """Отметка о поданной команде — чтобы лог не был безадресным.

        Режим и время запоминаются в записи нарочно: журнал общий на всю
        сессию, и без метки не видно, ГДЕ и КОГДА запущена команда. Метка
        превращает ленту в летопись сессии — то самое «пойми, что вообще
        происходило».
        """
        accent = palette.mode_hex(mode)
        self.runs.append({"cmd": line, "lines": [], "error": False,
                          "mode": mode,
                          "time": time.strftime("%H:%M")})
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
        # Запомнить, что запуск провалился: в журнале десяток команд подряд,
        # и без пометки неудачная выглядит ровно как удачная. Ошибки ядра
        # приходят сюда же (`_core_done` зовёт note(..., "error")).
        if role == "error" and self.runs:
            self.runs[-1]["error"] = True
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


class CommandItem(Static):
    """Команда в каталоге терминала. Клик — подставить её в строку ввода."""

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
    """Ввод терминала: ↑/↓ ходят по истории, а не по строкам.

    Отдельный класс, а не обработчик в родителе: у `Input` свои биндинги на
    стрелки, и перехватить их можно только своими — иначе история молча не
    работает, что для терминала неприемлемо.
    """

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
    """Развёрнутый ВЫВОД КОМАНД — рабочий терминал, а не список для чтения.

    Свёрнутая панель — лента: видно последнее, остальное уехало вверх.
    Развернуть её в ту же ленту подлиннее значило бы не решить ровно ту
    проблему, из-за которой её и разворачивают.

    Что здесь есть сверх ленты:
      — каталог ВСЕХ команд слева, с аргументами: набирать вслепую больше не
        надо, и не надо помнить, что вообще бывает;
      — каталог фильтруется живьём тем, что набираешь в строке ввода, а клик
        по команде подставляет её вместе с аргументом;
      — история команд по ↑/↓ и повтор выбранного запуска по ^R;
      — запуски с ошибкой помечены, а не выглядят как удачные;
      — у каждого запуска метка режима, где он был сделан: журнал общий на
        сессию, и «где это считалось» — часть записи, а не догадка;
      — мостик выбранного прогона: в РАЗБОР, АГЕНТУ или ЯДРУ — решает
        человек, ничто не уезжает само;
      — поток СОБЫТИЙ отдельно от вывода команд: живой текст планировщика
        и модели не перемешивается с отчётами (вкладка над выводом);
      — своя строка ввода прямо здесь, а не «где-то внизу экрана».

    Колонка слева нарочно узкая: главное здесь — вывод справа, а каталог и
    список запусков — вспомогательные. Раньше она занимала 40 колонок из
    150 при том, что длиннее «/load examples/probe.s» там ничего не бывает.

    Не универсальный виджет: у ЛЕНТЫ в ЯДРЕ развёрнутый вид свой, потому
    что там не запуски команд, а вычисления со значениями.
    """

    BINDINGS = [
        Binding("ctrl+r", "repeat", "повторить запуск", show=False),
        Binding("ctrl+l", "wipe", "очистить журнал", show=False),
    ]

    #: Ширина левой колонки. 32 — по строке коммита истории
    #: («▸ #12 14:02 к /code run»), а не «на глаз побольше».
    SIDE_W = 32

    class RunRequested(Message):
        """Команда, набранная прямо в развёрнутом журнале — не в общем доке."""

        def __init__(self, line: str) -> None:
            super().__init__()
            self.line = line

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self.runs: list[dict] = []
        self.commands: list[dict] = []
        self.events: list = []
        self.pos = -1
        self._seen = 0     # сколько запусков уже показывали (для терминала)
        self.mode = "lab"
        self._filter = ""
        self._hist_pos: int | None = None
        self._feed = "runs"    # runs | events — что показано в правой колонке

    def compose(self):
        with Vertical(id="journal-side"):
            yield Static("", id="journal-cmds-head")
            yield VerticalScroll(id="journal-cmds")
            yield Static("", id="journal-runs-head")
            yield VerticalScroll(id="journal-list")
        # Вывод и строка ввода — в одной колонке: журнал должен работать как
        # терминал сам по себе, а не подразумевать, что где-то далеко внизу
        # экрана есть общий док ввода, про который ещё нужно догадаться.
        with Vertical(id="journal-right"):
            # Мостик выбранного прогона: куда отправить то, что здесь
            # показано. Решает человек — ничто не уезжает само. Выбор
            # прогона — клик по строке в истории; кнопки действуют на него.
            yield BridgeRow(prefix="bridge", id="run-actions")
            with Horizontal(id="feed-tabs"):
                yield Tool("поток команд", "feed-runs",
                           "отчёты выполненных команд", id="feed-runs")
                yield Tool("события", "feed-events",
                           "живой поток планировщика и модели — отдельно "
                           "от отчётов", id="feed-events")
            yield RichLog(id="journal-out", highlight=False, markup=False,
                          wrap=False, auto_scroll=False)
            yield RichLog(id="events-out", highlight=False, markup=False,
                          wrap=True, auto_scroll=True)
            with Horizontal(id="journal-field"):
                yield Static("", id="journal-mark")
                yield JournalInput(placeholder="команда", id="journal-input")
                # Подсказка справа, а не в placeholder: в placeholder она
                # исчезала ровно тогда, когда человек начинал печатать.
                yield Static("каталог слева   ·   ↑↓ история   ·   ^R повтор",
                             id="journal-hint")

    def on_tool_picked(self, event) -> None:
        # Вкладки потока — своё, локальное. Мостик и «вернуть» не
        # останавливаем — их обрабатывает экран, у журнала нет права
        # решать, куда прыгать. Повтор перехватил сам BridgeRow.
        if event.tool in ("feed-runs", "feed-events"):
            event.stop()
            self.show_feed("runs" if event.tool == "feed-runs" else "events")

    def on_mount(self) -> None:
        self._repaint_mark()

    def _repaint_mark(self) -> None:
        accent = palette.mode_hex(self.mode)
        canvas = palette.SURFACES["canvas"]
        # Тот же бейдж со шевроном, что у командной строки панели: все
        # места, где печатают, выглядят одинаково.
        mark = Text()
        mark.append(" nex ", style=f"{canvas} on {accent} bold")
        mark.append(" ❯", style=accent)
        self.query_one("#journal-mark", Static).update(mark)

    # --- ввод -------------------------------------------------------------

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
        """Набранное фильтрует каталог слева — дополнение без отдельной клавиши.

        Tab тут занят справочником ИИ (общая клавиша всего интерфейса), да и
        дополнение по клавише надо ещё догадаться нажать. Живой фильтр видно
        без подсказки: набрал «do» — слева осталось /doctor.
        """
        event.stop()
        # Только ПЕРВОЕ слово: дальше идут аргументы, и по «run slotclash»
        # каталог не находил бы ничего ровно в тот момент, когда команда уже
        # набрана правильно.
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
        """Клик по команде: подставить, но НЕ запускать.

        У половины команд есть аргумент, и запуск по клику отправлял бы их
        без него. Подставляем и оставляем курсор в конце — дописать и Enter.
        """
        event.stop()
        inp = self.query_one("#journal-input", JournalInput)
        inp.value = event.line
        inp.cursor_position = len(event.line)
        inp.focus()

    def action_repeat(self) -> None:
        """^R — повторить выбранный запуск.

        Отдельно от «показать вывод»: перечитать старый отчёт и прогнать его
        заново — разные намерения, и склеивать их в один клик значит терять
        первое.
        """
        if 0 <= self.pos < len(self.runs):
            self.post_message(self.RunRequested(self.runs[self.pos]["cmd"]))

    def action_wipe(self) -> None:
        """^L — очистить журнал. Список запусков растёт всю сессию."""
        self.runs.clear()
        self.pos = -1
        self._seen = 0
        self.load(self.runs, self.mode, self.commands)

    # --- отрисовка --------------------------------------------------------

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

    # --- поток событий ------------------------------------------------------

    def show_feed(self, feed: str) -> None:
        """Что показано в правой колонке: отчёты команд или поток событий.

        Две вещи, которые раньше сваливались в одну ленту. Отчёт — ответ на
        «что вернула команда», события — «что происходило по ходу»: строки
        модели, пометки планировщика. Перемешанные, они лишали обе ленты
        смысла: отчёт тонул в потоке, а поток обрывался на таблицах.
        """
        self._feed = feed if feed in ("runs", "events") else "runs"
        self.query_one("#journal-out").display = self._feed == "runs"
        self.query_one("#events-out").display = self._feed == "events"
        for key in ("feed-runs", "feed-events"):
            self.query_one(f"#{key}", Tool).set_on(
                (key == "feed-runs") == (self._feed == "runs"))
        head = self.query_one("#feed-events", Tool)
        n = len(self.events)
        label = f"события {n}" if n else "события"
        head.update(label)
        if self._feed == "events":
            out = self.query_one("#events-out", RichLog)
            out.clear()
            for line in self.events:
                out.write(line)

    def append_event(self, line) -> None:
        """Живая строка потока — пишется и в закрытую вкладку: журнал
        обязан копить всё, что шло мимо, иначе «открыл — а там пусто».
        """
        self.events.append(line)
        if self._feed == "events" and self.is_mounted:
            self.query_one("#events-out", RichLog).write(line)
        try:
            self.query_one("#feed-events", Tool).update(
                f"события {len(self.events)}")
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
        # Совпадения с НАЧАЛА имени — выше: набирая «do», ищут /doctor, а не
        # /random, где «do» просто попалось в середине (ran-do-m).
        if self._filter:
            shown.sort(key=lambda c: not c["name"].lower()
                       .startswith(self._filter))
        h = Text()
        h.append("КОМАНДЫ ", style=f"{accent} bold")
        h.append(f" {len(shown)}", style=faint)
        if self._filter:
            h.append(f"  из {len(self.commands)}", style=faint)
        head.update(h)
        if not shown:
            box.mount(Static(Text("  ничего не совпало", style=faint)))
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
        h.append("ИСТОРИЯ ", style=f"{accent} bold")
        h.append(f" {len(self.runs)}", style=faint)
        head.update(h)
        if not self.runs:
            box.mount(Static(Text(
                "  пусто — первая команда\n  станет коммитом #1",
                style=faint)))
            self.query_one("#journal-out", RichLog).clear()
            self._seen = 0
            return
        # Последний запуск открыт сразу на входе — а если появился НОВЫЙ
        # запуск с прошлой отрисовки, прыгаем на него всегда, даже если до
        # этого читали старый: набранная команда должна показать СВОЙ вывод,
        # а не оставить читателя на чужом.
        grew = len(self.runs) > self._seen
        self._seen = len(self.runs)
        if grew or not 0 <= self.pos < len(self.runs):
            self.pos = len(self.runs) - 1
        for i, run in enumerate(self.runs):
            item = RunItem(i, self._row(i, run),
                           classes="run-item" + (" on" if i == self.pos
                                                 else ""))
            # Подсказка — ПОЛНАЯ команда, режим и состояние: в строке списка
            # имя обрезано, а запись — это коммит, у которого есть что
            # показать целиком. «Вернуть» — checkout состояния сессии.
            run_mode = run.get("mode") or "lab"
            where = {"lab": "РАЗБОР", "work": "ЯДРО", "mind": "АГЕНТ",
                     "code": "КОД"}.get(run_mode, run_mode)
            item.tooltip = (f"#{i + 1}  {run.get('time') or '--:--'}  "
                            f"{run['cmd']}\n{where}"
                            + (f"  ·  участок {run['scenario']}"
                               if run.get("scenario") else "")
                            + f"  ·  {len(run['lines'])} стр. вывода"
                            + ("  ·  ошибка" if run.get("error") else "")
                            + "\nклик — показать вывод\n"
                              "мостик — отправить в другой режим\n"
                              "«вернуть» — состояние сессии как здесь")
            box.mount(item)
        self.show(self.pos)

    #: Метка режима в строке запуска: одна буква своим цветом. Журнал общий
    #: на сессию — без метки «где это считалось» видно только по цвету стрелки,
    #: а он совпадает с цветом текущего режима и лжёт.
    MODE_MARKS = {"lab": "р", "work": "я", "mind": "а", "code": "к"}

    def _row(self, i: int, run: dict) -> Text:
        """Запись истории как коммит в git log: две строки и граф.

        Первая — «кто и когда»: точка графа, номер, время, метка режима,
        команда. Вторая — «что это было за состояние»: участок, число
        операций, объём вывода; вертикальная линия связывает коммиты в
        одну ветку. Список из одних команд («/doctor, /run, /doctor»)
        историей не читается — команды повторяются, состояния нет.
        """
        accent = palette.mode_hex(getattr(self, "mode", "lab"))
        here = i == self.pos
        failed = run.get("error")
        run_mode = run.get("mode") or "lab"
        faint = palette.role_hex("faint")
        t = Text()
        # Точка графа: цвет — режим, где сделан коммит. История читается
        # как карта сессии: оранжевые коммиты — разбор, мятные — код…
        t.append("● ", style=palette.mode_hex(run_mode))
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
            t.append(" ✗", style=palette.role_hex("error"))
        # Строка 2: линия графа и состояние, которое несёт запись.
        dag = run.get("dag")
        t.append("\n│  ", style=faint)
        if run.get("scenario"):
            t.append(str(run["scenario"])[:14],
                     style=palette.role_hex("dim"))
            if dag is not None:
                t.append(f" · {len(dag)} оп.", style=palette.role_hex("dim"))
        t.append(f" · {len(run['lines'])} стр.", style=faint)
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
        # Мостик: у прогонов, которым есть что отдать, свои кнопки видны.
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
    """Ряд переноса прогона между режимами («мостик»).

    ОБЩИЙ для развёрнутого журнала и свёрнутой вкладки ОТЧЁТ: перенос
    данных — главная функция отчёта, и требовать ради неё разворота
    значило бы снова спрятать «гит». Кнопки действуют на ВЫБРАННЫЙ
    в истории прогон (клик по строке), а без выбора — на последний.

    Полная сетка: в разбор / в агента / в ядро / в код / вернуть
    (checkout состояния на месте) / повторить. Кнопкам нужен префикс id:
    журнал и вкладка ОТЧЁТА живут на одном экране, и два ряда с одинаковыми
    id ломали бы query_one.
    """

    def __init__(self, prefix: str = "bridge", **kw) -> None:
        super().__init__(**kw)
        self.prefix = prefix
        self.runs: list[dict] = []
        self.pos = -1

    def on_mount(self) -> None:
        # До первой синхронизации все кнопки видны, а делать им нечего:
        # пустая история — пустой ряд, иначе кнопки обещают то, чего нет.
        self.sync([], -1)

    def compose(self):
        yield Static("мостик ▸", classes="bridge-label")
        p = self.prefix
        yield Tool("в разбор", "@lab",
                   "сделать этот прогон участком РАЗБОРА", id=f"{p}-lab")
        yield Tool("в агента", "@agent",
                   "спросить агента про этот прогон", id=f"{p}-agent")
        yield Tool("в ядро", "@work",
                   "открыть ЯДРО с этим прогоном в контексте",
                   id=f"{p}-work")
        yield Tool("в код", "@code",
                   "открыть КОД: исходник прогона — в буфер", id=f"{p}-code")
        yield Tool("вернуть", "@restore",
                   "вернуть состояние сессии этого прогона "
                   "(участок, исходник) — без перехода", id=f"{p}-restore")
        yield Tool("↻ повторить", "@repeat",
                   "прогнать команду заново", id=f"{p}-repeat")

    def sync(self, runs: list[dict], pos: int) -> None:
        """Показать кнопки, которым у выбранного прогона есть что делать.

        Без выбора (pos мимо) работает последний прогон: пустой ряд
        читался бы как сломанный, а «последний» — это то, что человек
        только что запускал.
        """
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
        # Повтор — локальное действие ряда: перезапустить выбранный прогон
        # тем же путём, что и строка ввода (RunRequested ловит экран).
        if event.tool != "@repeat":
            return
        event.stop()
        if 0 <= self.pos < len(self.runs):
            self.post_message(
                ConsoleJournal.RunRequested(self.runs[self.pos]["cmd"]))


# --------------------------------------------------------------------------
# Палитра команд («/»)
# --------------------------------------------------------------------------


class Palette(OptionList):
    """Список команд под курсором ввода. Открыт, пока строка начинается с «/».

    Пункты бывают двух видов: команды (kind="cmd") и заголовки групп
    (kind="header"). Заголовок — оформление, не выбор: стрелки его
    перепрыгивают, Enter/Tab видят только команды.
    """

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

    # --- индексация с учётом заголовков ------------------------------------

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
# Док ввода
# --------------------------------------------------------------------------


class NexInput(Input):
    """Поле ввода: цифры остаются цифрами, стрелки — истории и палитре.

    Многострочная вставка (bracketed paste) сюда не вставляется: поле одно-
    строчное, и многострочный текст в нём ломался бы. Вместо этого текст
    целиком уезжает в буфер КОДА (см. ModeScreen.on_nex_input_pasted).
    """

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
        """В поле вставили многострочный текст — он теперь в буфере КОДА."""

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
                 hint: str = "", **kw) -> None:
        super().__init__(**kw)
        self.mode = mode
        self.placeholder = placeholder
        self.hint = hint
        """Подсказка справа, живёт постоянно.

        Раньше подсказки жили в placeholder — и исчезали ровно в тот момент,
        когда человек начинал печатать, то есть когда они и нужны. Справа же
        было пусто: `#prompt-side` заполнялся только словом «считаю…» на
        время работы. Половина строки простаивала, вторая врала.
        """
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
        self.set_side("")
        self.query_one("#palette", Palette).display = False

    def repaint(self) -> None:
        accent = palette.mode_hex(self.mode)
        canvas = palette.SURFACES["canvas"]
        # Марка — бейдж на акцентной плашке и шеврон: приглашение должно
        # читаться как «сюда печатают», а не как ещё одна строка вывода.
        mark = Text()
        mark.append(" nex ", style=f"{canvas} on {accent} bold")
        mark.append(" ❯", style=accent)
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
        """Правая часть строки. Пустое значение возвращает подсказку.

        Так «считаю…» временно перекрывает подсказку, а по окончании она
        сама встаёт обратно — вызывающим не нужно помнить, что там было.
        """
        if not text and self.hint:
            text = Text(self.hint, style=palette.role_hex("faint"))
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


class Tool(Static):
    """Кнопка на панели инструментов развёрнутой панели.

    Отличие от Chip принципиальное: чип ПОДСТАВЛЯЕТ текст в строку ввода
    (это подсказка «что можно набрать»), инструмент СРАЗУ выполняет действие.
    Разворачивают панель, чтобы работать в ней — и инструменты у неё должны
    работать в один клик, а не через подстановку и Enter.
    """

    class Picked(Message):
        def __init__(self, tool: str) -> None:
            super().__init__()
            self.tool = tool

    def __init__(self, label: str, tool: str, tooltip: str = "", **kw) -> None:
        super().__init__(label, **kw)
        self.tool = tool
        if tooltip:
            self.tooltip = tooltip

    def on_click(self, event) -> None:
        event.stop()
        self.post_message(self.Picked(self.tool))

    def set_on(self, on: bool) -> None:
        """Пометка-состояние для тумблеров (включён/выключен)."""
        self.set_class(on, "tool-on")


class PanelToolbar(Horizontal):
    """Панель инструментов развёрнутой панели — то, чего ей не хватало.

    Долгое время разворот был «той же панелью крупнее»: контент растягивался,
    а инструменты оставались внизу экрана, в общем доке. Теперь каждый
    развёрнутый блок несёт СВОИ инструменты первой строкой: навигацию,
    тумблеры, переходы в связные панели.

    Видимость ведёт CSS, а не код: в обычном виде полоса display:none и не
    отнимает ни строки у решётки; у Panel.-maximized показывается. Экрану
    остаётся только отвечать на Tool.Picked — см. ModeScreen.panel_tool().
    """

    def __init__(self, *tools: tuple[str, str, str], **kw) -> None:
        super().__init__(**kw)
        # Каждый элемент — (надпись, идентификатор действия, всплывающая
        # подсказка). Кортежи, а не готовые Tool: compose() вызывается позже
        # конструктора, и виджеты нельзя создавать до монтирования в него.
        self._tools = tools

    def compose(self):
        for label, tool, tip in self._tools:
            yield Tool(label, tool, tip)

    def mark(self, tool: str, on: bool) -> None:
        """Отметить тумблер включённым. Неизвестный id молча пропускается."""
        for t in self.query(Tool):
            if t.tool == tool:
                t.set_on(on)


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
        accent = palette.mode_hex(self.mode)
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
