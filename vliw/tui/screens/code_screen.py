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
from ..widgets import (BridgeRow, Console, ConsoleJournal, HintBar, Panel,
                       PanelToolbar, PromptBar, Tool, TopBar, plural)
from .base import ModeScreen

#: Каталог примеров. Файлы лежат в `examples/code/*.s` и загружаются по
#: имени: `/example loads`. Держать их файлами, а не строками в коде, —
#: осознанно: тот же пример открывается снаружи (`/code load`), правится в
#: любом редакторе и проверяется тестом, который сверяет заявленные в шапке
#: числа с тем, что инструмент считает на самом деле.
EXAMPLES = [
    ("slots", "слоты простаивают",
     "восемь умножений по одному в такт вместо четырёх в один"),
    ("divport", "монополия делителя",
     "пока занят единственный ,5, пять каналов стоят пустыми"),
    ("loads", "загрузки в один канал",
     "четыре независимых ldw выстроены в очередь на ровном месте"),
    ("latency", "предел цепочки",
     "резерва нет — и это правильный ответ, а не молчание"),
    ("broken", "ошибки, которых не видит ассемблер",
     "канал, занятый порт и чтение раньше готовности"),
]

#: Запасной буфер: если каталога примеров рядом нет (пакет поставили без
#: `examples/`), редактор обязан открыться, а не упасть в пустоту.
FALLBACK = """\
! Ассемблер e2k: { } — одна широкая команда, ,N — канал.
! Правь и жми F5.
{
  muls,0 %r10, %r11, %r20
  adds,1 %r12, %r13, %r21
}
"""


def examples_dir():
    from pathlib import Path

    return Path(__file__).resolve().parents[3] / "examples" / "code"


def example_text(name: str) -> str | None:
    """Текст примера по имени или None, если файла нет."""
    try:
        return (examples_dir() / f"{name}.s").read_text(encoding="utf-8")
    except OSError:
        return None


