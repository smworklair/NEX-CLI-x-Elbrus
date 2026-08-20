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
from textual.containers import Horizontal, ItemGrid, Vertical, VerticalScroll
from textual.widgets import DataTable, Static

from ...core import SCENARIOS
from .. import palette
from ..widgets import Chip, Console, Panel, PromptBar
from .base import ModeScreen

CONT = "│"
EMPTY = "·"
VIEWS = {"baseline": "baseline", "oracle": "оракул", "model": "модель"}


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

    # --- раскладка --------------------------------------------------------

    def compose_body(self):
        with Horizontal(id="lab-body"):
            with Vertical(id="lab-left"):
                yield Panel(Horizontal(id="view-chips"),
                            ItemGrid(id="scenario-chips", min_column_width=15),
                            title="УЧАСТОК", id="p-scen")
                yield Panel(ScheduleGrid(id="grid", cursor_type="cell",
                                         zebra_stripes=False),
                            title="РАСПИСАНИЕ", id="p-grid")
                yield Panel(Static(id="detail"), title="ПОЧЕМУ ЗДЕСЬ",
                            id="p-detail")
                yield Panel(Console(id="console"), title="ВЫВОД КОМАНД",
                            id="p-console")
            with Vertical(id="lab-right"):
                yield Panel(Static(id="numbers"), title="ЧИСЛА", id="p-numbers")
                yield Panel(VerticalScroll(Static(id="diag")),
                            title="ДИАГНОЗ", id="p-diag")
                yield Panel(Static(id="machine"), title="МАШИНА", id="p-machine")

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
        self._mark_view()
        self._draw_grid()
        self._draw_numbers()
        self._draw_diag()
        self._draw_machine()
        self._draw_detail()
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
            title = f"РАСПИСАНИЕ   {VIEWS[self.view]}   {sched.makespan} тактов"
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

    def _render_grid(self, sched, title: str,
                     illegal: frozenset[int] = frozenset()) -> None:
        model = self.app.session.model()
        dag = self.app.session.dag_obj
        grid = self.query_one("#grid", ScheduleGrid)
        grid.clear(columns=True)
        for p in range(model.width):
            label = Text(model.port_label(p), style=palette.role_hex("dim"))
            grid.add_column(label, width=11, key=str(p))

        busy = sched.busy_map()
        crit = self._critical_set()
        self._cells = {}
        span = max(sched.span_cycles, 1)
        for cycle in range(span):
            cells = []
            issued = 0
            for port in range(model.width):
                slot = busy.get((cycle, port))
                if slot is None:
                    cells.append(Text(f" {EMPTY}", style=palette.role_hex("faint")))
                    continue
                instr, head = slot
                self._cells[(cycle, port)] = instr
                if not head:
                    cells.append(Text(f" {CONT}", style=palette.op_style(dag[instr].op)))
                    continue
                issued += 1
                cells.append(self._cell_text(dag, instr, crit, instr in illegal))
            grid.add_row(*cells, label=self._row_label(cycle, issued, model.width),
                         key=str(cycle))
        self.query_one("#p-grid", Panel).set_title(title)
        if span:
            row, col = self._want_cell or (0, 0)
            grid.move_cursor(row=min(row, span - 1),
                             column=min(col, model.width - 1))

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

    def on_data_table_cell_selected(self, event) -> None:
        event.stop()
        row = event.coordinate.row
        self.run_core(f"/explain {row}")

    def _draw_detail(self) -> None:
        target = self.query_one("#detail", Static)
        if self.view == "model":
            target.update(self._detail_model())
            return
        res = self._result
        if res is None:
            target.update(Text("расписание ещё не посчитано",
                               style=palette.role_hex("faint")))
            return
        grid = self.query_one("#grid", ScheduleGrid)
        coord = grid.cursor_coordinate
        cycle, port = coord.row, coord.column
        instr = self._cells.get((cycle, port))
        if instr is None:
            target.update(self._detail_empty(cycle, port))
        else:
            target.update(self._detail_instr(cycle, port, instr))

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

    def _draw_diag(self) -> None:
        target = self.query_one("#diag", Static)
        if self.base is None:
            return
        from ...core.doctor import diagnose

        s = self.app.session
        try:
            diag = diagnose(s.dag_obj, s.model(), self.base.schedule, self.met)
        except Exception as e:
            target.update(Text(str(e), style=palette.role_hex("error")))
            return
        dim = palette.role_hex("dim")
        t = Text()
        if diag.clean:
            t.append("находок нет — baseline уложился в предел",
                     style=palette.role_hex("success"))
            target.update(t)
            return
        marks = {"high": ("!!", "error"), "medium": ("!", "warning"),
                 "low": ("·", "dim")}
        width = max(24, self.query_one("#p-diag", Panel).size.width - 4)
        for i, f in enumerate(diag.top):
            if i:
                t.append("\n")
            mark, role = ("=", "dim") if f.kind == "limit" \
                else marks.get(f.severity, ("·", "dim"))
            head = f"{mark:<3}−{f.cycles_lost} т. "
            t.append(head, style=palette.role_hex(role))
            t.append(_wrapped(f.title, width, len(head)),
                     style=palette.role_hex("text"))
            t.append("\n")
            t.append("     " + _wrapped(f.where, width, 5), style=dim)
            t.append("\n")
        t.append("\n")
        t.append("/doctor — подробно", style=palette.role_hex("accent_soft"))
        target.update(t)

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
