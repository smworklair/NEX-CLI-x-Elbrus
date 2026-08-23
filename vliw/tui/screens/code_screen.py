"""КОД — редактор ассемблера e2k, который показывает расписание НА коде.

Идея режима: чтобы кроме NEX не нужно было ничего. Но «текстовое поле слева,
лог справа» — это блокнот с логом, а не инструмент: он не знает, что в нём
написано, и всё, что человек получал, — тот же отчёт ядра, только набранный
не в терминале. Здесь редактор разбирает буфер НА ЛЕТУ и отвечает на три
вопроса прямо в тексте:

  * **в каком такте пойдёт эта строка** — гуттер слева от кода, `т7 ,0`;
  * **что тут не по машине** — метка `▲` на строке и разбор в ЧТО НЕ ТАК:
    канал, которого у операции нет; порт, занятый предыдущей операцией;
    чтение результата раньше латентности (ассемблер это пропустит — код
    соберётся и будет считать не то);
  * **сколько такого кода лишнее** — после F5 в гуттере появляется `т7→1`:
    куда ту же строку кладёт точный поиск.

Всё, что дороже разбора (точный поиск, диагностика), считается по F5 и
только по F5. Разбор, линтер и расписание из самого исходника — на каждое
нажатие клавиши: они стоят микросекунды, а без них редактор снова становится
блокнотом.

Буфер один на сессию и живёт в `session.code_text`, а не в виджете: отсюда
его видят `/code run`, `/code save` и умная вставка из других режимов.
"""

from __future__ import annotations

import re

from rich.segment import Segment
from rich.style import Style as RichStyle
from rich.text import Text
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.strip import Strip
from textual.widgets import DataTable, Static, TextArea
from textual.widgets.text_area import TextAreaTheme

from ...core import asm_parser, doctor
from .. import palette
from ..widgets import (Console, ConsoleJournal, Panel, PanelToolbar, PromptBar,
                       Tool, plural)
from .base import ModeScreen

#: Что лежит в буфере, пока пользователь не начал писать своего.
#:
#: Пример не выдуман: это ровно тот случай, на котором в `core/model.py`
#: поймали ошибку первой версии модели — lcc разложил независимые умножения
#: по одному в такт в ОДИН канал `,0`, хотя ассемблер принимает `muls` на
#: четырёх (`,0 ,1 ,3 ,4`). Расписание законное, работает правильно и теряет
#: почти половину тактов — то есть показывает ровно то, ради чего инструмент
#: существует, и не встречает новичка стеной красных замечаний.
SEED = """\
! Фрагмент .s от lcc (e2k-v6). Правь и жми F5 — справа расписание.
! Восемь независимых умножений компилятор разложил по одному в такт,
! и все в один канал ,0. А muls исполним на четырёх: ,0 ,1 ,3 ,4.
{
  muls,0 %r10, %r11, %r20
}
{
  muls,0 %r12, %r13, %r21
}
{
  muls,0 %r14, %r15, %r22
}
{
  muls,0 %r16, %r17, %r23
}
{
  muls,0 %r18, %r19, %r24
}
{
  muls,0 %r30, %r31, %r25
}
{
  muls,0 %r32, %r33, %r26
}
{
  muls,0 %r34, %r35, %r27
}
{
  adds,1 %r20, %r21, %r40
}
{
  adds,1 %r22, %r23, %r41
}
{
  adds,1 %r24, %r25, %r42
}
{
  adds,1 %r26, %r27, %r43
}
{
  adds,2 %r40, %r41, %r44
}
{
  adds,2 %r42, %r43, %r45
}
{
  adds,3 %r44, %r45, %r46
}
"""

#: Второй пример — по кнопке «пример ▸»: тот же буфер, но с ошибками, которые
#: ассемблер пропускает молча. Нужен, чтобы линтер можно было увидеть в
#: работе, не сочиняя поломку самому.
SEED_BROKEN = """\
! Тот же участок, но с тремя ошибками, которые ассемблер НЕ ловит.
! Жми F5 и смотри ЧТО НЕ ТАК — там номера строк.
{
  sdivs,5 %r0, %r1, %r2
}
{
  sdivs,5 %r3, %r4, %r5
}
{
  muls,2 %r2, %r5, %r6
}
{
  adds,0 %r6, %r2, %r7
}
"""

CONT = "↓"        # клетка занята продолжением длинной операции
EMPTY = "·"


# --------------------------------------------------------------------------
# Подсветка ассемблера e2k
# --------------------------------------------------------------------------
#
# Через tree-sitter это не сделать: грамматики для `.s` Эльбруса не
# существует и не будет. Зато механика подсветки у TextArea от парсера не
# зависит — она красит по карте `_highlights` (строка → [(байт, байт, имя)])
# и таблице стилей темы. Карту строит `_build_highlight_map`, и здесь она
# переопределена своим разбором строки. Это не обход API, а единственная его
# точка расширения: всё остальное (кэш строк, перерисовка на правку, выбор
# стиля по имени) достаётся даром.

_COMMENT_RE = re.compile(r"(//|!|;)")
_MNEM_RE = re.compile(r"(?P<mn>[a-z][a-z0-9_]*)(?P<ch>,\d+)?")
_REG_RE = re.compile(r"%[a-z]+\d*(\[\d+\])?")
_NUM_RE = re.compile(r"(?<![\w%])\d+")

#: Мнемоники, которые к расписанию отношения не имеют (`nop 4`, `return`).
#: Разбор их пропускает — и подсветка тоже не должна выдавать их за операции.
META = {"nop", "return", "ct", "ibranch", "call", "disp"}


def _line_tokens(line: str) -> list[tuple[int, int, str]]:
    """Разметка одной строки: [(начало, конец, имя стиля)] в символах."""
    out: list[tuple[int, int, str]] = []

    m = _COMMENT_RE.search(line)
    code = line[:m.start()] if m else line
    if m:
        out.append((m.start(), len(line), "comment"))

    for i, ch in enumerate(code):
        if ch in "{}":
            out.append((i, i + 1, "brace"))

    body = code.strip()
    if body.startswith("."):
        out.append((code.index("."), len(code.rstrip()), "meta"))
        return out
    if body.endswith(":") and " " not in body:
        out.append((len(code) - len(code.lstrip()), len(code.rstrip()), "label"))
        return out

    for rm in _REG_RE.finditer(code):
        out.append((rm.start(), rm.end(), "reg"))
    for nm in _NUM_RE.finditer(code):
        out.append((nm.start(), nm.end(), "num"))

    # Мнемоника — первое слово строки (после `{` и пробелов). Дальше в строке
    # слов быть не может: операнды — регистры и числа.
    #
    # Идёт ПОСЛЕ регистров и чисел нарочно: подсветка накладывается по
    # порядку, и общее правило для чисел иначе перекрашивало `0` в `,0` —
    # канал терял половину себя и переставал читаться одним словом.
    tail = code.lstrip(" \t{")
    if tail:
        off = len(code) - len(tail)
        mm = _MNEM_RE.match(tail)
        if mm:
            mn = mm.group("mn").lower()
            if mn in META:
                name = "meta"
            else:
                cls = asm_parser.MNEMONICS.get(mn)
                name = f"op.{cls}" if cls else "unknown"
            out.append((off + mm.start("mn"), off + mm.end("mn"), name))
            if mm.group("ch"):
                out.append((off + mm.start("ch"), off + mm.end("ch"), "channel"))
    return out


