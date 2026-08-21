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
from textual.containers import Horizontal, ItemGrid, Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import Static

from ...core import InterpError, kernel_help
from ...core.interp import MEM_SIZE
from .. import palette
from ..widgets import Chip, Console, Panel, PromptBar, plural
from .base import ModeScreen

MEM_ROWS = 5
MEM_CELL = 6


class MemCell(Static):
    """Ячейка памяти в развёрнутой карте. Клик — подставить её в ввод.

    Смысл разворота ПАМЯТИ не в том, чтобы показать те же числа крупнее, а
    в том, что из карты можно СЧИТАТЬ: увидел непустую ячейку — забрал её в
    выражение, не набирая адрес руками и не сверяясь со столбиком.
    """

    class Picked(Message):
        def __init__(self, addr: int) -> None:
            super().__init__()
            self.addr = addr

    def __init__(self, addr: int, *args, **kw) -> None:
        super().__init__(*args, **kw)
        self.addr = addr

    def on_click(self, event) -> None:
        event.stop()
        self.post_message(self.Picked(self.addr))


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
        # Какая панель развёрнута. Разворот здесь — не «то же крупнее»: у
        # ИМЁН это происхождение значений, у ПАМЯТИ — карта, из которой
        # можно считать, у ПРОГРАММЫ — ярусы графа, то есть тот самый
        # параллелизм, который потом упаковывает РАЗБОР.
        self._wide = ""

    # --- раскладка --------------------------------------------------------

    def compose_body(self):
        with Horizontal(id="core-body"):
            with Vertical(id="core-left"):
                yield Panel(Console(id="console"), title="ЛЕНТА", id="p-tape")
                yield Panel(
                    Horizontal(id="kernel-chips"),
                    Horizontal(id="verb-chips"),
                    title="ЧЕМ СЧИТАТЬ", id="p-kernels",
                )
            with Vertical(id="core-right"):
                yield Panel(VerticalScroll(Static(id="names")),
                            VerticalScroll(Static(id="names-full"),
                                           id="names-wide"),
                            title="ИМЕНА", id="p-names", topic="names")
                yield Panel(Static(id="memory"),
                            Vertical(Static(id="mem-head"),
                                     ItemGrid(id="mem-map", min_column_width=11),
                                     Static(id="mem-foot"),
                                     id="mem-wide"),
                            title="ПАМЯТЬ", id="p-mem", topic="memory")
                yield Panel(VerticalScroll(Static(id="program")),
                            VerticalScroll(Static(id="prog-tiers"),
                                           id="prog-wide"),
                            title="ПРОГРАММА", id="p-prog", topic="program")

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
        for wide_id, short_id, topic in (
                ("#names-wide", "#names", "names"),
                ("#mem-wide", "#memory", "memory"),
                ("#prog-wide", "#program", "program")):
            self.query_one(wide_id).display = self._wide == topic
            self.query_one(short_id).display = self._wide != topic
        self._draw_names(ws)
        self._draw_memory(ws)
        self._draw_program(ws)
        # Развёрнутый вид рисуется ПОСЛЕ свёрнутого: оба ставят заголовок
        # панели, и в обратном порядке короткий затирал бы длинный.
        if self._wide == "names":
            self._draw_names_full(ws)
        elif self._wide == "memory":
            self._draw_mem_map(ws)
        elif self._wide == "program":
            self._draw_prog_tiers(ws)

    # --- развороты ЯДРА -----------------------------------------------------
    #
    # У каждой панели свой режим, а не «та же панель крупнее»:
    #   ИМЕНА    — откуда взялось значение (выражение, поддерево, глубина);
    #   ПАМЯТЬ   — карта всех 64 ячеек, из которой можно считать;
    #   ПРОГРАММА— граф по ярусам: тот параллелизм, который упакует РАЗБОР.

    def on_panel_expanded(self, event) -> None:
        event.stop()
        self._wide = getattr(event.panel, "topic", "")
        self.refresh_state()

    def on_panel_collapsed(self, event) -> None:
        event.stop()
        self._wide = ""
        self.refresh_state()

    def _section(self, label: str, note: str = "") -> Text:
        """Заголовок раздела: строчными и линейка до края — как в отчётах ядра."""
        width = max(40, self.app.size.width - 8)
        t = Text()
        t.append("  " + label + "  ", style=palette.role_hex("title") + " bold")
        used = len(label) + 4
        if note:
            t.append(note + "  ", style=palette.role_hex("faint"))
            used += len(note) + 2
        t.append("─" * max(0, width - used), style=palette.role_hex("line"))
        return t

    def _subtree(self, dag, root: int) -> set[int]:
        """Все операции, из которых собрано это значение."""
        seen: set[int] = set()
        stack = [root]
        while stack:
            i = stack.pop()
            if i in seen:
                continue
            seen.add(i)
            stack.extend(dag[i].preds)
        return seen

    def _draw_names_full(self, ws) -> None:
        target = self.query_one("#names-full", Static)
        panel = self.query_one("#p-names", Panel)
        dim, faint = palette.role_hex("dim"), palette.role_hex("faint")
        title = palette.role_hex("title")
        panel.set_title(f"ИМЕНА   ·   откуда взялись значения   ·   "
                        f"{len(ws.regs)} {plural(len(ws.regs), 'имя', 'имени', 'имён')}")
        t = Text()
        if not ws.regs:
            t.append("  пока пусто. Наберите  a = 10  или  x = load 0",
                     style=faint)
            target.update(t)
            return
        dag = ws.snapshot()
        ids = getattr(ws, "_ids", {})
        t.append_text(self._section("значения", "и чем они посчитаны"))
        t.append("\n\n")
        t.append("    " + "имя".ljust(12) + "значение".rjust(12)
                 + "   " + "операций".rjust(9) + "   выражение\n", style=faint)
        for name, value in ws.regs.items():
            hot = name in self._changed_regs
            t.append("    ")
            t.append(name[:11].ljust(12),
                     style=title if hot else palette.role_hex("text"))
            t.append(str(value).rjust(12),
                     style=(palette.role_hex("work") + " bold") if hot else dim)
            node = ids.get(name)
            if node is None or node >= len(dag):
                t.append("   " + "—".rjust(9) + "   ", style=faint)
                t.append("введено числом", style=faint)
            else:
                sub = self._subtree(dag, node)
                t.append("   " + str(len(sub)).rjust(9) + "   ", style=faint)
                t.append(dag[node].text, style=palette.op_style(dag[node].op))
            t.append("\n")
        t.append("\n")
        t.append_text(self._section("что это значит"))
        t.append("\n\n")
        t.append("    «операций» — сколько узлов графа держит это имя. Одно\n"
                 "    длинное выражение даёт длинную цепочку зависимостей,\n"
                 "    и в РАЗБОРЕ она станет критическим путём.\n", style=faint)
        target.update(t)

    def _draw_mem_map(self, ws) -> None:
        head = self.query_one("#mem-head", Static)
        grid = self.query_one("#mem-map", ItemGrid)
        foot = self.query_one("#mem-foot", Static)
        panel = self.query_one("#p-mem", Panel)
        dim, faint = palette.role_hex("dim"), palette.role_hex("faint")
        used = sum(1 for v in ws.mem if v)
        panel.set_title(f"ПАМЯТЬ   ·   карта   ·   {MEM_SIZE} ячеек, "
                        f"ненулевых {used}")
        # Куда писал накопленный граф. Адрес STORE сохранён в имени узла
        # (`st7`), у LOAD он теряется при присваивании — поэтому честно
        # показываем только записи, а не выдумываем чтения.
        dag = ws.snapshot()
        stores: set[int] = set()
        for ins in dag:
            if ins.op == "STORE" and ins.name.startswith("st"):
                digits = ins.name[2:].split(".")[0]
                if digits.isdigit():
                    stores.add(int(digits))
        h = Text()
        h.append_text(self._section("ячейки", "клик — подставить в ввод"))
        head.update(h)
        grid.remove_children()
        for addr in range(MEM_SIZE):
            value = ws.mem[addr] if addr < len(ws.mem) else 0
            cell = Text()
            # Ни одного пробела внутри ячейки: Static переносит по пробелам, и
            # с ними адрес уезжал на одну строку, а значение на другую — карта
            # превращалась в кашу из чисел без понятного порядка.
            cell.append("▸" if addr in stores else "·",
                        style=palette.role_hex("work") if addr in stores
                        else faint)
            cell.append(f"{addr:>2}", style=faint)
            cell.append("│", style=palette.role_hex("line"))
            style = dim
            if addr in self._changed_mem:
                style = palette.role_hex("accent2") + " bold"
            elif not value:
                style = faint
            cell.append(str(value)[:5].rjust(5), style=style)
            grid.mount(MemCell(addr, cell, classes="mem-cell"))
        f = Text()
        f.append("\n    ▸ ", style=palette.role_hex("work"))
        f.append("сюда писал store", style=faint)
        f.append("        ярким — изменено последней строкой", style=faint)
        foot.update(f)

    def on_mem_cell_picked(self, event) -> None:
        event.stop()
        bar = self.query_one("#prompt", PromptBar)
        bar.focus_input()
        bar.set_value(f"load {event.addr}")

    def _draw_prog_tiers(self, ws) -> None:
        target = self.query_one("#prog-tiers", Static)
        panel = self.query_one("#p-prog", Panel)
        dag = ws.snapshot()
        dim, faint = palette.role_hex("dim"), palette.role_hex("faint")
        title = palette.role_hex("title")
        panel.set_title(f"ПРОГРАММА   ·   граф по ярусам   ·   {len(dag)} оп.")
        t = Text()
        if not len(dag):
            t.append("  граф пуст. `x = load 0`, `s = x*2` — и он начнёт "
                     "набираться.", style=faint)
            target.update(t)
            return
        from ...core.dag import compute_metrics

        model = self.app.session.model()
        try:
            met = compute_metrics(dag, model)
        except Exception:
            met = None
        # Ярус = самый ранний такт по зависимостям. Операции одного яруса
        # независимы, то есть могут пойти в один такт, если хватит портов.
        # Это и есть весь запас параллелизма, который РАЗБОРУ достанется.
        tiers: dict[int, list[int]] = {}
        for ins in dag:
            lvl = met.asap[ins.id] if met else 0
            tiers.setdefault(lvl, []).append(ins.id)
        widest = max((len(v) for v in tiers.values()), default=0)
        t.append_text(self._section(
            "ярусы", f"{len(tiers)} {plural(len(tiers), 'ярус', 'яруса', 'ярусов')}"
            f"  ·  шире всего {widest}  ·  портов {model.width}"))
        t.append("\n\n")
        for lvl in sorted(tiers):
            t.append(f"    т.{lvl:<4}", style=faint)
            row = tiers[lvl]
            # Ярус шире машины — часть операций всё равно подождёт, и это
            # видно здесь, до всякого планирования.
            over = len(row) > model.width
            for i in row:
                ins = dag[i]
                t.append(ins.name[:6].ljust(7), style=palette.op_style(ins.op))
            if over:
                t.append(f"   {len(row)} > {model.width} портов — "
                         "часть подождёт", style=palette.role_hex("warning"))
            t.append("\n")
        t.append("\n")
        t.append_text(self._section("что дальше"))
        t.append("\n\n")
        if met:
            t.append(f"    цепочка зависимостей — {met.critical_path_bound} т., "
                     f"ресурсы — {met.resource_bound} т.\n", style=dim)
            t.append(f"    быстрее {met.lower_bound} т. этот граф не уложится "
                     "ни одним планировщиком.\n", style=faint)
        t.append("    `go` — отдать граф в РАЗБОР и посчитать расписание.",
                 style=palette.role_hex("work"))
        target.update(t)

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
