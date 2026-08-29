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

from rich.text import Text
from textual import work
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen

from .. import palette
from ..widgets import (Console, ConsoleJournal, HintBar, Panel, PanelChat,
                        PanelPrompt, PromptBar, Tool, TopBar)


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
        # Esc — ОДИН шаг назад, всегда и везде. priority=True обязателен:
        # без него Esc сначала достаётся сфокусированному виджету (полю
        # ввода, строке вопроса, решётке), и каждый трактовал его по-своему —
        # получалось три разных Esc в одном приложении. Теперь он один и
        # разбирает уровни по порядку, см. action_back.
        Binding("escape", "back", "назад", priority=True),
        # Tab — открыть/закрыть справочник ИИ у развёрнутой панели. Тоже
        # priority: иначе Tab уходит в поле ввода на дополнение команды.
        # Вне разворота дополнение и остаётся — см. action_ai_or_complete.
        Binding("tab", "ai_or_complete", "справочник ИИ", priority=True),
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

    #: Что остаётся видимым, когда панель развёрнута. Textual по умолчанию
    #: прячет ВСЕХ прямых детей экрана, кроме развёрнутого, — и чат по панели
    #: исчезал вместе с ними. #dock назван ПОЛНОСТЬЮ: его дети (PromptBar,
    #: HintBar) в списке есть, но родитель спрятанного контейнера не виден —
    #: без этого «полный экран» съедал строку ввода и подсказки, и выходить
    #: из разворота приходилось наугад.
    ALLOW_IN_MAXIMIZED_VIEW = ("PanelChat, PanelPrompt, PromptBar, HintBar, "
                               "Footer, #dock, TopBar")

    #: Textual сам перехватывает Esc ДО всех биндингов, когда что-то
    #: развёрнуто (`App._process_messages`: `escape_to_minimize` → сразу
    #: `screen.minimize()`), и наш каскад до дела не доходил: один Esc
    #: проскакивал уровень справочника и схлопывал панель. Хуже того,
    #: встроенный путь зовёт `minimize()` напрямую и НЕ шлёт
    #: `Panel.Collapsed` — экран не узнавал, что панель свернули, и держал
    #: развёрнутый режим отрисовки. Выключаем; сворачивание делает
    #: `action_back` сам, четвёртым шагом, и с уведомлением панели.
    ESCAPE_TO_MINIMIZE = False

    _chat_panel = None
    _chat_facts: list[str] = []
    _chat_offer = None
    _prompt_panel = None
    _expanded_panel = None

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
        return [("/", "команды"), ("Esc", "назад"), ("/exit", "выход")]

    def toggle_hints(self) -> list[tuple[str, str]]:
        """Подсказки про скрываемые панели — одинаковые во всех режимах."""
        out = []
        # Про двойной клик иначе не догадаться: мышь в текстовом интерфейсе
        # обычно ничего не делает, и панель на весь экран никто искать не станет.
        if self.screen is self and self.screen.maximized is not None:
            out.append(("Esc", "свернуть панель"))
        else:
            out.append(("2×клик", "панель на весь экран"))
        # Tab виден только там, где он что-то делает: справочник живёт
        # исключительно у развёрнутой панели.
        if (self.screen is self and self.maximized is not None
                and self._expanded_panel is not None):
            out.append(("Tab", "справочник ИИ"
                        if not list(self.query(PanelPrompt)) else "закрыть"))
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
        self.submit_line(event.value)

    def on_console_journal_run_requested(self, event) -> None:
        """Команда набрана прямо в развёрнутом ВЫВОДЕ КОМАНД — терминал
        внутри панели, а не только общий док внизу экрана. Тот же путь, что
        и у общей строки ввода: /exit, /clear и остальное работают одинаково
        независимо от того, откуда набрана команда.
        """
        event.stop()
        self.submit_line(event.line)

    def submit_line(self, raw: str) -> None:
        line = raw.strip()
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

    def on_nex_input_pasted(self, event) -> None:
        """Многострочную вставку поле ввода не рвёт построчно, а отдаёт
        целиком — в буфер КОДА. Из любого режима: вставил — F5 в КОДЕ.
        """
        event.stop()
        self.app.session.code_text = event.text
        lines = [l for l in event.text.splitlines() if l.strip()]
        con = self.console
        if con is not None:
            con.note(f"  вставлено {len(lines)} "
                     f"строк → буфер КОДА   ·   режим КОД (клавиша 4) — "
                     "редактор, /code run — прогнать", "warning")

    # --- инструменты развёрнутой панели ------------------------------------

    def on_tool_picked(self, event: Tool.Picked) -> None:
        """Клик по инструменту развёрнутой панели — действие сразу.

        Инструмент, в отличие от чипа, не подставляет команду в строку ввода:
        панель разворачивают, чтобы работать в ней, и её кнопки обязаны
        работать без обходного пути через док внизу экрана.
        """
        event.stop()
        self.panel_tool(event.tool)

    def panel_tool(self, tool: str) -> None:
        """Действие инструмента развёрнутой панели. Переопределяется экраном.

        Базовая реализация знает три вида инструментов: мостик журнала
        («@lab»/«@agent»/«@work»/«@code» — отправить выбранный прогон в
        другой режим), команду со слэшем; всё остальное (навигация
        курсором, тумблеры отрисовки, переходы между панелями) — дело
        конкретного экрана.
        """
        if tool in ("@lab", "@agent", "@work", "@code"):
            self._bridge_run(tool[1:])
        elif tool == "@restore":
            self._restore_run()
        elif tool.startswith("/"):
            self.handle_line(tool)
        else:
            self.app.bell()

    # --- мостик: прогон из журнала → другой режим ---------------------------

    def _bridge_run(self, dest: str) -> None:
        """Отправить выбранный в журнале прогон туда, куда решил человек.

        Ничего не уезжает само: пока кнопка не нажата, прогон живёт только
        в журнале. Какой прогон поедет — выбираешь кликом в ЗАПУСКАХ, и
        подсветка строки показывает, кого тронет кнопка. Полная сетка:
        из любого режима прогон доезжает до любого другого. «В разбор»
        делает прогон текущим участком и открывает РАЗБОР; «в агента»
        открывает АГЕНТА с готовым вопросом в строке; «в ядро» и «в код»
        открывают верстак с пометкой о прогоне — а если у записи есть его
        исходник (прогон буфера КОДА), «в код» кладёт исходник в буфер.
        """
        con = self.console
        if con is None or not con.runs:
            self.app.bell()
            return
        rec = con.runs[min(self._bridge_index(con), len(con.runs) - 1)]
        if dest == "lab":
            dag = rec.get("dag")
            if dag is None:
                self.app.bell()
                return
            self.app.session.set_dag(dag, rec.get("scenario") or "прогон")
            self.app.open_mode("lab")
        elif dest == "agent":
            scenario = rec.get("scenario") or "—"
            self.app.session.pending_question = (
                f"прогон «{rec['cmd']}» на участке {scenario} — что он "
                "показал и где здесь теряются такты?")
            self.app.open_mode("mind")
        elif dest == "work":
            self.app.session.pending_note = (
                f"из журнала: прогон «{rec['cmd']}» на участке "
                f"{rec.get('scenario') or '—'}")
            self.app.open_mode("work")
        elif dest == "code":
            src = rec.get("code")
            if src:
                # Исходник прогона существует только у прогонов буфера:
                # им «в код» возвращает текст целиком, правь и F5 заново.
                self.app.session.code_text = src
                self.app.session.pending_note = (
                    f"из журнала: исходник «{rec['cmd']}» — в буфере")
            else:
                self.app.session.pending_note = (
                    f"из журнала: прогон «{rec['cmd']}» на участке "
                    f"{rec.get('scenario') or '—'} — исходника у записи "
                    "нет, буфер не тронут")
            self.app.open_mode("code")

    def _restore_run(self) -> None:
        """«Вернуть» — checkout состояния выбранного прогона на месте.

        Мостик перевозит прогон в другой режим; «вернуть» делает то же,
        но без переезда: участок, граф и исходник сессии становятся такими,
        какими были у этого прогона, а экран остаётся текущим. Это ответ
        на «а что если вернуться к тому, что я считал десять минут назад» —
        вопрос, ради которого в git существует log.
        """
        con = self.console
        if con is None or not con.runs:
            self.app.bell()
            return
        pos = min(self._bridge_index(con), len(con.runs) - 1)
        rec = con.runs[pos]
        dag = rec.get("dag")
        code = rec.get("code")
        if dag is None and code is None:
            self.app.bell()
            return
        if dag is not None:
            self.app.session.set_dag(dag, rec.get("scenario") or "прогон")
        if code:
            self.app.session.code_text = code
        con.note(f"  состояние #{pos + 1} возвращено: "
                 f"{rec.get('scenario') or '—'}"
                 + (f"  ·  исходник в буфере" if code else ""),
                 "success")
        self.refresh_context()
        self.after_command()

    def _bridge_index(self, con) -> int:
        """Какой прогон мостим: тот, что выбран в журнале, если он открыт;
        иначе последний. Журнал у консоли один, выбранная позиция в нём.
        """
        try:
            journal = self.query_one(ConsoleJournal)
            if 0 <= journal.pos < len(con.runs):
                return journal.pos
        except Exception:
            pass
        return len(con.runs) - 1

    # --- Esc: один шаг назад ----------------------------------------------

    def action_back(self) -> None:
        """Esc — выйти на один уровень наружу, вплоть до начального экрана.

        Раньше Esc значил три разных вещи в зависимости от того, что в
        фокусе: закрыть справочник, переключить решётка⇄ввод, уйти к выбору
        режима. Каждый обработчик стоял в своём классе и не знал про
        остальные — отсюда и ощущение костыля. Теперь уровень ровно один и
        разбирается сверху вниз: что открыто последним, то и закрывается.
        """
        bar = None
        try:
            bar = self.query_one("#prompt", PromptBar)
        except Exception:
            pass
        # 1. Палитра команд поверх всего — закрыть её, ввод не трогать.
        if bar is not None and bar.palette_widget.display:
            bar.set_value("")
            return
        # 2. Справочник ИИ у развёрнутой панели.
        if list(self.query(PanelPrompt)):
            self.close_panel_prompt()
            self.refresh_hints()
            return
        # 3. Развёрнутая панель — свернуть обратно в раскладку экрана.
        if self.maximized is not None:
            panel = self.maximized
            self.minimize()
            panel.post_message(Panel.Collapsed())
            return
        # 4. Дальше выходить некуда, кроме как из самого режима.
        self.app.to_picker()

    def action_ai_or_complete(self) -> None:
        """Tab: у развёрнутой панели — справочник ИИ, иначе — дополнение.

        Справочник больше не выскакивает сам при развороте: панель
        разворачивают, чтобы работать в ней, и чужая строка снизу в этот
        момент только мешает. Открывается ровно по Tab и по нему же
        закрывается.

        Вне разворота Tab оставлен дополнению команды в общем доке — это
        его привычное место, и отбирать его ради функции, которой там всё
        равно нет (справочник живёт только у развёрнутой панели), значило бы
        сломать рабочую клавишу ради пустого действия.
        """
        if self.maximized is not None and self._expanded_panel is not None:
            self.action_toggle_panel_prompt()
            return
        try:
            self.query_one("#prompt", PromptBar).tab()
        except Exception:
            pass

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
        """Живой поток (строки модели, пометки планировщика) — в СОБЫТИЯ.

        Раньше он лился в вывод команд и перемешивался с отчётами: таблица
        обрывалась строкой генерации, а при открытом журнале — когда лента
        консоли скрыта — текст вообще уходил «в никуда». Отдельная лента
        решает оба раза: отчёты чисты, а поток читается целиком на вкладке
        СОБЫТИЯ развёрнутого ОТЧЁТА. Экраны, для которых этот поток — само
        содержимое (решётка РАЗБОРА), переопределяют метод и рисуют его
        по-своему.
        """
        clean = "  " + text.replace("[end of text]", "").rstrip()
        self.app.session.journal_events.append(
            Text(clean, style=palette.role_hex("dim")))
        try:
            journal = self.query_one("#journal", ConsoleJournal)
        except Exception:
            return
        journal.append_event(Text(clean, style=palette.role_hex("dim")))

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
            # Мостик-поля последнего прогона: что показывал, чем считалось.
            # Без них запись — просто текст; с ними её можно отправить в
            # РАЗБОР или АГЕНТУ одной кнопкой из журнала.
            if con.runs:
                rec = con.runs[-1]
                rec["scenario"] = self.app.session.scenario
                rec["dag"] = self.app.session.dag_obj
                rec["profile"] = self.app.session.profile
        self.set_busy(False)
        self.app.reload_palette()   # команда могла сменить тему
        self.refresh_context()
        self.after_command()
        # Журнал мог быть открыт ДО того, как команда донесла свой граф:
        # без перечитывания у свежего прогона оставались бы пустыми мостик-
        # кнопки и список строк. Перечитываем всегда, когда он виден.
        self._refresh_journal()

    def _refresh_journal(self) -> None:
        """Показанный журнал — перечитать: у него свои данные, а не общие
        с лентой консоли. Дешёво: список прогонов уже в памяти."""
        try:
            journal = self.query_one("#journal", ConsoleJournal)
        except Exception:
            return
        if not journal.display:
            return
        journal.load(self.app.session.journal_runs, self.mode,
                     list(self.app.commands) + self.extra_commands(),
                     self.app.session.journal_events)

    # --- чат по развёрнутой панели ----------------------------------------

    def panel_facts(self, topic: str) -> list[str]:
        """Факты открытой панели для ИИ. Переопределяется экраном.

        Пустой список — панели нечего рассказывать, спрашивать не о чем.
        """
        return []

    def panel_chips(self, topic: str) -> list[str]:
        """Готовые вопросы для всплывающей строки этой панели.

        Свои у каждой панели: спрашивают всегда про то, на что смотрят, и
        общий список «о чём спросить» на все панели был бы тем же боковым
        чатом, только без колонки.
        """
        return []

    def on_panel_expanded(self, event) -> None:
        event.stop()
        panel = event.panel
        # Помним, какая панель развёрнута: ^G возвращает строку вопроса без
        # того, чтобы сворачивать и разворачивать панель заново.
        # Справочник ИИ сам НЕ открывается: панель разворачивают, чтобы
        # работать в ней, и чужая строка снизу в этот момент мешает. Только
        # запоминаем панель — Tab поднимет справочник, когда он понадобится.
        self._expanded_panel = panel if getattr(panel, "topic", "") else None
        self.refresh_hints()

    def on_panel_collapsed(self, event) -> None:
        event.stop()
        self._expanded_panel = None
        self.close_panel_prompt()
        self.close_panel_chat()
        self.refresh_hints()

    # --- всплывающая строка вопроса ---------------------------------------

    def action_toggle_panel_prompt(self) -> None:
        """Открыть/закрыть справочник ИИ у развёрнутой панели (Tab)."""
        if list(self.query(PanelPrompt)):
            self.close_panel_prompt()
            self.refresh_hints()
            return
        panel = getattr(self, "_expanded_panel", None)
        if panel is not None:
            self.open_panel_prompt(panel)
            self.refresh_hints()

    def open_panel_prompt(self, panel) -> None:
        """Строка вопроса внизу развёрнутой панели.

        Раньше это была колонка сбоку (PanelChat) и открывалась она у двух
        панелей из шестнадцати: у остальных фактов не было, а у панелей со
        своим вводом колонка отбирала треть ширины ровно у того, ради чего
        панель и разворачивают. Строка снизу не отбирает ширину ни у кого,
        поэтому её можно дать каждой панели.
        """
        topic = getattr(panel, "topic", "")
        facts = self.panel_facts(topic)
        chips = self.panel_chips(topic)
        if not facts and not chips:
            return
        # remove() у Textual отложенный: если просто позвать close перед
        # mount, старый виджет ещё жив и новый падает на дублирующемся id.
        for old in self.query(PanelPrompt):
            old.remove()
            self._prompt_panel = None
            return self.call_after_refresh(self.open_panel_prompt, panel)
        full = getattr(panel, "_title", "") or topic
        title = full.split("   ")[0].strip() or topic
        prompt = PanelPrompt(title=title, chips=chips, facts=facts,
                             mode=self.mode, id="panel-prompt")
        self.mount(prompt)
        self._prompt_panel = panel

    def close_panel_prompt(self) -> None:
        for p in self.query(PanelPrompt):
            p.remove()
        self._prompt_panel = None

    def on_panel_prompt_closed(self, event) -> None:
        event.stop()
        self.close_panel_prompt()
        # Полоса подсказок должна сразу показать, что строку можно вернуть:
        # иначе скрытие по Esc выглядит как «функцию убрал навсегда».
        self.refresh_hints()

    def on_panel_prompt_asked(self, event) -> None:
        event.stop()
        prompts = list(self.query(PanelPrompt))
        if not prompts:
            return
        pp = prompts[0]
        pp.echo(event.question)
        pp.start_answer()
        self._panel_prompt_worker(event.question)

    @work(thread=True, exclusive=True, group="panel-prompt")
    def _panel_prompt_worker(self, question: str) -> None:
        """Отвечает НАСТОЯЩИЙ агент — тот же, что в АГЕНТЕ, не облегчённая копия.

        Раньше здесь стоял отдельный, узкий путь: `context.panel_prompt` +
        голый `llm.stream` — только текст, без единого действия. Спросить
        «переключись на wide_ilp» из всплывающей строки МАШИНЫ было нельзя:
        агент такого не умел, отвечал про факты, которые ему дали, и точка.
        Теперь это тот же `Agent.ask_stream`, что ведёт ДИАЛОГ в АГЕНТЕ: он
        сам распознаёт намерение, переключает сценарий, грузит файл, считает
        расписание — а панельные факты идут суффиксом (см. `panel=` в
        `Agent.ask_stream`), чтобы ответ не терял их и не портил кэш префикса.
        """
        import time

        panel = getattr(self, "_prompt_panel", None)
        full = getattr(panel, "_title", "") if panel is not None else ""
        title = full.split("   ")[0].strip() or "панель"
        prompts = list(self.query(PanelPrompt))
        facts = list(prompts[0].facts) if prompts else []
        agent = self.app.session.agent()
        t0 = time.monotonic()
        acted = False
        try:
            for kind, value in agent.ask_stream(question, panel=(title, facts)):
                if kind == "action":
                    acted = True
                    self.app.call_from_thread(self._pp_action, value)
                elif kind == "text":
                    self.app.call_from_thread(self._pp_piece, value)
                elif kind == "error":
                    self.app.call_from_thread(self._pp_fail, value)
        except Exception as e:
            self.app.call_from_thread(self._pp_fail, str(e))
        self.app.call_from_thread(self._pp_done, time.monotonic() - t0, acted)

    def _pp_action(self, note: str) -> None:
        for p in self.query(PanelPrompt):
            p.action(note)
            return

    def _pp_piece(self, piece: str) -> None:
        for p in self.query(PanelPrompt):
            p.first_piece()
            p.append(piece)
            return

    def _pp_done(self, seconds: float, acted: bool = False) -> None:
        for p in self.query(PanelPrompt):
            p.finish(seconds)
            break
        if acted:
            # after_command(), А НЕ redraw(): redraw() красит уже посчитанное
            # (единственный прежний вызывающий — repaint() при смене темы, где
            # self.base и session.dag_obj гарантированно согласованы). Действие
            # агента могло переключить сценарий — session.dag_obj уехал вперёд,
            # а self.base/orc/met в РАЗБОРЕ ещё старые до асинхронного
            # recompute(). Однажды так и упало: агент переключал на mulclash,
            # redraw() лез в старое self.base с DAG уже нового сценария и
            # получал IndexError на несуществующей инструкции. after_command()
            # — тот же путь, что и после обычной команды из дока ввода.
            self.refresh_context()
            self.after_command()

    def _pp_fail(self, message: str) -> None:
        for p in self.query(PanelPrompt):
            p.note("не получилось: " + message[:160], "error")
            return

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