def _asm_theme() -> TextAreaTheme:
    """Тема редактора из палитры проекта: `/theme` красит и код тоже.

    Операции подсвечены НЕ «ключевым словом», а своим классом: деление
    красное, умножение своё, загрузка своя — те же цвета, что в решётке
    расписания и в легенде. Смысл в том, чтобы `sdivs` в тексте и `sdivs` в
    клетке такта читались как одно и то же, а не как два разных объекта.
    """
    def st(role: str, **kw) -> RichStyle:
        return RichStyle(color=palette.role_hex(role), **kw)

    styles = {
        "comment": st("faint", italic=True),
        "brace": st("border"),
        "meta": st("faint"),
        "label": st("title", bold=True),
        # Канал — самое важное слово в строке e2k: он и есть распределение
        # по портам, из-за которого расписание получается таким, какое есть.
        "channel": st("accent", bold=True),
        "reg": st("dim"),
        "num": st("accent2_soft"),
        "unknown": st("warning", underline=True),
    }
    for op in ("ADD", "SUB", "MUL", "DIV", "LOAD", "STORE", "SHL", "AND"):
        color = palette.op_hex(op)
        styles[f"op.{op}"] = RichStyle(color=color, bold=True)

    return TextAreaTheme(
        name="nex-asm",
        base_style=RichStyle(color=palette.role_hex("text")),
        gutter_style=RichStyle(color=palette.role_hex("faint")),
        cursor_style=RichStyle(color=palette.SURFACES["canvas"],
                               bgcolor=palette.role_hex("accent2")),
        cursor_line_gutter_style=RichStyle(color=palette.role_hex("accent2")),
        bracket_matching_style=RichStyle(bgcolor=palette.SURFACES["raised"],
                                         bold=True),
        selection_style=RichStyle(bgcolor=palette.SURFACES["raised"]),
        syntax_styles=styles,
    )


class AsmArea(TextArea):
    """Текст ассемблера с подсветкой и колонкой расписания слева.

    Колонка — не украшение и не номера строк: в ней стоит ТАКТ, в котором
    операция уйдёт на исполнение, и канал, в который она попадёт. Пока этого
    не было, единственный способ узнать, во что превратится набранное, —
    прогнать и читать отчёт в другой панели, переводя глазами «третья
    операция» в «третью строку с фигурной скобкой».
    """

    #: Ширина метки расписания: по самой длинной, `▲ т12→3`.
    MARK_W = 9
    #: Ширина номера строки. Вместе с меткой это и есть весь гуттер.
    NUM_W = 4

    #: Номера строк рисуем САМИ, встроенные выключены. Иначе TextArea
    #: прижимает номер к правому краю гуттера, а гуттер у нас расширен под
    #: расписание — между меткой и номером зияла бы пустая колонка в треть
    #: экрана. Свой гуттер ставит их рядом: `  5   т0 ,0 │ muls,0 …`.
    BADGE_W = MARK_W + NUM_W

    def __init__(self, **kw) -> None:
        kw.setdefault("soft_wrap", False)
        kw.setdefault("tab_behavior", "indent")
        kw.setdefault("show_line_numbers", False)
        super().__init__(**kw)
        # строка (0-based) → (метка, стиль)
        self._marks: dict[int, tuple[str, RichStyle]] = {}
        self.register_theme(_asm_theme())
        self.theme = "nex-asm"

    # --- подсветка --------------------------------------------------------

    def _build_highlight_map(self) -> None:
        """Своя разметка вместо tree-sitter. Зовётся на каждую правку."""
        self._line_cache.clear()
        highlights = self._highlights
        highlights.clear()
        for row, line in enumerate(self.document.lines):
            tokens = _line_tokens(line)
            if not tokens:
                continue
            # Карта красится по БАЙТОВЫМ смещениям (см. `_render_line`:
            # `build_byte_to_codepoint_dict`). В коде это одно и то же, но
            # первая же строка комментария по-русски съезжает вдвое, если
            # отдать символьные позиции как есть.
            prefix = [0] * (len(line) + 1)
            total = 0
            for i, ch in enumerate(line):
                prefix[i] = total
                total += len(ch.encode("utf-8"))
            prefix[len(line)] = total
            for start, end, name in tokens:
                highlights[row].append((prefix[min(start, len(line))],
                                        prefix[min(end, len(line))], name))

    def refresh_theme(self) -> None:
        """Перечитать цвета после `/theme`."""
        self.register_theme(_asm_theme())
        self._set_theme("nex-asm")
        self._line_cache.clear()
        self.refresh()

    # --- колонка расписания -----------------------------------------------

    def set_marks(self, marks: dict[int, tuple[str, RichStyle]]) -> None:
        self._marks = marks
        self._line_cache.clear()
        self.refresh()

    @property
    def gutter_width(self) -> int:
        # Гуттер живёт внутри виджета и не уезжает при горизонтальной
        # прокрутке — поэтому расписание стоит именно здесь, а не отдельной
        # колонкой рядом, которую пришлось бы синхронизировать вручную.
        return self.BADGE_W

    def render_line(self, y: int) -> Strip:
        strip = super().render_line(y)
        row = self.scroll_offset.y + y
        if row >= self.document.line_count:
            return strip
        badge, style = self._marks.get(row, ("", None))
        if style is None:
            style = RichStyle(color=palette.role_hex("faint"))
        cursor = row == self.cursor_location[0]
        num_style = RichStyle(color=palette.role_hex(
            "accent2" if cursor else "faint"), bold=cursor)
        head = Strip([
            Segment(f"{row + 1:>{self.NUM_W - 1}} ", num_style),
            Segment(f"{badge:>{self.MARK_W - 1}} " if badge
                    else " " * self.MARK_W, style),
        ], cell_length=self.BADGE_W)
        # Хвост берём у родителя: там уже посчитаны подсветка, курсор и
        # выделение — переписывать `_render_line` целиком значило бы держать
        # у себя копию двухсот строк чужого кода.
        return Strip.join([head, strip])

    # --- курсор -----------------------------------------------------------
    #
    # О переезде курсора экран узнаёт из штатного `TextArea.SelectionChanged`
    # — своего сообщения здесь нет нарочно. Первая версия перехватывала
    # `_on_key`, и это была ошибка: он объявлен `async`, а переопределение
    # было обычным, так что корутина родителя никогда не выполнялась — в
    # редакторе переставали печататься буквы. Штатное сообщение приходит и
    # на клавиши, и на мышь, и на программный переход по замечанию.

    def goto_line(self, line: int) -> None:
        """Курсор на строку (1-based) и прокрутка к ней."""
        row = max(0, min(line - 1, self.document.line_count - 1))
        self.move_cursor((row, 0))
        self.scroll_cursor_visible(center=True)


class LintItem(Static):
    """Строка замечания. Клик — курсор на ту самую строку исходника."""

    class Picked(Message):
        def __init__(self, line: int) -> None:
            super().__init__()
            self.line = line

    def __init__(self, line: int, *args, **kw) -> None:
        super().__init__(*args, **kw)
        self.line = line

    def on_click(self, event) -> None:
        event.stop()
        self.post_message(self.Picked(self.line))


# --------------------------------------------------------------------------
# Экран
# --------------------------------------------------------------------------


