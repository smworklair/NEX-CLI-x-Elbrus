"""Общая основа рабочих экранов.

Три режима — три разных рабочих места со своей раскладкой. Общего у них
ровно столько, сколько нужно, чтобы это был один инструмент: полоса режима
сверху, док ввода снизу, одинаковый способ выполнить команду и одинаковый
выход — `/clear` возвращает к выбору режима.

Переключения между режимами на горячих клавишах нет намеренно: это разные
занятия, а не вкладки одного окна. Поэтому цифры, буквы и всё остальное
достаётся строке ввода целиком.
"""

from __future__ import annotations

from textual import work
from textual.containers import Vertical
from textual.screen import Screen

from .. import palette
from ..widgets import Console, HintBar, Panel, PanelChat, PromptBar, TopBar


class ModeScreen(Screen):
    """Каркас режима: шапка, тело (своё у каждого), док ввода."""

    mode = "lab"
    mode_title = ""
    mode_subtitle = ""
    placeholder = ""

    # Что можно убрать с экрана, когда мешает. Боковая колонка полезна, но
    # постоянно занимает треть ширины; полоса подсказок нужна, пока не выучил
    # команды. Обе прячутся с клавиатуры и не мешают работе, когда не нужны.
    SIDE_ID = ""
    TIPS_ID = ""

    BINDINGS = [
        ("ctrl+b", "toggle_side", "боковая панель"),
        ("ctrl+t", "toggle_tips", "полоса подсказок"),
        ("ctrl+o", "to_picker", "к выбору режима"),
        ("ctrl+q", "quit_app", "выход"),
    ]

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self.busy = False
        self.side_shown = True
        self.tips_shown = True

    # --- сборка -----------------------------------------------------------

    def compose(self):
        yield TopBar(self.mode, self.mode_title, self.mode_subtitle, id="topbar")
        yield from self.compose_body()
        with Vertical(id="dock"):
            yield PromptBar(self.mode, self.placeholder,
                            list(self.app.commands) + self.extra_commands(),
                            id="prompt")
            yield HintBar(id="hints")

    def extra_commands(self) -> list[dict]:
        """Команды, которые понимает только этот экран (попадают в палитру)."""
        return []

    def compose_body(self):
        """Раскладка режима. Переопределяется каждым экраном."""
        yield Vertical(id="body")

    #: Что ещё видно, когда панель развёрнута. По умолчанию Textual прячет
    #: ВСЕХ прямых детей экрана, кроме развёрнутого, — и чат по панели
    #: исчезал вместе с ними. Строка ввода и подсказки остаются нарочно: без
    #: них развёрнутая панель становится тупиком, из которого не видно, как
    #: выйти и что вообще можно.
    ALLOW_IN_MAXIMIZED_VIEW = "PanelChat, PromptBar, HintBar, Footer"

    _chat_panel = None
    _chat_facts: list[str] = []
    _chat_offer = None

    def on_mount(self) -> None:
        self.app.set_mode_theme(self.mode)
        self._apply_width(self.size.width or 120)
        self.query_one("#prompt", PromptBar).focus_input()
        self.refresh_hints()
        self.refresh_context()
        self.on_ready()

    def on_ready(self) -> None:
        """Первое наполнение панелей. Переопределяется экраном."""

    # --- ширина окна ------------------------------------------------------
    #
    # Правых колонок в раскладке не жалко ровно до тех пор, пока слева хватает
    # места на решётку и ленту. Дальше колонка ужимается, а на совсем узком
    # окне вспомогательные полосы с подсказками убираются: лучше потерять
    # подсказку, чем рабочую область.

    NARROW = 124
    TIGHT = 100

    def on_resize(self, event) -> None:
        self._apply_width(event.size.width)

    def _apply_width(self, width: int) -> None:
        self.set_class(width < self.NARROW, "narrow")
        self.set_class(width < self.TIGHT, "tight")

    # --- шапка и подсказки ------------------------------------------------

    def context_bits(self) -> str:
        s = self.app.session
        model = s.model()
        bits = [f"участок {s.scenario}", f"{len(s.dag_obj)} оп.", model.name]
        cached = s.peek()
        if cached is not None:
            base, orc, _ = cached
            b, o = base.schedule.makespan, orc.schedule.makespan
            bits.append(f"{b}→{o}" if b != o else f"{b} тактов")
        return "   ·   ".join(bits)

    def refresh_context(self) -> None:
        try:
            self.query_one("#topbar", TopBar).context = self.context_bits()
        except Exception:
            pass

    def hint_pairs(self) -> list[tuple[str, str]]:
        return [("/", "команды"), ("^O", "выбор режима"), ("/exit", "выход")]

    def toggle_hints(self) -> list[tuple[str, str]]:
        """Подсказки про скрываемые панели — одинаковые во всех режимах."""
        out = []
        # Про двойной клик иначе не догадаться: мышь в текстовом интерфейсе
        # обычно ничего не делает, и панель на весь экран никто искать не станет.
        if self.screen is self and self.screen.maximized is not None:
            out.append(("Esc", "свернуть панель"))
        else:
            out.append(("2×клик", "панель на весь экран"))
        if self.SIDE_ID:
            out.append(("^B", "панель" if self.side_shown else "панель ↩"))
        if self.TIPS_ID:
            out.append(("^T", "подсказки" if self.tips_shown else "подсказки ↩"))
        return out

    def refresh_hints(self) -> None:
        try:
            self.query_one("#hints", HintBar).set_hint(
                self.hint_pairs() + self.toggle_hints())
        except Exception:
            pass

    # --- ввод -------------------------------------------------------------

    def on_prompt_bar_submitted(self, event: PromptBar.Submitted) -> None:
        event.stop()
        line = event.value.strip()
        low = line.lower().lstrip("/")
        if low in ("exit", "quit"):
            self.app.exit(0)
            return
        if low in ("clear", "cls"):
            self.app.to_picker()
            return
        if low.split(" ")[0] == "mode":
            # Режимы больше не переключаются на месте — это разные рабочие
            # места. `/mode` остаётся в ядре ради построчного режима, здесь
            # он только объясняет, куда идти.
            if self.console is not None:
                self.console.note(
                    "  режим меняется через /clear — выбор откроется заново",
                    "warning")
            return
        self.handle_line(line)

    def handle_line(self, line: str) -> None:
        """Что делать с введённой строкой. Переопределяется экраном."""
        self.run_core(line)

    def on_chip_picked(self, event) -> None:
        """Клик по подсказке подставляет её в ввод и сразу выполняет."""
        event.stop()
        bar = self.query_one("#prompt", PromptBar)
        bar.focus_input()
        bar.history.append(event.value)
        self.handle_line(event.value)

    def on_prompt_bar_escaped(self, event) -> None:
        """Esc при закрытой палитре. По умолчанию — ничего."""
        event.stop()

    # --- выполнение команд ядра -------------------------------------------

    @property
    def console(self) -> Console | None:
        try:
            return self.query_one("#console", Console)
        except Exception:
            return None

    def run_core(self, line: str) -> None:
        """Выполнить команду ядра, вывод — в консоль экрана."""
        con = self.console
        if con is not None:
            con.echo(line, self.mode)
        self.set_busy(True)
        self._core_worker(line)

    @work(thread=True, exclusive=True, group="core")
    def _core_worker(self, line: str) -> None:
        from .. import bridge

        con = self.console
        width = con.size.width - 2 if con is not None and con.size.width else 96

        # Пока команда идёт, ядро отдаёт события планировщика сюда, а не
        # печатает их в перехваченный stdout. Разница принципиальная: stdout
        # моста копится и показывается ЦЕЛИКОМ В КОНЦЕ, поэтому обученная
        # модель раньше выглядела как замерший на полминуты экран. События
        # приходят по ходу — видно, как модель пишет и как заполняется
        # решётка.
        session = self.app.session
        session.event_sink = bridge.EventPump(
            self.app, self.on_scheduler_text, self.on_scheduler_event)
        try:
            out, err = bridge.run_command(self.app.execute, line, width)
        finally:
            session.event_sink = None
        self.app.call_from_thread(self._core_done, out, err)

    # --- события планировщика ---------------------------------------------
    #
    # Приходят уже в главном потоке. По умолчанию экран показывает поток
    # текстом; экран, у которого есть решётка, переопределяет и заливает её.

    def on_scheduler_text(self, text: str) -> None:
        con = self.console
        if con is not None:
            con.note("  " + text.replace("[end of text]", "").rstrip(), "dim")

    def on_scheduler_event(self, ev) -> None:
        """Не-текстовое событие: размещение, починка, вердикт, отказ."""

    def _core_done(self, out: str, err: str) -> None:
        con = self.console
        if con is not None:
            if out.strip():
                con.ansi(out.rstrip("\n"))
            if err:
                con.note("  " + err, "error")
            con.write("")
        self.set_busy(False)
        self.app.reload_palette()   # команда могла сменить тему
        self.refresh_context()
        self.after_command()

    # --- чат по развёрнутой панели ----------------------------------------

    def panel_facts(self, topic: str) -> list[str]:
        """Факты открытой панели для ИИ. Переопределяется экраном.

        Пустой список — панель нечего обсуждать, чат не открываем.
        """
        return []

    def on_panel_expanded(self, event) -> None:
        event.stop()
        panel = event.panel
        if not getattr(panel, "topic", ""):
            return
        # У панели со своим вводом чат сам не лезет: её разворачивают, чтобы
        # читать и вводить, и отобрать треть ширины значило бы помешать ровно
        # тому, ради чего разворот и сделан. Такую открывают клавишей.
        if getattr(panel, "has_own_input", False):
            self._chat_offer = panel
            self.refresh_hints()
            return
        self.open_panel_chat(panel)

    def on_panel_collapsed(self, event) -> None:
        event.stop()
        self.close_panel_chat()

    def open_panel_chat(self, panel) -> None:
        facts = self.panel_facts(getattr(panel, "topic", ""))
        if not facts:
            return
        self.close_panel_chat()
        # Только имя панели: полный заголовок несёт ещё и состояние
        # («РАСПИСАНИЕ   baseline   23 тактов») и в узкой колонке переносится
        # на три строки, съедая ленту диалога.
        full = getattr(panel, "_title", "") or panel.topic
        title = full.split("   ")[0].strip() or panel.topic
        chat = PanelChat(title=title, facts=facts, id="panel-chat")
        # Слева у панелей со своим вводом, справа у остальных: у первых справа
        # уже живёт их собственная строка, и два ввода рядом путают.
        chat.add_class("left" if getattr(panel, "has_own_input", False)
                       else "right")
        self.mount(chat)
        panel.add_class("with-chat")
        self._chat_panel = panel
        self._chat_facts = facts
        self.refresh_hints()

    def close_panel_chat(self) -> None:
        for chat in self.query(PanelChat):
            chat.remove()
        panel = getattr(self, "_chat_panel", None)
        if panel is not None:
            panel.remove_class("with-chat")
        self._chat_panel = None
        self._chat_facts = []
        self._chat_offer = None

    def on_panel_chat_asked(self, event) -> None:
        event.stop()
        chats = list(self.query(PanelChat))
        if not chats:
            return
        chat = chats[0]
        chat.echo(event.question)
        chat.start_answer()
        self._panel_chat_worker(event.question)

    @work(thread=True, exclusive=True, group="panel-chat")
    def _panel_chat_worker(self, question: str) -> None:
        from ...agent import context, llm

        panel = self._chat_panel
        full = getattr(panel, "_title", "") if panel is not None else ""
        title = full.split("   ")[0].strip() or "панель"
        system = context.panel_prompt(title, list(self._chat_facts))
        import time

        t0 = time.monotonic()
        try:
            for piece in llm.stream(system, question, None):
                self.app.call_from_thread(self._panel_chat_piece, piece)
        except Exception as e:
            self.app.call_from_thread(self._panel_chat_fail, str(e))
        self.app.call_from_thread(self._panel_chat_done, time.monotonic() - t0)

    def _panel_chat_piece(self, piece: str) -> None:
        chats = list(self.query(PanelChat))
        if not chats:
            return
        chats[0].first_piece()
        chats[0].append(piece)

    def _panel_chat_done(self, seconds: float) -> None:
        chats = list(self.query(PanelChat))
        if chats:
            chats[0].finish(seconds)

    def _panel_chat_fail(self, message: str) -> None:
        chats = list(self.query(PanelChat))
        if chats:
            chats[0].note("не получилось: " + message[:160], "error")

    def after_command(self) -> None:
        """Пересобрать панели после команды. Переопределяется экраном."""

    # --- перекраска (смена темы) ------------------------------------------

    def repaint(self) -> None:
        """Перерисовать всё, что несёт цвета темы. Виджеты не пересобираем."""
        self.query_one("#topbar", TopBar).refresh_bar()
        self.query_one("#prompt", PromptBar).repaint()
        self.refresh_hints()
        self.refresh_context()
        self.redraw()

    def redraw(self) -> None:
        """Содержимое панелей экрана. Переопределяется экраном."""

    def set_busy(self, busy: bool) -> None:
        self.busy = busy
        try:
            bar = self.query_one("#prompt", PromptBar)
        except Exception:
            return
        if busy:
            from rich.text import Text

            bar.set_side(Text("считаю…", style=palette.role_hex("warning")))
        else:
            bar.set_side("")

    # --- действия ---------------------------------------------------------

    def _toggle(self, selector: str, shown: bool) -> bool:
        if not selector:
            return shown
        try:
            self.query_one(selector).display = not shown
        except Exception:
            return shown
        self.refresh_hints()
        return not shown

    def action_toggle_side(self) -> None:
        self.side_shown = self._toggle(self.SIDE_ID, self.side_shown)

    def action_toggle_tips(self) -> None:
        self.tips_shown = self._toggle(self.TIPS_ID, self.tips_shown)

    def action_to_picker(self) -> None:
        self.app.to_picker()

    def action_quit_app(self) -> None:
        self.app.exit(0)
