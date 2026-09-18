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
from textual.widgets import Input, Static

from .. import palette
from ..widgets import (Chip, Panel, PromptBar, Tool, plural)
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
    placeholder = "спросите обычным языком"
    key_placeholder = "вставь API-ключ и нажми Enter…"
    hint = "/clear — очистить   ·   ключ — вставь сюда"
    SIDE_ID = "#mind-right"
    TIPS_ID = "#p-questions"

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self._answer: Static | None = None
        self._buf = ""
        self._actions: list[str] = []
        self._model: tuple[bool | None, str] = (None, "проверяю…")
        self._wide = ""
        #: Ждём вставки ключа вместо вопроса (см. _maybe_ask_key).
        self._awaiting_key = False
        #: Просьбу показали один раз за жизнь экрана — не нудим повторами.
        self._key_offered = False
        # Каждый заданный вопрос с его счётом: сколько модель думала и сколько
        # действий успела сделать до ответа. Это история рабочей области, а не
        # украшение: развёрнутый ДИАЛОГ показывает её слева, и клик повторяет
        # вопрос — тот же приём, что и журнал запусков в ВЫВОДЕ КОМАНД.
        self._asked: list[dict] = []
        self._last_q = ""
        self._t0 = 0.0
        #: Сколько реплик общей переписки уже в ленте (см. _sync_dialog).
        self._shown = 0
        #: Каталог моделей: выбранный провайдер, фильтр, заметка. Состояние
        #: только на сессию — как и ключ.
        self._model_prov: str | None = None
        self._model_filter = ""
        self._model_note = ""
        #: Штаб: миссии на проверенных подключениях. Только память сессии:
        #: [{id, conn, area, script, question, status, answer}].
        self._hq_tasks: list[dict] = []
        self._hq_seq = 0
        self._hq_conn = 0
        self._hq_area = "doctor"
        #: Глушим эхо программной записи в поле поиска (см. on_input_changed).
        self._mute_filter = False

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
                # ШТАБ — главный блок правой колонки: сводка + задача всегда
                # видны, детали (подключения, участок, скрипт, список миссий)
                # — в развороте. Двойной клик разворачивает каждый блок.
                yield Panel(Static(id="hq-mini"),
                            Input(placeholder="задача штабу… (Enter — отправить)",
                                  id="hq-task"),
                            VerticalScroll(id="hq-wide"),
                            title="ШТАБ", id="p-hq", topic="hq")
                # ПОДКЛЮЧЕНИЕ — мини-блок: провайдер на один клик + ключ.
                # Каталог, поиск-фильтр и проверка — только в развороте.
                with Panel(title="ПОДКЛЮЧЕНИЕ", id="p-model", topic="model"):
                    yield Static(id="model")
                    with Vertical(id="model-mini"):
                        yield ItemGrid(id="model-provs-mini",
                                       min_column_width=12)
                        with Horizontal(id="model-mini-row"):
                            yield Input(
                                placeholder="ключ… (Enter — подключить)",
                                password=True, id="model-key-mini")
                            yield Tool("подключить", "mconnect-mini",
                                       id="model-go")
                    yield VerticalScroll(id="model-wide")
                yield Panel(Static(id="seen"),
                            VerticalScroll(Static(id="seen-full"),
                                           id="seen-wide"),
                            title="ЧТО ВИДИТ АГЕНТ", id="p-seen", topic="seen")
                yield Panel(VerticalScroll(Static(id="trace")),
                            VerticalScroll(Static(id="trace-full"),
                                           id="trace-wide"),
                            title="ТРАССА", id="p-trace", topic="trace")
                # GIT-панели здесь НЕТ осознанно: агент живёт одну сессию и
                # не связан с общими экранами — ни общего журнала запусков,
                # ни коммитов. Вывод команд (`/doctor`, `/run`, …) идёт тем
                # же пузырём в диалог (см. _core_done), а не в консоль.

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

        Журнала запусков здесь нет (связи с GIT нет осознанно), поэтому
        все инструменты — базовые; действия диалога живут на ^L/^R.
        """
        super().panel_tool(tool)

    def on_screen_resume(self) -> None:
        """Вернулись на экран — подобрать реплики, добавленные в другом окне.

        Экран живёт по одному экземпляру на сессию (`NexApp._mode_screen`),
        поэтому повторный вход ленту не пересобирает: она осталась какой
        была. А разговор мог уйти вперёд — его продолжили в колонке КОДа.
        """
        try:
            self._sync_dialog()
        except Exception:
            pass

    def on_ready(self) -> None:
        grid = self.query_one("#question-chips", ItemGrid)
        for q in QUESTIONS:
            grid.mount(Chip("› " + q, q, classes="chip chip-question"))
        self._draw_seen()
        self._draw_trace()
        self._draw_model()
        self._draw_hq()
        self._greet()
        self._maybe_ask_key()
        self._check_model()
        self._watch_warmup()
        self._take_pending_question()

    def _maybe_ask_key(self) -> None:
        """Перед началом — просьба вставить ключ, если в сессии его нет.

        Только здесь, в АГЕНТЕ. Смотрят именно на ключ СЕССИИ (память), а не
        на сохранённые файлы: вставил — работаешь, закрыл терминал — ключа
        нет. Решение синхронное, без сети.
        """
        from ...agent import llm

        if self._key_offered or llm.has_session_key():
            return
        self._key_offered = True
        self._awaiting_key = True
        try:
            bar = self.query_one("#prompt", PromptBar)
            bar.input.placeholder = self.key_placeholder
        except Exception:
            pass
        t = Text()
        t.append("вставь API-ключ прямо сюда и нажми Enter — и спрашивай.\n",
                 style=palette.role_hex("title"))
        t.append("Ключ живёт только до закрытия терминала, никуда не "
                 "сохраняется.\n",
                 style=palette.role_hex("dim"))
        t.append("Без ключа тоже можно: просто спроси, отвечу по уже "
                 "посчитанным числам.\n",
                 style=palette.role_hex("dim"))
        hint = llm.key_source_hint(llm.provider())
        if hint:
            t.append(hint, style=palette.role_hex("faint"))
        self._bubble(Static(t, classes="msg-note"))
        self.chat.scroll_end(animate=False)

    def _stop_awaiting_key(self) -> None:
        """Вернуть строку в обычный режим (ключ принят или задан вопрос)."""
        self._awaiting_key = False
        try:
            bar = self.query_one("#prompt", PromptBar)
            bar.input.placeholder = self.placeholder
        except Exception:
            pass

    def _adopt_key(self, raw: str) -> None:
        """Вставленный ключ: принять, не светя его нигде, подтвердить маской.

        Сырая строка не попадает ни в переписку (`session.dialog`), ни в
        историю строки (`PromptBar.history`, стрелка ↑) — только маска.
        """
        from ...agent import llm

        line = raw.strip()
        try:
            bar = self.query_one("#prompt", PromptBar)
            bar.history = [h for h in bar.history if h != line]
        except Exception:
            pass
        try:
            label, shown, repaired = llm.adopt_pasted_key(line)
        except llm.LLMError as e:
            t = Text()
            t.append("не похоже на ключ: ", style=palette.role_hex("warning"))
            t.append(str(e)[:120], style=palette.role_hex("dim"))
            self._bubble(Static(t, classes="msg-note"))
            return
        self._stop_awaiting_key()
        t = Text()
        t.append("ключ принят: ", style=palette.role_hex("success"))
        t.append(f"{label} · {shown}", style=palette.role_hex("title"))
        if repaired:
            t.append("\nпочинил вставку: " + "; ".join(repaired),
                     style=palette.role_hex("warning"))
        t.append("\nтолько на эту сессию: закроешь терминал — ключа не будет. "
                 "Спрашивай.",
                 style=palette.role_hex("dim"))
        self._bubble(Static(t, classes="msg-note"))
        self.chat.scroll_end(animate=False)
        self._check_model()
        self.refresh_context()

    def _take_pending_question(self) -> None:
        """Вопрос, привезённый мостиком из журнала, — в строку, не в отправку.

        Кнопка «в агента» у прогона решает только одно: о чём спросить.
        Отправлять или стереть — решает тот, кто нажал. Поэтому текст
        подставляется, а Enter остаётся за человеком.
        """
        q = getattr(self.app.session, "pending_question", "")
        if not q:
            return
        self.app.session.pending_question = ""
        try:
            bar = self.query_one("#prompt", PromptBar)
        except Exception:
            return
        bar.focus_input()
        bar.set_value(q)

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
        # Чистим и общую переписку: иначе очищенная лента возвращалась бы
        # целиком при следующем входе на экран (её поднимает _replay_dialog).
        self.app.session.dialog.clear()
        self._shown = 0
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
        self._sync_dialog()

    def _sync_dialog(self) -> None:
        """Досыпать в ленту реплики, которых в ней ещё нет.

        Спрашивают агента из трёх мест — колонки в КОДЕ, вкладки АГЕНТ и
        этого экрана, — и до общей переписки это были три разных разговора:
        задал вопрос в колонке, развернул на весь экран, а тут пусто. Лента
        поднимается из `session.dialog`, поэтому «развернуть» значит
        продолжить, а не начать заново.

        Показанное считается по счётчику, а не перерисовывается целиком:
        ответ приходит потоком в живой виджет, и снос-монтаж на каждый
        токен мигал бы всей лентой.
        """
        for msg in self.app.session.dialog[self._shown:]:
            if msg["role"] == "you":
                head = Text()
                head.append("▌ ", style=palette.role_hex("faint"))
                head.append("вы", style=palette.role_hex("dim"))
                head.append("\n")
                head.append(msg["text"], style=palette.role_hex("title"))
                self._bubble(Static(head, classes="msg-you"))
                continue
            mark = Text()
            mark.append("▌ ", style=palette.role_hex("mind"))
            mark.append("nex", style=f"{palette.role_hex('mind')} bold")
            self._bubble(Static(mark, classes="msg-mark"))
            body = (self._render_answer(msg["text"]) if msg["text"]
                    else Text("…", style=palette.role_hex("faint")))
            widget = Static(body, classes="msg-nex")
            self._bubble(widget)
            # Последняя реплика может быть ещё в пути — в неё и польётся
            # поток ответа (см. _chunk).
            self._answer = widget
        self._shown = len(self.app.session.dialog)

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
        self._draw_model()
        self._draw_hq()

    # --- ввод -------------------------------------------------------------

    def handle_line(self, line: str) -> None:
        from ...agent import llm

        if line.startswith("/"):
            self.run_core(line)
            return
        if self._awaiting_key:
            if llm.looks_like_key_text(line):
                self._adopt_key(line)
                return
            # Обычный вопрос вместо ключа — значит, человек выбрал офлайн:
            # больше не ждём, спрашиваем как обычно.
            self._stop_awaiting_key()
        self._ask(line)

    def _ask(self, question: str) -> None:
        import time

        self._last_q = question
        self._t0 = time.monotonic()
        # Переписка одна на сессию: этот же разговор виден в колонке агента
        # и во вкладке АГЕНТ нижнего дока КОДа. См. Session.dialog.
        self.app.session.dialog.append({"role": "you", "text": question,
                                        "facts": []})
        self.app.session.dialog.append({"role": "nex", "text": "",
                                        "facts": [], "waiting": True})
        self._buf = ""
        self._actions = []
        # Лента рисуется из переписки, а не отдельным кодом на каждый путь:
        # вопрос мог прийти и отсюда, и из колонки в КОДе, и рисовать его
        # двумя способами значит однажды получить два разных вида одного
        # разговора. `_sync_dialog` заодно отдаёт виджет ответа под поток.
        self._sync_dialog()
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
        dialog = self.app.session.dialog
        if dialog and dialog[-1]["role"] == "nex":
            dialog[-1]["text"] = self._buf
            dialog[-1]["waiting"] = False
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
        self._draw_seen()
        self._draw_model()
        self._draw_hq()

    def _core_done(self, out: str, err: str) -> None:
        """Вывод команды — в диалог, а не в консоль: консоли здесь нет.

        GIT-панель убрана осознанно (агент не связан с общими экранами), и
        прятать отчёт команды некуда — поэтому он показывается тем же пузырём
        в ленте, что ответы. В журнал других экранов ничего не пишется.
        """
        self.set_busy(False)
        t = Text()
        if out.strip():
            try:
                t.append_text(Text.from_ansi(out.rstrip("\n")))
            except Exception:
                t.append(out.rstrip("\n"))
        if err.strip():
            if out.strip():
                t.append("\n")
            t.append(err.strip()[:500], style=palette.role_hex("warning"))
        if not out.strip() and not err.strip():
            t.append("(пусто)", style=palette.role_hex("faint"))
        self._bubble(Static(t, classes="msg-note"))
        self.chat.scroll_end(animate=False)
        self.app.reload_palette()
        self.refresh_context()
        self.after_command()

    def redraw(self) -> None:
        self._draw_seen()
        self._draw_trace()
        self._draw_model()
        self._draw_hq()

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
            chip = Chip(row, value=it["q"], classes="hist-item")
            # Подсказка — вопрос ЦЕЛИКОМ и что из него вышло: в колонке
            # истории текст зажат 40 колонками, и длинный вопрос без
            # наведения обрезан ровно там, где начинается смысл.
            chip.tooltip = (f"{it['q']}\n{it['seconds']:.0f} с  ·  "
                            f"действий {it['acts']}\nклик — задать ещё раз")
            hist.mount(chip)

    def on_panel_expanded(self, event) -> None:
        topic = getattr(event.panel, "topic", "")
        self._wide = topic
        self._draw_seen()
        self._draw_trace()
        self._draw_chat()
        self._draw_model()
        self._draw_hq()
        if topic == "model":
            # В каталоге сразу ищем: фокус в поле поиска, список строится.
            try:
                self.query_one("#model-filter", Input).focus()
            except Exception:
                pass
        elif topic == "hq":
            try:
                self.query_one("#hq-task", Input).focus()
            except Exception:
                pass
        self.refresh_hints()
        # Строку вопроса поднимает ModeScreen: Textual зовёт обработчик у
        # КАЖДОГО класса в MRO, поэтому super() здесь звать не надо — иначе
        # строка монтируется дважды и падает на дублирующемся id.

    def on_panel_collapsed(self, event) -> None:
        self._wide = ""
        self._draw_seen()
        self._draw_trace()
        self._draw_chat()
        self._draw_model()
        self._draw_hq()
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
        if topic == "hq":
            from ...agent import hq as hq_mod

            lines = [f"Подключений: {len(self.headquarters_connections())}, "
                     f"миссий: {len(self._hq_tasks)}."]
            for task in self._hq_tasks[-5:]:
                mark = {"working": "…", "done": "✓",
                        "error": "✗"}.get(task["status"], "·")
                lines.append(
                    f"{mark} {task['conn']} · "
                    f"{hq_mod.AREA_LABEL.get(task['area'], task['area'])}: "
                    f"{task['question'][:80]}")
            return base + lines
        if topic == "model":
            from ...agent import llm

            prov = self._model_provider()
            state = self._catalog_connection(prov)
            return base + [f"Провайдер: {llm._label(prov)}.",
                           f"Каталог: {state['status']}, "
                           f"строк: {len(state['rows'])}."]
        return base

    def panel_chips(self, topic: str) -> list[str]:
        from ...agent import hq as hq_mod

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
            "hq": [q for _, _, q in hq_mod.AREAS if q],
            "model": ["какой провайдер выбрать для разбора?",
                      "чем облако отличается от локального сервера?",
                      "что делать, если ключ отклонён?"],
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

    # --- панель МОДЕЛЬ: мини + каталог --------------------------------------
    #
    # Аналог /models в OpenCode: живой каталог (где есть), пометка бесплатных,
    # клик сразу применяет на сессию. Всё только в память — как и вставка
    # ключа в диалоге. Разворот — штатным двойным кликом (топик "model").

    #: Сколько строк каталога показываем (остальное — уточни поиск).
    _MODEL_LIST_CAP = 80

    #: Порядок вкладок каталога: рабочие лошадки — облака — агрегаторы —
    #: российские — Local последним. `custom` (legacy) и внутренний `local`
    #: скрыты: первый — ради совместимости CLI, второй — ради TINY.
    CATALOG_ORDER = ("mistral", "gemini", "openai", "deepseek", "qwen",
                     "kimi", "grok", "anthropic", "glm", "muse",
                     "openrouter", "vercel", "gigachat", "yandex",
                     "local-server")

    #: Мини-блок ПОДКЛЮЧЕНИЕ: пять кнопок на один клик. Остальные провайдеры
    #: — только в развороте, иначе мини перестаёт быть мини.
    MINI_PROVS = ("mistral", "gemini", "openai", "deepseek", "local-server")

    #: Сколько строк каталога показываем (остальное — уточни поиск).
    _MODEL_LIST_CAP = 80

    def _model_provider(self) -> str:
        """Выбранный в каталоге провайдер (по умолчанию — текущий)."""
        from ...agent import llm

        allowed = set(llm.PROVIDERS) - {"custom", "local"}
        if self._model_prov in allowed:
            return self._model_prov
        cur = llm.provider()
        return cur if cur in allowed else "mistral"

    def _draw_model(self) -> None:
        wide = self._wide == "model"
        try:
            self.query_one("#model-wide").display = wide
            self.query_one("#model-mini").display = not wide
            self.query_one("#model", Static).display = not wide
        except Exception:
            return
        if wide:
            self._draw_model_full()
            return
        self.query_one("#p-model", Panel).set_title(
            "ПОДКЛЮЧЕНИЕ   ·   каталог — двойной клик")
        target = self.query_one("#model", Static)
        from ...agent import llm

        t = Text()
        dim, title = palette.role_hex("dim"), palette.role_hex("title")
        t.append("провайдер".ljust(13), style=dim)
        t.append(llm.describe(), style=title)
        t.append("\n")
        t.append("ключ".ljust(13), style=dim)
        if llm.has_session_key():
            t.append("вставлен (на сессию)", style=palette.role_hex("success"))
        else:
            t.append("нет — вставь ниже", style=palette.role_hex("warning"))
        target.update(t)
        self._redraw_model_provs_mini()

    def _redraw_model_provs_mini(self) -> None:
        """Подсветка выбранного провайдера в мини-блоке."""
        from ...agent import llm

        try:
            bar = self.query_one("#model-provs-mini", ItemGrid)
        except Exception:
            return
        if not bar.children:
            for p in self.MINI_PROVS:
                bar.mount(Tool(llm._label(p), f"mprov:{p}"))
        cur = self._model_provider()
        for tool in bar.query(Tool):
            name = tool.tool[6:] if tool.tool.startswith("mprov:") else ""
            mark = "● " if name == cur else ""
            label = llm._label(name) if name else ""
            tool.update(f"{mark}{label or name}")

    def _catalog_connection(self, prov: str | None = None) -> dict:
        from ...agent import llm

        prov = prov or self._model_provider()
        if not hasattr(self, "_catalog_connections"):
            self._catalog_connections: dict[str, dict] = {}
        if prov not in self._catalog_connections:
            key = llm.setting(llm.KEY_VAR.get(prov, ""), "")
            if prov == "gigachat":
                cid = llm.setting("GIGACHAT_CLIENT_ID", "")
                secret = llm.setting("GIGACHAT_SECRET", "") or llm.setting(
                    "GIGACHAT_CLIENT_SECRET", "")
                key = f"{cid}:{secret}" if cid and secret else ""
            self._catalog_connections[prov] = {
                "key": key, "url": llm.setting("NEX_LOCAL_URL",
                    "http://localhost:11434/v1") if prov == "local-server" else "",
                "folder": llm.setting("YANDEX_FOLDER_ID", "") if prov == "yandex" else "",
                "rows": [], "status": "locked", "note": "",
                "generation": 0, "selected": "", "backend": None,
                "draft_key": "", "verified": "",
            }
        return self._catalog_connections[prov]

    def _catalog_snapshot(self, prov: str) -> tuple[str, str, str, str]:
        state = self._catalog_connection(prov)
        return prov, state["key"], state["url"], state["folder"]

    def _invalidate_catalog(self, prov: str | None = None) -> None:
        state = self._catalog_connection(prov)
        state.update(rows=[], status="locked", note="", selected="", backend=None,
                     verified="", generation=state["generation"] + 1)

    def _refresh_catalog(self) -> None:
        if self._wide == "model" and self.is_mounted:
            self._draw_model_full()

    def _model_rows(self) -> tuple[list, str]:
        state = self._catalog_connection()
        return state["rows"], state["status"]

    _LOCAL_PRESETS = {"ollama": ("Ollama", "http://localhost:11434/v1"),
                      "studio": ("LM Studio", "http://localhost:1234/v1"),
                      "llama": ("llama.cpp", "http://localhost:8080/v1")}

    def _draw_model_full(self) -> None:
        wide = self.query_one("#model-wide", VerticalScroll)
        panel = self.query_one("#p-model", Panel)
        panel.set_title("ПОДКЛЮЧЕНИЕ   ·   провайдер → ключ → каталог")
        from ...agent import llm

        if not wide.children:
            wide.mount(Static("1 · провайдер", id="model-sec-prov"))
            provs = ItemGrid(id="model-provs", min_column_width=14)
            wide.mount(provs)
            for p in self.CATALOG_ORDER:
                provs.mount(Tool(llm._label(p), f"mprov:{p}"))
            wide.mount(Static("2 · ключ → подключить", id="model-sec-key"))
            wide.mount(Input(placeholder="ключ · Enter загружает модели",
                             password=True, id="model-key"))
            wide.mount(Tool("подключить / обновить каталог", "mconnect"))
            wide.mount(Static(id="model-status"))
            wide.mount(Static("локальный сервер: пресет или свой URL",
                              id="model-sec-local"))
            presets = ItemGrid(id="model-presets", min_column_width=16)
            wide.mount(presets)
            for name, (label, _) in self._LOCAL_PRESETS.items():
                presets.mount(Tool(label, f"mpreset:{name}"))
            wide.mount(Input(placeholder="Local URL · http://localhost:11434/v1",
                             id="model-url"))
            wide.mount(Input(placeholder="Yandex folder ID", id="model-folder"))
            wide.mount(Static(
                "Запусти сервер вручную: Ollama — ollama serve; LM Studio — Start Server; "
                "llama.cpp — llama-server -m <путь к существующему GGUF>. "
                "Загрузи уже установленную модель на сервере и нажми подключить. "
                "Здесь нет скачивания моделей и запуска TINY.", id="model-local-help"))
            wide.mount(Static("3 · каталог: клик применяет модель на сессию",
                              id="model-sec-list"))
            wide.mount(Static("поиск — только фильтр списка ниже: "
                              "печатай, Enter — взять первую строку",
                              id="model-filter-help"))
            wide.mount(Input(placeholder="фильтр каталога…", id="model-filter"))
            wide.mount(VerticalScroll(id="model-list"))
            wide.mount(Static(id="model-note"))
            wide.mount(Static("нет в списке? введи ID вручную",
                              id="model-sec-manual"))
            wide.mount(Input(placeholder="ID модели · Enter проверяет API (платный запрос)",
                             id="model-manual"))
            wide.mount(Tool("проверить модель (платный запрос к API)", "mcheck"))
            wide.mount(Tool("активировать проверенный ID", "mactivate", id="model-activate"))
        self._redraw_model_provs()
        self._sync_catalog_fields()
        self._draw_model_status()
        self._redraw_model_list()
        self._redraw_model_note()

    def _sync_catalog_fields(self) -> None:
        prov = self._model_provider()
        state = self._catalog_connection(prov)
        local = prov == "local-server"
        for wid in ("model-url", "model-presets"):
            self.query_one(f"#{wid}").display = local
        self.query_one("#model-folder").display = prov == "yandex"
        self.query_one("#model-manual").display = state["status"] in ("unsupported", "text")
        self.query_one("#model-key", Input).placeholder = (
            "ключ необязателен · Enter подключает Local" if local else
            "ключ · Enter загружает модели")
        if getattr(self, "_catalog_field_provider", None) != prov:
            self._catalog_field_provider = prov
            for wid, value in (("model-url", state["url"]),
                               ("model-folder", state["folder"]),
                               ("model-key", state["draft_key"] or ""),
                               ("model-manual", ""),
                               ("model-filter", "")):
                field = self.query_one(f"#{wid}", Input)
                with field.prevent(Input.Changed):
                    field.value = value


    def _draw_model_status(self) -> None:
        try:
            target = self.query_one("#model-status", Static)
        except Exception:
            return
        prov = self._model_provider()
        state = self._catalog_connection(prov)
        from ...agent import llm

        t = Text()
        label = llm._label(prov)
        status = state["status"]
        if status == "live":
            style = palette.role_hex("success")
            t.append(f"{label}: каталог загружен", style=style)
        elif status == "error":
            t.append(f"{label}: {state['note'] or 'ошибка'}",
                     style=palette.role_hex("warning"))
        elif status in ("unsupported", "text"):
            t.append(f"{label}: каталога нет — введи ID и проверь модель через API",
                     style=palette.role_hex("dim"))
        elif status == "locked":
            hint = llm.key_source_hint(prov)
            t.append(f"{label}: нужен ключ", style=palette.role_hex("warning"))
            if hint:
                t.append(f" — {hint}", style=palette.role_hex("faint"))
        else:
            t.append(f"{label}: загрузка каталога…",
                     style=palette.role_hex("dim"))
        target.update(t)

    def _redraw_model_provs(self) -> None:
        from ...agent import llm

        try:
            bar = self.query_one("#model-provs", ItemGrid)
        except Exception:
            return
        cur = self._model_provider()
        for tool in bar.query(Tool):
            name = tool.tool[6:] if tool.tool.startswith("mprov:") else ""
            mark = "● " if name == cur else ""
            label = llm._label(name) if name else ""
            tool.update(f"{mark}{label or name}")

    def _visible_model_rows(self) -> list:
        rows, _src = self._model_rows()
        q = self._model_filter.strip().lower()
        if not q:
            return rows
        return [r for r in rows
                if q in r.id.lower() or q in r.label.lower()]

    def _redraw_model_list(self) -> None:
        try:
            box = self.query_one("#model-list", VerticalScroll)
        except Exception:
            return
        box.remove_children()
        rows = self._visible_model_rows()
        for r in rows[:self._MODEL_LIST_CAP]:
            mark = "  [free]" if r.free else ""
            label = f"{r.label} · {r.id}" if r.label != r.id else r.id
            tool = Tool(Text(f"{label}{mark}"), f"model:{r.id}")
            tool.tooltip = r.id
            box.mount(tool)
        if len(rows) > self._MODEL_LIST_CAP:
            box.mount(Static(
                Text(f"… ещё {len(rows) - self._MODEL_LIST_CAP} — уточни поиск",
                     style=palette.role_hex("faint"))))
        if not rows:
            _rows, src = self._model_rows()
            hints = {"live": "",
                     "error": "сервер не ответил — проверь сеть или адрес",
                     "locked": "вставь ключ выше — список появится после подключения",
                     "unsupported": "введи ID модели в строке выше",
                     "text": "каталога нет — введи ID модели выше"}
            hint = hints.get(src, "")
            box.mount(Static(Text(
                "ничего не найдено" + (f" ({hint})" if hint else ""),
                style=palette.role_hex("faint"))))

    def _redraw_model_note(self, text: str = "") -> None:
        state = self._catalog_connection()
        if text:
            state["note"] = text
        try:
            self.query_one("#model-note", Static).update(
                Text(state["note"], style=palette.role_hex("dim")))
        except Exception:
            pass

    def _apply_catalog_model(self, mid: str, verify: bool = False) -> None:
        """Клик по модели: применить на сессию и закрыть окно."""
        from ...agent import llm

        prov = self._model_provider()
        state = self._catalog_connection(prov)
        listed = state["status"] == "live" and any(
            row.id == mid for row in state["rows"])
        manual = state["status"] in ("unsupported", "text") and state["verified"] == mid
        if not mid or not (listed or manual):
            self._redraw_model_note("сначала выбери строку каталога или проверь ID через API")
            return
        snapshot = self._catalog_snapshot(prov)
        try:
            if prov == "yandex" and not state["folder"]:
                raise llm.LLMError("Yandex: укажи folder ID")
            backend = llm.configured_backend(prov, mid, *snapshot[1:])
            updates = llm.provider_updates(prov, {
                "model": mid, "key": snapshot[1], "url": snapshot[2],
                "folder": snapshot[3]})
            if prov == "local-server":
                updates["NEX_LOCAL_KEY"] = snapshot[1]
        except Exception:
            self._redraw_model_note("не удалось применить модель — проверь ключ, URL и folder ID")
            return
        import os as _os

        for k, v in updates.items():
            if v is None:
                _os.environ.pop(k, None)
            else:
                _os.environ[k] = v
        self._model_prov = prov
        state["selected"] = mid
        state["backend"] = backend
        t = Text()
        t.append("модель: ", style=palette.role_hex("success"))
        t.append(f"{prov} · {mid} (на сессию)", style=palette.role_hex("title"))
        self._bubble(Static(t, classes="msg-note"))
        self.chat.scroll_end(animate=False)
        self.refresh_context()
        self._check_model()
        self._draw_model()
        self._redraw_hq()
        if verify:
            self._check_catalog_model()
        try:
            panel = self.query_one("#p-model", Panel)
            self.screen.minimize()
            panel.post_message(Panel.Collapsed())
        except Exception:
            pass

    def _build_verified_backend(self, prov: str, mid: str):
        from ...agent import llm

        state = self._catalog_connection(prov)
        folder = state["folder"] if prov == "yandex" else ""
        try:
            return llm.configured_backend(prov, mid, state["key"],
                                          state["url"], folder)
        except llm.LLMError:
            return None

    def headquarters_connections(self) -> list[tuple[str, object]]:
        """(label, backend) по подтверждённым выборам — подключения штаба."""
        from ...agent import llm

        if not hasattr(self, "_catalog_connections"):
            return []
        out: list[tuple[str, object]] = []
        for prov, state in self._catalog_connections.items():
            backend = state.get("backend")
            if backend is not None and state.get("selected"):
                out.append((f"{llm._label(prov)} · {state['selected']}", backend))
        return out

    # --- ШТАБ: главный блок -------------------------------------------------
    #
    # Мини: сводка (подключения · миссии · последняя) + поле задачи всегда
    # под рукой — отправить можно не разворачивая. Разворот: подключения,
    # участок работы, скрипт и список миссий с повтором/удалением.

    def _draw_hq(self) -> None:
        wide = self._wide == "hq"
        try:
            self.query_one("#hq-wide").display = wide
        except Exception:
            return
        if wide:
            self._draw_hq_full()
        else:
            self.query_one("#p-hq", Panel).set_title("ШТАБ")
        self._draw_hq_mini()

    def _draw_hq_full(self) -> None:
        from ...agent import llm

        wide = self.query_one("#hq-wide", VerticalScroll)
        n_conns = len(self.headquarters_connections())
        n_tasks = len(self._hq_tasks)
        self.query_one("#p-hq", Panel).set_title(
            f"ШТАБ   ·   подключений: {n_conns}   ·   миссий: {n_tasks}")
        if not wide.children:
            wide.mount(Static("подключение — на нём пойдёт задача "
                              "(выбирается в ПОДКЛЮЧЕНИИ)", id="hq-sec-conn"))
            wide.mount(ItemGrid(id="hq-conns", min_column_width=22))
            wide.mount(Static("участок работы", id="hq-sec-area"))
            wide.mount(ItemGrid(id="hq-areas", min_column_width=14))
            wide.mount(Static(id="hq-area-desc"))
            wide.mount(Static("скрипт — дописка к промпту (необязательно)",
                              id="hq-sec-script"))
            wide.mount(Input(placeholder="скрипт агенту… (необязательно)",
                             id="hq-script"))
            wide.mount(Static(id="hq-note"))
            wide.mount(Horizontal(
                Tool("отправить агента", "hqrun"),
                Tool("убрать выполненные", "hqclear"),
                id="hq-actions"))
            wide.mount(Static("миссии", id="hq-sec-list"))
            wide.mount(VerticalScroll(id="hq-list"))
        self._redraw_hq()

    def _draw_hq_mini(self) -> None:
        try:
            target = self.query_one("#hq-mini", Static)
        except Exception:
            return
        t = Text()
        dim, title = palette.role_hex("dim"), palette.role_hex("title")
        n_conns = len(self.headquarters_connections())
        working = sum(1 for task in self._hq_tasks
                      if task["status"] == "working")
        if not n_conns:
            t.append("нет подключений", style=palette.role_hex("warning"))
            t.append(" — выбери API и вставь ключ в ПОДКЛЮЧЕНИИ",
                     style=dim)
        else:
            t.append(f"подключений: {n_conns}", style=title)
            t.append(f"   ·   миссий: {len(self._hq_tasks)}", style=dim)
            if working:
                t.append(f"   ·   в работе: {working}",
                         style=palette.role_hex("mind"))
        if self._hq_tasks:
            last = self._hq_tasks[-1]
            mark = {"working": "… ", "done": "✓ ", "error": "✗ "}.get(
                last["status"], "· ")
            # Мини — в одну строку: колонка узкая, перенос здесь крадёт
            # целую строку у соседних блоков.
            t.append(f"\n{mark}{last['question'][:30]}", style=dim)
        else:
            t.append("\nзадача штабу — в поле ниже, Enter отправляет",
                     style=palette.role_hex("faint"))
        target.update(t)

    def _hq_note(self, text: str) -> None:
        try:
            self.query_one("#hq-note", Static).update(
                Text(text, style=palette.role_hex("dim")))
        except Exception:
            self._redraw_model_note(text)
        self._draw_hq_mini()

    def _redraw_hq(self) -> None:
        from ...agent import hq as hq_mod

        self._draw_hq_mini()
        try:
            conns = self.query_one("#hq-conns", ItemGrid)
            areas = self.query_one("#hq-areas", ItemGrid)
            box = self.query_one("#hq-list", VerticalScroll)
        except Exception:
            return
        labels = self.headquarters_connections()
        if self._hq_conn >= len(labels):
            self._hq_conn = 0
        conns.remove_children()
        if not labels:
            conns.mount(Static(Text("нет подключений — выбери модель "
                                    "в ПОДКЛЮЧЕНИИ",
                                    style=palette.role_hex("faint"))))
        for i, (label, _be) in enumerate(labels):
            mark = "● " if i == self._hq_conn else ""
            conns.mount(Tool(f"{mark}{label}", f"hqconn:{i}"))
        areas.remove_children()
        for aid, alabel, _q in hq_mod.AREAS:
            mark = "● " if aid == self._hq_area else ""
            areas.mount(Tool(f"{mark}{alabel}", f"hqarea:{aid}"))
        try:
            desc = next(q for aid, _, q in hq_mod.AREAS
                        if aid == self._hq_area)
            self.query_one("#hq-area-desc", Static).update(
                Text(desc or "свой вопрос — текст берётся из поля задачи",
                     style=palette.role_hex("faint")))
        except Exception:
            pass
        box.remove_children()
        for task in self._hq_tasks[-20:]:
            box.mount(Static(self._hq_task_text(task)))
            tools = Horizontal()
            box.mount(tools)
            tools.mount(Tool("ещё раз", f"hqretry:{task['id']}"))
            tools.mount(Tool("убрать", f"hqdel:{task['id']}"))

    def _hq_task_text(self, task: dict) -> Text:
        from ...agent import hq as hq_mod

        t = Text()
        mark = {"working": "… ", "done": "✓ ", "error": "✗ "}.get(
            task["status"], "· ")
        t.append(f"{mark}{task['conn']} · "
                 f"{hq_mod.AREA_LABEL.get(task['area'], task['area'])}",
                 style=palette.role_hex("title"))
        t.append(f"\nзадача: {task['question']}",
                 style=palette.role_hex("dim"))
        if task.get("script"):
            t.append(f"\nскрипт: {task['script']}",
                     style=palette.role_hex("faint"))
        if task.get("answer"):
            t.append(f"\n{task['answer']}",
                     style=palette.role_hex("text"))
        return t

    def _hq_run(self, retry: dict | None = None) -> None:
        from ...agent import hq as hq_mod

        labels = self.headquarters_connections()
        if not labels:
            self._hq_note("штаб: сначала подключи модель — ПОДКЛЮЧЕНИЕ ниже")
            return
        if self._hq_conn >= len(labels):
            self._hq_conn = 0
        try:
            script = self.query_one("#hq-script", Input).value or ""
        except Exception:
            script = ""
        try:
            asked = self.query_one("#hq-task", Input).value or ""
        except Exception:
            asked = ""
        if retry is not None:
            area = retry["area"]
            script = script or retry.get("script", "")
            asked = asked or retry.get("question", "")
        else:
            area = self._hq_area
        question = asked.strip() or hq_mod.AREA_QUESTION.get(area, "")
        if not question:
            self._hq_note("штаб: впиши задачу агенту")
            return
        try:
            system = hq_mod.mission_system(self.app.session, area, script)
        except Exception as e:  # noqa: BLE001 — факты не собрались, честно
            self._hq_note(f"штаб: нет данных — {e}"[:160])
            return
        label, backend = labels[self._hq_conn]
        self._hq_seq += 1
        task = {"id": self._hq_seq, "conn": label, "area": area,
                "script": script.strip(), "question": question,
                "status": "working", "answer": "",
                "backend": backend, "system": system}
        self._hq_tasks.append(task)
        self._redraw_hq()
        tid = task["id"]
        self.run_worker(lambda: self._hq_worker(tid), thread=True,
                        group=f"hq:{tid}", exclusive=True)

    def _hq_worker(self, tid: int) -> None:
        from ...agent import hq as hq_mod

        task = next((t for t in self._hq_tasks if t["id"] == tid), None)
        if task is None:
            return
        try:
            answer = hq_mod.run_mission(task["backend"], task["system"],
                                        task["question"])
            self.app.call_from_thread(self._hq_done, tid, True, answer)
        except Exception as e:  # noqa: BLE001 — любой отказ сети сюда
            self.app.call_from_thread(self._hq_done, tid, False, str(e)[:400])

    def _hq_done(self, tid: int, ok: bool, text: str) -> None:
        task = next((t for t in self._hq_tasks if t["id"] == tid), None)
        if task is None:
            return
        task["status"] = "done" if ok else "error"
        task["answer"] = text.strip()[:4000]
        task.pop("backend", None)
        task.pop("system", None)
        if self.is_mounted:
            self._redraw_hq()


    def _adopt_catalog_key(self, raw: str) -> None:
        """Ключ из поля каталога: явно за выбранным провайдером (без угадайки)."""
        from ...agent import llm

        prov = self._model_provider()
        state = self._catalog_connection(prov)
        state["draft_key"] = (raw or "").strip()
        self._connect_catalog()

    def _connect_catalog(self) -> None:
        from ...agent import llm

        prov = self._model_provider()
        state = self._catalog_connection(prov)
        raw = state["draft_key"]
        self._invalidate_catalog(prov)
        if raw:
            try:
                updates = llm.key_updates(prov, raw.split() if prov == "gigachat" else [raw])
            except llm.LLMError:
                state.update(status="error", note="проверь формат ключа; GigaChat: id:secret")
                self._refresh_catalog()
                return
            import os as _os

            for k, v in updates.items():
                _os.environ[k] = v
            state["key"] = (f"{updates['GIGACHAT_CLIENT_ID']}:{updates['GIGACHAT_SECRET']}"
                            if prov == "gigachat" else raw)
            state["draft_key"] = ""
            for fid in ("#model-key", "#model-key-mini"):
                try:
                    field = self.query_one(fid, Input)
                except Exception:
                    continue
                with field.prevent(Input.Changed):
                    field.value = ""
        if not state["key"] and prov != "local-server":
            self._refresh_catalog()
            return
        state["status"] = "loading"
        snapshot = self._catalog_snapshot(prov)
        gen = state["generation"]
        self._refresh_catalog()
        self.run_worker(lambda: self._catalog_fetch_worker(snapshot, gen),
                        thread=True, group=f"catalog:{prov}", exclusive=True)

    @staticmethod
    def _catalog_error(error: Exception, snapshot: tuple) -> str:
        from ...agent import llm
        from urllib.parse import quote

        note = (str(error) if isinstance(error, llm.LLMError) else
                "не удалось подключиться — проверь ключ, URL и сеть")
        secrets = [snapshot[1], snapshot[2], snapshot[3]]
        if snapshot[0] == "gigachat":
            secrets.extend(snapshot[1].split(":"))
        for secret in sorted(filter(None, secrets), key=len, reverse=True):
            note = note.replace(secret, "[скрыто]").replace(quote(secret, safe=""), "[скрыто]")
        return note[:240]

    def _catalog_fetch_worker(self, snapshot: tuple, gen: int) -> None:
        from ...agent import models as catalog

        prov, key, url, folder = snapshot
        status, note, rows = "error", "", []
        try:
            if prov == "local-server":
                url = catalog.local_base_url(url)
            rows, status = catalog.catalog(prov, key, url)
            if status not in ("locked", "live", "unsupported", "text", "error"):
                status = "error"
            if status != "live":
                rows = []
            if status == "error":
                note = "сервер не отдал каталог — проверь ключ, URL и сеть"
        except Exception as error:
            rows, status = [], "error"
            note = self._catalog_error(error, snapshot)
        out = {"rows": list(rows), "status": status, "note": note}
        self.app.call_from_thread(self._catalog_fetch_done, prov, gen, out)

    def _catalog_fetch_done(self, prov: str, gen: int, payload: dict) -> None:
        state = self._catalog_connection(prov)
        if gen != state["generation"]:
            return
        state.update(payload)
        if prov == self._model_provider():
            self._refresh_catalog()


    def _check_catalog_model(self, mid: str = "") -> None:
        prov = self._model_provider()
        state = self._catalog_connection(prov)
        manual = state["status"] in ("unsupported", "text")
        if not mid:
            mid = (self.query_one("#model-manual", Input).value.strip() if manual
                   else state["selected"])
        if not mid or (not manual and not any(
                row.id == mid for row in state["rows"])):
            self._redraw_model_note("выбери модель или введи ID для платной проверки")
            return
        if prov == "yandex" and not state["folder"]:
            self._redraw_model_note("Yandex: укажи folder ID и обнови каталог")
            return
        if state["status"] not in ("live", "unsupported", "text"):
            return
        state["generation"] += 1
        state["verified"] = ""
        snapshot, gen = self._catalog_snapshot(prov), state["generation"]
        self._redraw_model_note("проверка модели через API — запрос может быть платным…")
        self.run_worker(lambda: self._catalog_check_worker(snapshot, gen, mid),
                        thread=True, group=f"catalog:{prov}", exclusive=True)

    def _catalog_check_worker(self, snapshot: tuple, gen: int, mid: str) -> None:
        from ...agent import llm

        prov, key, url, folder = snapshot
        success = False
        try:
            be = llm.configured_backend(prov, mid, key, url, folder)
            be.complete("Отвечай одним словом.", "Скажи «готово».", temperature=0.0)
            success, note = True, "модель доступна — можно активировать"
        except Exception as error:
            note = self._catalog_error(error, snapshot)
        self.app.call_from_thread(self._catalog_note_done, prov, gen, mid, success, note)

    def _catalog_note_done(self, prov: str, gen: int, mid: str,
                           success: bool, note: str) -> None:
        state = self._catalog_connection(prov)
        if gen != state["generation"]:
            return
        state.update(verified=mid if success else "", note=note)
        if prov == self._model_provider():
            self._refresh_catalog()

    def on_input_changed(self, event) -> None:
        wid = getattr(event, "input", None)
        if wid is None:
            return
        iid = getattr(wid, "id", "")
        if iid == "model-filter":
            event.stop()
            if self._mute_filter:
                return
            self._model_filter = wid.value or ""
            self._redraw_model_list()
        elif iid in ("model-url", "model-folder"):
            event.stop()
            state = self._catalog_connection()
            field = "url" if iid == "model-url" else "folder"
            value = (wid.value or "").strip()
            if state[field] or value:
                state[field] = value
                self._invalidate_catalog()
        elif iid in ("model-key", "model-key-mini"):
            event.stop()
            state = self._catalog_connection()
            state["draft_key"] = (wid.value or "").strip()
            if state["draft_key"]:
                self._invalidate_catalog()

    def on_input_submitted(self, event) -> None:
        wid = getattr(event, "input", None)
        if wid is None:
            return
        iid = getattr(wid, "id", "")
        if iid in ("model-key", "model-key-mini"):
            event.stop()
            self._adopt_catalog_key(wid.value or "")
        elif iid == "model-url":
            event.stop()
            self._connect_catalog()
        elif iid == "model-manual":
            event.stop()
            mid = (wid.value or "").strip()
            if mid:
                self._apply_catalog_model(mid, verify=True)
        elif iid == "model-filter":
            event.stop()
            rows = self._visible_model_rows()
            if rows:
                self._apply_catalog_model(rows[0].id)
        elif iid == "hq-task":
            event.stop()
            self._hq_run()

    def panel_tool(self, tool: str) -> None:
        """Инструменты каталога МОДЕЛИ + базовые.

        Журнала запусков здесь нет (связи с GIT нет осознанно), поэтому
        все инструменты — базовые; действия диалога живут на ^L/^R.
        """
        if tool.startswith("mprov:"):
            self._model_prov = tool[6:]
            self._model_filter = ""
            self._catalog_field_provider = None
            try:
                self._mute_filter = True
                self.query_one("#model-filter", Input).value = ""
            except Exception:
                pass
            finally:
                self._mute_filter = False
            if self._wide == "model":
                self._draw_model_full()
            else:
                self._draw_model()
            self._draw_hq()
            state = self._catalog_connection()
            if state["status"] in ("", "locked") and state["key"]:
                self._connect_catalog()
            return
        if tool.startswith("mpreset:"):
            preset = self._LOCAL_PRESETS.get(tool[8:])
            if preset:
                url_input = self.query_one("#model-url", Input)
                url_input.value = preset[1]
                self._connect_catalog()
            return
        if tool.startswith("model:"):
            self._apply_catalog_model(tool[6:])
            return
        if tool in ("mconnect", "mconnect-mini"):
            self._connect_catalog()
            return
        if tool == "mcheck":
            self._check_catalog_model()
            return
        if tool == "mactivate":
            state = self._catalog_connection()
            if state["verified"]:
                self._apply_catalog_model(state["verified"])
            else:
                self._redraw_model_note("сначала проверь модель через API — активация только после")
            return
        if tool.startswith("hqconn:"):
            try:
                self._hq_conn = int(tool[7:])
            except ValueError:
                pass
            self._redraw_hq()
            return
        if tool.startswith("hqarea:"):
            self._hq_area = tool[7:]
            self._redraw_hq()
            return
        if tool == "hqrun":
            self._hq_run()
            return
        if tool == "hqclear":
            self._hq_tasks = [t for t in self._hq_tasks
                              if t["status"] == "working"]
            self._redraw_hq()
            return
        if tool.startswith("hqretry:"):
            try:
                tid = int(tool[8:])
            except ValueError:
                return
            task = next((t for t in self._hq_tasks if t["id"] == tid), None)
            if task is not None:
                self._hq_run(retry=task)
            return
        if tool.startswith("hqdel:"):
            try:
                tid = int(tool[6:])
            except ValueError:
                return
            self._hq_tasks = [t for t in self._hq_tasks if t["id"] != tid]
            self._redraw_hq()
            return
        super().panel_tool(tool)
