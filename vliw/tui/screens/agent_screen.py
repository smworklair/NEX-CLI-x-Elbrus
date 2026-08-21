"""АГЕНТ — диалог, у которого видно основание.

Претензия к прежнему чату была простая: он отвечал текстом в ту же ленту, где
до этого печатались отчёты, и понять, на чём основан ответ, было нельзя.

Здесь ответ и его основание разведены. Слева — разговор, ответ печатается по
мере поступления. Справа — ровно те числа, которые агенту переданы, и трасса:
что он сделал сам, прежде чем отвечать (загрузил файл, переключил участок,
посчитал расписание). Ответ можно перепроверить теми же командами, поэтому
трасса — не украшение, а способ не поверить агенту на слово.
"""

from __future__ import annotations

from rich.text import Text
from textual.containers import Horizontal, ItemGrid, Vertical, VerticalScroll
from textual.widgets import Static

from .. import palette
from ..widgets import Chip, Console, ConsoleJournal, Panel, plural
from .base import ModeScreen

QUESTIONS = [
    "почему этот участок медленный?",
    "где теряются такты и что менять?",
    "сравни baseline с точным поиском",
    "что за монопольный порт ,5?",
    "загрузи examples/probe.s и разбери",
    "какой предел у этого участка?",
]


def _wrap(text: str, width: int, indent: int) -> str:
    """Перенос с висячим отступом — колонка узкая, а находки длинные."""
    import textwrap

    pad = " " * indent
    return ("\n" + pad).join(textwrap.wrap(text, max(12, width - indent)) or [""])


