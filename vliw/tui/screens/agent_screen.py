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
from textual.binding import Binding
from textual.containers import Horizontal, ItemGrid, Vertical, VerticalScroll
from textual.widgets import Static

from .. import palette
from ..widgets import Chip, Console, ConsoleJournal, Panel, PanelToolbar, plural
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
    placeholder = ("спросите обычным языком   ·   /clear — очистить диалог   ·   "
                   "/ai — состояние модели")
    SIDE_ID = "#mind-right"
    TIPS_ID = "#p-questions"

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self._answer: Static | None = None
        self._buf = ""
        self._actions: list[str] = []
        self._model: tuple[bool | None, str] = (None, "проверяю…")
        self._console_expanded = False
        self._wide = ""
        # Каждый заданный вопрос с его счётом: сколько модель думала и сколько
        # действий успела сделать до ответа. Это история рабочей области, а не
        # украшение: развёрнутый ДИАЛОГ показывает её слева, и клик повторяет
        # вопрос — тот же приём, что и журнал запусков в ВЫВОДЕ КОМАНД.
        self._asked: list[dict] = []
        self._last_q = ""
        self._t0 = 0.0

    # --- раскладка --------------------------------------------------------

    def compose_body(self):
        with Horizontal(id="mind-body"):
            with Vertical(id="mind-left"):
                # Развёрнутый ДИАЛОГ — рабочая область с историей слева
                # (заполняется кодом при развороте, как слои у других панелей),
                # а не та же лента в большем размере. Кнопок над лентой нет
                # намеренно: очистка и повтор живут на ^L/^R, как в журнале
                # команд, — полоса инструментов над разговором читалась бы
                # как чужая панель и залезала на текст.
                with Panel(title="ДИАЛОГ", id="p-chat", topic="chat"):
                    with Horizontal(id="chat-body"):
                        yield Vertical(VerticalScroll(id="chat-hist"),
                                       id="chat-hist-col")
                        yield VerticalScroll(id="chat")
                yield Panel(ItemGrid(id="question-chips", min_column_width=34),
                            title="О ЧЁМ СПРОСИТЬ", id="p-questions")
            with Vertical(id="mind-right"):
                yield Panel(Static(id="seen"),
                            VerticalScroll(Static(id="seen-full"),
                                           id="seen-wide"),
                            title="ЧТО ВИДИТ АГЕНТ", id="p-seen", topic="seen")
                yield Panel(VerticalScroll(Static(id="trace")),
                            VerticalScroll(Static(id="trace-full"),
                                           id="trace-wide"),
                            title="ТРАССА", id="p-trace", topic="trace")
                yield Panel(
                    PanelToolbar(
                        ("↻ повторить", "journal-repeat",
                         "прогнать выбранный запуск заново (^R)"),
                        ("очистить", "journal-wipe",
                         "стереть журнал запусков (^L)"),
                        ("диалог ▶", "open-chat", "развернуть ДИАЛОГ"),
                    ),
                    Console(id="console"),
                    ConsoleJournal(id="journal"),
                    title="ВЫВОД КОМАНД",
                    id="p-mind-console", topic="console",
                    has_own_input=True)

    BINDINGS = ModeScreen.BINDINGS + [
        # Клавиши развёрнутого ДИАЛОГА — тот же паттерн, что у журнала
        # команд (^R повтор / ^L очистить), только действуют они здесь на
        # разговор. Никаких кнопок над лентой: действие есть, шума нет.
        Binding("ctrl+l", "dialog_clear", "очистить диалог", show=False),
        Binding("ctrl+r", "dialog_repeat", "повторить вопрос", show=False),
    ]

    def action_dialog_clear(self) -> None:
        """^L — стереть ленту диалога; история вопросов остаётся."""
        if self._wide == "chat":
            self.submit_line("/clear")

    def action_dialog_repeat(self) -> None:
        """^R — задать последний вопрос ещё раз (из истории или живой)."""
        if self._wide != "chat":
            return
        q = self._last_q or (self._asked[-1]["q"] if self._asked else "")
        if q:
            import time as _time

            self._t0 = _time.monotonic()
            self.submit_line(q)

    def panel_tool(self, tool: str) -> None:
        """Инструменты развёрнутых панелей АГЕНТА.

        Действия диалога живут на ^L/^R (см. BINDINGS), здесь остаётся
        только журнал запусков.
        """
        if tool in ("journal-repeat", "journal-wipe"):
            try:
                journal = self.query_one("#journal", ConsoleJournal)
            except Exception:
                return
            journal.action_repeat() if tool == "journal-repeat" \
                else journal.action_wipe()
            return
        super().panel_tool(tool)

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
        out = [("Enter", "спросить"), ("/", "команды"),
               ("Esc", "к выбору режима")]
        # Клавишу очистки — текстом в подсказки: лента растёт и при активном
        # использовании занимает весь экран, а «/clear уводит к выбору режима»
        # никто не угадает, пока не попробовал случайно.
        if self._wide == "chat":
            out.append(("/clear", "очистить диалог"))
        return out

    # --- ввод -------------------------------------------------------------

    def submit_line(self, raw: str) -> None:
        """В АГЕНТЕ `/clear` чистит диалог, а не уводит к выбору режима.

        Базовый экран — про команды, и там /clear действительно выход. Здесь
        разговор и есть рабочая область: после десятка вопросов лента занимает
        весь экран, и стереть её — первое, что хочется сделать, не покидая
        режим. К выбору режима по-прежнему ведут Esc и ^O, а история вопросов
        слева остаётся: чистится лента, не работа.
        """
        import time as _time

        line = raw.strip()
        if line.lstrip("/").lower() in ("clear", "cls"):
            self.clear_dialog()
            self._t0 = _time.monotonic()   # приветствие не должно ломать таймер
            return
        super().submit_line(raw)

    def clear_dialog(self) -> None:
        self.chat.remove_children()
        self._buf = ""
        self._answer = None
        self._greet()
        self._bubble(Static(Text("— лента очищена, история вопросов слева —",
                                 style=palette.role_hex("faint")),
                            classes="msg-note"))
        self._draw_chat()
        self.chat.scroll_end(animate=False)

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
        import time

        self._last_q = question
        self._t0 = time.monotonic()
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
        import time

        self.set_busy(False)
        if self._answer is not None and not self._buf.strip():
            self._answer.update(Text("ответа не было",
                                     style=palette.role_hex("warning")))
        # Вопрос в историю — только когда ответ закончился: строка без счёта
        # («сколько думала», «что успела сделать») вела бы себя как кнопка, у
        # которой половина функции не работает.
        if self._last_q:
            self._asked.append({"q": self._last_q,
                                "seconds": time.monotonic() - self._t0,
                                "acts": len(self._actions)})
            self._last_q = ""
        self._draw_seen()
        self._draw_chat()
        self.refresh_context()
        self.chat.scroll_end(animate=False)

    def after_command(self) -> None:
        self._draw_journal()
        self._draw_seen()

    def redraw(self) -> None:
        self._draw_seen()
        self._draw_trace()

    # --- правая колонка ---------------------------------------------------

    # --- развороты панелей --------------------------------------------------

    def _draw_chat(self) -> None:
        """Развёрнутый ДИАЛОГ — рабочая область, а не лента покрупнее.

        Слева — каждый заданный вопрос с его счётом (время, действия);
        клик повторяет вопрос, как клик по запуску в журнале команд повторяет
        просмотр его вывода. Справа — сама лента на всю оставшуюся ширину.
        Свёрнутая панель истории не видит: там вопрос задают один раз и
        уходят, возвращаться не к чему.
        """
        wide = self._wide == "chat"
        try:
            self.query_one("#chat-hist-col").display = wide
        except Exception:
            return
        panel = self.query_one("#p-chat", Panel)
        if not wide:
            panel.set_title("ДИАЛОГ")
            return
        n = len(self._asked)
        panel.set_title(f"ДИАЛОГ   ·   {n} "
                        f"{plural(n, 'вопрос', 'вопроса', 'вопросов')}"
                        f"   ·   /clear — очистить ленту")
        hist = self.query_one("#chat-hist", VerticalScroll)
        hist.remove_children()
        faint = palette.role_hex("faint")
        if not n:
            hist.mount(Static(Text("  задайте первый вопрос — он появится "
                                   "здесь,\n  и его можно будет повторить "
                                   "кликом", style=faint)))
            return
        accent = palette.role_hex("mind")
        title = palette.role_hex("title")
        for i, it in enumerate(self._asked, 1):
            row = Text()
            row.append(f"{i:>2}  ", style=faint)
            row.append(_wrap(it["q"], 40, 5), style=title)
            row.append("\n     ")
            row.append(f"{it['seconds']:.0f} с", style=faint)
            if it["acts"]:
                row.append(f"   ·   ⚙ {it['acts']} "
                           + plural(it["acts"], "действие", "действия",
                                    "действий"), style=accent)
            row.append("\n")
            hist.mount(Chip(row, value=it["q"], classes="hist-item"))

    def on_panel_expanded(self, event) -> None:
        topic = getattr(event.panel, "topic", "")
        self._console_expanded = topic == "console"
        self._wide = topic
        self._draw_journal()
        self._draw_seen()
        self._draw_trace()
        self._draw_chat()
        self.refresh_hints()
        # Строку вопроса поднимает ModeScreen: Textual зовёт обработчик у
        # КАЖДОГО класса в MRO, поэтому super() здесь звать не надо — иначе
        # строка монтируется дважды и падает на дублирующемся id.

    def on_panel_collapsed(self, event) -> None:
        self._console_expanded = False
        self._wide = ""
        self._draw_journal()
        self._draw_seen()
        self._draw_trace()
        self._draw_chat()
        self.refresh_hints()

    def panel_facts(self, topic: str) -> list[str]:
        """Факты по теме открытой панели. Спрашивают про то, на что смотрят."""
        s = self.app.session
        base = [f"Участок {s.scenario}, {len(s.dag_obj)} операций, "
                f"машина {s.model().name}."]
        cached = s.peek()
        if cached is not None:
            b, o, met = cached
            base.append(f"baseline {b.schedule.makespan} т., "
                        f"оракул {o.schedule.makespan} т., "
                        f"нижняя граница {met.lower_bound} т.")
        if topic == "trace":
            return base + (["Агент сделал: " + a for a in self._actions[-8:]]
                           or ["Агент ещё ничего не делал."])
        if topic == "chat":
            asked = self._asked
            lines = [f"В диалоге {len(list(self.chat.children))} сообщений, "
                     f"вопросов задано {len(asked)}."]
            if asked:
                lines.append("Последний вопрос: " + asked[-1]["q"])
                lines.append("Повторить любой вопрос можно кликом по нему "
                             "в истории слева.")
            return base + lines
        if topic == "console":
            con = self.query_one("#console", Console)
            return base + [f"Запусков в журнале: {len(con.runs)}."]
        return base

    def panel_chips(self, topic: str) -> list[str]:
        return {
            "seen": ["что из этого ты придумал, а что посчитано?",
                     "какие числа ты видишь прямо сейчас?",
                     "чего тебе не хватает, чтобы ответить точно?"],
            "trace": ["зачем ты это сделал?",
                      "какой командой это перепроверить?",
                      "что ты сделаешь следующим?"],
            "chat": ["повтори короче",
                     "с чего начать разбор этого участка?",
                     "какой вопрос стоит задать следующим?"],
            "console": ["перескажи последний отчёт",
                        "какую команду дать следующей?"],
        }.get(topic, [])

    def _section(self, label: str, note: str = "") -> Text:
        """Заголовок раздела: строчными и линейка до края."""
        width = max(40, self.app.size.width - 8)
        t = Text()
        t.append("  " + label + "  ", style=palette.role_hex("title") + " bold")
        used = len(label) + 4
        if note:
            t.append(note + "  ", style=palette.role_hex("faint"))
            used += len(note) + 2
        t.append("─" * max(0, width - used), style=palette.role_hex("line"))
        return t

    def _draw_seen_full(self) -> None:
        """Развёрнутое «ЧТО ВИДИТ АГЕНТ» — дословный контекст, а не сводка.

        Свёрнутая панель показывает вывеску: модель, участок, три числа.
        Развёрнутая показывает ровно те строки, которые уходят в модель, —
        столько, сколько их есть. Это единственное место, где видно, на чём
        ответ основан; без него «проверяемость» остаётся словом.
        """
        target = self.query_one("#seen-full", Static)
        panel = self.query_one("#p-seen", Panel)
        from ...agent import context, llm

        s = self.app.session
        dim, faint = palette.role_hex("dim"), palette.role_hex("faint")
        title = palette.role_hex("title")
        # Ровно те строки, что собирает контекст агента, — не пересказ их
        # своими словами: панель обязана показывать то, что реально уходит.
        try:
            facts = (context.machine_facts(s.model())
                     + context.schedule_facts(s)
                     + context.doctor_facts(s))
        except Exception:
            facts = self.panel_facts("seen")
        chars = sum(len(f) for f in facts)
        panel.set_title(f"ЧТО ВИДИТ АГЕНТ   ·   контекст дословно   ·   "
                        f"{len(facts)} {plural(len(facts), 'факт', 'факта', 'фактов')}")
        t = Text()
        t.append_text(self._section("модель"))
        t.append("\n\n")
        ok, detail = self._model
        t.append("    " + ("проверяю…" if ok is None else
                           (llm.describe() if ok else "нет модели: " + detail)),
                 style=(faint if ok is None else
                        (palette.role_hex("success") if ok
                         else palette.role_hex("warning"))))
        t.append("\n\n")
        t.append_text(self._section(
            "факты, которые уходят в модель",
            f"{chars} символов  ·  примерно {max(1, chars // 3)} токенов"))
        t.append("\n\n")
        for i, f in enumerate(facts, 1):
            t.append(f"    {i:>2}  ", style=faint)
            t.append(_wrap(f, max(40, self.app.size.width - 14), 8),
                     style=dim)
            t.append("\n")
        t.append("\n")
        t.append_text(self._section("чего тут нет"))
        t.append("\n\n")
        t.append("    Модель не видит исходник, не видит решётку и не умеет\n"
                 "    считать. Всё, что она может, — пересказать строки выше.\n"
                 "    Любое число из ответа, которого нет в этом списке,\n"
                 "    выдумано: сверьте командой (/doctor, /bounds, /compare).",
                 style=faint)
        target.update(t)

    def _draw_trace_full(self) -> None:
        """Развёрнутая ТРАССА — что агент делал сам, по шагам и с проверкой."""
        target = self.query_one("#trace-full", Static)
        panel = self.query_one("#p-trace", Panel)
        dim, faint = palette.role_hex("dim"), palette.role_hex("faint")
        n = len(self._actions)
        panel.set_title(f"ТРАССА   ·   действия агента   ·   "
                        f"{n} {plural(n, 'шаг', 'шага', 'шагов')}")
        t = Text()
        t.append_text(self._section("что агент сделал сам",
                                    "прежде чем отвечать"))
        t.append("\n\n")
        if not self._actions:
            t.append("    Агент ещё ничего не делал. Он берётся за действия\n"
                     "    сам: загрузить файл, переключить участок, посчитать\n"
                     "    расписание — и каждое попадает сюда.", style=faint)
        else:
            for i, note in enumerate(self._actions, 1):
                t.append(f"    {i:>2}  ", style=palette.role_hex("mind"))
                t.append(_wrap(note, max(40, self.app.size.width - 14), 8),
                         style=dim)
                t.append("\n")
        t.append("\n")
        t.append_text(self._section("перепроверить"))
        t.append("\n\n")
        for cmd, note in (("/doctor", "где именно теряются такты"),
                          ("/compare", "оба расписания бок о бок"),
                          ("/bounds", "предел участка"),
                          ("/ai", "состояние модели")):
            t.append("    " + cmd.ljust(12), style=palette.role_hex("mind"))
            t.append(note + "\n", style=faint)
        t.append("\n    Числа считает ядро. Трасса нужна, чтобы не верить\n"
                 "    агенту на слово, а повторить его шаги руками.",
                 style=faint)
        target.update(t)

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
        journal.load(con.runs, self.mode, list(self.app.commands))

    def _draw_seen(self) -> None:
        wide = self._wide == "seen"
        self.query_one("#seen-wide").display = wide
        self.query_one("#seen", Static).display = not wide
        if wide:
            self._draw_seen_full()
            return
        self.query_one("#p-seen", Panel).set_title("ЧТО ВИДИТ АГЕНТ")
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
        wide = self._wide == "trace"
        self.query_one("#trace-wide").display = wide
        self.query_one("#trace", Static).display = not wide
        if wide:
            self._draw_trace_full()
            return
        self.query_one("#p-trace", Panel).set_title("ТРАССА")
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
