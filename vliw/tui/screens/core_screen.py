"""ЯДРО — верстак интерпретатора.

Прежде интерпретатор был вкладкой с лентой текста: вычисления улетали в лог,
а всё, ради чего он существует — имена, память и накопленный граф участка —
приходилось выпрашивать командами `names`, `mem`, `list`. Здесь они видны
постоянно и обновляются на каждой строке, а лента остаётся лентой.

Раскладка:
    слева   лента вычислений (что ввели → что получилось)
    справа  ИМЕНА, ПАМЯТЬ, ПРОГРАММА — состояние машины
    внизу   чем считать (ядра и служебные слова) + строка ввода с превью

Превью считает выражение на копии рабочего пространства, пока вы печатаете:
настоящее состояние не трогается, а число видно до нажатия Enter.
"""

from __future__ import annotations

import copy

from rich.text import Text
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Static

from ...core import InterpError, kernel_help
from ...core.interp import MEM_SIZE
from .. import palette
from ..widgets import Chip, Console, Panel, PromptBar
from .base import ModeScreen

MEM_ROWS = 5
MEM_CELL = 6


class CoreScreen(ModeScreen):
    """Интерпретатор: считает здесь, граф копится на глазах."""

    mode = "work"
    mode_title = "ЯДРО"
    mode_subtitle = "интерпретатор"
    placeholder = "считайте:  2+2  ·  a=10  ·  sum 8  ·  go     или  /команда"
    SIDE_ID = "#core-right"
    TIPS_ID = "#p-kernels"

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self._prev_regs: dict[str, int] = {}
        self._prev_mem: list[int] = []
        self._changed_regs: set[str] = set()
        self._changed_mem: set[int] = set()

    # --- раскладка --------------------------------------------------------

    def compose_body(self):
        with Horizontal(id="core-body"):
            with Vertical(id="core-left"):
                yield Panel(Console(id="console"), title="ЛЕНТА", id="p-tape",
                            classes="primary")
                yield Panel(
                    Horizontal(id="kernel-chips"),
                    Horizontal(id="verb-chips"),
                    title="ЧЕМ СЧИТАТЬ", id="p-kernels",
                )
            with Vertical(id="core-right"):
                yield Panel(VerticalScroll(Static(id="names")),
                            title="ИМЕНА", id="p-names")
                yield Panel(Static(id="memory"), title="ПАМЯТЬ", id="p-mem",
                            classes="quiet")
                yield Panel(VerticalScroll(Static(id="program")),
                            title="ПРОГРАММА", id="p-prog")

    def on_ready(self) -> None:
        self._fill_chips()
        self._intro()
        self.refresh_state()

    def hint_pairs(self):
        return [("Enter", "считать"), ("/", "команды"), ("go", "граф в разбор"),
                ("^O", "выбор режима")]

    def context_bits(self) -> str:
        """Контекст ЯДРА — состояние интерпретатора, а не сценарий сессии."""
        ws = self.app.session.workspace()
        graph = len(ws.snapshot())
        bits = [f"имён {len(ws.regs)}", f"граф {graph} оп."]
        if ws.last is not None:
            bits.append(f"последнее {ws.last}")
        bits.append(self.app.session.model().name)
        return "   ·   ".join(bits)

    # --- чипы -------------------------------------------------------------

    def _fill_chips(self) -> None:
        """Ядра и служебные слова — подписи короткие, подсказка в tooltip."""
        row = self.query_one("#kernel-chips", Horizontal)
        row.mount(Static("ядра", classes="chip-label"))
        for name, default, hint in kernel_help():
            chip = Chip(name, f"{name} {default}", classes="chip chip-kernel")
            chip.tooltip = f"{hint}  ·  по умолчанию {default}"
            row.mount(chip)
        row = self.query_one("#verb-chips", Horizontal)
        row.mount(Static("ещё", classes="chip-label"))
        for word, hint in (
            ("names", "показать имена и значения"),
            ("mem", "показать память"),
            ("list", "показать накопленный граф"),
            ("reset", "очистить имена и память"),
            ("go", "отдать граф в разбор и посчитать"),
        ):
            chip = Chip(word, classes="chip chip-verb")
            chip.tooltip = hint
            row.mount(chip)

    def _intro(self) -> None:
        con = self.console
        if con is None:
            return
        dim = palette.role_hex("dim")
        accent = palette.role_hex("work")
        t = Text()
        t.append("считает здесь. ", style=palette.role_hex("text"))
        t.append("память с начала: 1 2 3 4 …", style=dim)
        con.write(t)
        con.write("")
        for line, note in (
            ("2+2", "арифметика"),
            ("a=10;  b=3;  a*b+1", "имена; несколько выражений через ;"),
            ("x=load 0", "взять из памяти — в графе появится LOAD"),
            ("store x 3", "положить обратно — появится STORE"),
            ("sum 8", "ядро: считает по памяти и подставляет свой граф"),
            ("go", "отдать накопленный граф в разбор"),
        ):
            row = Text()
            row.append("  " + line.ljust(22), style=accent)
            row.append(note, style=dim)
            con.write(row)
        con.write("")

    # --- ввод -------------------------------------------------------------

    def handle_line(self, line: str) -> None:
        if line.startswith("/"):
            self.run_core(line)
            return
        self._exec_interp(line)

    def _exec_interp(self, line: str) -> None:
        from ...ui import interp_view

        con = self.console
        ws = self.app.session.workspace()
        self._snapshot_state()
        if con is not None:
            con.echo(line, self.mode)
        try:
            result = ws.exec(line)
        except InterpError as e:
            if con is not None:
                con.note(f"  {e}", "error")
                con.write("")
            return
        except Exception as e:
            if con is not None:
                con.note(f"  {type(e).__name__}: {e}", "error")
                con.write("")
            return

        if result.kind not in ("reset", "empty") and not ws.empty():
            self.app.session.set_dag(ws.snapshot(), "interp")
        if con is not None:
            con.ansi("\n".join(interp_view.render_result(
                ws, result, width=max(24, con.size.width - 2))))
            con.write("")
        self.refresh_state()
        self.refresh_context()
        if result.kind == "go":
            self._handoff()

    def _handoff(self) -> None:
        """`go`: посчитать накопленный граф и показать короткий вердикт."""
        ws = self.app.session.workspace()
        if ws.empty():
            if self.console is not None:
                self.console.note("  графа нет — считали без записи в программу",
                                  "warning")
            return
        self.set_busy(True)
        self.run_worker(self._go_worker, thread=True, exclusive=True, group="core")

    def _go_worker(self) -> None:
        """Точный поиск идёт в отдельном потоке — экран не замирает."""
        try:
            base, orc, met = self.app.session.results()
        except Exception as e:  # оракул может не уложиться — не роняем экран
            self.app.call_from_thread(self._verdict_error, str(e))
            return
        self.app.call_from_thread(self._go_done, base, orc, met)

    def _go_done(self, base, orc, met) -> None:
        self.set_busy(False)
        self._verdict(base, orc, met)
        self.refresh_context()

    def _verdict_error(self, msg: str) -> None:
        self.set_busy(False)
        if self.console is not None:
            self.console.note(f"  не посчиталось: {msg}", "error")

    def _verdict(self, base, orc, met) -> None:
        con = self.console
        if con is None:
            return
        b, o = base.schedule.makespan, orc.schedule.makespan
        accent = palette.role_hex("work")
        dim = palette.role_hex("dim")
        title = palette.role_hex("title")
        head = Text()
        head.append("граф передан в разбор", style=f"{accent} bold")
        head.append(f"   {len(self.app.session.dag_obj)} оп.", style=dim)
        con.write(head)
        row = Text()
        row.append("  baseline ", style=dim)
        row.append(str(b), style=title)
        row.append("   оракул ", style=dim)
        row.append(str(o), style=f"{palette.role_hex('success')} bold")
        row.append("   предел ", style=dim)
        row.append(str(met.lower_bound), style=title)
        if b > o:
            row.append(f"   −{b - o} тактов", style=palette.role_hex("success"))
        con.write(row)
        con.write(Text("  целиком — /clear и режим РАЗБОР", style=dim))
        con.write("")

    # --- превью -----------------------------------------------------------

    def on_prompt_bar_changed(self, event: PromptBar.Changed) -> None:
        event.stop()
        self._preview(event.value.strip())

    def _preview(self, text: str) -> None:
        """Значение выражения до нажатия Enter — на копии, без побочных следов."""
        bar = self.query_one("#prompt", PromptBar)
        if not text or text.startswith("/") or self.busy:
            bar.set_side("")
            return
        head = text.split()[0].lower()
        if head in ("go", "reset", "new", "names", "env", "list", "graph",
                    "ops", "mem") or "=" in text or text.startswith("store"):
            bar.set_side("")
            return
        try:
            ws = copy.deepcopy(self.app.session.workspace())
            result = ws.exec(text)
        except Exception:
            bar.set_side("")
            return
        if result.value is None:
            bar.set_side("")
            return
        t = Text()
        t.append("= ", style=palette.role_hex("faint"))
        t.append(str(result.value), style=palette.role_hex("work_soft"))
        bar.set_side(t)

    # --- состояние машины -------------------------------------------------

    def redraw(self) -> None:
        self.refresh_state()

    def _snapshot_state(self) -> None:
        ws = self.app.session.workspace()
        self._prev_regs = dict(ws.regs)
        self._prev_mem = list(ws.mem)

    def refresh_state(self) -> None:
        ws = self.app.session.workspace()
        self._changed_regs = {k for k, v in ws.regs.items()
                              if self._prev_regs.get(k) != v}
        self._changed_mem = {i for i, v in enumerate(ws.mem)
                             if i < len(self._prev_mem) and self._prev_mem[i] != v}
        self._draw_names(ws)
        self._draw_memory(ws)
        self._draw_program(ws)

    def _draw_names(self, ws) -> None:
        target = self.query_one("#names", Static)
        dim = palette.role_hex("dim")
        if not ws.regs:
            target.update(Text("пока пусто — a=10", style=palette.role_hex("faint")))
            return
        width = max(20, self.query_one("#p-names", Panel).size.width - 4)
        key_w = max(6, width - 12)
        t = Text()
        for i, (name, value) in enumerate(ws.regs.items()):
            if i:
                t.append("\n")
            hot = name in self._changed_regs
            t.append(name[: key_w - 1].ljust(key_w),
                     style=palette.role_hex("title") if hot else palette.role_hex("text"))
            t.append(str(value).rjust(11),
                     style=(f"{palette.role_hex('work')} bold") if hot else dim)
        target.update(t)

    def _draw_memory(self, ws) -> None:
        target = self.query_one("#memory", Static)
        dim = palette.role_hex("dim")
        faint = palette.role_hex("faint")
        hot = f"{palette.role_hex('accent2')} bold"
        # Сколько ячеек в строке — по фактической ширине панели: на узком окне
        # сетка иначе переносится и перестаёт быть сеткой.
        inner = max(16, self.query_one("#p-mem", Panel).size.width - 4)
        cols = max(3, (inner - 4) // MEM_CELL)
        shown = min(MEM_SIZE, cols * MEM_ROWS)
        t = Text()
        for row_start in range(0, shown, cols):
            if row_start:
                t.append("\n")
            t.append(f"{row_start:>3} │", style=faint)
            for i in range(row_start, min(row_start + cols, shown)):
                value = ws.mem[i] if i < len(ws.mem) else 0
                cell = str(value)
                if len(cell) > MEM_CELL - 1:
                    cell = cell[: MEM_CELL - 2] + "…"
                t.append(cell.rjust(MEM_CELL),
                         style=hot if i in self._changed_mem else dim)
        t.append(f"\nвсего {MEM_SIZE} ячеек, показаны первые {shown}",
                 style=faint)
        target.update(t)

    def _draw_program(self, ws) -> None:
        target = self.query_one("#program", Static)
        panel = self.query_one("#p-prog", Panel)
        dag = ws.snapshot()
        panel.set_title(f"ПРОГРАММА   {len(dag)} оп.")
        if not len(dag):
            target.update(Text("граф пуст — load/store и арифметика с именами\n"
                               "кладут сюда операции",
                               style=palette.role_hex("faint")))
            return
        dim = palette.role_hex("dim")
        t = Text()
        for i, ins in enumerate(dag):
            if i:
                t.append("\n")
            t.append(f"{ins.name:<7}", style=palette.role_hex("text"))
            t.append(f"{ins.op:<6}", style=palette.op_style(ins.op))
            t.append(ins.text, style=dim)
        target.update(t)