class AgentScreen(ModeScreen):
    mode = "mind"
    mode_title = "АГЕНТ"
    mode_subtitle = "диалог"
    placeholder = "спросите обычным языком   ·   /ai — состояние модели   ·   /команда"
    SIDE_ID = "#mind-right"
    TIPS_ID = "#p-questions"

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self._answer: Static | None = None
        self._buf = ""
        self._actions: list[str] = []
        self._model: tuple[bool | None, str] = (None, "проверяю…")
        self._console_expanded = False

    # --- раскладка --------------------------------------------------------

    def compose_body(self):
        with Horizontal(id="mind-body"):
            with Vertical(id="mind-left"):
                yield Panel(VerticalScroll(id="chat"), title="ДИАЛОГ", id="p-chat")
                yield Panel(ItemGrid(id="question-chips", min_column_width=34),
                            title="О ЧЁМ СПРОСИТЬ", id="p-questions")
            with Vertical(id="mind-right"):
                yield Panel(Static(id="seen"), title="ЧТО ВИДИТ АГЕНТ", id="p-seen")
                yield Panel(VerticalScroll(Static(id="trace")),
                            title="ТРАССА", id="p-trace")
                yield Panel(Console(id="console"),
                            ConsoleJournal(id="journal"),
                            title="ВЫВОД КОМАНД",
                            id="p-mind-console", topic="console",
                            has_own_input=True)

    def on_ready(self) -> None:
        grid = self.query_one("#question-chips", ItemGrid)
        for q in QUESTIONS:
            grid.mount(Chip("› " + q, q, classes="chip chip-question"))
        self._draw_seen()
        self._draw_trace()
        self._seed_console()
        self._greet()
        self._check_model()
        self._watch_warmup()

    def _watch_warmup(self) -> None:
        """Пока модель греется — обновлять панель, потом перестать.

        Таймер снимает сам себя: держать вечный опрос ради строки, которая
        меняется дважды за сессию, незачем.
        """
        from ...agent import llm

        if not llm.is_local():
            return

        def tick() -> None:
            from ...agent import local

            self._draw_seen()
            if local.warm_state()[0] in ("ready", "failed"):
                timer.stop()

        timer = self.set_interval(0.7, tick)

    def _seed_console(self) -> None:
        con = self.console
        if con is None:
            return
        dim = palette.role_hex("dim")
        accent = palette.role_hex("mind")
        con.write(Text("проверить агента теми же командами:", style=dim))
        for cmd, note in (("/doctor", "потери"), ("/compare", "оба расписания"),
                          ("/bounds", "предел"), ("/ai", "состояние модели")):
            row = Text()
            row.append("  " + cmd.ljust(11), style=accent)
            row.append(note, style=dim)
            con.write(row)

    def hint_pairs(self):
        return [("Enter", "спросить"), ("/", "команды"), ("^O", "выбор режима")]

    def context_bits(self) -> str:
        from ...agent import llm

        base = super().context_bits()
        return f"{base}   ·   {llm.describe()}"

    # --- лента ------------------------------------------------------------

    @property
    def chat(self) -> VerticalScroll:
        return self.query_one("#chat", VerticalScroll)

    def _bubble(self, widget: Static) -> None:
        self.chat.mount(widget)
        self.chat.scroll_end(animate=False)

    def _greet(self) -> None:
        dim = palette.role_hex("dim")
        t = Text()
        t.append("числа считает ядро, агент их объясняет.\n",
                 style=palette.role_hex("text"))
        t.append("что он сделал перед ответом — в трассе справа; "
                 "любой ответ можно перепроверить командой.", style=dim)
        self._bubble(Static(t, classes="msg-note"))

    def _check_model(self) -> None:
        self.run_worker(self._model_worker, thread=True, group="mind")

    def _model_worker(self) -> None:
        from ...agent import agent as agent_mod

        try:
            ok, detail = agent_mod.status()
        except Exception as e:
            ok, detail = False, str(e)
        self.app.call_from_thread(self._model_done, ok, detail)

    def _model_done(self, ok: bool, detail: str) -> None:
        # Состояние модели — в панель фактов, а не в ленту: проверка идёт по
        # сети и приходит когда угодно, в том числе посреди чужого ответа.
        self._model = (ok, detail)
        self._draw_seen()

    # --- ввод -------------------------------------------------------------

    def handle_line(self, line: str) -> None:
        if line.startswith("/"):
            self.run_core(line)
            return
        self._ask(line)

    def _ask(self, question: str) -> None:
        head = Text()
        head.append("▌ ", style=palette.role_hex("faint"))
        head.append("вы", style=palette.role_hex("dim"))
        head.append("\n")
        head.append(question, style=palette.role_hex("title"))
        self._bubble(Static(head, classes="msg-you"))

        mark = Text()
        mark.append("▌ ", style=palette.role_hex("mind"))
        mark.append("nex", style=f"{palette.role_hex('mind')} bold")
        self._bubble(Static(mark, classes="msg-mark"))

        self._buf = ""
        self._actions = []
        self._answer = Static(Text("…", style=palette.role_hex("faint")),
                              classes="msg-nex")
        self._bubble(self._answer)
        self.set_busy(True)
        self.run_worker(lambda: self._ask_worker(question), thread=True,
                        exclusive=True, group="mind")

    def _ask_worker(self, question: str) -> None:
        try:
            for kind, value in self.app.session.agent().ask_stream(question):
                self.app.call_from_thread(self._chunk, kind, value)
        except Exception as e:
            self.app.call_from_thread(self._chunk, "error", str(e))
        self.app.call_from_thread(self._ask_done)

    def _chunk(self, kind: str, value: str) -> None:
        if kind == "action":
            self._actions.append(value)
            self._draw_trace()
            return
        if kind == "error":
            t = Text()
            t.append("без модели: ", style=palette.role_hex("warning"))
            t.append(value[:160], style=palette.role_hex("dim"))
            self._bubble(Static(t, classes="msg-note"))
            return
        self._buf += value
        if self._answer is not None:
            self._answer.update(self._render_answer(self._buf))
            self.chat.scroll_end(animate=False)

    def _render_answer(self, text: str) -> Text:
        """Лёгкая разметка ответа: **жирное**, `код`, списки — без markdown."""
        from ...ui import agent_view

        out = Text()
        for i, line in enumerate(text.split("\n")):
            if i:
                out.append("\n")
            body = line.strip()
            if body.startswith(("- ", "* ")):
                body = "— " + body[2:]
            out.append_text(Text.from_ansi(agent_view.markup(body)))
        return out

    def _ask_done(self) -> None:
        self.set_busy(False)
        if self._answer is not None and not self._buf.strip():
            self._answer.update(Text("ответа не было",
                                     style=palette.role_hex("warning")))
        self._draw_seen()
        self.refresh_context()
        self.chat.scroll_end(animate=False)

    def after_command(self) -> None:
        self._draw_seen()

    def redraw(self) -> None:
        self._draw_seen()
        self._draw_trace()

    # --- правая колонка ---------------------------------------------------

    # --- развороты панелей --------------------------------------------------

    def on_panel_expanded(self, event) -> None:
        event.stop()
        if getattr(event.panel, "topic", "") == "console":
            self._console_expanded = True
            self._draw_journal()

    def on_panel_collapsed(self, event) -> None:
        event.stop()
        self._console_expanded = False
        self._draw_journal()

    def _draw_journal(self) -> None:
        journal = self.query_one("#journal", ConsoleJournal)
        con = self.query_one("#console", Console)
        panel = self.query_one("#p-mind-console", Panel)
        journal.display = self._console_expanded
        con.display = not self._console_expanded
        if not self._console_expanded:
            panel.set_title("ВЫВОД КОМАНД")
            return
        n = len(con.runs)
        panel.set_title(f"ВЫВОД КОМАНД   ·   журнал   ·   "
                        f"{n} {plural(n, 'запуск', 'запуска', 'запусков')}")
        journal.load(con.runs, self.mode)

    def _draw_seen(self) -> None:
        target = self.query_one("#seen", Static)
        s = self.app.session
        dim = palette.role_hex("dim")
        title = palette.role_hex("title")
        t = Text()

        def row(key: str, value: str, style: str = "") -> None:
            t.append(key.ljust(13), style=dim)
            t.append(value, style=style or title)
            t.append("\n")

        from ...agent import llm

        ok, detail = self._model
        if ok is None:
            row("модель", detail, palette.role_hex("faint"))
        elif ok:
            row("модель", llm.describe(), palette.role_hex("success"))
            # Прогрев видно, пока он идёт. Молчащий интерфейс во время
            # семисекундного подъёма сервера читается как «зависло», а
            # человек в этот момент как раз выбирает, что спросить.
            if llm.is_local():
                from ...agent import local

                state, note = local.warm_state()
                if state == "warming":
                    row("", f"греется — {note}", palette.role_hex("warning"))
                elif state == "ready":
                    row("", "прогрета, первый ответ быстрый",
                        palette.role_hex("faint"))
                elif state == "failed":
                    row("", "прогрев не удался, ответит медленнее",
                        palette.role_hex("faint"))
        else:
            row("модель", "нет сети", palette.role_hex("warning"))
            t.append(_wrap(detail, 40, 13), style=palette.role_hex("faint"))
            t.append("\n")
        row("участок", s.scenario)
        row("инструкций", str(len(s.dag_obj)))
        row("машина", s.model().name)
        cached = s.peek()
        if cached is None:
            t.append("\n")
            t.append("расписание ещё не считалось — агент посчитает его сам,\n"
                     "прежде чем отвечать", style=palette.role_hex("faint"))
            target.update(t)
            return
        base, orc, met = cached
        t.append("\n")
        row("baseline", f"{base.schedule.makespan} т.")
        row("оракул", f"{orc.schedule.makespan} т.",
            f"{palette.role_hex('success')} bold")
        row("предел", f"{met.lower_bound} т.")
        t.append("это те же числа, что в РАЗБОРЕ", style=palette.role_hex("faint"))
        target.update(t)

    def _draw_trace(self) -> None:
        target = self.query_one("#trace", Static)
        if not self._actions:
            target.update(Text("агент ещё ничего не делал",
                               style=palette.role_hex("faint")))
            return
        t = Text()
        for i, note in enumerate(self._actions):
            if i:
                t.append("\n")
            t.append("· ", style=palette.role_hex("mind"))
            t.append(_wrap(note, 40, 2), style=palette.role_hex("dim"))
        target.update(t)