def example_title(name: str) -> str:
    for key, title, _ in EXAMPLES:
        if key == name:
            return title
    return name


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

    #: Номера строк рисуем САМИ, встроенные выключены. Иначе TextArea
    #: прижимает номер к правому краю гуттера, а гуттер у нас расширен под
    #: расписание — между меткой и номером зияла бы пустая колонка в треть
    #: экрана. Свой гуттер ставит их рядом: `  5  т0 │ muls,0 …`.
    #:
    #: Ширина гуттера СЧИТАЕТСЯ по содержимому, а не задана числом. Пока
    #: она была постоянной (13 колонок под самую длинную метку `▲ т12→13`),
    #: буфер без прогона отдавал те же 13 колонок под метки вида `т7` — и на
    #: окне в 124 знака у кода оставалось 59, комментарии обрезались на
    #: середине. Считаем по факту: 3 колонки на номер + самая длинная метка.
    MIN_MARK_W = 3
    MAX_MARK_W = 10

    #: Пустая разметка на уровне класса, а не только в `__init__`: ширину
    #: гуттера спрашивает уже `TextArea.__init__` (через `gutter_width`), то
    #: есть ДО того, как экземпляр успел завести свою.
    _marks: dict[int, tuple[str, RichStyle]] = {}

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

    @property
    def NUM_W(self) -> int:
        return len(str(max(1, self.document.line_count))) + 2

    @property
    def MARK_W(self) -> int:
        if not self._marks:
            return 0
        widest = max(len(text) for text, _ in self._marks.values())
        return min(self.MAX_MARK_W, max(self.MIN_MARK_W, widest + 1))

    @property
    def BADGE_W(self) -> int:
        return self.NUM_W + self.MARK_W

    def set_marks(self, marks: dict[int, tuple[str, RichStyle]]) -> None:
        self._marks = marks
        self._line_cache.clear()
        # layout=True: ширина гуттера зависит от самой длинной метки, а от
        # неё — сколько знаков остаётся коду. Без пересчёта раскладки строка
        # уезжала бы под правую границу панели.
        self.refresh(layout=True)

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
        mark_w = self.MARK_W
        head = Strip([
            Segment(f"{row + 1:>{self.NUM_W - 1}} ", num_style),
            Segment((f"{badge:>{mark_w - 1}} " if badge else " " * mark_w)
                    if mark_w else "", style),
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


class SuggestItem(Static):
    """Один вариант в подсказке."""

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


class Suggest(Vertical):
    """Подсказка при наборе — та, которой у редактора ассемблера не бывает.

    Обычное дополнение знает слова. Это знает МАШИНУ: после `muls,`
    предлагаются только каналы, на которых умножение вообще исполнимо
    (`,0 ,1 ,3 ,4` — проверено ассемблером), причём занятые в этой же
    широкой команде помечены. После `%` предлагаются регистры, уже
    записанные выше по буферу, и у каждого написано, в каком такте он будет
    готов, — то есть ошибку «читаю раньше, чем посчитано» видно ДО того, как
    она набрана, а не после прогона.
    """

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self.items: list[tuple[str, str, str, str]] = []
        self.index = 0

    def show(self, items: list[tuple[str, str, str, str]]) -> None:
        """items: (что вставить, метка, пояснение, роль цвета)."""
        self.items = items[:8]
        self.index = 0
        self.remove_children()
        if not self.items:
            self.display = False
            return
        rows = []
        for i, (_ins, label, note, role) in enumerate(self.items):
            rows.append(SuggestItem(i, self._row(label, note, role),
                                    classes="suggest-item"))
        self.mount(*rows)
        self.display = True
        self.call_after_refresh(self._mark)

    def _row(self, label: str, note: str, role: str) -> Text:
        t = Text()
        t.append(" " + label.ljust(10), style=palette.role_hex(role) + " bold")
        t.append(note, style=palette.role_hex("dim"))
        return t

    def _mark(self) -> None:
        for i, row in enumerate(self.query(SuggestItem)):
            row.set_class(i == self.index, "suggest-on")

    def step(self, delta: int) -> None:
        if not self.items:
            return
        self.index = (self.index + delta) % len(self.items)
        self._mark()

    def current(self) -> str:
        return self.items[self.index][0] if self.items else ""

    def hide(self) -> None:
        self.display = False
        self.items = []


class LineChip(Static):
    """Строка курсора в полосе состояния. Клик раскрывает разбор.

    Прогрессивное раскрытие вместо постоянной колонки: обычно человеку
    хватает «стр.17 · MUL · латентность 4», а полный разбор (кто кормит
    операцию, что с ней сделает точный поиск, замечания на ней) нужен
    изредка — и тогда он приходит целым блоком, а не тремя строками в углу.
    """

    class Picked(Message):
        pass

    def on_click(self, event) -> None:
        event.stop()
        self.post_message(self.Picked())


class DrawerChip(Static):
    """Пункт полосы состояния, открывающий вкладку нижней панели.

    Как строка состояния в IDE: «ошибки» и «терминал» — не надписи, а
    кнопки. Панель снизу и так открывается F12, но клавиатура не объясняет,
    ЧТО внутри; пункт статуса показывает состояние прямо на месте (сколько
    ошибок, сколько команд) и открывает нужную вкладку одним кликом.
    """

    class Picked(Message):
        def __init__(self, target: str) -> None:
            super().__init__()
            self.target = target

    def __init__(self, target: str, label: str = "", tip: str = "",
                 **kw) -> None:
        super().__init__(label, **kw)
        self.target = target
        self._label = label
        if tip:
            self.tooltip = tip

    def set_label(self, label: str) -> None:
        self._label = label
        self.update(label)

    def on_click(self, event) -> None:
        event.stop()
        self.post_message(self.Picked(self.target))


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
    placeholder = ("команда со слэша: /doctor   ·   /code save my.s   ·   "
                   "/example   ·   ↑ история")
    SIDE_ID = ""        # боковой колонки нет: рабочая область одна
    TIPS_ID = ""

    BINDINGS = ModeScreen.BINDINGS + [
        Binding("f5", "run_code", "прогнать", priority=True),
        ("ctrl+s", "save_code", "сохранить"),
        # F6 рядом с F5 нарочно: прогнать и переписать — два шага одного
        # движения. ^R сюда просится, но он уже занят повтором запуска в
        # развёрнутом ОТЧЁТЕ (ConsoleJournal), а приоритетный биндинг экрана
        # отобрал бы его у журнала молча.
        Binding("f6", "rewrite", "переписать по оракулу", priority=True),
        # F12 — как ^` в IDE: показать/убрать нижнюю панель.
        Binding("f12", "toggle_drawer", "панель снизу", priority=True),
        # ^P — открыть панель на ОТЧЁТЕ и начать команду. Не «/» и не «:»:
        # оба знака печатные и в ассемблере встречаются (`//` в комментарии,
        # двоеточие в метке `main:`), отбирать их у текста нельзя. Поэтому
        # набор команды начинается с клавиши, которой в тексте не бывает.
        Binding("ctrl+p", "command", "команда", priority=True),
        # А «/» остаётся быстрым входом там, где фокус НЕ в тексте — в
        # решётке расписания или в списке замечаний.
        Binding("slash", "slash", "команда", priority=True),
        # Пока открыта подсказка, стрелки и Enter принадлежат ей. Биндинги
        # включаются `check_action` только в этот момент, поэтому в обычном
        # наборе клавиши достаются редактору нетронутыми. Переопределять
        # `_on_key` у TextArea нельзя — см. предупреждение выше по файлу.
        Binding("up", "suggest_up", "выше", priority=True),
        Binding("down", "suggest_down", "ниже", priority=True),
        Binding("enter", "suggest_take", "вставить", priority=True),
    ]

    #: Действия, живые только при открытой подсказке.
    SUGGEST_ACTIONS = ("suggest_up", "suggest_down", "suggest_take")

    #: Что остаётся видимым, когда блок развёрнут. Textual по умолчанию
    #: прячет ВСЕХ прямых детей экрана, кроме развёрнутого, — и разворот
    #: редактора убирал заодно расписание, полосу состояния и нижнюю панель.
    #: Работать становилось хуже, а не лучше. Здесь разворот значит «отдай
    #: коду всю ширину», всё остальное остаётся на местах.
    ALLOW_IN_MAXIMIZED_VIEW = ("PanelChat, PanelPrompt, PromptBar, HintBar, "
                               "Footer, TopBar, #p-code-sched, "
                               "#code-status-row, #p-drawer")

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
        self._example = ""          # какой пример сейчас в буфере
        # Выдвижная панель снизу: закрыта по умолчанию, вкладки внутри.
        self.drawer_open = False
        self.drawer_tab = "lint"    # lint | term | line
        # Мягкий разворот: "" | code | sched | drawer. Не прячет соседей —
        # отдаёт блоку больше места и ДОБАВЛЯЕТ ему колонки, которых в
        # обычном виде нет.
        self.zoom = ""

    # --- раскладка --------------------------------------------------------
    #
    # Каркас режима собран здесь целиком, а не взят у `ModeScreen`: строки
    # ввода в доке снизу больше нет. Она переехала внутрь выдвижной панели
    # (вкладка ОТЧЁТ) и как отдельная сущность исчезла — в редакторе она
    # была нужна раз в сотню нажатий, а ряд занимала всегда.
    #
    # Экран получился как в IDE: рабочая область во всю ширину, снизу одна
    # строка состояния, и по клавише выезжает панель с вкладками
    # ЗАМЕЧАНИЯ / ОТЧЁТ / СТРОКА. Любой блок разворачивается на весь экран
    # со своим полным набором инструментов — основной вид показывает только
    # то, что нужно сейчас, глубина приходит по требованию.

    def compose(self):
        yield TopBar(self.mode, self.mode_title, self.mode_subtitle,
                     id="topbar")
        with Horizontal(id="code-body"):
            yield Panel(
                PanelToolbar(
                    ("▶ прогнать", "/code run", "разобрать буфер и найти "
                     "лучшее расписание (F5)"),
                    ("переписать по оракулу", "code-rewrite",
                     "переставить операции так, как их кладёт точный "
                     "поиск (F6)"),
                    ("сохранить", "code-save", "записать буфер в файл (^S)"),
                    ("расписание ▶", "open-sched", "развернуть РАСПИСАНИЕ"),
                ),
                Horizontal(
                    AsmArea(id="code-edit"),
                    # Одна колонка разворота, две секции: что это за строка
                    # и её цепочка. Двумя колонками они отбирали у кода
                    # больше места, чем сами стоят.
                    VerticalScroll(Static(id="code-line-body"),
                                   Static(id="code-chain-body"),
                                   id="code-zoom-col"),
                    id="code-main"),
                title="ИСХОДНИК", id="p-code", topic="code",
                has_own_input=True, soft=True)   # заголовок дополняется в _draw_title
            yield Panel(
                PanelToolbar(
                    ("к коду", "sched-to-code",
                     "курсор на строку операции из клетки под курсором"),
                    ("▶ прогнать", "/code run", "пересчитать буфер (F5)"),
                    ("переписать по оракулу", "code-rewrite",
                     "разложить операции так, как их кладёт поиск (F6)"),
                ),
                Horizontal(
                    Tool("как написано", "sched-src",
                         "расписание из самого буфера", id="tab-src"),
                    Tool("оракул", "sched-orc",
                         "расписание точного поиска (F5)", id="tab-orc"),
                    Static(id="sched-head"),
                    id="sched-tabs"),
                Horizontal(
                    # cell_padding=0: шесть каналов и так впритык к ширине
                    # колонки, а по умолчанию DataTable добавляет по два
                    # пробела на клетку — канал ,5 уезжал за край.
                    Vertical(DataTable(id="code-grid", cursor_type="cell",
                                       zebra_stripes=False, cell_padding=0),
                             id="code-grid-wrap"),
                    Vertical(Static(id="code-grid-orc-head"),
                             DataTable(id="code-grid-orc", cursor_type="cell",
                                       zebra_stripes=False, cell_padding=0),
                             id="code-grid-orc-wrap"),
                    VerticalScroll(Static(id="sched-side-body"),
                                   id="sched-side"),
                    id="code-grids"),
                title="РАСПИСАНИЕ", id="p-code-sched", topic="sched",
                soft=True)

        # Строка состояния: слева курсор (кликом раскрывается), справа итог
        # по буферу, и два пункта-лаунчера нижней панели — замечания с живым
        # счётчиком ошибок и отчёт со счётчиком команд. Панель снизу
        # открывается любым из них одним кликом, как строка состояния в IDE.
        with Horizontal(id="code-status-row"):
            yield LineChip(id="code-line-chip")
            yield Static(id="code-status")
            yield DrawerChip(
                "lint", "▲ 0",
                "замечания машины: клик открывает панель снизу",
                id="status-lint")
            yield DrawerChip(
                "term", "git 0",
                "git сессии — история прогонов и мостик между режимами: "
                "клик открывает панель снизу",
                id="status-term")

        yield Panel(
            Horizontal(
                Tool("замечания", "drawer-lint",
                     "что не так по машине и где теряются такты",
                     id="tab-lint"),
                Tool("git", "drawer-term",
                     "история сессии и мостик: прогон отсюда уезжает в "
                     "разбор, агенту, ядро или обратно в код",
                     id="tab-term"),
                Tool("такты", "drawer-line",
                     "все широкие команды: сколько слотов занято",
                     id="tab-line"),
                Static(id="drawer-head"),
                id="drawer-tabs"),
            VerticalScroll(id="lint-scroll"),
             Vertical(
                 # Мостик ПРЯМО во вкладке, без разворота: выбрал прогон в
                 # истории — отправил в другой режим двумя кликами.
                 BridgeRow(prefix="dbridge", id="drawer-bridge"),
                 Console(id="console",
                         runs=self.app.session.journal_runs),
                 ConsoleJournal(id="journal"),
                 PromptBar(self.mode, self.placeholder,
                           list(self.app.commands) + self.extra_commands(),
                           id="prompt"),
                 id="drawer-term-box"),
            Vertical(
                Static(id="code-line-info"),
                VerticalScroll(id="drawer-bundles"),
                id="drawer-line-box"),
            title="ЗАМЕЧАНИЯ", id="p-drawer", topic="lint",
            has_own_input=True, soft=True)

        yield Suggest(id="suggest")
        yield HintBar(id="hints")

    def on_ready(self) -> None:
        edit = self.query_one("#code-edit", AsmArea)
        if not self.app.session.code_text:
            self.app.session.code_text = example_text("slots") or FALLBACK
            self._example = "slots"
        edit.text = self.app.session.code_text
        # Подсказка у строки курсора: без неё кликабельность не видна ни
        # разу — а это вход в разбор строки и в ТАКТЫ.
        self.query_one("#code-line-chip", LineChip).tooltip = (
            "строка под курсором: такт, каналы, замечания\n"
            "клик — полный разбор (вкладка ТАКТЫ снизу)")
        self._seed_console()
        self._take_pending_note()
        self.reparse()
        edit.focus()

    def _take_pending_note(self) -> None:
        """Пометка от мостика журнала («в код») — строкой в отчёт.

        Буфер к этому моменту уже заменён, если у прогона был исходник;
        пометка говорит, ЧТО произошло и откуда — молчаливая подмена текста
        в редакторе выглядела бы как полтергейст.
        """
        note = getattr(self.app.session, "pending_note", "")
        if not note:
            return
        self.app.session.pending_note = ""
        con = self.console
        if con is not None:
            con.note("  " + note, "accent2")

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

    # --- подсказки при наборе ----------------------------------------------

    def check_action(self, action: str, parameters) -> bool:
        """Клавиши подсказки активны, только пока она на экране.

        Textual пропускает нажатие дальше, если `check_action` вернул False,
        — поэтому стрелки и Enter достаются редактору ровно тогда, когда
        подсказки нет, и ничего не приходится перехватывать вручную.
        """
        if action in self.SUGGEST_ACTIONS:
            sug = self.suggest
            return bool(sug is not None and sug.display)
        return True

    @property
    def suggest(self):
        try:
            return self.query_one("#suggest", Suggest)
        except Exception:
            return None

    def action_suggest_up(self) -> None:
        self.suggest.step(-1)

    def action_suggest_down(self) -> None:
        self.suggest.step(1)

    def action_suggest_take(self) -> None:
        self._accept_suggest()

    #: Что набирают в этой позиции строки.
    _MNEM_TAIL = re.compile(r"(?:^|[{\s])([a-z][a-z0-9_]*)$")
    _CHAN_TAIL = re.compile(r"\b([a-z][a-z0-9_]+),(\d*)$")
    _REG_TAIL = re.compile(r"%([a-z]*\d*)$")

    def _update_suggest(self) -> None:
        """Пересобрать подсказку под то, что набрано слева от курсора."""
        sug = self.query_one("#suggest", Suggest)
        edit = self.query_one("#code-edit", AsmArea)
        if not edit.has_focus:
            sug.hide()
            return
        row, col = edit.cursor_location
        line = edit.document.get_line(row)[:col]
        # В комментарии подсказывать нечего.
        if _COMMENT_RE.search(line):
            sug.hide()
            return

        items = self._suggest_items(line, row)
        if not items:
            sug.hide()
            return
        sug.show(items)
        # Ставим окно у курсора: подсказка должна быть там, где глаз. Если
        # снизу места нет — переворачиваем наверх, иначе у последних строк
        # файла она уезжала за край экрана и была бесполезна ровно там, где
        # обычно и дописывают код.
        try:
            x, y = edit.cursor_screen_offset
            height = min(len(sug.items), 8) + 2      # + рамка
            width = int(sug.styles.width.value or 52)
            below = y + 1
            if below + height > self.size.height - 1:
                below = max(0, y - height)
            sug.styles.offset = (max(0, min(x - 2, self.size.width - width)),
                                 below)
        except Exception:
            pass

    def _suggest_items(self, line: str, row: int):
        model = self.app.session.model()

        m = self._CHAN_TAIL.search(line)
        if m:
            return self._chan_items(m.group(1), m.group(2), row, model)
        m = self._REG_TAIL.search(line)
        if m:
            return self._reg_items(m.group(1), row, model)
        m = self._MNEM_TAIL.search(line)
        if m:
            return self._mnem_items(m.group(1), model)
        return []

    def _mnem_items(self, prefix: str, model):
        """Мнемоники e2k с латентностью и каналами прямо в подсказке."""
        out = []
        for mn in sorted(asm_parser.MNEMONICS):
            if not mn.startswith(prefix) or mn == prefix:
                continue
            cls = asm_parser.MNEMONICS[mn]
            chans = " ".join(model.port_label(p)
                             for p in model.channels_for(cls))
            out.append((mn[len(prefix):], mn,
                        f"{cls}  лат.{model.latency(cls)}  {chans}",
                        "text"))
        return out[:8]

    def _chan_items(self, mnemonic: str, typed: str, row: int, model):
        """Каналы — ТОЛЬКО те, на которых операция исполнима.

        Плюс контекст расписания: канал, уже занятый в этой же широкой
        команде, помечен. Обычный редактор предложил бы все шесть цифр и
        промолчал про то, что две из них аппаратно невозможны, а третья
        занята соседней строкой.
        """
        cls = asm_parser.MNEMONICS.get(mnemonic.lower())
        if cls is None:
            return []
        busy = self._busy_channels(row)
        out = []
        for port in model.channels_for(cls):
            label = str(port)
            if typed and not label.startswith(typed):
                continue
            if port in busy:
                note = f"занят: {busy[port]}"
                role = "warning"
            else:
                note = "свободен в этой команде"
                role = "success"
            out.append((label[len(typed):], f",{port}", note, role))
        return out

    def _busy_channels(self, row: int) -> dict[int, str]:
        """Какие каналы уже заняты в широкой команде вокруг строки row."""
        edit = self.query_one("#code-edit", AsmArea)
        lines = edit.document.lines
        start = row
        while start > 0 and "{" not in lines[start]:
            start -= 1
        busy: dict[int, str] = {}
        for i in range(start, min(len(lines), start + 12)):
            if i == row:
                continue
            if i > start and "}" in lines[i]:
                break
            m = _MNEM_RE.match(lines[i].lstrip(" \t{"))
            if m and m.group("ch"):
                busy[int(m.group("ch")[1:])] = m.group("mn")
        return busy

    def _reg_items(self, prefix: str, row: int, model):
        """Регистры из буфера — с тактом, в котором значение будет готово."""
        if self.parsed is None:
            return []
        seen: dict[str, tuple[int, str]] = {}
        for op in self.parsed.ops:
            if op.line - 1 >= row:
                break
            if op.dst:
                seen[op.dst] = (op.cycle + model.latency(op.op), op.mnemonic)
        here = self._op_at_line(row + 1)
        out = []
        for reg, (ready, who) in sorted(seen.items()):
            if prefix and not reg.startswith(prefix):
                continue
            role = "text"
            note = f"готов в т.{ready}   ← {who}"
            if here is not None and here.cycle < ready:
                role = "error"
                note = f"НЕ готов: т.{ready}, а строка в т.{here.cycle}"
            out.append((reg[len(prefix):], "%" + reg, note, role))
        return out[:8]

    def on_suggest_item_picked(self, event) -> None:
        event.stop()
        sug = self.query_one("#suggest", Suggest)
        sug.index = event.index
        self._accept_suggest()

    def _accept_suggest(self) -> bool:
        sug = self.query_one("#suggest", Suggest)
        if not sug.display or not sug.items:
            return False
        edit = self.query_one("#code-edit", AsmArea)
        edit.insert(sug.current())
        sug.hide()
        return True

    # --- выдвижная панель --------------------------------------------------

    #: Вкладка → (заголовок, id блока с содержимым, id кнопки, тема для ИИ).
    TABS = {
        "lint": ("ЗАМЕЧАНИЯ", "#lint-scroll", "#tab-lint", "lint"),
        "term": ("GIT", "#drawer-term-box", "#tab-term", "console"),
        "line": ("ТАКТЫ", "#drawer-line-box", "#tab-line", "code"),
    }

    def action_toggle_drawer(self) -> None:
        if self.drawer_open:
            self.close_drawer()
        else:
            self.open_drawer(self.drawer_tab)

    def action_slash(self) -> None:
        """«/»: в тексте — символ, вне текста — начало команды."""
        edit = self.query_one("#code-edit", AsmArea)
        if edit.has_focus:
            edit.insert("/")
            return
        self.action_command()

    def action_command(self) -> None:
        """^P — панель на вкладке ОТЧЁТ с уже введённым слэшем."""
        self.open_drawer("term")
        bar = self.query_one("#prompt", PromptBar)
        bar.focus_input()
        bar.set_value("/")

    def open_drawer(self, tab: str) -> None:
        self.drawer_tab = tab if tab in self.TABS else "lint"
        self.drawer_open = True
        self._draw_drawer()
        if self.drawer_tab == "term":
            self.query_one("#prompt", PromptBar).focus_input()

    def close_drawer(self) -> None:
        self.drawer_open = False
        self._draw_drawer()
        self.query_one("#code-edit", AsmArea).focus()

    def _draw_drawer(self) -> None:
        """Показать нужную вкладку и убрать остальные."""
        panel = self.query_one("#p-drawer", Panel)
        panel.display = self.drawer_open
        # Класс на экране: в узком окне открытая панель забирает место у
        # расписания, а не у кода. Трёх этажей на тридцати строках не бывает.
        self.set_class(self.drawer_open, "drawer")
        title, box_id, tool_id, topic = self.TABS[self.drawer_tab]
        for key, (_, box, tool, _t) in self.TABS.items():
            self.query_one(box).display = key == self.drawer_tab
            self.query_one(tool, Tool).set_on(key == self.drawer_tab)
        panel.topic = topic
        panel.set_title(title + self._drawer_note())
        self._draw_journal()
        if self.drawer_tab == "lint":
            self._draw_lint()
        elif self.drawer_tab == "line":
            # Две секции вкладки: разбор такта под курсором сверху, каталог
            # тактов всего буфера снизу. Курсор двигается — верхняя живёт.
            self._draw_line_info(self._cursor_line or 1)
            self._draw_bundles()
        self.refresh_hints()

    def _drawer_note(self) -> str:
        """Что показать в заголовке панели рядом с именем вкладки."""
        if self.drawer_tab == "lint":
            errs = sum(1 for p in self.problems if p.severity == "error")
            if errs:
                return (f"   ·   {errs} "
                        f"{plural(errs, 'ошибка', 'ошибки', 'ошибок')}")
            if self.findings and not self._stale():
                k = len(self.findings)
                return (f"   ·   {k} "
                        f"{plural(k, 'находка', 'находки', 'находок')}")
            return "   ·   чисто"
        if self.drawer_tab == "term":
            n = len(self.query_one("#console", Console).runs)
            return (f"   ·   {n} "
                    f"{plural(n, 'коммит', 'коммита', 'коммитов')}"
                    if n else "   ·   пусто — F5 станет коммитом #1")
        n = self.parsed.bundles if self.parsed is not None else 0
        line = self._cursor_line or 1
        return (f"   ·   {n} {plural(n, 'команда', 'команды', 'команд')}"
                f"   ·   стр.{line}")

    def on_line_chip_picked(self, event) -> None:
        event.stop()
        self.open_drawer("line")

    def on_drawer_chip_picked(self, event) -> None:
        """Пункт строки состояния открывает свою вкладку нижней панели."""
        event.stop()
        if self.drawer_open and self.drawer_tab == event.target:
            self.close_drawer()
            return
        self.open_drawer(event.target)

    def refresh_status(self) -> None:
        """Живые счётчики в полосе состояния: ошибки и коммиты git.

        Счётчик ошибок — главный аргумент заглянуть в ЗАМЕЧАНИЯ: пока он
        «▲ 0», туда идти нечего, а «▲ 3» видно краем глаза из любого места
        экрана. Счётчик git — то же для истории: журнал общий на сессию,
        и число растёт даже от команд, набранных в других режимах.
        """
        try:
            lint = self.query_one("#status-lint", DrawerChip)
            errs = sum(1 for p in self.problems if p.severity == "error")
            warns = len(self.problems) - errs
            if errs:
                lint.set_label(f"▲ {errs}"
                               + (f" ~{warns}" if warns else ""))
            elif warns:
                lint.set_label(f"~ {warns}")
            else:
                lint.set_label("✓ чисто")
            term = self.query_one("#status-term", DrawerChip)
            n = len(self.app.session.journal_runs)
            term.set_label(f"git {n}" if n else "git")
        except Exception:
            pass

    # --- буфер ------------------------------------------------------------

    def _sync_buffer(self) -> None:
        """Текст редактора → сессия. Зовётся перед прогоном и при уходе."""
        self.app.session.code_text = self.query_one("#code-edit", AsmArea).text

    def context_bits(self) -> str:
        """Шапка режима. Порядок — по убыванию важности НАРОЧНО.

        В узком окне шапка обрезается справа, и первой должна уезжать не
        главная цифра, а имя профиля машины: оно постоянно, а «15→8 т.»
        меняется от правки к правке. Раньше профиль стоял первым и на 90
        знаках вытеснял именно то, ради чего в шапку и смотрят.
        """
        s = self.app.session
        bits = []
        if self.parsed is not None and self.parsed.ops:
            src = self.comp.makespan if self.comp is not None else None
            orc = (self.orc.schedule.makespan
                   if self.orc is not None and not self._stale() else None)
            if src is not None and orc is not None:
                bits.append(f"{src}→{orc} т.")
            elif src is not None:
                bits.append(f"{src} т.")
            bits.append(f"{len(self.parsed.ops)} оп.")
        else:
            bits.append("буфер пуст")
        errs = sum(1 for p in self.problems if p.severity == "error")
        if errs:
            bits.append(f"▲ {errs} {plural(errs, 'ошибка', 'ошибки', 'ошибок')}")
        if self.app.session.code_path:
            bits.append(self.app.session.code_path)
        bits.append(s.model().name)
        return "   ·   ".join(bits)

    def hint_pairs(self) -> list[tuple[str, str]]:
        pairs = [("F5", "прогнать")]
        pairs.append(("F12", "панель ↓" if not self.drawer_open else "убрать ↓"))
        pairs.append(("^P", "команда"))
        # F6 появляется только когда ему есть что делать: пока точного поиска
        # нет, «переписать по оракулу» — обещание без покрытия.
        if self._have_orc():
            pairs.append(("F6", "переписать по оракулу"))
        pairs.append(("^S", "сохранить"))
        pairs.append(("2×клик", "развернуть блок" if not self.zoom
                      else "свернуть"))
        if self.drawer_open:
            pairs.append(("Esc", "убрать панель"))
        return pairs

    def extra_commands(self) -> list[dict]:
        return [
            {"name": "rewrite", "arg": "",
             "help": "переписать буфер по расписанию точного поиска (F6)",
             "local": True},
            {"name": "example", "arg": "[" + "|".join(
                k for k, _, _ in EXAMPLES) + "]",
             "help": "каталог примеров: без имени — список, с именем — в буфер",
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
        # Подсказка — без задержки: она про то, что печатают ПРЯМО СЕЙЧАС.
        self._update_suggest()

    def on_text_area_selection_changed(self, event) -> None:
        """Курсор в коде переехал: обновить разбор строки и клетку решётки."""
        event.stop()
        line = event.selection.end[0] + 1
        if line == self._cursor_line:
            return
        self._cursor_line = line
        self._update_suggest()
        self._draw_line_chip(line)
        self._sync_grid_cursor(line)
        # Полный разбор пересчитываем, только если он открыт: он стоит куда
        # дороже строки состояния, а курсор ездит на каждое нажатие стрелки.
        if self.zoom == "code":
            self._draw_zoom()
        if self.drawer_open and self.drawer_tab == "line":
            self._draw_line_info(line)
            self._draw_bundles()
            # Заголовок вкладки несёт номер строки под курсором — он меняется
            # вместе с курсором, а не только при открытии вкладки.
            title, _, _, _ = self.TABS["line"]
            self.query_one("#p-drawer", Panel).set_title(
                title + self._drawer_note())

    def _stale(self) -> bool:
        """Числа точного поиска относятся к другому тексту?"""
        edit = self.query_one("#code-edit", AsmArea)
        return bool(self.run_text) and edit.text != self.run_text

    def reparse(self) -> None:
        """Разобрать буфер и обновить всё, что считается без точного поиска."""
        self._debounce = None
        edit = self.query_one("#code-edit", AsmArea)
        text = edit.text
        if self._example and text != example_text(self._example):
            self._example = ""      # правил руками — это уже не пример
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
        self.refresh_status()

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
        first = self.orc is None
        if cached is not None:
            self.base, self.orc, self.met = cached
            self.run_text = self.query_one("#code-edit", AsmArea).text
            self.findings = self._diagnose()
            # Связь с остальными режимами не догадаешься: прогон буфера
            # ДЕЛАЕТ его текущим участком сессии, и РАЗБОР с АГЕНТОМ дальше
            # говорят про твой код, а не про демо-сценарий. Говорим это
            # вслух один раз за сессию — на первом успешном прогоне.
            con = self.console
            if first and con is not None:
                # Тремя короткими строками, а не одной длинной: у ОТЧЁТА
                # перенос выключен (wrap=False), и длинная фраза обрезается
                # ровно там, где начинается смысл.
                con.note("  буфер стал текущим участком", "accent2")
                con.note("  РАЗБОР (^O → 2): такт за тактом", "dim")
                con.note("  АГЕНТ (3): по этим же числам", "dim")
        # `/code load` мог заменить буфер целиком — покажем его в редакторе.
        edit = self.query_one("#code-edit", AsmArea)
        if self.app.session.code_text != edit.text:
            edit.text = self.app.session.code_text
        self.reparse()
        # Журнал общий на сессию: команда могла приехать из другого режима,
        # и счётчик отчёта в строке состояния обязан это показать сразу.
        self.refresh_status()
        # И ряд мостика во вкладке ОТЧЁТ: у свежего прогона появились поля,
        # и кнопки «в разбор / в агента» должны найтись без переоткрытия.
        self._sync_drawer_bridge()
        # Исходник прогона — в запись журнала: только у прогонов буфера он
        # есть, и только они по «в код» возвращаются в редактор с текстом.
        con = self.console
        if con is not None and con.runs:
            rec = con.runs[-1]
            if rec.get("cmd", "").lstrip("/").startswith("code"):
                rec["code"] = self.app.session.code_text

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

    def _draw_title(self) -> None:
        """Заголовок редактора: на чём тут пишут и что открыто.

        «ИСХОДНИК» сам по себе не отвечает ни на «где писать», ни на «на
        каком языке» — а это первые два вопроса всякого, кто открыл режим.
        Язык называется прямо в рамке, а имя файла показывает, правишь ты
        безымянный буфер или конкретный `.s`.
        """
        path = self.app.session.code_path
        title = "ИСХОДНИК   ·   ассемблер e2k (.s)"
        if path:
            title += f"   ·   {path}"
        elif self._example:
            title += f"   ·   пример: {example_title(self._example)}"
        try:
            self.query_one("#p-code", Panel).set_title(title)
        except Exception:
            pass

    def redraw(self) -> None:
        self._draw_title()
        self._draw_marks()
        self._draw_status()
        self._draw_grids()
        line = self.query_one("#code-edit", AsmArea).cursor_location[0] + 1
        self._draw_line_chip(line)
        # Содержимое ящика считаем, только если он открыт: закрытая вкладка
        # не должна стоить ни такта отрисовки на каждое нажатие клавиши.
        if self.drawer_open:
            self._draw_drawer()
        self.refresh_context()
        self.refresh_hints()

    def _draw_line_chip(self, line: int) -> None:
        """Левая половина полосы состояния: что под курсором, одной строкой."""
        chip = self.query_one("#code-line-chip", LineChip)
        model = self.app.session.model()
        op = self._op_at_line(line)
        t = Text()
        t.append(f" стр.{line}", style=palette.role_hex("accent2"))
        if op is not None:
            t.append(f"  {op.op}", style=palette.op_style(op.op))
            t.append(f"  лат.{model.latency(op.op)}",
                     style=palette.role_hex("dim"))
            t.append(f"  т{op.cycle}", style=palette.role_hex("dim"))
            orc = self._orc_cycle(op.index)
            if orc is not None and orc < op.cycle:
                t.append(f"→{orc}", style=palette.role_hex("success"))
        else:
            t.append("  не операция", style=palette.role_hex("faint"))
        mine = [x for x in self.problems if x.line == line]
        if mine:
            t.append(f"  ▲{len(mine)}", style=palette.role_hex("error"))
        t.append("  ▸", style=palette.role_hex("faint"))
        chip.update(t)

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
                    # Канала в метке нет нарочно: он написан в самой строке
                    # (`muls,0`), и дублировать его — три колонки кода за
                    # то, что уже видно.
                    label = f"т{o.cycle}"
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
                marks[o.line - 1] = (label, style)
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
        """Ширина клетки — по месту, а не константой.

        Шесть каналов обязаны быть видны ЦЕЛИКОМ: решётка отвечает на вопрос
        «в какой канал это встало», и обрезанный шестой канал (`,5` — тот
        самый монопольный делитель) делает её бесполезной. Поэтому в узкой
        колонке жертвуем буквами мнемоники, а не столбцами: мнемоника целиком
        всё равно написана в коде слева.
        """
        if self._sched_expanded:
            return 8
        try:
            avail = self.query_one("#p-code-sched", Panel).size.width - 4
        except Exception:
            avail = 40
        model = self.app.session.model()
        return max(4, min(6, (avail - 5) // max(1, model.width)))

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
                item = LintItem(p.line, self._lint_text(p),
                                classes="lint-item")
                # Полный текст замечания — в подсказке: строка в списке
                # обрезана шириной панели, а совет целиком нужен до клика.
                item.tooltip = f"стр.{p.line}  ·  {p.text}\nклик — курсор сюда"
                widgets.append(item)
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
                item = LintItem(line, self._finding_text(f),
                                classes="lint-item")
                item.tooltip = (f"{f.title}: {f.why}\nклик — курсор на "
                                f"стр.{line}")
                widgets.append(item)
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
                item = LintItem(line, text, classes="lint-item")
                item.tooltip = f"клик — курсор на стр.{line}"
                widgets.append(item)
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
        # Заголовок ящика ведёт `_draw_drawer`: он один знает, какая вкладка
        # сейчас открыта, и незачем двум методам спорить за одну рамку.

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
        # Пояснение к разделу — только там, где оно влезает в строку. В
        # колонке 38 знаков «по расписанию из буфера» переносилось на вторую
        # строку и съедало место у самих замечаний, ради которых панель и
        # существует.
        if note and len(label) + len(note) + 5 <= self._lint_width():
            t.append("   " + note, style=palette.role_hex("faint"))
        return t

    def _lint_width(self) -> int:
        try:
            return self.query_one("#p-drawer", Panel).size.width - 4
        except Exception:
            return 40

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

    def _bundle_at(self, line: int):
        """Широкая команда, внутри которой стоит курсор.

        Единица работы в VLIW — не строка, а пачка `{ … }`: она и есть один
        такт выдачи. Курсор всегда внутри какой-то пачки, поэтому и
        рассказать про неё можно всегда — в том числе стоя на скобке, на
        комментарии или на пустой строке. Раньше здесь спрашивали про
        строку, и на всём, что не операция (а это больше половины файла),
        ответом было «здесь не операция» — то есть панель молчала ровно в
        самом частом положении курсора.

        Возвращает (номер такта, [операции этой пачки]) или (None, []).
        """
        if self.parsed is None or not self.parsed.ops:
            return None, []
        edit = self.query_one("#code-edit", AsmArea)
        lines = edit.document.lines
        row = max(0, min(line - 1, len(lines) - 1))
        # Вверх до открывающей скобки, вниз до закрывающей.
        start = row
        while start > 0 and "{" not in lines[start]:
            if "}" in lines[start] and start != row:
                break
            start -= 1
        end = row
        while end < len(lines) - 1 and "}" not in lines[end]:
            if "{" in lines[end] and end != row:
                break
            end += 1
        inside = [o for o in self.parsed.ops if start + 1 <= o.line <= end + 1]
        if not inside:
            # Курсор вне пачек (шапка файла) — берём ближайшую следующую.
            later = [o for o in self.parsed.ops if o.line > line]
            if not later:
                return None, []
            cycle = later[0].cycle
            return cycle, [o for o in self.parsed.ops if o.cycle == cycle]
        return inside[0].cycle, inside

    def _draw_bundles(self) -> None:
        """Каталог тактов: где машина простаивает, видно одним столбцом.

        Это не разбор одной строки покрупнее — это ответ на вопрос «где
        вообще теряется ширина» по всему буферу сразу: полоска занятости
        у каждого такта, клик ведёт курсор в эту пачку. Свои дети — только
        у #drawer-bundles: разбор строки под курсором (#code-line-info)
        живёт выше и курсором же обновляется, стирать его нельзя.
        """
        box = self.query_one("#drawer-bundles", VerticalScroll)
        box.remove_children()
        if self.parsed is None or not self.parsed.ops:
            box.mount(Static(Text("  буфер пуст",
                                  style=palette.role_hex("dim"))))
            return
        model = self.app.session.model()
        width = model.width
        by_cycle: dict[int, list] = {}
        for o in self.parsed.ops:
            by_cycle.setdefault(o.cycle, []).append(o)

        rows = []
        head = Text()
        head.append("  такт   слоты      операции", style=palette.role_hex("dim"))
        rows.append(Static(head))
        span = max(by_cycle) + 1 if by_cycle else 0
        for cycle in range(span):
            ops = by_cycle.get(cycle, [])
            k = len(ops)
            t = Text()
            t.append(f"  т{cycle:<5}", style=palette.role_hex("accent2"))
            role = "success" if k >= width - 1 else (
                "error" if k <= 1 else "warning")
            # Полоска занятости: заполненные слоты и пустые.
            t.append("█" * k, style=palette.role_hex(role))
            t.append("░" * (width - k), style=palette.role_hex("faint"))
            t.append(f" {k}/{width}  ", style=palette.role_hex(role))
            if ops:
                t.append("  ".join(f"{o.mnemonic},{o.channel}"
                                   if o.channel is not None else o.mnemonic
                                   for o in ops[:4]),
                         style=palette.op_style(ops[0].op))
            else:
                t.append("простой", style=palette.role_hex("faint"))
            line = ops[0].line if ops else 0
            rows.append(LintItem(line, t, classes="lint-item"))
        box.mount(*rows)

    def _draw_line_info(self, line: int, target_id: str = "#code-line-info") -> None:
        """Разбор ТАКТА под курсором: что в нём стоит и что в нём пропадает.

        Отвечает на вопрос, ради которого инструмент и существует, — сколько
        машины занято в этот такт и чем свободные каналы могли бы быть
        заняты. Раньше здесь был разбор строки, и он молчал на скобках.
        """
        target = self.query_one(target_id, Static)
        model = self.app.session.model()
        cycle, ops = self._bundle_at(line)
        t = Text()
        if cycle is None:
            t.append("буфер пуст — набери операцию e2k\n",
                     style=palette.role_hex("dim"))
            target.update(t)
            return

        # Строка под курсором — прежде чем говорить про весь такт: что это
        # за операция, сколько машина будет её выполнять и когда результат
        # можно читать. Это ответ на вопрос «я стою на этой строке — что
        # она мне стоит».
        op = self._op_at_line(line)
        if op is not None:
            t.append(f"стр.{op.line}  ", style=palette.role_hex("accent2"))
            t.append(op.mnemonic, style=palette.op_style(op.op))
            t.append(f"   латентность {model.latency(op.op)}",
                     style=palette.role_hex("dim"))
            orc = self._orc_cycle(op.index)
            if orc is not None and orc != op.cycle:
                t.append(f"   оракул: т{orc}", style=palette.role_hex("success"))
            t.append("\n\n")

        used = {o.channel: o for o in ops if o.channel is not None}
        width = model.width
        t.append(f"ТАКТ {cycle}", style=palette.role_hex("title"))
        k = len(ops)
        role = "success" if k >= width - 1 else ("error" if k <= 1 else "warning")
        t.append(f"   занято {k} из {width}\n\n", style=palette.role_hex(role))

        # Полоса слотов: занятые и пустые каналы этого такта, по порядку.
        for port in range(width):
            op = used.get(port)
            t.append(f" {model.port_label(port):>3} ", style=palette.role_hex("dim"))
            if op is not None:
                t.append(f"{op.mnemonic:<8}", style=palette.op_style(op.op))
                t.append(f"стр.{op.line}", style=palette.role_hex("accent2"))
                orc = self._orc_cycle(op.index)
                if orc is not None and orc != op.cycle:
                    t.append(f"  → т{orc}", style=palette.role_hex("success"))
            else:
                # Пустой канал — не «ничего», а упущенная возможность:
                # говорим классами операций, ЧТО сюда можно поставить.
                # Классы, а не слова: те же имена и те же цвета, что в
                # решётке и в легенде, и в 38 колонок они помещаются.
                t.append("пусто ", style=palette.role_hex("faint"))
                for cls in ("ADD", "MUL", "LOAD", "STORE", "DIV"):
                    if port in model.channels_for(cls):
                        t.append(cls + " ", style=palette.op_style(cls))
            t.append("\n")

        # Что этот такт делает у точного поиска.
        if ops and self.orc is not None and not self._stale():
            moved = [o for o in ops if (self._orc_cycle(o.index) or o.cycle) != o.cycle]
            t.append("\n")
            if moved:
                t.append(f"точный поиск уводит отсюда {len(moved)} из {k}\n",
                         style=palette.role_hex("success"))
            else:
                t.append("точный поиск оставляет этот такт как есть\n",
                         style=palette.role_hex("dim"))

        mine = [p for p in self.problems
                if any(o.line == p.line for o in ops) or p.line == line]
        if mine:
            t.append("\nзамечания\n", style=palette.role_hex("title"))
            for p in mine[:4]:
                mark, role = self.MARKS.get(p.severity, ("·", "dim"))
                t.append(f" {mark} стр.{p.line} {p.text}\n",
                         style=palette.role_hex(role))
        target.update(t)

    # --- развороты --------------------------------------------------------

    def on_panel_expanded(self, event) -> None:
        """Разворот блока. Здесь он ДОБАВЛЯЕТ, а не убирает.

        Встроенный maximize показывает ровно один виджет и прячет всё
        остальное — от этого разворот редактора отбирал расписание, полосу
        состояния и нижнюю панель, то есть чем глубже работаешь, тем меньше
        видно. Свой разворот отдаёт блоку место за счёт соседей, но их не
        убирает, и раскрывает то, чему в обычном виде места не было:
        у ИСХОДНИКА — разбор строки и цепочку зависимостей, у РАСПИСАНИЯ —
        загрузку портов и список перестановок, у нижнего блока — высоту.
        """
        event.stop()
        want = {"p-code": "code", "p-code-sched": "sched",
                "p-drawer": "drawer"}.get(getattr(event.panel, "id", ""), "")
        self.set_zoom("" if want == self.zoom else want)

    def on_panel_collapsed(self, event) -> None:
        event.stop()
        self.set_zoom("")

    def set_zoom(self, zoom: str) -> None:
        self.zoom = zoom
        for key in ("code", "sched", "drawer"):
            self.set_class(zoom == key, f"zoom-{key}")
        # Развёрнутый блок обязан быть виден: нижний открывается сам.
        if zoom == "drawer" and not self.drawer_open:
            self.open_drawer(self.drawer_tab)
        self._sched_expanded = zoom == "sched"
        self._lint_expanded = zoom == "drawer" and self.drawer_tab == "lint"
        self._console_expanded = zoom == "drawer" and self.drawer_tab == "term"
        self._code_expanded = zoom == "code"
        self._draw_grids()
        self._draw_zoom()
        if self.drawer_open:
            self._draw_drawer()
        self.refresh_hints()

    def _draw_zoom(self) -> None:
        """Колонки, которые появляются только в развороте ИСХОДНИКА."""
        line = self._cursor_line or 1
        self._draw_line_info(line, "#code-line-body")
        self._draw_chain(line)

    def _draw_chain(self, line: int) -> None:
        """Цепочка зависимостей строки: кто её кормит и кто ждёт её.

        В обычном виде этого нет и не должно быть — вопрос «кто от кого
        зависит» задают редко, но когда задают, отвечать надо графом, а не
        одной строкой. Здесь он и разворачивается: вверх по предкам, вниз
        по потомкам, с номерами строк и тактами готовности.
        """
        target = self.query_one("#code-chain-body", Static)
        t = Text()
        if self.local_dag is None or self.parsed is None:
            target.update(t)
            return
        op = self._op_at_line(line)
        if op is None:
            # Курсор на скобке или комментарии — берём первую операцию
            # этого же такта: цепочка у пачки всё равно есть.
            _cycle, ops = self._bundle_at(line)
            op = ops[0] if ops else None
        if op is None:
            target.update(t)
            return
        model = self.app.session.model()
        dag = self.local_dag
        t.append("ЦЕПОЧКА\n\n", style=palette.role_hex("title"))

        preds = dag[op.index].preds if op.index < len(dag) else ()
        t.append("кормят эту строку\n", style=palette.role_hex("dim"))
        if not preds:
            t.append("  никто — операнды готовы заранее\n",
                     style=palette.role_hex("faint"))
        for pid in preds:
            src = self.parsed.ops[pid]
            ready = src.cycle + model.latency(src.op)
            role = "error" if ready > op.cycle else "text"
            t.append(f"  стр.{src.line:<4}", style=palette.role_hex("accent2"))
            t.append(f"{src.mnemonic:<8}", style=palette.op_style(src.op))
            t.append(f"т{src.cycle} → готов т{ready}\n",
                     style=palette.role_hex(role))

        succs = [i for i in range(len(dag)) if op.index in dag[i].preds]
        t.append("\nждут её\n", style=palette.role_hex("dim"))
        if not succs:
            t.append("  никто — результат дальше не используется\n",
                     style=palette.role_hex("faint"))
        for sid in succs:
            dst = self.parsed.ops[sid]
            t.append(f"  стр.{dst.line:<4}", style=palette.role_hex("accent2"))
            t.append(f"{dst.mnemonic:<8}", style=palette.op_style(dst.op))
            t.append(f"т{dst.cycle}\n", style=palette.role_hex("text"))

        ready = op.cycle + model.latency(op.op)
        t.append(f"\nэта отдаст результат в такте {ready}\n",
                 style=palette.role_hex("dim"))
        target.update(t)

    def _draw_journal(self) -> None:
        """Развёрнутый ОТЧЁТ — история-терминал с каталогом команд.

        В обычном виде вкладка ОТЧЁТ — это лента вывода, мостик над ней и
        строка ввода под ней, то есть ровно терминал. В развороте она
        становится историей сессии с каталогом ВСЕХ команд слева: то же
        место, но больше инструментов, а не тот же текст крупнее.
        """
        journal = self.query_one("#journal", ConsoleJournal)
        con = self.query_one("#console", Console)
        deep = self._console_expanded and self.drawer_tab == "term"
        journal.display = deep
        con.display = not deep
        # Строка ввода прячется только под журналом: у него своя.
        self.query_one("#prompt", PromptBar).display = not deep
        # Ряд мостика общий: и во вкладке, и в журнале он действует на
        # выбранный (или последний) прогон.
        self.query_one("#drawer-bridge", BridgeRow).display = not deep
        if deep:
            journal.load(con.runs, self.mode,
                         list(self.app.commands) + self.extra_commands(),
                         self.app.session.journal_events)
        self._sync_drawer_bridge()

    def _sync_drawer_bridge(self) -> None:
        """Ряд мостика во вкладке ОТЧЁТ — по выбору в истории сессии."""
        try:
            row = self.query_one("#drawer-bridge", BridgeRow)
            journal = self.query_one("#journal", ConsoleJournal)
        except Exception:
            return
        row.sync(self.app.session.journal_runs, journal.pos)

    # --- инструменты панелей ----------------------------------------------

    def panel_tool(self, tool: str) -> None:
        if tool.startswith("drawer-"):
            self.open_drawer(tool.split("-", 1)[1])
        elif tool == "code-save":
            self.action_save_code()
        elif tool == "code-rewrite":
            self.action_rewrite()
        elif tool == "code-broken":
            self._load_example_named("broken")
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

    def _load_example_named(self, name: str) -> None:
        """`/example <имя>` — положить пример в буфер. Без имени — каталог."""
        name = (name or "").strip().lower()
        if not name:
            self._list_examples()
            return
        text = example_text(name)
        if text is None:
            con = self.console
            if con is not None:
                con.note(f"  примера «{name}» нет", "error")
            self._list_examples()
            return
        self._load_example(text, name)

    def _list_examples(self) -> None:
        con = self.console
        if con is None:
            return
        con.note("  примеры: /example <имя>", "accent2")
        for key, title, note in EXAMPLES:
            row = Text()
            row.append("  " + key.ljust(9), style=palette.role_hex("accent2"))
            row.append(title, style=palette.role_hex("text"))
            con.write(row)
            con.note("           " + note, "dim")

    def _load_example(self, text: str, name: str = "") -> None:
        """Пример в буфер.

        `code_path` НЕ трогаем нарочно: иначе ^S молча перезапишет файл
        примера в репозитории вместо работы человека. Имя показывается в
        заголовке — видно, что правишь пример, а не свой файл.
        """
        edit = self.query_one("#code-edit", AsmArea)
        edit.replace(text, (0, 0), edit.document.end)
        self.app.session.code_text = text
        self._example = name
        self.orc = self.base = self.met = None
        self.findings = []
        self.run_text = ""
        self.reparse()
        edit.focus()
        con = self.console
        if con is not None:
            con.note(f"  пример «{name or 'без имени'}» в буфере — F5",
                     "accent2")

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
            self._load_example_named(arg.strip().lower())
            return
        super().handle_line(line)

    def action_back(self) -> None:
        """Esc — шаг наружу. В КОДЕ первый шаг наружу это закрыть ящик.

        Строка ввода больше не отдельное место, куда «выходят» из редактора:
        она внутри ОТЧЁТА. Поэтому каскад короче — закрыть панель, потом
        свернуть разворот, потом уйти из режима.
        """
        sug = self.suggest
        if sug is not None and sug.display:
            sug.hide()
            return
        self._sync_buffer()
        if self.zoom:
            self.set_zoom("")
            return
        if self.drawer_open:
            self.close_drawer()
            return
        super().action_back()

    def action_ai_or_complete(self) -> None:
        """Tab: в редакторе — отступ, вне его — как у всех."""
        if self._accept_suggest():
            return
        edit = self.query_one("#code-edit", AsmArea)
        if edit.has_focus and self.zoom != "sched":
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
