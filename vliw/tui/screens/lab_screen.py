"""РАЗБОР — расписание, которое можно потрогать.

Раньше расписание было картинкой в ленте: его печатали и листали. Здесь оно
стало решёткой «такты × каналы», по которой ходит курсор, а панель под ней
на каждое движение отвечает на один вопрос — почему эта операция оказалась
именно здесь. Это и есть главный инструмент режима: не «посмотреть отчёт»,
а разобраться.

Раскладка:
    слева   участок (чипы сценариев), решётка, «почему здесь», вывод команд
    справа  числа, диагноз, машина

Клавиатура делится честно: пока курсор в строке ввода, все клавиши — текст.
Esc отдаёт клавиатуру решётке, Esc из решётки возвращает обратно, а любая
печатная клавиша в решётке сама возвращает вас в ввод и начинает набор.
"""

from __future__ import annotations

from rich.text import Text
from textual import work
from textual.containers import Horizontal, ItemGrid, Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import DataTable, Static

from ...core import SCENARIOS
from .. import palette
from ..widgets import Chip, Console, Panel, PromptBar
from .base import ModeScreen

CONT = "│"
EMPTY = "·"
VIEWS = {"baseline": "baseline", "oracle": "оракул", "model": "модель"}


def _takt(n: int) -> str:
    """такт / такта / тактов — по числу.

    Мелочь, но заголовок решётки читают чаще любой другой строки в
    инструменте, и «23 тактов» там мозолит глаза каждый запуск.
    """
    if 11 <= n % 100 <= 14:
        return "тактов"
    return {1: "такт", 2: "такта", 3: "такта", 4: "такта"}.get(n % 10, "тактов")


def _wrapped(text: str, width: int, indent: int) -> str:
    """Перенос с висячим отступом: продолжение находки не липнет к краю."""
    import textwrap

    pad = " " * indent
    lines = textwrap.wrap(text, max(12, width - indent)) or [""]
    return ("\n" + pad).join(lines)


class ScheduleGrid(DataTable):
    """Решётка расписания. Печатная клавиша здесь возвращает фокус вводу."""

    def on_key(self, event) -> None:
        ch = event.character
        if ch and ch.isprintable() and event.key not in ("space",):
            event.stop()
            event.prevent_default()
            bar = self.screen.query_one("#prompt", PromptBar)
            bar.focus_input()
            bar.set_value(bar.input.value + ch)


class FindingItem(Static):
    """Строка находки в развёрнутом ДИАГНОЗЕ.

    Разворот этой панели — не панель покрупнее, а ДРУГОЙ инструмент: полный
    список находок (без потолка top-5 обычного вида) и клик по любой сразу
    ставит курсор решётки на нужную клетку и открывает РЕШЁТКУ — переход к
    месту, а не пересказ того же текста крупным шрифтом.
    """

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


class GridLink(Static):
    """Мостик под решёткой обратно к развёрнутому ДИАГНОЗУ.

    Живёт только когда РЕШЁТКА развёрнута: показывает находку про клетку под
    курсором и по клику уводит в полный список находок, на неё же. Без этого
    разворот решётки был бы тупиком — читаешь находку в заголовке, а вернуться
    к её разбору можно только вручную сворачивая и снова разворачивая другую
    панель.
    """

    class Picked(Message):
        pass

    def __init__(self, *args, **kw) -> None:
        super().__init__(*args, **kw)
        self.active = False

    def on_click(self, event) -> None:
        event.stop()
        if self.active:
            self.post_message(self.Picked())


