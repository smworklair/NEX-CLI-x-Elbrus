"""ЯДРО — верстак интерпретатора.

Прежде интерпретатор был вкладкой с лентой текста: вычисления улетали в лог,
а всё, ради чего он существует — имена, память и накопленный граф участка —
приходилось выпрашивать командами `names`, `mem`, `list`. Здесь они видны
постоянно и обновляются на каждой строке.

Раскладка:
    слева   ЛЕНТА — лист вычислений: каждая строка человека с её итогом
            (значение, +операции, имена) и вердиктом `go`; консоль внутри
            ЛЕНТы осталась только для отчётов slash-команд
    справа  ИМЕНА, ПАМЯТЬ, ПРОГРАММА — состояние машины
    внизу   чем считать (ядра и служебные слова) + строка ввода с превью

Связки, ради которых экран существует:
    — строка листа ↔ операции графа: клик по операции подсвечивает строку,
      которая её породила, клик по строке — её операции в ПРОГРАММЕ;
    — каждая строка, изменившая машину, — коммит в общем git-журнале с
      ПОЛНЫМ снимком машины: «вернуть» из журнала восстанавливает имена,
      память и граф, из любого режима.

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
from ..widgets import (Chip, Console, ConsoleJournal, Panel, PanelToolbar,
                        PromptBar, plural)
from .base import ModeScreen

MEM_MINI_W = 8
MEM_MINI_ROWS = 4


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


class TapeRow(Static):
    """Строка листа ЛЕНТЫ. Клик — связка с ПРОГРАММОЙ: подсветить операции,
    которые эта строка положила в граф (повторный клик снимает подсветку)."""

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


class ProgramItem(Static):
    """Операция в ПРОГРАММЕ. Клик — связка с ЛЕНТОЙ: подсветить строку,
    которая эту операцию породила."""

    class Picked(Message):
        def __init__(self, node: int) -> None:
            super().__init__()
            self.node = node

    def __init__(self, node: int, *args, **kw) -> None:
        super().__init__(*args, **kw)
        self.node = node

    def on_click(self, event) -> None:
        event.stop()
        self.post_message(self.Picked(self.node))


class CoreScreen(ModeScreen):
    """Интерпретатор: считает здесь, граф копится на глазах."""

    mode = "work"
    mode_title = "ЯДРО"
    mode_subtitle = "интерпретатор"
    placeholder = "2+2   ·   a=10   ·   sum 8   ·   go"
    hint = "«/» команда   ·   ↑ история"
    SIDE_ID = "#core-right"
    TIPS_ID = "#p-kernels"

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self._prev_regs: dict[str, int] = {}
        self._prev_mem: list[int] = []
        self._changed_regs: set[str] = set()
        self._changed_mem: set[int] = set()
        # Лист ЛЕНТЫ: каждая строка человека — запись одного из видов
        # (line — вычисление, error — ошибка, note — пометка мостика,
        # verdict — итог `go`, report — вывод names/mem/list). Список
        # только растёт: лист — летопись сессии, а не окно вывода.
        self._rows: list[dict] = []
        self._line_seq = 0          # номер последней строки-вычисления
        self._sheet_drawn = 0       # сколько строк листа уже смонтировано
        self._sheet_theme = ""      # тема, в которой нарисован лист
        self._last_added = 0        # операций добавила последняя строка
        self._link: tuple | None = None   # ("row", i) | ("op", node) | None
        self._report_on = False     # консоль-отчёт slash-команды на виду
        self._last_commit: dict | None = None   # запись журнала для go
        # Журнал команд внутри ЛЕНТЫ: выключен по умолчанию — здесь он
        # не главный, но должен быть под рукой, как на остальных экранах.
        self._tape_journal = False
        # Какая панель развёрнута. Разворот здесь — не «то же крупнее»: у
        # ИМЁН это происхождение значений, у ПАМЯТИ — карта, из которой
        # можно считать, у ПРОГРАММЫ — ярусы графа, то есть тот самый
        # параллелизм, который потом упаковывает РАЗБОР.
        self._wide = ""

    # --- раскладка --------------------------------------------------------

    def compose_body(self):
        with Horizontal(id="core-body"):
            with Vertical(id="core-left"):
                yield Panel(
                    # Развёрнутая ЛЕНТА — рабочий терминал интерпретатора:
                    # глаголы под рукой, а не «где-то в соседней панели».
                    PanelToolbar(
                        ("names", "verb-names", "показать имена и значения"),
                        ("mem", "verb-mem", "показать память"),
                        ("list", "verb-list", "показать накопленный граф"),
                        ("go", "verb-go",
                         "отдать граф в разбор и посчитать"),
                        ("reset", "verb-reset",
                         "очистить имена и память"),
                        ("git", "tape-journal",
                         "история сессии и мостик в другие режимы"),
                    ),
                    # Лист — главный вид ЛЕНТЫ: каждая строка человека с её
                    # итогом. Консоль осталась для отчётов slash-команд,
                    # журнал («git») открывается своей кнопкой.
                    VerticalScroll(id="tape-sheet"),
                    Console(id="console",
                            runs=self.app.session.journal_runs),
                    ConsoleJournal(id="journal"),
                    title="ЛЕНТА", id="p-tape", topic="tape")
                yield Panel(
                    Horizontal(id="kernel-chips"),
                    Horizontal(id="verb-chips"),
                    VerticalScroll(Static(id="kern-full"), id="kern-wide"),
                    title="ЧЕМ СЧИТАТЬ", id="p-kernels", topic="kernels",
                )
            with Vertical(id="core-right"):
                yield Panel(VerticalScroll(Static(id="names")),
                            VerticalScroll(Static(id="names-full"),
                                           id="names-wide"),
                            title="ИМЕНА", id="p-names", topic="names")
                yield Panel(ItemGrid(id="mem-mini", min_column_width=8),
                            Static(id="mem-mini-foot"),
                            Vertical(Static(id="mem-head"),
                                     ItemGrid(id="mem-map", min_column_width=11),
                                     Static(id="mem-foot"),
                                     id="mem-wide"),
                            title="ПАМЯТЬ", id="p-mem", topic="memory")
                yield Panel(
                    PanelToolbar(
                        ("go", "verb-go", "отдать граф в разбор и посчитать"),
                        ("list", "verb-list", "показать накопленный граф"),
                    ),
                    VerticalScroll(id="program"),
                    VerticalScroll(Static(id="prog-tiers"),
                                   id="prog-wide"),
                    title="ПРОГРАММА", id="p-prog", topic="program")

    def panel_tool(self, tool: str) -> None:
        """Инструменты развёрнутых панелей ЯДРА — глаголы интерпретатора.

        Это НЕ slash-команды: обычная строка здесь и есть запись в ленту,
        и инструменты идут тем же путём `_exec_interp`, что и набранное.
        Вывод виден сразу — консоль лежит внутри той же ЛЕНТЫ.
        """
        verbs = {"verb-names": "names", "verb-mem": "mem",
                 "verb-list": "list", "verb-go": "go",
                 "verb-reset": "reset"}
        if tool in verbs:
            self._exec_interp(verbs[tool])
            return
        if tool == "tape-journal":
            self._toggle_tape_journal()
            return
        super().panel_tool(tool)

    # --- журнал сессии внутри ЛЕНТЫ -----------------------------------------

    def _toggle_tape_journal(self) -> None:
        """«журнал» — показать/убрать общий журнал команд в блоке ЛЕНТЫ.

        На других экранах журнал открывается разворотом панели; здесь
        ЛЕНТА и так разворачивается в лист вычислений, и второй смысл
        разворота был бы загадкой. Поэтому у журнала своя кнопка: нажатие
        разворачивает ЛЕНТУ, если она ещё не развёрнута, и меняет её
        содержимое на журнал — каталог команд, история и мостик в другие
        режимы, ровно то же, что у остальных экранов.
        """
        self._tape_journal = not self._tape_journal
        if self._tape_journal and self._wide != "tape":
            panel = self.query_one("#p-tape", Panel)
            self.maximize(panel, container=False)
            panel.post_message(Panel.Expanded(panel))
            return
        try:
            bar = self.query_one("#p-tape PanelToolbar", PanelToolbar)
            bar.mark("tape-journal", self._tape_journal)
        except Exception:
            pass
        self.refresh_state()

    def _load_journal(self) -> None:
        con = self.query_one("#console", Console)
        n = len(con.runs)
        self.query_one("#p-tape", Panel).set_title(
            f"ЛЕНТА   ·   git   ·   "
            f"{n} {plural(n, 'запуск', 'запуска', 'запусков')}")
        journal = self.query_one("#journal", ConsoleJournal)
        journal.load(con.runs, self.mode, list(self.app.commands),
                     self.app.session.journal_events)
        try:
            self.query_one("#p-tape PanelToolbar",
                           PanelToolbar).mark("tape-journal", True)
        except Exception:
            pass

    def _take_pending_note(self) -> None:
        """Пометка от мостика журнала («в ядро») — строкой в лист.

        Чужой граф сюда не вставляется: здесь его собирают руками, и это
        осознанно. Мостик привозит контекст — чей прогон смотрели, — чтобы
        человек знал, что перед ним, а не догадывался.
        """
        note = getattr(self.app.session, "pending_note", "")
        if not note:
            return
        self.app.session.pending_note = ""
        self._rows.append({"kind": "note", "text": note})
        self._rows.append({"kind": "note",
                           "text": "собери здесь свой вариант графа и отдай go"})
        self.refresh_state()

    def on_ready(self) -> None:
        self._fill_chips()
        self._take_pending_note()
        self.refresh_state()

    def run_core(self, line: str) -> None:
        """Slash-команда — отчёт в консоли под листом.

        Лист ЛЕНТЫ — про строки человека, отчёты команд — отдельный жанр.
        Консоль показывается, пока отчёт свежий: первая же строка
        интерпретатора возвращает главный вид листу (отчёт остаётся в git).
        """
        self._report_on = True
        super().run_core(line)
        self.refresh_state()

    def hint_pairs(self):
        return [("Enter", "считать"), ("/", "команды"), ("go", "граф в разбор"),
                ("Esc", "к выбору режима")]

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

    # --- ввод -------------------------------------------------------------

    def handle_line(self, line: str) -> None:
        if line.startswith("/"):
            self.run_core(line)
            return
        self._exec_interp(line)

    def _exec_interp(self, line: str) -> None:
        """Строка интерпретатора: лист, состояние и — если машина
        изменилась — коммит в общий git-журнал с полным снимком."""
        from ...ui import interp_view

        con = self.console
        ws = self.app.session.workspace()
        self._snapshot_state()
        self._report_on = False     # строка человека возвращает лист
        prev_graph = ws.graph_size()
        try:
            result = ws.exec(line)
        except InterpError as e:
            self._rows.append({"kind": "error", "line": line, "msg": str(e)})
            self.refresh_state()
            return
        except Exception as e:
            self._rows.append({"kind": "error", "line": line,
                               "msg": f"{type(e).__name__}: {e}"})
            self.refresh_state()
            return

        # Что строка положила в граф. Ядро (`sum 8` и прочие) пересобирает
        # граф с нуля — его операции все; обычная строка только дописывает
        # в конец (id узла равен индексу).
        if result.kind == "kernel":
            created = list(range(ws.graph_size()))
        else:
            created = list(range(prev_graph, ws.graph_size()))
        self._last_added = len(created)
        names_changed = sorted(n for n, v in ws.regs.items()
                               if self._prev_regs.get(n) != v)
        mem_changed = {i for i, v in enumerate(ws.mem)
                       if i < len(self._prev_mem) and self._prev_mem[i] != v}

        # Служебные виды (names/mem/list) показываются выводом команды —
        # они едут в лист как готовый блок ANSI. Но `mem 5 6` ещё и ПИШЕТ
        # память: запись в машину обязана остаться коммитом.
        if result.kind in ("env", "mem", "list"):
            self._rows.append({
                "kind": "report",
                "ansi": interp_view.render_result(
                    ws, result, width=max(24, self.app.size.width - 8)),
            })
            if result.kind == "mem" and mem_changed:
                rec = con.commit(line, self.mode) if con is not None else {
                    "cmd": line, "lines": [], "error": False,
                    "mode": self.mode, "time": ""}
                rec["lines"] = [self._tape_text(len(self._rows) - 1)]
                rec["ws"] = ws.machine()
                self._last_commit = rec
            self.refresh_state()
            self.refresh_context()
            return

        self._line_seq += 1
        entry = {
            "kind": "line",
            "n": self._line_seq,
            "line": line,
            "value": result.value,
            "ops": len(created),
            "names": names_changed,
            "ids": created,
            # У store в message живёт адрес: показывать голое «5» вместо
            # значения — путать с именем. Ясность стоит одного слова.
            "msg": (f"яч. {result.message}" if result.kind == "store"
                    else result.message or ""),
        }
        self._rows.append(entry)

        changed = (bool(created) or bool(names_changed) or bool(mem_changed)
                   or result.kind == "reset")
        is_go = result.kind == "go" and not ws.empty()
        if changed or is_go:
            # Коммит в git сессии. `2+2` и ошибки — не коммиты: журнал —
            # история состояний машины, а не лог нажатий.
            rec = con.commit(line, self.mode) if con is not None else {
                "cmd": line, "lines": [], "error": False, "mode": self.mode,
                "time": ""}
            rec["lines"] = [self._tape_text(len(self._rows) - 1)]
            rec["ws"] = ws.machine()
            if result.kind != "reset" and not ws.empty():
                self.app.session.set_dag(ws.snapshot(), "interp")
                rec["scenario"] = self.app.session.scenario
                rec["dag"] = self.app.session.dag_obj
                rec["profile"] = self.app.session.profile
            self._last_commit = rec
        self.refresh_state()
        self.refresh_context()
        if result.kind == "go":
            self._handoff()

    def _handoff(self) -> None:
        """`go`: посчитать накопленный граф и показать короткий вердикт."""
        ws = self.app.session.workspace()
        if ws.empty():
            self._rows.append({"kind": "warn",
                               "text": "графа нет — считали без записи "
                                       "в программу"})
            self.refresh_state()
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
        self._rows.append({"kind": "error", "line": "go",
                           "msg": f"не посчиталось: {msg}"})
        self.refresh_state()

    def _verdict(self, base, orc, met) -> None:
        """Итог `go` — строкой в лист и числами в коммит журнала."""
        b, o = base.schedule.makespan, orc.schedule.makespan
        self._rows.append({"kind": "verdict", "base": b, "oracle": o,
                           "bound": met.lower_bound})
        rec = self._last_commit
        if rec is not None:
            rec["verdict"] = (b, o)
            rec["lines"].append(self._verdict_text(b, o, met.lower_bound))
        self.refresh_state()

    def _verdict_text(self, b: int, o: int, bound: int) -> Text:
        t = Text()
        t.append("  ●  граф передан в разбор",
                 style=f"{palette.role_hex('work')} bold")
        t.append("\n")
        t.append("     baseline ", style=palette.role_hex("dim"))
        t.append(str(b), style=palette.role_hex("title"))
        t.append("   оракул ", style=palette.role_hex("dim"))
        t.append(str(o), style=f"{palette.role_hex('success')} bold")
        t.append("   предел ", style=palette.role_hex("dim"))
        t.append(str(bound), style=palette.role_hex("title"))
        if b > o:
            t.append(f"   −{b - o} т.", style=palette.role_hex("success"))
        return t

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
        for wide_id, short_ids, topic in (
                ("#names-wide", ("#names",), "names"),
                ("#mem-wide", ("#mem-mini", "#mem-mini-foot"), "memory"),
                ("#prog-wide", ("#program",), "program"),
                ("#kern-wide", ("#kernel-chips", "#verb-chips"), "kernels")):
            self.query_one(wide_id).display = self._wide == topic
            for short_id in short_ids:
                self.query_one(short_id).display = self._wide != topic
        # ЛЕНТА — три состояния: лист (главный вид, свёрнутый и развёрнутый),
        # консоль-отчёт slash-команды (пока отчёт свежий) и журнал команд.
        # Журнал заменяет собой и лист, и отчёт: это место «что вообще
        # происходило в сессии», ему нужен весь блок.
        con = self.query_one("#console", Console)
        journal = self.query_one("#journal", ConsoleJournal)
        if self._wide == "tape" and self._tape_journal:
            self.query_one("#tape-sheet").display = False
            con.display = False
            journal.display = True
            self._load_journal()
        else:
            journal.display = False
            con.display = self._report_on
            sheet = self.query_one("#tape-sheet")
            sheet.display = True
            self._draw_tape()
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
        elif self._wide == "kernels":
            self._draw_kern_full()
        else:
            self.query_one("#p-kernels", Panel).set_title("ЧЕМ СЧИТАТЬ")

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

    def panel_facts(self, topic: str) -> list[str]:
        ws = self.app.session.workspace()
        dag = ws.snapshot()
        base = [f"Интерпретатор: имён {len(ws.regs)}, операций в графе "
                f"{len(dag)}, машина {self.app.session.model().name}."]
        if topic == "names":
            return base + [f"{n} = {v}" for n, v in list(ws.regs.items())[:12]]
        if topic == "memory":
            filled = [(i, v) for i, v in enumerate(ws.mem) if v][:12]
            return base + [f"Ячейка {i} = {v}" for i, v in filled]
        if topic == "program":
            return base + [f"{i.name}: {i.text} ({i.op})"
                           for i in list(dag)[:12]]
        if topic == "tape":
            lines = [r for r in self._rows if r["kind"] == "line"]
            return base + [f"Строка «{h['line']}» дала {h['value']}, "
                           f"операций +{h['ops']}." for h in lines[-8:]]
        if topic == "kernels":
            return base + [f"Ядро {n} {d}: {h}" for n, d, h in kernel_help()]
        return base

    def panel_chips(self, topic: str) -> list[str]:
        return {
            "names": ["какое имя тут самое дорогое?",
                      "что значит «операций» в этой таблице?"],
            "memory": ["что лежит в памяти по умолчанию?",
                       "чем load отличается от store?"],
            "program": ["что тут можно распараллелить?",
                        "почему ярусы такие узкие?"],
            "tape": ["что я вообще посчитал?",
                     "какие строки положили операции в граф?"],
            "kernels": ["какое ядро взять для начала?",
                        "чем dot отличается от saxpy?"],
        }.get(topic, [])

    # --- лист ЛЕНТЫ ---------------------------------------------------------

    def _draw_tape(self) -> None:
        """Лист — главный вид ЛЕНТЫ: история строк человека с их итогом.

        Монтируется инкрементально: лист только растёт, и на каждой строке
        добавляется лишь новый ряд. Полная перемонка — при смене темы,
        цвета строк считаются в момент монтирования.
        """
        from ...ui import render

        box = self.query_one("#tape-sheet", VerticalScroll)
        panel = self.query_one("#p-tape", Panel)
        if render.THEME.name != self._sheet_theme:
            box.remove_children()
            self._sheet_drawn = 0
            self._sheet_theme = render.THEME.name
        n = len([r for r in self._rows if r["kind"] == "line"])
        place = ("лист вычислений" if self._wide == "tape" else "лист")
        panel.set_title(f"ЛЕНТА   ·   {place}   ·   "
                        f"{n} {plural(n, 'строка', 'строки', 'строк')}")
        if not self._rows:
            if not box.children:
                box.mount(Static(Text(
                    "    каждая строка ляжет сюда: что ввёл, что вышло,\n"
                    "    сколько операций ушло в граф.\n\n"
                    "    память с начала заполнена 1 2 3 4 …\n\n"
                    "    2+2   ·   a=10   ·   x=load 0   ·   sum 8   ·   go",
                    style=palette.role_hex("faint")),
                    classes="tape-empty"))
            return
        if self._sheet_drawn == 0:
            box.remove_children()   # пустое состояние уступает первой строке
        fresh = False
        for i in range(self._sheet_drawn, len(self._rows)):
            box.mount(TapeRow(i, self._tape_text(i),
                              classes="tape-row tape-" + self._rows[i]["kind"]))
            fresh = True
        self._sheet_drawn = len(self._rows)
        if fresh and self._wide != "tape":
            box.scroll_end(animate=False)
        self._apply_link()

    def _tape_text(self, i: int) -> Text:
        """Текст строки листа. Один и тот же и на экране, и в записи
        git-журнала: журнал показывает вывод коммита этими же строками."""
        r = self._rows[i]
        faint = palette.role_hex("faint")
        dim = palette.role_hex("dim")
        title = palette.role_hex("title")
        work = palette.role_hex("work")
        kind = r["kind"]
        t = Text()
        if kind == "line":
            t.append(f"{r['n']:>3}  ", style=faint)
            t.append(r["line"][:26].ljust(26), style=title)
            val = "—" if r["value"] is None else str(r["value"])
            t.append(f"= {val}".ljust(12),
                     style=work if r["value"] is not None else faint)
            if r["ops"]:
                t.append(f"+{r['ops']} оп.".ljust(9),
                         style=palette.role_hex("accent2"))
            else:
                t.append("·".ljust(9), style=faint)
            tail = ", ".join(r["names"]) if r["names"] else r.get("msg", "")
            if tail:
                t.append(tail[:32], style=dim)
        elif kind == "error":
            t.append("  ✗  ", style=palette.role_hex("error"))
            t.append(r["line"][:26], style=palette.role_hex("error"))
            t.append("   " + r["msg"], style=dim)
        elif kind == "warn":
            t.append("  ⚠  ", style=palette.role_hex("warning"))
            t.append(r["text"], style=dim)
        elif kind == "note":
            t.append("  ·  ", style=palette.role_hex("accent2"))
            t.append(r["text"], style=dim)
        elif kind == "verdict":
            t.append_text(self._verdict_text(r["base"], r["oracle"],
                                             r["bound"]))
        elif kind == "report":
            return Text.from_ansi("\n".join(r["ansi"]))
        return t

    # --- связка строк ↔ операций -------------------------------------------

    def on_tape_row_picked(self, event: TapeRow.Picked) -> None:
        event.stop()
        if self._rows[event.index]["kind"] != "line":
            return
        self._set_link(None if self._link == ("row", event.index)
                       else ("row", event.index))

    def on_program_item_picked(self, event: ProgramItem.Picked) -> None:
        event.stop()
        self._set_link(None if self._link == ("op", event.node)
                       else ("op", event.node))
        if self._link is None:
            return
        i = self._row_of_node(event.node)
        if i is None:
            return
        sheet = self.query_one("#tape-sheet", VerticalScroll)
        for row in sheet.query(TapeRow):
            if row.index == i:
                sheet.scroll_to_widget(row, animate=False)
                break

    def _set_link(self, link: tuple | None) -> None:
        self._link = link
        self._apply_link()

    def _row_of_node(self, node: int) -> int | None:
        """Строка листа, которая положила узел `node` в граф."""
        for i, r in enumerate(self._rows):
            if r.get("kind") == "line" and node in r.get("ids", ()):
                return i
        return None

    def _apply_link(self) -> None:
        """Подсветка связки в обе стороны — без перерисовки содержимого."""
        link = self._link
        linked_ids: set[int] = set()
        if link is not None:
            if link[0] == "op":
                linked_ids.add(link[1])
            else:
                row = self._rows[link[1]]
                linked_ids = set(row.get("ids", ()))
        for row in self.query(TapeRow):
            on = False
            if link is not None:
                if link[0] == "row":
                    on = row.index == link[1]
                else:
                    # Клик по операции: «on» получает и строка-родитель —
                    # иначе связка видна только со стороны программы.
                    r = self._rows[row.index]
                    on = r.get("kind") == "line" and link[1] in r.get("ids", ())
            row.set_class(on, "on")
        for item in self.query(ProgramItem):
            item.set_class(item.node in linked_ids, "hot")

    def _draw_kern_full(self) -> None:
        """Развёрнутое «ЧЕМ СЧИТАТЬ» — каталог ядер, а не ряд чипов.

        Чип говорит имя, но не говорит, что ядро посчитает: `chase` и `dot`
        для нового человека одинаково пусты. Каталог показывает форму вызова
        и что она делает.
        """
        target = self.query_one("#kern-full", Static)
        panel = self.query_one("#p-kernels", Panel)
        dim, faint = palette.role_hex("dim"), palette.role_hex("faint")
        work = palette.role_hex("work")
        rows = kernel_help()
        panel.set_title(f"ЧЕМ СЧИТАТЬ   ·   каталог   ·   {len(rows)} ядер")
        t = Text()
        t.append_text(self._section("ядра", "вызов подставляется кликом по чипу"))
        t.append("\n\n")
        t.append("      " + "вызов".ljust(18) + "что считает\n", style=faint)
        for name, default, hint in rows:
            t.append("      ")
            t.append(f"{name} {default}".ljust(18), style=work)
            t.append(hint, style=dim)
            t.append("\n")
        t.append("\n")
        t.append_text(self._section("служебные слова"))
        t.append("\n\n")
        for word, hint in (("names", "показать имена и значения"),
                           ("mem", "показать память"),
                           ("list", "показать накопленный граф"),
                           ("reset", "очистить имена и память"),
                           ("go", "отдать граф в РАЗБОР и посчитать")):
            t.append("      " + word.ljust(18), style=palette.role_hex("text"))
            t.append(hint + "\n", style=faint)
        t.append("\n")
        t.append_text(self._section("как писать"))
        t.append("\n\n")
        t.append("      a0 = load [0]        взять из памяти\n"
                 "      s = a0 * b0          арифметика с именами\n"
                 "      store s 7            положить обратно\n\n", style=dim)
        t.append("      Здесь считают выражениями, а не мнемониками e2k:\n"
                 "      `mul m0 a0 b0` — это ассемблер, его разбирает /load.",
                 style=faint)
        target.update(t)

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
        faint = palette.role_hex("faint")
        used = sum(1 for v in ws.mem if v)
        panel.set_title(f"ПАМЯТЬ   ·   карта   ·   {MEM_SIZE} ячеек, "
                        f"ненулевых {used}")
        stores = self._store_cells(ws.snapshot())
        h = Text()
        h.append_text(self._section("ячейки", "клик — подставить в ввод"))
        head.update(h)
        grid.remove_children()
        for addr in range(MEM_SIZE):
            grid.mount(MemCell(addr, self._mem_cell_text(addr, ws, stores),
                               classes="mem-cell"))
        f = Text()
        written = ", ".join(f"{a}←{n}" if n else str(a)
                            for a, n in sorted(stores.items())[:8])
        f.append("\n    ▸ ", style=palette.role_hex("work"))
        f.append(f"сюда писал store: {written}" if written
                 else "пока без записей store", faint)
        f.append("        ярким — изменено последней строкой", faint)
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
        panel = self.query_one("#p-names", Panel)
        dim = palette.role_hex("dim")
        badge = (f"   +{len(self._changed_regs)}"
                 if self._changed_regs else "")
        panel.set_title(f"ИМЕНА   {len(ws.regs)}{badge}")
        if not ws.regs:
            target.update(Text("пока пусто — a=10", style=palette.role_hex("faint")))
            return
        width = max(20, panel.size.width - 4)
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

    def _store_cells(self, dag) -> dict[int, str]:
        """Адрес → источник записи: куда положил `store` и ЧТО положил.

        Адрес STORE хранит в имени узла (`st7`), источник — в тексте
        (`st x`). Чтения адрес не сохраняют, поэтому в карте честно
        показаны только записи.
        """
        stores: dict[int, str] = {}
        for ins in dag:
            if ins.op == "STORE" and ins.name.startswith("st"):
                digits = ins.name[2:].split(".")[0]
                if digits.isdigit():
                    parts = ins.text.split()
                    stores[int(digits)] = parts[1] if len(parts) > 1 else ""
        return stores

    def _mem_cell_text(self, addr: int, ws, stores: dict[int, str]) -> Text:
        """Текст ячейки: маркер записи, адрес, значение. Ни одного лишнего
        пробела внутри: Static переносит по пробелам, и с ними адрес уезжал
        на одну строку, а значение на другую."""
        value = ws.mem[addr] if addr < len(ws.mem) else 0
        faint = palette.role_hex("faint")
        cell = Text()
        cell.append("▸" if addr in stores else "·",
                    style=palette.role_hex("work") if addr in stores else faint)
        cell.append(f"{addr:>2}", style=faint)
        cell.append("│", style=palette.role_hex("line"))
        if addr in self._changed_mem:
            style = f"{palette.role_hex('accent2')} bold"
        elif addr in stores:
            style = palette.role_hex("work")
        elif not value:
            style = faint
        else:
            style = palette.role_hex("dim")
        cell.append(str(value)[:4].rjust(4), style=style)
        return cell

    def _draw_memory(self, ws) -> None:
        """Свёрнутая ПАМЯТЬ — та же живая карта, что в развороте, только
        первые ряды: клик по ячейке подставляет `load`, запись store
        помечена маркером. Отдельная таблица «цифры без адресов» больше
        не нужна: она не отвечала ни на один вопрос."""
        grid = self.query_one("#mem-mini", ItemGrid)
        foot = self.query_one("#mem-mini-foot", Static)
        panel = self.query_one("#p-mem", Panel)
        badge = (f"   +{len(self._changed_mem)}"
                 if self._changed_mem else "")
        panel.set_title(f"ПАМЯТЬ{badge}")
        stores = self._store_cells(ws.snapshot())
        grid.remove_children()
        # Сколько ячеек в строке — по фактической ширине панели: на узком
        # окне сетка иначе переносится и перестаёт быть сеткой.
        inner = max(16, panel.size.width - 4)
        cols = max(3, (inner - 4) // MEM_MINI_W)
        for addr in range(min(MEM_SIZE, cols * MEM_MINI_ROWS)):
            grid.mount(MemCell(addr, self._mem_cell_text(addr, ws, stores),
                               classes="mem-cell mini"))
        f = Text()
        written = ", ".join(f"{a}←{n}" if n else str(a)
                            for a, n in sorted(stores.items())[:6])
        f.append("▸ ", style=palette.role_hex("work"))
        if written:
            f.append(f"store: {written}", style=palette.role_hex("dim"))
            f.append("  ·  ", style=palette.role_hex("faint"))
        # Подпись короткая: подвал в один ряд, иначе переносится на вторую
        # строку и съедает ряд у карты.
        f.append("клик — load · карта в развороте",
                 style=palette.role_hex("faint"))
        foot.update(f)

    def _draw_program(self, ws) -> None:
        """ПРОГРАММА — по операции на строку: операции кликабельны, это
        половина связки «строка ↔ операция» (вторая половина в листе)."""
        box = self.query_one("#program", VerticalScroll)
        panel = self.query_one("#p-prog", Panel)
        dag = ws.snapshot()
        badge = (f"   +{self._last_added}" if self._last_added else "")
        panel.set_title(f"ПРОГРАММА   {len(dag)} оп.{badge}")
        box.remove_children()
        if not len(dag):
            box.mount(Static(Text(
                "граф пуст — load/store и арифметика с именами\n"
                "кладут сюда операции",
                style=palette.role_hex("faint"))))
            return
        dim = palette.role_hex("dim")
        for ins in dag:
            t = Text()
            t.append(f"{ins.name:<7}", style=palette.role_hex("text"))
            t.append(f"{ins.op:<6}", style=palette.op_style(ins.op))
            t.append(ins.text, style=dim)
            box.mount(ProgramItem(ins.id, t, classes="prog-item"))
        self._apply_link()