class CodeScreen(ModeScreen):
    mode = "code"
    mode_title = "КОД"
    mode_subtitle = "редактор"
    placeholder = ("F5 — прогнать буфер   ·   /code save my.s   ·   "
                   "/code load examples/probe.s")
    SIDE_ID = "#code-right"
    TIPS_ID = ""

    BINDINGS = ModeScreen.BINDINGS + [
        Binding("f5", "run_code", "прогнать", priority=True),
        ("ctrl+s", "save_code", "сохранить"),
        # F6 рядом с F5 нарочно: прогнать и переписать — два шага одного
        # движения. ^R сюда просится, но он уже занят повтором запуска в
        # развёрнутом ОТЧЁТЕ (ConsoleJournal), а приоритетный биндинг экрана
        # отобрал бы его у журнала молча.
        Binding("f6", "rewrite", "переписать по оракулу", priority=True),
    ]

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        # Живой разбор: считается на каждую правку, стоит микросекунды.
        self.parsed = None
        self.local_dag = None
        self.comp = None              # расписание из самого исходника
        self.problems: list = []
        # Дорогое: точный поиск и диагностика — только по F5.
        self.base = None
        self.orc = None
        self.met = None
        self.findings: list = []
        self.findings_from = "буфер"
        self.run_text = ""            # текст буфера на момент прогона
        self._grid_cells: dict[tuple[str, int, int], int] = {}
        self._lint_lines: list[int] = []
        self._code_expanded = False
        self._sched_expanded = False
        self._lint_expanded = False
        self._console_expanded = False
        self._debounce = None
        self.sched_view = "src"     # какое расписание в решётке
        self._cursor_line = 0

    # --- раскладка --------------------------------------------------------

    def compose_body(self):
        with Horizontal(id="code-body"):
            yield Panel(
                PanelToolbar(
                    ("▶ прогнать", "/code run", "разобрать буфер и найти "
                     "лучшее расписание (F5)"),
                    ("переписать по оракулу", "code-rewrite",
                     "переставить операции так, как их кладёт точный "
                     "поиск (F6)"),
                    ("сохранить", "code-save", "записать буфер в файл (^S)"),
                    ("пример с ошибками", "code-broken",
                     "заменить буфер примером, на котором видно линтер"),
                    ("расписание ▶", "open-sched", "развернуть РАСПИСАНИЕ"),
                ),
                Horizontal(
                    AsmArea(id="code-edit"),
                    VerticalScroll(Static(id="code-line-info"), id="code-side"),
                    id="code-main"),
                Static(id="code-status"),
                title="ИСХОДНИК", id="p-code", topic="code",
                has_own_input=True)
            with Vertical(id="code-right"):
                yield Panel(
                    PanelToolbar(
                        ("к коду", "sched-to-code",
                         "курсор на строку операции из клетки под курсором"),
                        ("▶ прогнать", "/code run", "пересчитать буфер (F5)"),
                        ("переписать по оракулу", "code-rewrite",
                         "разложить операции так, как их кладёт поиск (F6)"),
                    ),
                    # Переключатель видов живёт НАД решёткой, а не в полосе
                    # инструментов: полоса показывается только в развороте, а
                    # сравнить «как написано» с «как надо» хочется в обычном
                    # виде — за этим сюда и приходят.
                    Horizontal(
                        Tool("как написано", "sched-src",
                             "расписание из самого буфера", id="tab-src"),
                        Tool("оракул", "sched-orc",
                             "расписание точного поиска (F5)", id="tab-orc"),
                        Static(id="sched-head"),
                        id="sched-tabs"),
                    Horizontal(
                        # cell_padding=0: шесть каналов и так впритык к
                        # ширине колонки, а по умолчанию DataTable добавляет
                        # по два пробела на клетку — канал ,5 уезжал за край.
                        Vertical(DataTable(id="code-grid", cursor_type="cell",
                                           zebra_stripes=False,
                                           cell_padding=0),
                                 id="code-grid-wrap"),
                        Vertical(Static(id="code-grid-orc-head"),
                                 DataTable(id="code-grid-orc",
                                           cursor_type="cell",
                                           zebra_stripes=False,
                                           cell_padding=0),
                                 id="code-grid-orc-wrap"),
                        # Разбор рядом с решётками, а не «решётка крупнее»:
                        # загрузка портов и список перестановок отвечают на
                        # вопрос, ради которого сюда и разворачивают, — за
                        # счёт чего поиск выигрывает эти такты.
                        VerticalScroll(Static(id="sched-side-body"),
                                       id="sched-side"),
                        id="code-grids"),
                    title="РАСПИСАНИЕ", id="p-code-sched", topic="sched")
                yield Panel(
                    PanelToolbar(
                        ("▶ прогнать", "/code run",
                         "пересчитать: замечания линтера видны и без прогона, "
                         "потери тактов — только после"),
                        ("к коду", "lint-first", "курсор на первое замечание"),
                    ),
                    VerticalScroll(id="lint-scroll"),
                    title="ЧТО НЕ ТАК", id="p-code-lint", topic="lint")
                yield Panel(Console(id="console"),
                            ConsoleJournal(id="journal"),
                            title="ОТЧЁТ", id="p-code-out", topic="console",
                            has_own_input=True)

    def on_ready(self) -> None:
        edit = self.query_one("#code-edit", AsmArea)
        if not self.app.session.code_text:
            self.app.session.code_text = SEED
        edit.text = self.app.session.code_text
        self._seed_console()
        self.reparse()
        edit.focus()

    def _seed_console(self) -> None:
        con = self.console
        if con is None:
            return
        dim = palette.role_hex("dim")
        accent = palette.role_hex("accent2")
        con.write(Text("что делает F5", style=dim))
        for cmd, note in (
            ("разбор", "строки .s → граф по регистрам"),
            ("расписание", "как ляжет написанное"),
            ("точный поиск", "во сколько тактов это влезает"),
            ("диагноз", "где теряются такты"),
        ):
            row = Text()
            row.append("  " + cmd.ljust(14), style=accent)
            row.append(note, style=dim)
            con.write(row)

    # --- буфер ------------------------------------------------------------

    def _sync_buffer(self) -> None:
        """Текст редактора → сессия. Зовётся перед прогоном и при уходе."""
        self.app.session.code_text = self.query_one("#code-edit", AsmArea).text

    def context_bits(self) -> str:
        s = self.app.session
        bits = [s.model().name]
        if self.parsed is not None and self.parsed.ops:
            n = len(self.parsed.ops)
            bits.append(f"{n} {plural(n, 'операция', 'операции', 'операций')}")
            if self.comp is not None:
                bits.append(f"исходник {self.comp.makespan} т.")
            if self.orc is not None and not self._stale():
                bits.append(f"поиск {self.orc.schedule.makespan} т.")
        else:
            bits.append("буфер пуст")
        errs = sum(1 for p in self.problems if p.severity == "error")
        if errs:
            bits.append(f"{errs} {plural(errs, 'ошибка', 'ошибки', 'ошибок')}")
        return "   ·   ".join(bits)

    def hint_pairs(self) -> list[tuple[str, str]]:
        pairs = [("F5", "прогнать")]
        # F6 появляется только когда ему есть что делать: пока точного поиска
        # нет, «переписать по оракулу» — обещание без покрытия.
        if self._have_orc():
            pairs.append(("F6", "переписать по оракулу"))
        pairs += [("^S", "сохранить"), ("Esc", "к вводу")]
        return pairs

    def extra_commands(self) -> list[dict]:
        return [
            {"name": "rewrite", "arg": "",
             "help": "переписать буфер по расписанию точного поиска (F6)",
             "local": True},
            {"name": "example", "arg": "[broken]",
             "help": "положить в буфер пример: рабочий или с ошибками",
             "local": True},
        ]

    # --- живой разбор -----------------------------------------------------

    def on_text_area_changed(self, event) -> None:
        """Правка буфера. Разбор откладываем на четверть секунды.

        Без задержки разбор шёл бы на каждый символ имени регистра — а он
        тянет за собой перерисовку решётки и списка замечаний. Четверть
        секунды — это пауза между словами, а не между нажатиями: набор
        остаётся плавным, а результат появляется раньше, чем человек
        переведёт взгляд.
        """
        event.stop()
        if self._debounce is not None:
            self._debounce.stop()
        self._debounce = self.set_timer(0.25, self.reparse)

    def on_text_area_selection_changed(self, event) -> None:
        """Курсор в коде переехал: обновить разбор строки и клетку решётки."""
        event.stop()
        line = event.selection.end[0] + 1
        if line == self._cursor_line:
            return
        self._cursor_line = line
        self._draw_line_info(line)
        self._sync_grid_cursor(line)

    def _stale(self) -> bool:
        """Числа точного поиска относятся к другому тексту?"""
        edit = self.query_one("#code-edit", AsmArea)
        return bool(self.run_text) and edit.text != self.run_text

    def reparse(self) -> None:
        """Разобрать буфер и обновить всё, что считается без точного поиска."""
        self._debounce = None
        edit = self.query_one("#code-edit", AsmArea)
        text = edit.text
        self.app.session.code_text = text
        model = self.app.session.model()
        try:
            parsed = asm_parser.parse_asm(text, source="<буфер>")
        except Exception:
            parsed = None
        self.parsed = parsed
        self.local_dag = None
        self.comp = None
        # Замечания разбора живут ОТДЕЛЬНО от наличия операций: буфер, где
        # ни одна строка не разобралась, — самый частый случай у новичка, и
        # молчать в нём хуже всего. Линтер по модели нужен только там, где
        # есть что проверять.
        self.problems = list(parsed.problems) if parsed is not None else []
        if parsed is not None and parsed.ops:
            self.local_dag = asm_parser.build_dag(parsed, key="asm:буфер",
                                                  title="буфер")
            self.comp = asm_parser.compiler_schedule(parsed, self.local_dag,
                                                     model)
            self.problems += asm_parser.lint(parsed, model)
        self.redraw()

    # --- прогон -----------------------------------------------------------

    def action_run_code(self) -> None:
        self._sync_buffer()
        if not self.app.session.code_text.strip():
            con = self.console
            if con is not None:
                con.note("  буфер пуст — писать нечего", "error")
            return
        self.run_core("/code run")

    def after_command(self) -> None:
        """Команда отработала: подобрать посчитанное ядром, если оно есть."""
        cached = self.app.session.peek()
        if cached is not None:
            self.base, self.orc, self.met = cached
            self.run_text = self.query_one("#code-edit", AsmArea).text
            self.findings = self._diagnose()
        # `/code load` мог заменить буфер целиком — покажем его в редакторе.
        edit = self.query_one("#code-edit", AsmArea)
        if self.app.session.code_text != edit.text:
            edit.text = self.app.session.code_text
        self.reparse()

    def _diagnose(self) -> list:
        """Диагноз того расписания, которое написано в буфере.

        Не baseline и не оракула: человек спрашивает «где теряет МОЙ код»,
        а `/doctor` по умолчанию разбирает жадный планировщик. Если
        раскладка по каналам не сходится с моделью (тогда `compiler_schedule`
        честно отдаёт None), разбираем baseline и говорим об этом в панели.
        """
        sched = self.app.session.compiler_sched
        self.findings_from = "буфер"
        if sched is None:
            # Раскладку из буфера ядро не приняло — разбираем жадное
            # расписание того же графа. Числа при этом относятся НЕ к
            # написанному тексту, и подпись у раздела обязана это сказать.
            sched = self.base.schedule if self.base is not None else None
            self.findings_from = "жадный планировщик"
        if sched is None or self.met is None:
            return []
        try:
            d = doctor.diagnose(self.app.session.dag_obj, self.app.session.model(),
                                sched, self.met)
        except Exception:
            return []
        return list(d.findings)

    # --- отрисовка --------------------------------------------------------

    def redraw(self) -> None:
        self._draw_marks()
        self._draw_status()
        self._draw_grids()
        self._draw_lint()
        self._draw_line_info(
            self.query_one("#code-edit", AsmArea).cursor_location[0] + 1)
        self.refresh_context()
        self.refresh_hints()

    def repaint(self) -> None:
        self.query_one("#code-edit", AsmArea).refresh_theme()
        super().repaint()

    def _op_at_line(self, line: int):
        if self.parsed is None:
            return None
        for o in self.parsed.ops:
            if o.line == line:
                return o
        return None

    def _orc_cycle(self, instr: int) -> int | None:
        """Такт операции по точному поиску — если он относится к ЭТОМУ тексту."""
        if self.orc is None or self._stale():
            return None
        p = self.orc.schedule.placements.get(instr)
        return None if p is None else p.cycle

    def _draw_marks(self) -> None:
        """Колонка расписания в гуттере редактора."""
        edit = self.query_one("#code-edit", AsmArea)
        marks: dict[int, tuple[str, RichStyle]] = {}
        bad = {p.line for p in self.problems if p.severity == "error"}
        warn = {p.line for p in self.problems if p.severity == "warn"}
        if self.parsed is not None:
            for o in self.parsed.ops:
                orc = self._orc_cycle(o.index)
                if orc is None:
                    label = f"т{o.cycle}"
                    if o.channel is not None:
                        label += f" ,{o.channel}"
                    role = "dim"
                elif orc < o.cycle:
                    label = f"т{o.cycle}→{orc}"
                    role = "success"
                elif orc > o.cycle:
                    # Поиск отодвинул операцию — значит, в буфере она стоит
                    # раньше, чем машина её примет. Знак «=» здесь соврал бы.
                    label = f"т{o.cycle}→{orc}"
                    role = "warning"
                else:
                    label = f"т{o.cycle} ="
                    role = "faint"
                if o.line in bad:
                    label = "▲ " + label
                    role = "error"
                elif o.line in warn:
                    label = "▲ " + label
                    role = "warning"
                style = RichStyle(color=palette.role_hex(role),
                                  bold=role in ("success", "error"))
                marks[o.line - 1] = (label[-(AsmArea.BADGE_W - 2):], style)
        for line in sorted(bad | warn):
            if line - 1 not in marks:
                role = "error" if line in bad else "warning"
                marks[line - 1] = ("▲", RichStyle(color=palette.role_hex(role),
                                                  bold=True))
        edit.set_marks(marks)

    def _draw_status(self) -> None:
        """Строка итога под редактором: чем этот код обходится."""
        line = Text()
        dim = palette.role_hex("dim")
        if self.parsed is None or not self.parsed.ops:
            if self.problems:
                bad = len(self.problems)
                line.append(f"  ни одной операции: {bad} "
                            f"{plural(bad, 'строка', 'строки', 'строк')} "
                            f"не разобрать — см. ЧТО НЕ ТАК",
                            style=palette.role_hex("warning"))
            else:
                line.append("  пусто — набери операции e2k или "
                            "/code load examples/probe.s", style=dim)
            self.query_one("#code-status", Static).update(line)
            return
        n = len(self.parsed.ops)
        line.append(f"  {n} оп.   ·   {self.parsed.bundles} "
                    f"{plural(self.parsed.bundles, 'команда', 'команды', 'команд')}",
                    style=dim)
        errs = sum(1 for p in self.problems if p.severity == "error")
        if errs:
            line.append(f"   ·   ▲ {errs} "
                        f"{plural(errs, 'ошибка', 'ошибки', 'ошибок')}",
                        style=palette.role_hex("error"))
        if self.comp is not None:
            line.append(f"   ·   исходник {self.comp.makespan} т.",
                        style=palette.role_hex("text"))
            slots = self.comp.slot_utilization
            line.append(f"  (слоты {slots * 100:.0f}%)", style=dim)
        else:
            line.append("   ·   буфер не сходится с моделью",
                        style=palette.role_hex("warning"))
        if self.orc is not None and not self._stale():
            orc = self.orc.schedule.makespan
            line.append(f"   →   поиск {orc} т.", style=palette.role_hex("accent"))
            src = self.comp.makespan if self.comp is not None else None
            if src is not None and src > orc:
                gap = src - orc
                line.append(f"   ·   резерв {gap} т. ({100 * gap / src:.0f}%)",
                            style=palette.role_hex("success"))
            elif src is not None:
                line.append("   ·   резерва нет", style=dim)
        elif self._stale():
            line.append("   ·   ", style=dim)
            line.append("буфер правили — F5", style=palette.role_hex("warning"))
        else:
            line.append("   ·   ", style=dim)
            line.append("F5 — во сколько тактов это влезает",
                        style=palette.role_hex("accent2"))
        self.query_one("#code-status", Static).update(line)

    # --- решётка ----------------------------------------------------------

    def _cell_w(self) -> int:
        return 8 if self._sched_expanded else 6

    def _have_orc(self) -> bool:
        return self.orc is not None and not self._stale()

    def _draw_grids(self) -> None:
        """Решётка: один вид в обычной панели, оба — в развороте.

        В колонку шириной 48 две решётки по шесть каналов не влезают, а
        сравнивать надо: весь смысл режима в разнице между «как написано» и
        «как можно». Поэтому в обычном виде это ПЕРЕКЛЮЧАТЕЛЬ (одно и то же
        место, два состояния — глаз сравнивает по памяти положения клеток), а
        в развороте — две решётки рядом.
        """
        self._grid_cells = {}
        both = self._sched_expanded and self._have_orc()
        if self.sched_view == "orc" and not self._have_orc():
            self.sched_view = "src"
        # Расписание из буфера не восстановилось (каналы спорят с моделью), а
        # точный поиск есть: показываем его, а не пустой прямоугольник. Что
        # именно не сошлось — сказано в строке итога и в ЧТО НЕ ТАК.
        if self.comp is None and self._have_orc():
            self.sched_view = "orc"
            both = False
        left = (self.comp if (both or self.sched_view == "src")
                else self.orc.schedule)
        which = "src" if (both or self.sched_view == "src") else "orc"
        self._fill_grid("code-grid", left, which)

        for tool, name in (("#tab-src", "src"), ("#tab-orc", "orc")):
            self.query_one(tool, Tool).set_on(
                both or self.sched_view == name)

        head = self.query_one("#sched-head", Static)
        t = Text()
        if self.parsed is None or not self.parsed.ops:
            t.append("пусто ", style=palette.role_hex("faint"))
        elif left is None:
            t.append("не по модели ", style=palette.role_hex("warning"))
        elif which == "src":
            t.append(f"{left.makespan} т. ", style=palette.role_hex("text"))
            if self._have_orc():
                gap = left.makespan - self.orc.schedule.makespan
                if gap > 0:
                    t.append(f"  −{gap} ", style=palette.role_hex("success"))
        else:
            t.append(f"{left.makespan} т. ", style=palette.role_hex("accent"))
        head.update(t)
        self._draw_sched_side()

        wrap = self.query_one("#code-grid-orc-wrap")
        wrap.display = both
        if both:
            self.query_one("#code-grid-orc-head", Static).update(
                Text(f"  точный поиск   ·   {self.orc.schedule.makespan} т.",
                     style=palette.role_hex("accent")))
            self._fill_grid("code-grid-orc", self.orc.schedule, "orc")

    def _draw_sched_side(self) -> None:
        """Колонка разбора: за счёт чего поиск выигрывает эти такты."""
        try:
            target = self.query_one("#sched-side-body", Static)
        except Exception:
            return
        model = self.app.session.model()
        t = Text()
        dim = palette.role_hex("dim")
        if self.comp is None and not self._have_orc():
            target.update(Text("расписания пока нет — F5", style=dim))
            return

        t.append("ЗАГРУЗКА ПОРТОВ\n", style=palette.role_hex("title"))
        t.append("  канал" + "написано".rjust(10) + "поиск".rjust(9) + "\n",
                 style=palette.role_hex("faint"))
        for port in range(model.width):
            src = self._port_load(self.comp, port)
            orc = (self._port_load(self.orc.schedule, port)
                   if self._have_orc() else None)
            t.append(f"  {model.port_label(port):<5}", style=dim)
            t.append(f"{src:>10}",
                     style=palette.role_hex("text" if src else "faint"))
            if orc is not None:
                role = "success" if orc > src else ("dim" if orc == src
                                                    else "warning")
                t.append(f"{orc:>9}", style=palette.role_hex(role))
            t.append("\n")
        if self.comp is not None:
            t.append(f"\nслоты заняты на "
                     f"{self.comp.slot_utilization * 100:.0f}%", style=dim)
            if self._have_orc():
                t.append(f"  →  "
                         f"{self.orc.schedule.slot_utilization * 100:.0f}%",
                         style=palette.role_hex("success"))
            t.append("\n")

        moves = self._moves()
        if moves:
            t.append(f"\nЧТО ПЕРЕСТАВЛЕНО   {len(moves)}\n",
                     style=palette.role_hex("title"))
            for line, text in moves[:12]:
                t.append_text(text)
                t.append("\n")
            if len(moves) > 12:
                t.append(f"      ещё {len(moves) - 12}\n",
                         style=palette.role_hex("faint"))
            t.append("\nF6 разложит буфер именно так\n",
                     style=palette.role_hex("accent2"))
        elif self._have_orc():
            t.append("\nпереставлять нечего: буфер уже уложен так же, "
                     "как его кладёт точный поиск\n",
                     style=palette.role_hex("success"))
        else:
            t.append("\nF5 — и здесь появится, что переставить\n", style=dim)
        target.update(t)

    def _port_load(self, sched, port: int) -> int:
        """Сколько операций выдано в этот канал за всё расписание."""
        if sched is None:
            return 0
        return sum(1 for p in sched.placements.values() if p.channel == port)

    def _fill_grid(self, table_id: str, sched, which: str) -> None:
        table = self.query_one("#" + table_id, DataTable)
        table.clear(columns=True)
        if sched is None or self.parsed is None:
            return
        model = self.app.session.model()
        dag = sched.dag
        busy = sched.busy_map()
        used = {p.channel for p in sched.placements.values()}
        cw = self._cell_w()
        for p in range(model.width):
            idle = p not in used
            label = Text(model.port_label(p),
                         style=palette.role_hex("faint" if idle else "dim"))
            table.add_column(label, width=4 if idle else cw, key=str(p))

        # Красная клетка значит «так написано и так нельзя». В решётке
        # точного поиска раскладка законна по построению — красить там
        # нечего, иначе метка обвиняет поиск в чужой ошибке.
        bad = ({p.op for p in self.problems
                if p.severity == "error" and p.op >= 0}
               if which == "src" else set())
        span = max(sched.span_cycles, 1)
        for cycle in range(span):
            cells = []
            issued = 0
            for port in range(model.width):
                slot = busy.get((cycle, port))
                if slot is None:
                    cells.append(Text(f" {EMPTY}",
                                      style=palette.role_hex("faint")))
                    continue
                instr, head = slot
                self._grid_cells[(which, cycle, port)] = instr
                style = palette.op_style(dag[instr].op)
                if not head:
                    cells.append(Text(f" {CONT}", style=style))
                    continue
                issued += 1
                cells.append(self._cell_text(instr, cw, instr in bad))
            table.add_row(*cells, label=self._row_label(cycle, issued,
                                                        model.width))

    def _cell_text(self, instr: int, width: int, bad: bool) -> Text:
        """Клетка — мнемоника из исходника, а не «i7»: код перед глазами."""
        op = None
        if self.parsed is not None and instr < len(self.parsed.ops):
            op = self.parsed.ops[instr]
        name = op.mnemonic if op is not None else f"i{instr}"
        style = palette.op_style(op.op if op is not None else "ADD")
        if bad:
            style = palette.role_hex("error") + " bold"
        t = Text(" ")
        t.append(name[:width - 1], style=style)
        return t

    def _row_label(self, cycle: int, issued: int, width: int) -> Text:
        """Номер такта и сколько слотов из шести занято именно в нём."""
        t = Text(f"т{cycle}".rjust(4), style=palette.role_hex("dim"))
        if self._sched_expanded:
            role = "success" if issued >= width - 1 else (
                "warning" if issued <= 1 else "dim")
            t.append(f" {issued}/{width}", style=palette.role_hex(role))
        return t

    def _sync_grid_cursor(self, line: int) -> None:
        """Курсор в коде → клетка в решётке. Связь в обе стороны."""
        op = self._op_at_line(line)
        if op is None:
            return
        for (which, cycle, port), instr in self._grid_cells.items():
            if which != "src" or instr != op.index:
                continue
            table = self.query_one("#code-grid", DataTable)
            if cycle < table.row_count and port < len(table.columns):
                table.move_cursor(row=cycle, column=port)
            return

    def on_data_table_cell_selected(self, event) -> None:
        """Клик по клетке — курсор на строку этой операции в исходнике."""
        event.stop()
        which = "orc" if event.data_table.id == "code-grid-orc" else "src"
        instr = self._grid_cells.get((which, event.coordinate.row,
                                      event.coordinate.column))
        if instr is None or self.parsed is None or instr >= len(self.parsed.ops):
            return
        self._goto_line(self.parsed.ops[instr].line)

    # --- замечания --------------------------------------------------------

    def _draw_lint(self) -> None:
        """ЧТО НЕ ТАК: сперва замечания линтера, потом потери тактов.

        Порядок не случаен: замечание — это «машина так не умеет» и читается
        как ошибка, находка — «машина умеет, но код её не занял» и читается
        как резерв. Смешивать их в один список значит уравнять «код считает
        не то» и «код считает медленно».
        """
        scroll = self.query_one("#lint-scroll", VerticalScroll)
        scroll.remove_children()
        self._lint_lines = []
        limit = None if self._lint_expanded else 4

        errs = [p for p in self.problems if p.severity == "error"]
        warns = [p for p in self.problems if p.severity == "warn"]
        infos = [p for p in self.problems if p.severity == "info"]
        shown = (errs + warns + infos)[:limit]

        widgets: list = []
        if shown:
            widgets.append(Static(self._section(
                "по машине", f"{len(errs)} ошибок · {len(warns)} предупр."
                if (errs or warns) else "", first=True)))
            for p in shown:
                widgets.append(LintItem(p.line, self._lint_text(p),
                                        classes="lint-item"))
                self._lint_lines.append(p.line)
        elif self.parsed is not None and self.parsed.ops:
            widgets.append(Static(Text("  по машине замечаний нет",
                                       style=palette.role_hex("success"))))

        if self.findings and not self._stale():
            widgets.append(Static(self._section(
                "потери тактов",
                "по расписанию из буфера" if self.findings_from == "буфер"
                else "буфер не сошёлся с моделью — разобран жадный")))
            for f in (self.findings if self._lint_expanded
                      else self.findings[:3]):
                line = self._finding_line(f)
                widgets.append(LintItem(line, self._finding_text(f),
                                        classes="lint-item"))
                self._lint_lines.append(line)
        elif self.orc is None:
            widgets.append(Static(Text("\n  F5 — и здесь появится, где именно "
                                       "теряются такты",
                                       style=palette.role_hex("dim"))))

        # Что переставить — не диагноз, а готовое действие: конкретная строка
        # и конкретный такт, куда она уезжает. Диагноз объясняет ПОЧЕМУ
        # длинно; этот список отвечает ЧТО СДЕЛАТЬ, а F6 делает это сам.
        moves = self._moves()
        if moves:
            widgets.append(Static(self._section(
                "что переставить", "F6 сделает это сам")))
            for line, text in (moves if self._lint_expanded else moves[:4]):
                widgets.append(LintItem(line, text, classes="lint-item"))
                self._lint_lines.append(line)
            if not self._lint_expanded and len(moves) > 4:
                widgets.append(Static(Text(
                    f"      ещё {len(moves) - 4} операций",
                    style=palette.role_hex("faint"))))
        if not self._lint_expanded and len(self.problems) > 4:
            widgets.append(Static(Text(
                f"\n  ещё {len(self.problems) - 4} — 2×клик по панели",
                style=palette.role_hex("faint"))))
        if widgets:
            scroll.mount(*widgets)
        n = sum(1 for p in self.problems if p.severity == "error")
        title = "ЧТО НЕ ТАК"
        if n:
            title += f"   ·   {n} {plural(n, 'ошибка', 'ошибки', 'ошибок')}"
        elif self.findings and not self._stale():
            k = len(self.findings)
            title += f"   ·   {k} {plural(k, 'находка', 'находки', 'находок')}"
        self.query_one("#p-code-lint", Panel).set_title(title)

    def _moves(self) -> list[tuple[int, Text]]:
        """Операции, которые точный поиск ставит раньше, — по выигрышу."""
        if not self._have_orc() or self.parsed is None:
            return []
        out = []
        for o in self.parsed.ops:
            pl = self.orc.schedule.placements.get(o.index)
            if pl is None or pl.cycle >= o.cycle:
                continue
            t = Text()
            t.append(f" ↑ ", style=palette.role_hex("success"))
            t.append(f"стр.{o.line}", style=palette.role_hex("accent2"))
            t.append(f"  {o.mnemonic}", style=palette.op_style(o.op))
            t.append(f"  т{o.cycle} → т{pl.cycle}",
                     style=palette.role_hex("text"))
            t.append(f", канал ,{pl.channel}", style=palette.role_hex("dim"))
            out.append((o.cycle - pl.cycle, o.line, t))
        out.sort(key=lambda x: (-x[0], x[1]))
        return [(line, t) for _, line, t in out]

    def _section(self, label: str, note: str = "", first: bool = False) -> Text:
        t = Text()
        if not first:
            t.append("\n")
        t.append("  " + label.upper(), style=palette.role_hex("title"))
        if note:
            t.append("   " + note, style=palette.role_hex("faint"))
        return t

    #: Метка серьёзности замечания: та же грамматика, что у находок доктора.
    MARKS = {"error": ("▲", "error"), "warn": ("▲", "warning"),
             "info": ("·", "dim")}

    def _lint_text(self, p) -> Text:
        mark, role = self.MARKS.get(p.severity, ("·", "dim"))
        t = Text()
        t.append(f" {mark} ", style=palette.role_hex(role))
        t.append(f"стр.{p.line}", style=palette.role_hex("accent2"))
        t.append("  " + p.text, style=palette.role_hex("text"))
        if p.hint and self._lint_expanded:
            t.append("\n      " + p.hint, style=palette.role_hex("dim"))
        return t

    def _finding_line(self, f) -> int:
        """Строка исходника, к которой относится находка доктора."""
        if not f.instrs or self.parsed is None:
            return 0
        instr = f.instrs[0]
        if instr < len(self.parsed.ops):
            return self.parsed.ops[instr].line
        return 0

    def _finding_text(self, f) -> Text:
        role = {"high": "error", "medium": "warning"}.get(f.severity, "dim")
        if f.kind == "limit":
            role = "accent"
        t = Text()
        t.append(f" {f.mark():>2} ", style=palette.role_hex(role))
        t.append(f.title, style=palette.role_hex("text"))
        if f.cycles_lost:
            t.append(f"  −{f.cycles_lost} т.", style=palette.role_hex(role))
        if self._lint_expanded:
            t.append("\n      " + f.why, style=palette.role_hex("dim"))
            t.append("\n      " + f.fix, style=palette.role_hex("faint"))
        return t

    def on_lint_item_picked(self, event) -> None:
        event.stop()
        if event.line:
            self._goto_line(event.line)

    def _goto_line(self, line: int) -> None:
        edit = self.query_one("#code-edit", AsmArea)
        if self.screen.maximized is not None and self.screen.maximized.id != "p-code":
            self.minimize()
            self.query_one("#p-code", Panel).post_message(Panel.Collapsed())
        edit.goto_line(line)
        edit.focus()

    # --- «эта строка» (колонка разворота ИСХОДНИКА) ------------------------

    def _draw_line_info(self, line: int) -> None:
        """Что известно про строку под курсором.

        Главный вопрос редактора — не «что я написал», это и так видно, а
        «почему оно встанет именно туда». Ответ собирается из измеренных
        чисел модели (латентность, каналы) и из графа (кто кормит эту
        операцию и из какой строки), а не из общих слов.
        """
        target = self.query_one("#code-line-info", Static)
        model = self.app.session.model()
        op = self._op_at_line(line)
        t = Text()
        t.append(f"СТРОКА {line}\n", style=palette.role_hex("title"))
        if op is None:
            t.append("\nздесь не операция — комментарий, скобка или "
                     "директива.\n", style=palette.role_hex("dim"))
            near = [p for p in self.problems if p.line == line]
            for p in near:
                t.append("\n▲ " + p.text + "\n", style=palette.role_hex("warning"))
            target.update(t)
            return

        t.append("\n" + op.text + "\n", style=palette.op_style(op.op))
        t.append(f"\nкласс      {op.op}\n", style=palette.role_hex("dim"))
        t.append(f"латентность {model.latency(op.op)} т."
                 f"   порт держит {model.occupancy(op.op)} т.\n",
                 style=palette.role_hex("dim"))
        ch = " ".join(model.port_label(p) for p in model.channels_for(op.op))
        t.append(f"каналы     {ch or '—'}\n", style=palette.role_hex("dim"))

        t.append(f"\nв буфере   такт {op.cycle}", style=palette.role_hex("text"))
        if op.channel is not None:
            t.append(f", канал ,{op.channel}", style=palette.role_hex("text"))
        orc = self._orc_cycle(op.index)
        if orc is not None:
            role = "success" if orc < op.cycle else "dim"
            t.append(f"\nточный поиск такт {orc}", style=palette.role_hex(role))
            if orc < op.cycle:
                t.append(f"   раньше на {op.cycle - orc} т.",
                         style=palette.role_hex("success"))
        elif self._stale():
            t.append("\nточный поиск устарел — F5",
                     style=palette.role_hex("warning"))

        # Кто кормит эту операцию: номер строки, а не номер инструкции.
        if self.local_dag is not None and op.index < len(self.local_dag):
            preds = self.local_dag[op.index].preds
            if preds:
                t.append("\n\nждёт результата\n", style=palette.role_hex("title"))
                for pid in preds:
                    src = self.parsed.ops[pid]
                    ready = src.cycle + model.latency(src.op)
                    role = "error" if ready > op.cycle else "dim"
                    t.append(f"  стр.{src.line}  {src.mnemonic}"
                             f"  → готов в такте {ready}\n",
                             style=palette.role_hex(role))
            else:
                t.append("\n\nоперанды готовы заранее — эта операция может "
                         "идти в первом такте\n", style=palette.role_hex("dim"))

        mine = [p for p in self.problems if p.line == line]
        if mine:
            t.append("\nзамечания\n", style=palette.role_hex("title"))
            for p in mine:
                mark, role = self.MARKS.get(p.severity, ("·", "dim"))
                t.append(f"  {mark} {p.text}\n", style=palette.role_hex(role))
                if p.hint:
                    t.append(f"    {p.hint}\n", style=palette.role_hex("faint"))
        target.update(t)

    # --- развороты --------------------------------------------------------

    def on_panel_expanded(self, event) -> None:
        event.stop()
        topic = getattr(event.panel, "topic", "")
        self._code_expanded = topic == "code"
        self._sched_expanded = topic == "sched"
        self._lint_expanded = topic == "lint"
        self._console_expanded = topic == "console"
        self._draw_journal()
        if topic == "code":
            self._draw_line_info(
                self.query_one("#code-edit", AsmArea).cursor_location[0] + 1)
            self.query_one("#code-edit", AsmArea).focus()
        elif topic in ("sched", "lint"):
            self._draw_grids()
            self._draw_lint()

    def on_panel_collapsed(self, event) -> None:
        event.stop()
        self._code_expanded = False
        self._sched_expanded = False
        self._lint_expanded = False
        self._console_expanded = False
        self._draw_journal()
        self._draw_grids()
        self._draw_lint()

    def _draw_journal(self) -> None:
        """Развёрнутый ОТЧЁТ — журнал-терминал, как в РАЗБОРЕ."""
        journal = self.query_one("#journal", ConsoleJournal)
        con = self.query_one("#console", Console)
        journal.display = self._console_expanded
        con.display = not self._console_expanded
        panel = self.query_one("#p-code-out", Panel)
        if not self._console_expanded:
            panel.set_title("ОТЧЁТ")
            return
        n = len(con.runs)
        panel.set_title(f"ОТЧЁТ   ·   журнал   ·   "
                        f"{n} {plural(n, 'запуск', 'запуска', 'запусков')}")
        # Каталог с командами САМОГО экрана: /rewrite и /example живут
        # только здесь, и если их нет в каталоге, узнать о них можно лишь
        # из подсказки внизу.
        journal.load(con.runs, self.mode,
                     list(self.app.commands) + self.extra_commands())

    # --- инструменты панелей ----------------------------------------------

    def panel_tool(self, tool: str) -> None:
        if tool == "code-save":
            self.action_save_code()
        elif tool == "code-rewrite":
            self.action_rewrite()
        elif tool == "code-broken":
            self._load_example(SEED_BROKEN)
        elif tool == "open-sched":
            self._open_panel("#p-code-sched", "sched")
        elif tool == "sched-src":
            self._sched_view("src")
        elif tool == "sched-orc":
            self._sched_view("orc")
        elif tool == "sched-to-code":
            self._cell_to_code()
        elif tool == "lint-first":
            if self._lint_lines:
                self._goto_line(next((l for l in self._lint_lines if l), 0))
        else:
            super().panel_tool(tool)

    def _load_example(self, text: str) -> None:
        edit = self.query_one("#code-edit", AsmArea)
        edit.text = text
        self.app.session.code_text = text
        self.orc = self.base = self.met = None
        self.findings = []
        self.run_text = ""
        self.reparse()
        edit.focus()
        con = self.console
        if con is not None:
            con.note("  буфер заменён примером — F5 покажет, что с ним не так",
                     "warning")

    # --- переписать по оракулу --------------------------------------------

    def action_rewrite(self) -> None:
        """F6: разложить операции буфера так, как их кладёт точный поиск.

        Это единственное место инструмента, которое ПИШЕТ код, и сделано оно
        нарочно после всего остального: пока человек не увидел, где теряет
        такты, готовый ответ ему нечего проверять. Зато увидев — он получает
        не совет «переставьте умножения», а сам текст, который остаётся
        сохранить: те же мнемоники и те же операнды, изменены только каналы
        и разбивка на широкие команды.

        Правка идёт через `replace`, а не через присваивание текста: так она
        попадает в историю редактора и отменяется по ^Z, как любая другая.
        """
        if not self._have_orc():
            con = self.console
            if con is not None:
                con.note("  сначала F5: без точного поиска переставлять "
                         "нечем", "warning")
            return
        text = self._rewrite_by_oracle()
        edit = self.query_one("#code-edit", AsmArea)
        edit.replace(text, (0, 0), edit.document.end)
        self.app.session.code_text = text
        src = self.comp.makespan if self.comp is not None else None
        self.reparse()
        con = self.console
        if con is not None:
            gain = f"{src} → {self.orc.schedule.makespan} т." if src else ""
            con.note(f"  буфер переписан по точному поиску   {gain}"
                     f"   ·   ^Z вернёт как было", "success")
        edit.focus()

    def _rewrite_by_oracle(self) -> str:
        """Текст .s по расписанию точного поиска — из операций буфера."""
        model = self.app.session.model()
        sched = self.orc.schedule
        src = self.comp.makespan if self.comp is not None else 0
        by_cycle: dict[int, list[tuple[int, int]]] = {}
        for pl in sched.placements.values():
            by_cycle.setdefault(pl.cycle, []).append((pl.channel, pl.instr))

        out = [f"! Переписано NEX по точному поиску: "
               f"{src} т.  →  {sched.makespan} т.",
               "! Мнемоники и операнды твои; изменены каналы и разбивка "
               "на { }."]
        prev = None
        for cycle in sorted(by_cycle):
            if prev is not None and cycle > prev + 1:
                out.append(f"  nop {cycle - prev - 1}")
            out.append("{")
            for channel, instr in sorted(by_cycle[cycle]):
                op = self.parsed.ops[instr]
                args = self._operands(op)
                out.append(f"  {op.mnemonic},{channel}"
                           + (f" {args}" if args else ""))
            out.append("}")
            prev = cycle
        return "\n".join(out) + "\n"

    def _operands(self, op) -> str:
        """Операнды строки как они были написаны — без мнемоники и канала."""
        text = op.text.strip()
        head = op.mnemonic + (f",{op.channel}" if op.channel is not None else "")
        if text.lower().startswith(head.lower()):
            return text[len(head):].strip()
        # Канал в исходнике мог отсутствовать: тогда отрезаем одну мнемонику.
        if text.lower().startswith(op.mnemonic):
            return text[len(op.mnemonic):].lstrip(" ,0123456789").strip()
        return text

    def _sched_view(self, which: str) -> None:
        """Переключить решётку между «как написано» и точным поиском."""
        if which == "orc" and not self._have_orc():
            con = self.console
            if con is not None:
                con.note("  точного поиска для этого текста ещё нет — F5",
                         "warning")
            return
        self.sched_view = which
        self._draw_grids()

    def _cell_to_code(self) -> None:
        table = self.query_one("#code-grid", DataTable)
        instr = self._grid_cells.get(("src", table.cursor_row,
                                      table.cursor_column))
        if instr is not None and self.parsed is not None:
            self._goto_line(self.parsed.ops[instr].line)

    def _open_panel(self, selector: str, topic: str) -> None:
        panel = self.query_one(selector, Panel)
        self.maximize(panel, container=False)
        panel.post_message(Panel.Expanded(panel))

    # --- факты для ИИ ------------------------------------------------------

    def panel_facts(self, topic: str) -> list[str]:
        if topic == "code":
            return self._code_facts()
        if topic == "sched":
            return self._sched_facts()
        if topic == "lint":
            return self._lint_facts()
        return []

    def _code_facts(self) -> list[str]:
        if self.parsed is None or not self.parsed.ops:
            return ["буфер пуст"]
        model = self.app.session.model()
        line = self.query_one("#code-edit", AsmArea).cursor_location[0] + 1
        out = [f"в буфере {len(self.parsed.ops)} операций, "
               f"{self.parsed.bundles} широких команд",
               f"расписание из буфера: "
               f"{self.comp.makespan if self.comp else '—'} тактов"]
        op = self._op_at_line(line)
        if op is not None:
            out.append(f"курсор на строке {line}: {op.text}")
            out.append(f"класс {op.op}, латентность {model.latency(op.op)} т., "
                       f"каналы " + " ".join(model.port_label(p)
                                             for p in model.channels_for(op.op)))
            out.append(f"в буфере она в такте {op.cycle}")
            orc = self._orc_cycle(op.index)
            if orc is not None:
                out.append(f"точный поиск ставит её в такт {orc}")
        return out

    def _sched_facts(self) -> list[str]:
        out = []
        if self.comp is not None:
            out.append(f"как написано — {self.comp.makespan} тактов, "
                       f"слоты заняты на "
                       f"{self.comp.slot_utilization * 100:.0f}%")
        if self.orc is not None and not self._stale():
            out.append(f"точный поиск — {self.orc.schedule.makespan} тактов")
        if self.met is not None:
            out.append(f"нижняя граница — {self.met.lower_bound} тактов")
        return out

    def _lint_facts(self) -> list[str]:
        out = [f"стр.{p.line}: {p.text}" for p in self.problems[:8]]
        out += [f"{f.title}: {f.why}" for f in self.findings[:4]]
        return out or ["замечаний нет"]

    def panel_chips(self, topic: str) -> list[str]:
        if topic == "code":
            return ["почему эта строка стоит в этом такте?",
                    "как переписать этот участок короче?"]
        if topic == "sched":
            return ["почему точный поиск успевает быстрее?",
                    "какой порт здесь узкое место?"]
        if topic == "lint":
            return ["как исправить первое замечание?",
                    "что здесь самое дорогое?"]
        return []

    # --- ввод -------------------------------------------------------------

    def handle_line(self, line: str) -> None:
        head, _, arg = line.strip().lstrip("/").partition(" ")
        head = head.lower()
        if head == "code" and not arg.strip():
            # голое /code в этом режиме означает «вернуться к редактору»
            self.query_one("#code-edit", AsmArea).focus()
            return
        if head == "rewrite":
            self.action_rewrite()
            return
        if head == "example":
            self._load_example(SEED_BROKEN if arg.strip().startswith("broken")
                               else SEED)
            return
        super().handle_line(line)

    def action_back(self) -> None:
        """Esc: из редактора — к строке ввода, дальше — как у всех."""
        edit = self.query_one("#code-edit", AsmArea)
        if edit.has_focus:
            self._sync_buffer()
            self.query_one("#prompt", PromptBar).focus_input()
            return
        super().action_back()

    def action_ai_or_complete(self) -> None:
        """Tab: в редакторе — отступ, вне его — как у всех."""
        edit = self.query_one("#code-edit", AsmArea)
        if edit.has_focus and self.maximized is None:
            edit.insert("\t")
            return
        super().action_ai_or_complete()

    def action_save_code(self) -> None:
        """Ctrl+S: сохранить под последним именем или спросить строку ввода."""
        self._sync_buffer()
        last = getattr(self.app.session, "code_path", "")
        if last:
            self.handle_line(f"/code save {last}")
        else:
            bar = self.query_one("#prompt", PromptBar)
            bar.focus_input()
            bar.set_value("/code save ")