class LabScreen(ModeScreen):
    mode = "lab"
    mode_title = "РАЗБОР"
    mode_subtitle = "исследование"
    placeholder = "/run slotclash   ·   /doctor   ·   /load examples/probe.s   ·   /compare"
    SIDE_ID = "#lab-right"
    TIPS_ID = "#p-scen"

    BINDINGS = ModeScreen.BINDINGS + [
        ("escape", "swap_focus", "решётка ⇄ ввод"),
    ]

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self.view = "baseline"
        self.base = None
        self.orc = None
        self.met = None
        self.diverged: set[int] = set()
        self._cells: dict[tuple[int, int], int] = {}
        # Живой прогон обученной модели. Решётка заполняется по событиям, по
        # ходу генерации, и держит СЫРОЙ ответ модели — с незаконными
        # клетками. Починка отдельным действием (`/repair`): иначе ошибка
        # модели молча превращается в её же заслугу.
        self.model_sched = None
        self.model_note = ""
        self.model_repairs: list[tuple[int, int, int]] = []
        # Куда поставить курсор при следующей отрисовке решётки. Нужно
        # потому, что после команды экран перерисовывается ЕЩЁ РАЗ
        # (`after_command` → `recompute` → `_compute_done`), и без этого
        # найденная незаконная клетка теряется: прокрутка уезжает наверх.
        self._want_cell: tuple[int, int] | None = None
        # ИИ, подключённый к курсору. `_cell_ai_token` — номер текущего
        # запроса: любое движение курсора его увеличивает, и работающий
        # запрос, увидев чужой номер, бросает генерацию на полуслове.
        self._detail_base: Text | None = None
        self._cell_ai_token = 0
        self._cell_ai_text = ""
        self._cell_ai_state = ""        # "" | "ждёт" | "готово" | текст ошибки
        self._cell_ai_on = True
        self._cell_ai_facts: list[str] = []
        # Строка решётки больше не равна такту: простои схлопнуты в одну.
        self._rows: list[tuple] = []
        self._expanded_gaps: set[tuple[int, int]] = set()
        # Разворот ДИАГНОЗА и РЕШЁТКИ — два разных режима одного экрана, не
        # панель покрупнее (см. docstring FindingItem/GridLink). Флаги здесь,
        # а не в CSS-классе панели: рисование зависит от режима, а не только
        # от размера.
        self._diag_expanded = False
        self._grid_expanded = False
        self._diag_filter = "all"      # all | high | medium | low | limit
        self._find_pos = -1            # позиция в отфильтрованном списке

    # --- раскладка --------------------------------------------------------

    def compose_body(self):
        with Horizontal(id="lab-body"):
            with Vertical(id="lab-left"):
                yield Panel(Horizontal(id="view-chips"),
                            ItemGrid(id="scenario-chips", min_column_width=15),
                            title="УЧАСТОК", id="p-scen")
                yield Panel(ScheduleGrid(id="grid", cursor_type="cell",
                                         zebra_stripes=False),
                            GridLink(id="grid-link"),
                            title="РАСПИСАНИЕ", id="p-grid", topic="grid")
                yield Panel(Static(id="detail"), title="ПОЧЕМУ ЗДЕСЬ",
                            id="p-detail", topic="detail")
                yield Panel(Console(id="console"), title="ВЫВОД КОМАНД",
                            id="p-console", topic="console",
                            has_own_input=True)
            with Vertical(id="lab-right"):
                yield Panel(Static(id="numbers"), title="ЧИСЛА",
                            id="p-numbers", topic="numbers")
                yield Panel(Horizontal(id="diag-filter"),
                            VerticalScroll(id="diag-scroll"),
                            title="ДИАГНОЗ", id="p-diag", topic="diag")
                yield Panel(Static(id="machine"), title="МАШИНА",
                            id="p-machine", topic="machine")

    def on_ready(self) -> None:
        self._fill_chips()
        self._draw_machine()
        self._seed_console()
        self.recompute()

    def _seed_console(self) -> None:
        con = self.console
        if con is None:
            return
        dim = palette.role_hex("dim")
        accent = palette.role_hex("lab")
        con.write(Text("отчёты команд приходят сюда", style=dim))
        for cmd, note in (
            ("/compare", "baseline и оракул бок о бок"),
            ("/doctor", "где именно теряются такты"),
            ("/asm", "расписание как широкие команды e2k { … }"),
            ("/load examples/probe.s", "разобрать настоящий .s от lcc"),
        ):
            row = Text()
            row.append("  " + cmd.ljust(24), style=accent)
            row.append(note, style=dim)
            con.write(row)

    def hint_pairs(self):
        return [("Esc", "решётка ⇄ ввод"), ("↑↓←→", "по тактам"),
                ("Enter", "разбор такта"), ("/", "команды")]

    # --- чипы -------------------------------------------------------------

    def _fill_chips(self) -> None:
        row = self.query_one("#view-chips", Horizontal)
        row.mount(Static("вид", classes="chip-label"))
        for key, label in VIEWS.items():
            chip = Chip(label, f"/view {key}", classes="chip chip-view",
                        id=f"view-{key}")
            chip.tooltip = "какое расписание показывать в решётке"
            row.mount(chip)
        grid = self.query_one("#scenario-chips", ItemGrid)
        for key in sorted(SCENARIOS):
            chip = Chip(key, f"/run {key}", classes="chip chip-scen",
                        id=f"scen-{key}")
            chip.tooltip = "прогнать этот участок"
            grid.mount(chip)
        self._mark_view()

    def _mark_view(self) -> None:
        for key in VIEWS:
            try:
                self.query_one(f"#view-{key}", Chip).set_class(
                    key == self.view, "chip-on")
            except Exception:
                pass
        current = self.app.session.scenario
        for key in SCENARIOS:
            try:
                self.query_one(f"#scen-{key}", Chip).set_class(
                    key == current, "chip-on")
            except Exception:
                pass

    # --- ввод -------------------------------------------------------------

    def extra_commands(self) -> list[dict]:
        return [
            {"name": "view", "arg": "[baseline|oracle|model]",
             "help": "какое расписание в решётке", "local": True},
            {"name": "repair", "arg": "",
             "help": "переназначить незаконные каналы в ответе модели",
             "local": True},
            {"name": "find", "arg": "[next|prev|filter <severity>]",
             "help": "по находкам доктора — курсор к следующей/предыдущей",
             "local": True},
        ]

    def handle_line(self, line: str) -> None:
        head, _, arg = line.lstrip("/").partition(" ")
        if head.lower() == "view":
            self._set_view(arg.strip().lower() or
                           ("oracle" if self.view == "baseline" else "baseline"))
            return
        if head.lower() == "repair":
            self._repair_model()
            return
        if head.lower() == "find":
            self._cmd_find(arg.strip().lower())
            return
        self.run_core(line)

    def _repair_model(self) -> None:
        """Переназначить незаконные каналы. Такты модели не трогаются.

        Отдельным действием, а не автоматически: сырой ответ модели и
        починенный гибрид — разные вещи, и подменять первое вторым молча
        значит записывать на счёт модели чужую работу.
        """
        con = self.console
        if self.model_sched is None or not self.model_sched.placements:
            if con is not None:
                con.note("  чинить нечего: модель ещё не запускалась", "warning")
            return
        if not self.model_repairs:
            if con is not None:
                con.note("  чинить нечего: незаконных каналов нет", "dim")
            return
        was = len(self._model_illegal())
        for i, _frm, to in self.model_repairs:
            p = self.model_sched.placements.get(i)
            if p is not None:
                self.model_sched.place(i, p.cycle, to)
        self.model_note = f"гибрид: починено каналов {len(self.model_repairs)}"
        self.model_repairs = []
        if con is not None:
            con.note(f"  починено каналов: {was}  ·  такты модели не тронуты, "
                     f"makespan её же", "success")
        self.view = "model"
        self._mark_view()
        self._draw_model_grid()
        self._draw_detail()

    def _set_view(self, view: str) -> None:
        view = {"base": "baseline", "оракул": "oracle", "orc": "oracle",
                "модель": "model", "learned": "model"}.get(view, view)
        if view not in VIEWS:
            if self.console is not None:
                self.console.note("  вид бывает baseline, oracle или model",
                                  "warning")
            return
        self.view = view
        self._want_cell = None
        self._mark_view()
        self._draw_grid()
        self._draw_detail()

    # --- живой прогон модели ----------------------------------------------

    def on_scheduler_text(self, text: str) -> None:
        """Строка ответа модели — в вывод команд, по мере генерации."""
        con = self.console
        if con is not None:
            con.note("  " + text.replace("[end of text]", "").rstrip(), "dim")

    def on_scheduler_event(self, ev) -> None:
        from ...core import Done, Failed, Note, Placed, Repaired, Started
        from ...core.schedule import Schedule

        con = self.console
        if isinstance(ev, Started):
            if ev.who != "learned":
                return          # baseline и оракул решётку не перехватывают
            self._want_cell = None
            self.model_sched = Schedule(self.app.session.dag_obj,
                                        self.app.session.model())
            self.model_note = "пишет…"
            self.model_repairs = []
            self.view = "model"
            self._mark_view()
            self._draw_model_grid()
            return
        if isinstance(ev, Note):
            if con is not None:
                con.note("  " + ev.text, ev.level)
            return
        if self.model_sched is None:
            return
        if isinstance(ev, Placed):
            # Ставим ровно то, что написала модель, включая незаконное: это
            # её ответ, и прятать его до вердикта значит прятать главное.
            p = ev.placement
            self.model_sched.place(p.instr, p.cycle, p.channel)
            # Курсор идёт за моделью: панель «почему здесь» разбирает ровно
            # ту операцию, которую модель только что поставила. Иначе на
            # экране заполняется решётка, а разбор молчит про пустую клетку,
            # на которой курсор стоял с самого начала.
            self._want_cell = (p.cycle, p.channel)
            self._draw_model_grid()
            self._draw_detail()
            self._draw_numbers()
            return
        if isinstance(ev, Repaired):
            # Копим, но НЕ применяем: решение показывать сырое — осознанное.
            self.model_repairs.append((ev.instr, ev.frm, ev.to))
            return
        if isinstance(ev, Failed):
            self.model_note = "не запустилась"
            self._draw_model_grid()
            return
        if isinstance(ev, Done):
            self._model_done(ev.result)

    def _first_illegal_cell(self) -> tuple[int, int] | None:
        """Самая ранняя незаконная клетка — (такт, порт)."""
        illegal = self._model_illegal()
        if not illegal or self.model_sched is None:
            return None
        p = min((self.model_sched.placements[i] for i in illegal),
                key=lambda pl: (pl.cycle, pl.channel))
        return p.cycle, p.channel

    def _model_done(self, res) -> None:
        illegal = self._model_illegal()
        placed = len(self.model_sched.placements) if self.model_sched else 0
        total = len(self.app.session.dag_obj)
        if placed < total:
            self.model_note = f"не разместила {total - placed}"
        elif illegal:
            self.model_note = ""      # счётчик незаконных уже в заголовке
        else:
            self.model_note = f"законно, {self.model_sched.makespan} т."
        self._draw_model_grid()

        # Курсор сам встаёт на первую незаконную клетку — иначе главное
        # оказывается ниже видимой области. Найдено по факту: на slotclash
        # модель ошибается со STORE в такте 22 из 23, то есть в самой
        # последней строке решётки. Заголовок честно писал «незаконных 1», а
        # чтобы это увидеть, надо было пролистать двадцать два такта.
        cell = self._first_illegal_cell()
        con = self.console
        if cell is not None:
            self._want_cell = cell
            self._draw_model_grid()          # перерисовать уже с курсором
            if con is not None:
                machine = self.app.session.model()
                con.note(f"  незаконных каналов: {len(illegal)}  ·  первый: "
                         f"такт {cell[0]}, порт {machine.port_label(cell[1])}"
                         f"  —  курсор уже там", "warning")
        self._draw_detail()
        if con is not None and self.model_repairs:
            con.note("  починить каналы, не трогая такты:  /repair", "warning")

    def panel_facts(self, topic: str) -> list[str]:
        """В РАЗБОРЕ чата сбоку НЕТ — и это решение, а не недоделка.

        Здесь уже есть свой способ спросить: курсор. Он ходит по решётке, а
        панель «ПОЧЕМУ ЗДЕСЬ» отвечает про клетку под ним — мгновенно и
        точно. Поле ввода рядом заставляло бы человека ПЕРЕСПРАШИВАТЬ
        словами то, на что он уже показал курсором, — шаг назад от того, что
        в экране и так работало.

        Поэтому ИИ здесь подключён к курсору (см. `_cell_ai_*` ниже), а не к
        строке ввода. Чат сбоку остаётся крайним средством для поверхностей,
        где показать не на что.
        """
        return []

    def _grid_facts(self) -> list[str]:
        s = self.app.session
        out = [f"В решётке показан вид «{VIEWS.get(self.view, self.view)}»: "
               f"такты по вертикали, каналы (порты) по горизонтали."]
        if self.view == "model" and self.model_sched is not None:
            illegal = self._model_illegal()
            out.append(f"Это СЫРОЙ ответ обученной модели, размещено "
                       f"{len(self.model_sched.placements)} из {len(s.dag_obj)}.")
            if illegal:
                dag, machine = s.dag_obj, s.model()
                out.append(f"Незаконных размещений: {len(illegal)} "
                           f"(канал не исполняет эту операцию).")
                for i in sorted(illegal)[:4]:
                    p = self.model_sched.placements[i]
                    ok = ", ".join(machine.port_label(c)
                                   for c in machine.channels_for(dag[i].op))
                    out.append(f"  {dag[i].op} #{i} поставлена на "
                               f"{machine.port_label(p.channel)}, а исполняют "
                               f"только {ok}.")
            else:
                out.append("Незаконных размещений нет.")
            return out
        res = self._result
        if res is None:
            return out + ["Расписание ещё не посчитано — нужна команда /run."]
        sch = res.schedule
        out.append(f"Выдача занимает {sch.span_cycles} тактов, всё готово к "
                   f"такту {sch.makespan}, слоты заняты на "
                   f"{sch.slot_utilization:.0%}.")
        empty = [c for c in range(sch.span_cycles)
                 if not any(p.cycle == c for p in sch.placements.values())]
        if empty:
            out.append(f"Полностью пустых тактов: {len(empty)} "
                       f"(например, {', '.join('т.' + str(c) for c in empty[:6])}).")
        return out

    def _cursor_facts(self) -> list[str]:
        """Про клетку под курсором — то же, что видно в панели."""
        s = self.app.session
        target = self._cursor_target()
        if target is None:
            return []
        machine, dag = s.model(), s.dag_obj
        if target[0] == "простой":
            f = self._gap_finding(target[1], target[2])
            if f is None:
                return []
            return [f"Простой {f.cycles_lost} т., {f.where}.", f.why, f.fix]
        _kind, cycle, port, instr = target
        head = (f"Курсор стоит на такте {cycle}, порт "
                f"{machine.port_label(port)} (вид «{VIEWS.get(self.view, self.view)}»).")
        if instr is None:
            return [head, "В этой клетке ничего не выдано."]
        ins = dag[instr]
        allowed = ", ".join(machine.port_label(c)
                            for c in machine.channels_for(ins.op))
        out = [head,
               f"Здесь операция {ins.op} «{ins.name}» (номер {instr}).",
               f"{ins.op} исполняется на портах: {allowed}.",
               f"Латентность {ins.op}: {machine.latency(ins.op)} т."]
        if self.view == "model" and instr in self._model_illegal():
            out.append("ЭТО РАЗМЕЩЕНИЕ НЕЗАКОННО: канал операцию не исполняет.")
        preds = list(dag[instr].preds)
        if preds:
            out.append("Зависит от: "
                       + ", ".join(f"{dag[p].op} «{dag[p].name}»" for p in preds[:5]))
        return out

    def after_command(self) -> None:
        self.recompute()

    def redraw(self) -> None:
        if self.base is None:
            return
        self._mark_view()
        self._draw_grid()
        self._draw_numbers()
        self._draw_diag()
        self._draw_machine()
        self._draw_detail()
        self._draw_grid_link()

    def on_prompt_bar_escaped(self, event) -> None:
        event.stop()
        self.query_one("#grid", ScheduleGrid).focus()

    def action_swap_focus(self) -> None:
        grid = self.query_one("#grid", ScheduleGrid)
        bar = self.query_one("#prompt", PromptBar)
        if grid.has_focus:
            bar.focus_input()
        else:
            if bar.palette_widget.display:
                bar.set_value("")
                return
            grid.focus()

    # --- счёт -------------------------------------------------------------

    def recompute(self) -> None:
        """Пересчитать расписания текущего участка (в отдельном потоке)."""
        self.set_busy(True)
        self._blank_grid("считаю расписание…")
        self.run_worker(self._compute, thread=True, exclusive=True, group="lab")

    def _compute(self) -> None:
        try:
            base, orc, met = self.app.session.results()
        except Exception as e:
            self.app.call_from_thread(self._compute_failed, str(e))
            return
        self.app.call_from_thread(self._compute_done, base, orc, met)

    def _compute_failed(self, msg: str) -> None:
        self.set_busy(False)
        self._blank_grid(f"не посчиталось: {msg}")

    def _compute_done(self, base, orc, met) -> None:
        self.base, self.orc, self.met = base, orc, met
        self.diverged = {
            i for i in base.schedule.placements
            if i in orc.schedule.placements
            and base.schedule.placements[i].cycle != orc.schedule.placements[i].cycle
        }
        self.set_busy(False)
        self._find_pos = -1
        self._mark_view()
        self._draw_grid()
        self._draw_numbers()
        self._draw_diag()
        self._draw_machine()
        self._draw_detail()
        self._draw_grid_link()
        self.refresh_context()

    # --- решётка ----------------------------------------------------------

    @property
    def _result(self):
        if self.view == "model":
            return None          # у живого прогона модели нет SchedulingResult
        return self.orc if self.view == "oracle" else self.base

    def _blank_grid(self, note: str) -> None:
        grid = self.query_one("#grid", ScheduleGrid)
        grid.clear(columns=True)
        grid.add_column(note, width=40)
        self.query_one("#p-grid", Panel).set_title("РАСПИСАНИЕ")

    def _draw_grid(self) -> None:
        if self.view == "model":
            self._draw_model_grid()
            return
        res = self._result
        if res is None:
            return
        sched = res.schedule
        span = max(sched.span_cycles, 1)
        # Выдача и готовность — разные числа: последнее деление считается ещё
        # долго после того, как его выдали. В решётке видна выдача, поэтому
        # обе величины стоят в заголовке рядом, чтобы их не путать.
        if span == sched.makespan:
            title = (f"РАСПИСАНИЕ   {VIEWS[self.view]}   "
                     f"{sched.makespan} {_takt(sched.makespan)}")
        else:
            title = (f"РАСПИСАНИЕ   {VIEWS[self.view]}   выдача {span} т."
                     f"   ·   всё готово к т.{sched.makespan}")
        if self.view == "oracle" and res.optimal:
            title += "   ·   оптимум доказан"
        self._render_grid(sched, title)

    def _model_illegal(self) -> frozenset[int]:
        """Клетки, где канал не исполняет свою операцию.

        Это НЕ придирка к оформлению: 85% ошибок «ресурс» у прогона 1 —
        STORE, поставленный на канал `,0`, который его не исполняет
        (см. docs/ROADMAP.md). Красные клетки показывают это глазами, вместо
        строчки «нарушений 3» в конце отчёта.
        """
        sched = self.model_sched
        if sched is None:
            return frozenset()
        dag = self.app.session.dag_obj
        machine = self.app.session.model()
        return frozenset(
            i for i, p in sched.placements.items()
            if p.channel not in machine.channels_for(dag[i].op))

    def _draw_model_grid(self) -> None:
        sched = self.model_sched
        if sched is None or not sched.placements:
            self._blank_grid(self.model_note
                             or "модель ещё не запускалась  —  /learned")
            return
        dag = self.app.session.dag_obj
        illegal = self._model_illegal()
        title = (f"РАСПИСАНИЕ   модель   "
                 f"размещено {len(sched.placements)}/{len(dag)}")
        if illegal:
            title += f"   ·   незаконных {len(illegal)}"
        if self.model_note:
            title += f"   ·   {self.model_note}"
        if len(sched.placements) == len(dag) and not illegal and not self.model_note:
            title += f"   ·   {sched.makespan} тактов"
        self._render_grid(sched, title, illegal)

    MIN_GAP = 3
    """Со скольких подряд пустых тактов простой схлопывается в одну строку.

    Три — не круглое число, а порог доктора: короче трёх он простой находкой
    и не считает (`_rule_idle_stretches`). Пороги должны совпадать, иначе
    решётка схлопывает то, чего диагноз не объясняет.
    """

    def _gaps(self, sched) -> list[tuple[int, int]]:
        """Отрезки тактов без единой выдачи: [(первый, последний), …].

        ЗАЧЕМ ЭТО ВООБЩЕ. Замерено по всем сценариям: пустые такты занимают
        от 23% до 69% строк решётки (simple4 — 69%, ptrchase — 62%,
        slotclash — 52%). До сих пор через них приходилось скроллить, а
        объяснение простоя лежало в панели ДИАГНОЗ, то есть в другом месте
        экрана и другими словами.

        При этом простой — не пустое место, а ГЛАВНОЕ, что показывает
        инструмент: именно там теряются такты. Двенадцать одинаковых пустых
        строк прячут находку ровно тем, что показывают её слишком подробно.
        """
        used = {p.cycle for p in sched.placements.values()}
        out: list[tuple[int, int]] = []
        span = max(sched.span_cycles, 1)
        t = 0
        while t < span:
            if t in used:
                t += 1
                continue
            start = t
            while t < span and t not in used:
                t += 1
            if t - start >= self.MIN_GAP:
                out.append((start, t - 1))
        return out

    def _gap_finding(self, start: int, end: int):
        """Находка доктора про этот простой — источник объяснения."""
        for f in self._findings():
            if f.code == "idle-stall" and f.where == f"такты {start}–{end}":
                return f
        return None

    def _findings(self):
        if self.base is None or self.met is None:
            return []
        try:
            from ...core.doctor import diagnose

            return diagnose(self.app.session.dag_obj, self.app.session.model(),
                            self.base.schedule, self.met).findings
        except Exception:
            return []

    SEVERITIES = ("all", "high", "medium", "low", "limit")

    def _filtered_findings(self):
        """Находки по текущему фильтру — тот же порядок, что отдал доктор."""
        findings = self._findings()
        if self._diag_filter == "all":
            return findings
        if self._diag_filter == "limit":
            return [f for f in findings if f.kind == "limit"]
        return [f for f in findings
                if f.kind != "limit" and f.severity == self._diag_filter]

    def _cmd_find(self, arg: str) -> None:
        """`/find` — курсор к следующей находке, `filter` — сузить список.

        Работает независимо от того, развёрнут ли ДИАГНОЗ: находка та же, что
        подсвечена под курсором в решётке, только двигает её сама команда, а
        не мышь.
        """
        parts = arg.split()
        con = self.console
        if parts and parts[0] == "filter":
            sev = parts[1] if len(parts) > 1 else "all"
            if sev not in self.SEVERITIES:
                if con is not None:
                    con.note(f"  фильтр: {', '.join(self.SEVERITIES)}", "warning")
                return
            self._diag_filter = sev
            self._find_pos = -1
            self._draw_diag()
            return
        findings = self._filtered_findings()
        if not findings:
            if con is not None:
                con.note("  находок нет — /find filter all", "dim")
            return
        delta = -1 if parts and parts[0] == "prev" else 1
        self._find_pos = (self._find_pos + delta) % len(findings)
        self._jump_to_finding(findings[self._find_pos])

    def _jump_to_finding(self, f) -> None:
        """Ставит курсор решётки на клетку (или простой), к которой находка.

        Единственное место, которое переводит находку доктора в координаты
        решётки — им пользуются и `/find`, и клик по строке в развёрнутом
        ДИАГНОЗЕ, и обратная ссылка из развёрнутой РЕШЁТКИ.
        """
        if f.code == "idle-stall":
            start = int(f.where.replace("такты ", "").split("–")[0])
            row, col = self._row_of_cycle(start), 0
        elif f.instrs:
            pos = next((rc for rc, i in self._cells.items() if i == f.instrs[0]),
                       None)
            if pos is None:
                return
            row, col = pos
        else:
            return
        width = max(self.app.session.model().width, 1)
        grid = self.query_one("#grid", ScheduleGrid)
        grid.move_cursor(row=min(row, max(len(self._rows) - 1, 0)),
                         column=min(col, width - 1))
        self._draw_detail()
        self._draw_diag()
        self._draw_grid_link()

    def _render_grid(self, sched, title: str,
                     illegal: frozenset[int] = frozenset()) -> None:
        model = self.app.session.model()
        dag = self.app.session.dag_obj
        grid = self.query_one("#grid", ScheduleGrid)
        grid.clear(columns=True)
        busy = sched.busy_map()
        # Порты, на которые за всё расписание не встало ни одной операции.
        # На slotclash таких три из шести: они занимали половину ширины
        # решётки и не несли ничего, кроме точек. Сужаем до метки — простой
        # порта остаётся видимым (это те же 9% занятости слотов, только по
        # горизонтали), но перестаёт отбирать место у рабочих колонок.
        used_ports = {p.channel for p in sched.placements.values()}
        for p in range(model.width):
            idle = p not in used_ports
            role = "faint" if idle else "dim"
            label = Text(model.port_label(p), style=palette.role_hex(role))
            grid.add_column(label, width=4 if idle else 11, key=str(p))

        crit = self._critical_set()
        self._cells = {}
        # Строка решётки больше НЕ равна такту: простои схлопнуты. Список
        # переводит номер строки обратно — ("такт", n) или ("простой", a, b).
        self._rows = []
        span = max(sched.span_cycles, 1)
        gaps = {a: b for a, b in self._gaps(sched)
                if (a, b) not in self._expanded_gaps}

        cycle = 0
        while cycle < span:
            if cycle in gaps:
                end = gaps[cycle]
                grid.add_row(*self._gap_cells(cycle, end, model.width),
                             label=self._gap_label(cycle, end))
                self._rows.append(("простой", cycle, end))
                cycle = end + 1
                continue
            row = len(self._rows)
            cells = []
            issued = 0
            for port in range(model.width):
                slot = busy.get((cycle, port))
                if slot is None:
                    cells.append(Text(f" {EMPTY}", style=palette.role_hex("faint")))
                    continue
                instr, head = slot
                self._cells[(row, port)] = instr
                if not head:
                    cells.append(Text(f" {CONT}", style=palette.op_style(dag[instr].op)))
                    continue
                issued += 1
                cells.append(self._cell_text(dag, instr, crit, instr in illegal))
            grid.add_row(*cells, label=self._row_label(cycle, issued, model.width))
            self._rows.append(("такт", cycle))
            cycle += 1

        self.query_one("#p-grid", Panel).set_title(title)
        if self._rows:
            want = self._want_cell or (0, 0)
            grid.move_cursor(row=min(self._row_of_cycle(want[0]), len(self._rows) - 1),
                             column=min(want[1], model.width - 1))

    def _row_of_cycle(self, cycle: int) -> int:
        """Номер строки, в которой виден этот такт (или его простой)."""
        for i, r in enumerate(self._rows):
            if r[0] == "такт" and r[1] == cycle:
                return i
            if r[0] == "простой" and r[1] <= cycle <= r[2]:
                return i
        return 0

    def _gap_cells(self, start: int, end: int, width: int) -> list[Text]:
        """Строка простоя: сплошная черта вместо точек «слот пуст».

        Разница видна боковым зрением и означает ровно то, что произошло:
        не «здесь ничего не выдали в этот такт», а «здесь не выдавали
        несколько тактов подряд».
        """
        style = palette.role_hex("faint")
        return [Text(" ─────────", style=style) for _ in range(width)]

    def _active_finding(self):
        """Находка доктора, к которой относится клетка под курсором.

        Связь, которой не было: ДИАГНОЗ говорит «монопольный порт ,5 занят
        менее срочной z0», в решётке есть та самая z0 — а понять, что это
        одно и то же, было нельзя. Теперь наведение на клетку подсвечивает
        находку про неё, и наоборот: читая находку, видно, о какой клетке
        речь. Ткнуть по находке мышью в терминале нельзя, зато курсор уже
        ходит — используем то, что есть.
        """
        target = self._cursor_target()
        if target is None:
            return None
        if target[0] == "простой":
            return self._gap_finding(target[1], target[2])
        instr = target[3]
        if instr is None:
            return None
        for f in self._findings():
            if instr in f.instrs:
                return f
        return None

    def _gap_label(self, start: int, end: int) -> Text:
        f = self._gap_finding(start, end)
        # Потеря или предел машины — разные вещи, и цвет здесь единственное
        # место, где это видно до наведения курсора.
        role = "error" if (f is not None and f.recoverable) else "dim"
        t = Text()
        t.append(f"т.{start}–{end}", style=palette.role_hex(role))
        t.append(f" ⌄{end - start + 1}", style=palette.role_hex("faint"))
        return t

    def _cell_text(self, dag, instr: int, crit: set[int],
                   illegal: bool = False) -> Text:
        ins = dag[instr]
        t = Text()
        if illegal:
            # Значком, а не только цветом: цвет теряется на 256-цветном
            # терминале и у людей с нарушением цветовосприятия, а именно эти
            # клетки — главное, что показывает прогон модели.
            t.append("✗", style=palette.role_hex("error") + " bold")
        else:
            moved = instr in self.diverged
            t.append("▸" if moved else " ",
                     style=palette.role_hex("diverge") if moved else "")
        t.append(ins.op.lower()[:3].ljust(4), style=palette.op_style(ins.op))
        if illegal:
            style = palette.role_hex("error") + " bold"
        elif instr in crit:
            style = palette.role_hex("crit") + " bold"
        else:
            style = palette.role_hex("text")
        t.append(ins.name[:7], style=style)
        return t

    def _row_label(self, cycle: int, issued: int, width: int) -> Text:
        """Метка такта + сколько слотов широкой команды занято.

        Значки одноширинные намеренно: эмодзи в терминале занимает две
        клетки и разъезжает вся колонка.
        """
        t = Text()
        if issued == 0:
            role, mark = "error", "▁"
        elif issued == width:
            role, mark = "success", "█"
        else:
            role, mark = "dim", "▄"
        t.append(f"т.{cycle:<3}", style=palette.role_hex(role))
        t.append(mark, style=palette.role_hex(role))
        return t

    def _critical_set(self) -> set[int]:
        if self.met is None:
            return set()
        from ...ui.schedule_view import critical_set

        return critical_set(self.app.session.dag_obj, self.met)

    # --- «почему здесь» ---------------------------------------------------

    def on_data_table_cell_highlighted(self, event) -> None:
        event.stop()
        self._draw_detail()
        self._draw_diag()          # подсветить находку про эту клетку
        self._draw_grid_link()     # то же для мостика под развёрнутой решёткой
        self._cell_ai_restart()

    # --- разворот ДИАГНОЗА и РЕШЁТКИ — два разных режима, не общий чат -----
    #
    # У остальных панелей экрана чата сбоку нет вовсе (см. panel_facts выше).
    # Эти две панели при развороте получают КАЖДАЯ СВОЁ: ДИАГНОЗ — список
    # находок целиком с фильтром, РЕШЁТКА — мостик к находке под курсором.
    # Переход между ними двусторонний: находка → клетка, клетка → находка.

    def on_panel_expanded(self, event) -> None:
        event.stop()
        topic = getattr(event.panel, "topic", "")
        if topic == "diag":
            self._diag_expanded = True
            self._find_pos = -1
            self._draw_diag()
        elif topic == "grid":
            self._grid_expanded = True
            self._draw_grid_link()

    def on_panel_collapsed(self, event) -> None:
        event.stop()
        self._diag_expanded = False
        self._grid_expanded = False
        self._draw_diag()
        self._draw_grid_link()

    def _draw_grid_link(self) -> None:
        try:
            link = self.query_one("#grid-link", GridLink)
        except Exception:
            return
        if not self._grid_expanded:
            link.active = False
            link.update("")
            return
        f = self._active_finding()
        if f is None:
            link.active = False
            link.update(Text("курсор — по клеткам   ·   /find — по находкам",
                             style=palette.role_hex("faint")))
            return
        link.active = True
        t = Text()
        t.append("▸ ", style=palette.role_hex("accent"))
        t.append(f.title, style=palette.role_hex("title") + " bold")
        t.append("   ·   клик — все находки в ДИАГНОЗЕ",
                 style=palette.role_hex("accent_soft"))
        link.update(t)

    def on_finding_item_picked(self, event) -> None:
        event.stop()
        findings = self._filtered_findings()
        if not (0 <= event.index < len(findings)):
            return
        self._find_pos = event.index
        self._jump_to_finding(findings[event.index])
        self._diag_expanded = False
        self._grid_expanded = True
        self.screen.minimize()
        self.screen.maximize(self.query_one("#p-grid", Panel), container=False)
        self._draw_diag()
        self._draw_grid_link()

    def on_grid_link_picked(self, event) -> None:
        event.stop()
        f = self._active_finding()
        if f is None:
            return
        findings = self._filtered_findings()
        if f not in findings:
            self._diag_filter = "all"
            findings = self._filtered_findings()
        self._find_pos = findings.index(f) if f in findings else -1
        self._grid_expanded = False
        self._diag_expanded = True
        self.screen.minimize()
        self.screen.maximize(self.query_one("#p-diag", Panel), container=False)
        self._draw_diag()

    # --- ИИ по курсору -----------------------------------------------------
    #
    # ЗАЧЕМ ИМЕННО ТАК. У этого экрана уже есть способ спросить — курсор.
    # Человек показывает на клетку, «ПОЧЕМУ ЗДЕСЬ» отвечает точно и мгновенно.
    # ИИ дописывает к этому одну фразу обычным языком — и тоже без вопроса,
    # по тому же движению курсора.
    #
    # ПОЧЕМУ С ЗАДЕРЖКОЙ. Ответ на этой машине идёт секунды, а курсор ходит
    # быстрее. Запуск на каждое нажатие стрелки означал бы очередь из
    # брошенных запросов и шесть занятых потоков впустую. Ждём, пока курсор
    # ОСТАНОВИТСЯ: остановился — значит на эту клетку и смотрят.
    #
    # ПОЧЕМУ ИИ НИЧЕГО НЕ РЕШАЕТ. В подсказку уходит ровно то, что уже
    # написано в панели, и задача ставится как пересказ, а не разбор. Числа
    # он не считает и добавлять их ему запрещено — считает ядро. На 3B это
    # единственный режим, в котором ему можно верить: он ошибается, когда
    # надо связать несколько чисел, и не ошибается, когда надо переформулировать
    # одно готовое утверждение.

    CELL_AI_DELAY = 1.5

    CELL_AI_QUESTION = "Скажи это одной фразой обычным языком."
    """Переформулировать, а не рассуждать.

    Пробовали спрашивать «почему эта операция оказалась здесь» — вопрос сам по
    себе требует ПРИЧИНЫ, и 3B её выдаёт всегда, даже когда причины нет: на
    клетке такта 0 сочинила ожидание предыдущих операций, которых не было.
    Причину считает ядро и уже написало её выше; модели остаются слова.
    """

    def _cell_ai_restart(self) -> None:
        """Курсор двинулся: прежний ответ недействителен, новый — не сразу."""
        self._cell_ai_token += 1
        self._cell_ai_text = ""
        self._cell_ai_state = ""
        self._render_detail()
        if not self._cell_ai_on or self.view == "model" and self.model_sched is None:
            return
        if not self._cell_has_a_story():
            return
        tok = self._cell_ai_token
        self.set_timer(self.CELL_AI_DELAY, lambda: self._cell_ai_start(tok))

    def _cell_has_a_story(self) -> bool:
        """Есть ли про эту клетку что рассказывать. Если нет — ИИ молчит.

        Это не оптимизация, а защита от выдумки, и она нужна именно этой
        модели. Проверено вживую: на клетке «DIV z0, такт 0» — где ничего не
        предшествует и ждать нечего — 3B сочинила «пришлось ждать завершения
        предыдущих операций». Она не умеет ответить «здесь всё обычно»: на
        прямой вопрос «почему здесь» она ОБЯЗАНА выдать причину и берёт её
        откуда придётся.

        Поэтому решаем МЫ, а не она. Рассказывать есть что, когда:
          · размещение незаконно — модель ошиблась каналом;
          · baseline и точный поиск разошлись — здесь и потерян такт;
          · операция на критическом пути — она задаёт длину всего участка;
          · клетка пуста — почему простаивает порт, вопрос не праздный.
        Во всех остальных клетках операция просто стоит где стоит, и честный
        ответ — молчание. Заодно это совпадает с ощущением: инструмент не
        бубнит над ухом, а подаёт голос там, где есть находка.
        """
        target = self._cursor_target()
        if target is None:
            return False
        if target[0] == "простой":
            return True                       # потерянные такты — всегда тема
        instr = target[3]
        if instr is None:
            return True                       # пустой слот — тоже вопрос
        if self.view == "model":
            return instr in self._model_illegal()
        return instr in self.diverged or instr in self._critical_set()

    def _cell_ai_start(self, tok: int) -> None:
        if tok != self._cell_ai_token:
            return                      # курсор уже ушёл, пока ждали
        # Источник — ТЕКСТ САМОЙ ПАНЕЛИ, а не отдельно собранный список.
        # Во-первых, в панели лежит настоящее рассуждение («готова в т.1,
        # выдана только в т.2»), а плоский список свойств модель просто
        # зачитывала обратно. Во-вторых, так ИИ и панель физически не могут
        # разойтись: у них один и тот же текст.
        base = self._detail_base
        facts = [l for l in (base.plain.split("\n") if base else []) if l.strip()]
        if len(facts) < 2:
            return
        self._cell_ai_state = "ждёт"
        self._cell_ai_facts = facts
        self._render_detail()
        self._cell_ai_worker(tok, facts)

    @work(thread=True, group="cellai")
    def _cell_ai_worker(self, tok: int, facts: list[str]) -> None:
        from ...agent import context, llm

        system = context.cell_prompt(facts)
        gen = llm.stream(system, self.CELL_AI_QUESTION, None, nudge=False)
        try:
            for piece in gen:
                if tok != self._cell_ai_token:
                    break               # курсор ушёл — бросаем на полуслове
                self.app.call_from_thread(self._cell_ai_piece, tok, piece)
        except Exception as e:
            self.app.call_from_thread(self._cell_ai_failed, tok, str(e))
        finally:
            # Закрываем в СВОЁМ потоке: генератор рвёт соединение, сервер
            # снимает задачу и остаётся жив для следующей клетки.
            closer = getattr(gen, "close", None)
            if closer is not None:
                closer()
        self.app.call_from_thread(self._cell_ai_done, tok)

    def _cell_ai_piece(self, tok: int, piece: str) -> None:
        if tok != self._cell_ai_token:
            return
        self._cell_ai_state = "готово"
        self._cell_ai_text += piece
        self._render_detail()

    def _cell_ai_done(self, tok: int) -> None:
        if tok != self._cell_ai_token:
            return
        if self._cell_ai_state == "ждёт":
            self._cell_ai_state = ""
            self._render_detail()
            return
        # Сторож на выдуманные числа. Ответ уже показан по частям — если он
        # не прошёл проверку, убираем его целиком: пустое место честнее
        # уверенной ошибки, а разбор ядра над ним никуда не делся.
        from ...agent import context

        if not context.cell_answer_is_grounded(self._cell_ai_text,
                                               self._cell_ai_facts):
            self._cell_ai_text = ""
            self._cell_ai_state = "NEX сочинил числа — ответ убран"
            self._render_detail()

    def _cell_ai_failed(self, tok: int, msg: str) -> None:
        if tok != self._cell_ai_token:
            return
        self._cell_ai_state = "нет модели"
        self._render_detail()

    def on_data_table_cell_selected(self, event) -> None:
        event.stop()
        target = self._cursor_target()
        if target is not None and target[0] == "простой":
            # Схлопнутое всегда можно раскрыть: инструмент ничего не прячет,
            # он лишь не показывает двенадцать одинаковых пустых строк, пока
            # их не попросили.
            key = (target[1], target[2])
            if key in self._expanded_gaps:
                self._expanded_gaps.discard(key)
            else:
                self._expanded_gaps.add(key)
            self._want_cell = (target[1], event.coordinate.column)
            self._draw_grid()
            self._draw_detail()
            return
        if target is not None:
            self.run_core(f"/explain {target[1]}")

    def _cursor_target(self):
        """На чём стоит курсор: («такт», такт, порт, инстр) или («простой», a, b).

        Единственное место, которое знает про схлопывание. Всё остальное
        (разбор, факты для ИИ, Enter) спрашивает здесь и про строки решётки
        больше не думает.
        """
        grid = self.query_one("#grid", ScheduleGrid)
        coord = grid.cursor_coordinate
        row, port = coord.row, coord.column
        if not (0 <= row < len(self._rows)):
            return None
        r = self._rows[row]
        if r[0] == "простой":
            return ("простой", r[1], r[2])
        return ("такт", r[1], port, self._cells.get((row, port)))

    def _render_detail(self) -> None:
        """Точный разбор + фраза ИИ под ним, разделённые чертой.

        Порядок принципиален: сверху то, что посчитано, снизу то, что
        пересказано. Не наоборот — иначе человек читает сперва пересказ и
        принимает его за источник.
        """
        target = self.query_one("#detail", Static)
        base = self._detail_base
        if base is None:
            return
        t = base.copy()
        faint = palette.role_hex("faint")
        if self._cell_ai_state == "ждёт":
            t.append("\n\n" + "─" * 3 + " NEX разбирает…", style=faint)
        elif self._cell_ai_state == "готово":
            t.append("\n\n" + "─" * 3 + " NEX\n", style=faint)
            t.append(self._cell_ai_text.strip(), style=palette.role_hex("dim"))
        elif self._cell_ai_state:
            t.append("\n\n" + "─" * 3 + " " + self._cell_ai_state, style=faint)
        target.update(t)

    def _set_detail(self, text: Text) -> None:
        self._detail_base = text
        self._render_detail()

    def _draw_detail(self) -> None:
        if self.view == "model":
            self._set_detail(self._detail_model())
            return
        res = self._result
        if res is None:
            self._set_detail(Text("расписание ещё не посчитано",
                                  style=palette.role_hex("faint")))
            return
        target = self._cursor_target()
        if target is None:
            return
        if target[0] == "простой":
            self._set_detail(self._detail_gap(target[1], target[2]))
            return
        _kind, cycle, port, instr = target
        if instr is None:
            self._set_detail(self._detail_empty(cycle, port))
        else:
            self._set_detail(self._detail_instr(cycle, port, instr))

    def _detail_model(self) -> Text:
        """Почему клетка красная — на месте, а не строчкой в отчёте.

        Главная находка прогона 1 (docs/ROADMAP.md): 85% ошибок «ресурс» —
        это STORE на канале `,0`, который его не исполняет. В отчёте это
        одна строка «нарушений 3». Здесь на неё можно навести курсор и
        увидеть, какие каналы операцию исполняют и откуда это известно.
        """
        faint = palette.role_hex("faint")
        sched = self.model_sched
        if sched is None or not sched.placements:
            return Text("модель ещё не запускалась  —  /learned", style=faint)

        grid = self.query_one("#grid", ScheduleGrid)
        coord = grid.cursor_coordinate
        cycle, port = coord.row, coord.column
        instr = self._cells.get((cycle, port))
        machine, dag = self.app.session.model(), self.app.session.dag_obj

        t = Text()
        if instr is None:
            t.append("такт ", style=faint)
            t.append(f"{cycle}", style=palette.role_hex("title"))
            t.append(f", порт {machine.port_label(port)} — ", style=faint)
            t.append("модель сюда ничего не поставила", style=faint)
            return t

        ins = dag[instr]
        allowed = machine.channels_for(ins.op)
        ok = port in allowed
        t.append(f"{ins.op.lower()} {ins.name}", style=palette.op_style(ins.op))
        t.append(f"  #{instr}\n", style=faint)
        t.append("модель поставила: ", style=faint)
        t.append(f"такт {cycle}, порт {machine.port_label(port)}\n",
                 style=palette.role_hex("title"))

        if ok:
            t.append("канал операцию исполняет — размещение законно",
                     style=palette.role_hex("success"))
            return t

        labels = ", ".join(machine.port_label(c) for c in allowed) or "нет таких"
        t.append("✗ этот канал операцию НЕ исполняет\n",
                 style=palette.role_hex("error") + " bold")
        t.append(f"{ins.op} исполняют только: ", style=faint)
        t.append(f"{labels}\n", style=palette.role_hex("success"))
        t.append(f"источник матрицы портов: {machine.matrix_source}\n",
                 style=faint)
        if self.model_repairs:
            t.append("починить каналы, не трогая такты:  /repair",
                     style=palette.role_hex("warning"))
        return t

    def _detail_gap(self, start: int, end: int) -> Text:
        """Простой как объект: сколько потеряно, почему и можно ли отыграть.

        Текст берётся у доктора, а не пишется заново: в панели ДИАГНОЗ он уже
        есть, и две формулировки одного простоя разошлись бы на первой же
        правке.
        """
        dim, title = palette.role_hex("dim"), palette.role_hex("title")
        t = Text()
        t.append(f"простой {end - start + 1} т.", style=f"{title} bold")
        t.append(f"   такты {start}–{end}\n", style=dim)
        f = self._gap_finding(start, end)
        if f is None:
            t.append("короткий разрыв — доктор его находкой не считает",
                     style=palette.role_hex("faint"))
            return t
        if f.recoverable:
            t.append(f"−{f.cycles_lost} т. можно отыграть\n",
                     style=palette.role_hex("error") + " bold")
        else:
            t.append("предел участка, а не просчёт\n",
                     style=palette.role_hex("success"))
        t.append(_wrapped(f.why, 70, 0) + "\n", style=dim)
        t.append(_wrapped(f.fix, 70, 0) + "\n", style=palette.role_hex("faint"))
        t.append("\nEnter — развернуть такты по одному",
                 style=palette.role_hex("faint"))
        return t

    def _detail_empty(self, cycle: int, port: int) -> Text:
        """Пустой слот — это тоже ответ: важно, ПОЧЕМУ он пуст."""
        s = self.app.session
        model, dag = s.model(), s.dag_obj
        sched = self._result.schedule
        dim = palette.role_hex("dim")
        t = Text()
        t.append(f"такт {cycle}", style=f"{palette.role_hex('lab')} bold")
        t.append(f"   канал {model.port_label(port)}", style=dim)
        t.append("   слот пуст\n", style=palette.role_hex("faint"))

        ops = [op for op in sorted({i.op for i in dag})
               if port in model.channels_for(op)]
        t.append("канал принимает: ", style=dim)
        if ops:
            for i, op in enumerate(ops):
                if i:
                    t.append("  ", style=dim)
                t.append(op, style=palette.op_style(op))
        else:
            t.append("ничего из этого участка", style=palette.role_hex("warning"))
        t.append("\n\n")

        # Кто ещё не выдан и чего он ждёт — это и есть причина пустоты.
        pending = [i for i in range(len(dag))
                   if i in sched.placements and sched.cycle_of(i) > cycle]
        if not pending:
            t.append("всё уже выдано — участок дорабатывает начатое", style=dim)
            return t
        ready_at = {i: max((sched.ready_at(p) for p in dag[i].preds), default=0)
                    for i in pending}
        able = [i for i in pending if ready_at[i] <= cycle
                and port in model.channels_for(dag[i].op)]
        if able:
            i = min(able, key=lambda k: sched.cycle_of(k))
            t.append("операнды готовы у ", style=dim)
            t.append(dag[i].name, style=palette.op_style(dag[i].op))
            t.append(", но планировщик выдал её в т.", style=dim)
            t.append(str(sched.cycle_of(i)), style=palette.role_hex("warning"))
            t.append("\nэто потерянный такт — сравните с оракулом",
                     style=palette.role_hex("warning"))
            return t
        soonest = min(pending, key=lambda k: ready_at[k])
        t.append("ждём операндов: ближайшая ", style=dim)
        t.append(dag[soonest].name, style=palette.op_style(dag[soonest].op))
        t.append(" готова к т.", style=dim)
        t.append(str(ready_at[soonest]), style=palette.role_hex("title"))
        blockers = sorted(
            {p for p in dag[soonest].preds if sched.ready_at(p) == ready_at[soonest]})
        if blockers:
            t.append("\nдержит: ", style=dim)
            for k, p in enumerate(blockers):
                if k:
                    t.append(", ", style=dim)
                t.append(dag[p].name, style=palette.op_style(dag[p].op))
                t.append(f" ({dag[p].op}, латентность {model.latency(dag[p].op)},"
                         f" выдана в т.{sched.cycle_of(p)})", style=dim)
        return t

    def _detail_instr(self, cycle: int, port: int, instr: int) -> Text:
        s = self.app.session
        model, dag = s.model(), s.dag_obj
        sched = self._result.schedule
        ins = dag[instr]
        dim = palette.role_hex("dim")
        title = palette.role_hex("title")
        t = Text()

        t.append(ins.name, style=f"{title} bold")
        t.append("   ")
        t.append(ins.op, style=palette.op_style(ins.op))
        t.append(f"   {ins.text}", style=dim)
        t.append(f"     канал {model.port_label(port)}\n", style=dim)

        lat = model.latency(ins.op)
        occ = model.occupancy(ins.op)
        place = sched.placements[instr]
        t.append("выдана в такте ", style=dim)
        t.append(str(place.cycle), style=title)
        t.append(", результат готов к ", style=dim)
        t.append(str(place.cycle + lat), style=title)
        t.append(f"   латентность {lat}", style=dim)
        if occ > 1:
            t.append(f", держит канал {occ} т.", style=palette.role_hex("warning"))
        t.append("\n")

        if ins.preds:
            t.append("ждала операндов: ", style=dim)
            for k, p in enumerate(ins.preds):
                if k:
                    t.append(", ", style=dim)
                t.append(dag[p].name, style=palette.op_style(dag[p].op))
                t.append(f" готов к т.{sched.ready_at(p)}", style=dim)
            t.append("\n")
        else:
            t.append("операндов не ждёт — может идти с первого такта\n", style=dim)

        if self.met is not None:
            t.append("раньше т.", style=dim)
            t.append(str(self.met.asap[instr]), style=title)
            t.append(" не могла; до конца участка отсюда ", style=dim)
            t.append(str(self.met.height[instr]), style=title)
            t.append(" т.", style=dim)
            if self.met.asap[instr] + self.met.height[instr] == self.met.critical_path_bound:
                t.append("   на критическом пути", style=palette.role_hex("crit"))
            t.append("\n")

        other = self.orc if self.view == "baseline" else self.base
        who = "оракул" if self.view == "baseline" else "baseline"
        if other is not None and instr in other.schedule.placements:
            oc = other.schedule.placements[instr].cycle
            if oc != place.cycle:
                t.append(f"{who} ставит её в такт ", style=palette.role_hex("diverge"))
                t.append(str(oc), style=f"{palette.role_hex('diverge')} bold")
                t.append(f"  ({oc - place.cycle:+d})", style=dim)
            else:
                t.append(f"{who} ставит её туда же", style=palette.role_hex("success"))
        return t

    # --- правая колонка ---------------------------------------------------

    def _draw_numbers(self) -> None:
        target = self.query_one("#numbers", Static)
        if self.base is None:
            return
        b = self.base.schedule.makespan
        o = self.orc.schedule.makespan
        lb = self.met.lower_bound
        dim = palette.role_hex("dim")
        title = palette.role_hex("title")
        t = Text()

        def row(key: str, value: str, style: str, note: str = "") -> None:
            t.append(key.ljust(11), style=dim)
            t.append(value.rjust(5), style=style)
            if note:
                t.append("  " + note, style=dim)
            t.append("\n")

        row("baseline", str(b), title)
        row("оракул", str(o), f"{palette.role_hex('success')} bold")
        self._row_model(row, b, o)
        row("предел", str(lb), title, self.met.binding)
        gap = b - o
        row("выигрыш", f"−{gap}" if gap else "нет",
            palette.role_hex("success") if gap else dim,
            f"{100 * gap // b}%" if gap and b else "")
        t.append("\n")
        t.append("оптимум доказан" if self.orc.optimal else "оптимум не доказан",
                 style=palette.role_hex("success") if self.orc.optimal
                 else palette.role_hex("warning"))
        t.append("\n")
        util = self.base.schedule.slot_utilization
        t.append(f"слоты baseline заняты на {util:.0%}", style=dim)
        target.update(t)

    def _row_model(self, row, base_t: int, orc_t: int) -> None:
        """Число модели — рядом с двумя другими, а не в отдельном отчёте.

        Решение по интерфейсу: модель — это ещё один планировщик, и судить её
        надо в той же таблице и по тем же тактам. Пока она не запускалась,
        строки нет: пустая строка «модель —» выглядела бы как результат.

        Незаконное расписание числом НЕ подписывается. Такты у незаконного
        расписания посчитать можно, но сравнивать их с baseline нельзя: это
        число получено нарушением правил машины, и поставить его в один
        столбик с честными значило бы засчитать модели то, чего она не
        добилась.
        """
        sched = self.model_sched
        if sched is None or not sched.placements:
            return
        dim = palette.role_hex("dim")
        total = len(self.app.session.dag_obj)
        illegal = self._model_illegal()
        if len(sched.placements) < total:
            row("модель", f"{len(sched.placements)}/{total}", dim, "пишет…")
            return
        if illegal:
            row("модель", "—", palette.role_hex("error"),
                f"незаконно: каналов {len(illegal)}")
            return
        m = sched.makespan
        if m < orc_t:
            note = "ниже оракула — проверить"
            style = palette.role_hex("warning")
        elif m == orc_t:
            note = "оптимум"
            style = f"{palette.role_hex('success')} bold"
        elif m < base_t:
            note = "обыграла эвристику"
            style = palette.role_hex("success")
        elif m == base_t:
            note = "вровень с эвристикой"
            style = palette.role_hex("title")
        else:
            note = "хуже эвристики"
            style = palette.role_hex("warning")
        row("модель", str(m), style, note)

    _SEV_MARKS = {"high": ("!!", "error"), "medium": ("!", "warning"),
                  "low": ("·", "dim")}

    def _finding_mark(self, f) -> tuple[str, str]:
        return ("=", "dim") if f.kind == "limit" \
            else self._SEV_MARKS.get(f.severity, ("·", "dim"))

    def _draw_diag(self) -> None:
        scroll = self.query_one("#diag-scroll", VerticalScroll)
        if self.base is None:
            return
        if self._diag_expanded:
            self._draw_diag_full(scroll)
            return
        self.query_one("#diag-filter", Horizontal).remove_children()
        from ...core.doctor import diagnose

        s = self.app.session
        scroll.remove_children()
        try:
            diag = diagnose(s.dag_obj, s.model(), self.base.schedule, self.met)
        except Exception as e:
            scroll.mount(Static(Text(str(e), style=palette.role_hex("error"))))
            return
        dim = palette.role_hex("dim")
        t = Text()
        if diag.clean:
            t.append("находок нет — baseline уложился в предел",
                     style=palette.role_hex("success"))
            scroll.mount(Static(t))
            return
        width = max(24, self.query_one("#p-diag", Panel).size.width - 4)
        # Простои НЕ повторяем: они теперь видны в самой решётке отдельными
        # строками, и наведение на них даёт этот же разбор. Две формулировки
        # одного факта на одном экране — это и есть лишнее; панель оставляет
        # себе то, чего в решётке не видно.
        shown_in_grid = {f"такты {a}–{b}" for a, b in self._gaps(self.base.schedule)
                         if (a, b) not in self._expanded_gaps}
        rest = [f for f in diag.top
                if not (f.code == "idle-stall" and f.where in shown_in_grid)]
        hidden = len(diag.top) - len(rest)
        # Структурно, не по объекту: находка приходит из СВОЕГО вызова
        # diagnose() (diag.top выше), а активная — из _active_finding(),
        # который зовёт diagnose() заново и получает НОВЫЕ объекты Finding с
        # теми же полями. `is` тут всегда врал бы — сравниваем содержимое.
        active = self._active_finding()
        for i, f in enumerate(rest):
            if i:
                t.append("\n")
            here = active is not None and f == active
            mark, role = self._finding_mark(f)
            # Находка про клетку под курсором помечена стрелкой и подсвечена.
            # Без этого ДИАГНОЗ и решётка говорили об одном и том же, но
            # связать их взглядом было нельзя.
            head = f"{'▸' if here else mark:<3}−{f.cycles_lost} т. "
            t.append(head, style=palette.role_hex("accent" if here else role))
            t.append(_wrapped(f.title, width, len(head)),
                     style=(palette.role_hex("title") + " bold") if here
                     else palette.role_hex("text"))
            t.append("\n")
            t.append("     " + _wrapped(f.where, width, 5),
                     style=palette.role_hex("accent_soft") if here else dim)
            t.append("\n")
        if hidden:
            if rest:
                t.append("\n")
            t.append(f"простои ({hidden}) — строками в решётке, "
                     "наведите курсор", style=palette.role_hex("faint"))
            t.append("\n")
        t.append("\n")
        t.append("2×клик — все находки и переход по ним",
                 style=palette.role_hex("accent_soft"))
        scroll.mount(Static(t))

    def _fill_diag_filter(self, row: Horizontal) -> None:
        row.remove_children()
        counts = {"all": 0, "high": 0, "medium": 0, "low": 0, "limit": 0}
        for f in self._findings():
            counts["all"] += 1
            counts["limit" if f.kind == "limit" else f.severity] += 1
        labels = {"all": "все", "high": "критично", "medium": "средне",
                  "low": "мелко", "limit": "предел"}
        for key in self.SEVERITIES:
            n = counts.get(key, 0)
            chip = Chip(f"{labels[key]} {n}", f"/find filter {key}",
                        classes="chip diag-sev")
            chip.set_class(key == self._diag_filter, "chip-on")
            row.mount(chip)

    def _draw_diag_full(self, scroll: VerticalScroll) -> None:
        """Развёрнутый ДИАГНОЗ: не топ-5, а все находки целиком, с фильтром.

        Каждая строка кликабельна: клик ставит курсор решётки на нужную
        клетку и сразу открывает РЕШЁТКУ — «посмотреть, где именно» не
        требует ни другой команды, ни выхода из режима находок.
        """
        self._fill_diag_filter(self.query_one("#diag-filter", Horizontal))
        scroll.remove_children()
        findings = self._filtered_findings()
        if not findings:
            scroll.mount(Static(Text("для этого фильтра находок нет",
                                     style=palette.role_hex("faint"))))
            return
        active = self._active_finding()
        dim = palette.role_hex("dim")
        width = max(30, self.size.width // 2 - 6)
        for i, f in enumerate(findings):
            here = active is not None and f == active
            mark, role = self._finding_mark(f)
            t = Text()
            head = f"{'▸' if here else mark:<3}−{f.cycles_lost} т. "
            t.append(head, style=palette.role_hex("accent" if here else role))
            t.append(_wrapped(f.title, width, len(head)),
                     style=(palette.role_hex("title") + " bold") if here
                     else palette.role_hex("text"))
            t.append("\n     " + _wrapped(f.where, width, 5),
                     style=palette.role_hex("accent_soft") if here else dim)
            t.append("\n     " + _wrapped(f.why, width, 5), style=dim)
            row = FindingItem(i, t, classes="finding-row" + (" here" if here else ""))
            scroll.mount(row)

    def _draw_machine(self) -> None:
        target = self.query_one("#machine", Static)
        model = self.app.session.model()
        dim = palette.role_hex("dim")
        t = Text()
        t.append("профиль".ljust(11), style=dim)
        t.append(model.name, style=palette.role_hex("text"))
        t.append("\n")
        t.append("каналов".ljust(11), style=dim)
        t.append(str(model.width), style=palette.role_hex("text"))
        t.append("\n")
        for port, ops in sorted(model.sole_host_ops().items()):
            t.append("  " + "/".join(ops), style=palette.op_style(ops[0]))
            t.append(f" → только {model.port_label(port)}", style=dim)
            t.append("\n")
        t.append("/model — матрица целиком", style=palette.role_hex("accent_soft"))
        target.update(t)
