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
import time
from pathlib import Path

from rich.segment import Segment
from rich.style import Style as RichStyle
from rich.text import Text
from textual import work
from textual.binding import Binding
from textual.containers import Horizontal, ItemGrid, Vertical, VerticalScroll
from textual.message import Message
from textual.strip import Strip
from textual.widgets import DataTable, Input, RichLog, Static, TextArea
from textual.widgets.text_area import TextAreaTheme

from ...core import asm_parser, doctor
from .. import palette
from ..widgets import (BridgeRow, Chip, Console, ConsoleJournal, HintBar,
                       PanelPrompt, PromptBar, Tool, double_click, plural)
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


CONT = "═"        # клетка занята продолжением длинной операции
                  # (тянется вправо: решётка развёрнута, см. _fill_grid)
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

    #: Колонка действия в самом начале гуттера: `▷` на строке под курсором.
    #: Гуттер несёт действие — так запуск живёт в IDE, стрелкой у строки, а
    #: не рядом текстовых кнопок над кодом. Ряд кнопок отбирал целую строку
    #: экрана всегда и повторял то, что уже написано в подсказках клавиш;
    #: стрелка стоит там, где и так лежит взгляд, и не стоит ни строки.
    RUN_W = 2

    #: Пустая разметка на уровне класса, а не только в `__init__`: ширину
    #: гуттера спрашивает уже `TextArea.__init__` (через `gutter_width`), то
    #: есть ДО того, как экземпляр успел завести свою.
    _marks: dict[int, tuple[str, RichStyle]] = {}

    #: Можно ли прогнать то, что в буфере. У скрипта и заметки стрелки в
    #: гуттере нет: кнопка, которая на этом файле откажет, — не кнопка.
    runnable: bool = True

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
        # TextArea сам вычитает эту ширину при переводе клика в позицию в
        # тексте, поэтому колонку действия достаточно объявить здесь.
        return self.RUN_W + self.BADGE_W

    class RunHere(Message):
        """Кликнули по стрелке запуска в гуттере."""

    def on_click(self, event) -> None:
        """Клик по стрелке — прогнать буфер. Остальной гуттер не трогаем.

        Ровно две колонки, и только они: клик по номеру строки или по метке
        такта обязан оставаться кликом по коду. Точный поиск стоит секунды,
        и запускать его промахом мимо строки — худшее, что тут можно
        сделать.
        """
        if event.x < self.RUN_W:
            event.stop()
            if self.runnable:
                self.post_message(self.RunHere())

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
            # Стрелка — только на строке под курсором: шестьдесят стрелок
            # подряд были бы обоями, а не кнопкой.
            Segment("▷ " if (cursor and self.runnable) else "  ",
                    RichStyle(color=palette.role_hex("success"), bold=True)
                    if cursor else num_style),
            Segment(f"{row + 1:>{self.NUM_W - 1}} ", num_style),
            Segment((f"{badge:>{mark_w - 1}} " if badge else " " * mark_w)
                    if mark_w else "", style),
        ], cell_length=self.gutter_width)
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
        # Колонка описаний — по самой длинной метке в ЭТОМ списке. Жёсткие
        # десять клеток («label.ljust(10)») не работали там, где метка
        # длиннее: у `/gen <сколько> <операция> [плотно]` описание прилипало
        # к аргументам вплотную и читалось как продолжение синтаксиса.
        pad = min(34, max(len(label) for _i, label, _n, _r in self.items) + 2)
        rows = []
        for i, (_ins, label, note, role) in enumerate(self.items):
            rows.append(SuggestItem(i, self._row(label, note, role, pad),
                                    classes="suggest-item"))
        self.mount(*rows)
        self.display = True
        self.call_after_refresh(self._mark)

    def _row(self, label: str, note: str, role: str, pad: int = 10) -> Text:
        t = Text()
        t.append(" " + label.ljust(pad), style=palette.role_hex(role) + " bold")
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


class FileStrip(Static):
    """Полоса вкладок открытых буферов. Клик — переключить, ✕ — закрыть.

    Вкладки файлов нужны не ради «как в редакторе». Сравнение двух участков
    — основная работа в этом инструменте: открыл `probe.s` от lcc, рядом
    свою переписанную версию, и переключаешься между ними, не теряя ни
    расписания, ни замечаний. Пока буфер был один на сессию, второй участок
    можно было держать только в чужом окне.

    Полоса — ОДИН виджет с размеченными зонами клика, а не вкладки-виджеты.
    Виджетами она пересобиралась бы на каждую паузу в наборе (имя буфера и
    признак «правлен» живые), а снос-монтаж в одном кадре у Textual значит
    столкновение идентификаторов и мигание строки. Здесь перерисовка — это
    `update()` с новым текстом, то есть ровно то, чем она и является.
    """

    class Picked(Message):
        def __init__(self, index: int) -> None:
            super().__init__()
            self.index = index

    class Closed(Message):
        def __init__(self, index: int) -> None:
            super().__init__()
            self.index = index

    class Toggled(Message):
        """Клик по кнопке панели в правом краю полосы."""

        def __init__(self, which: str) -> None:
            super().__init__()
            self.which = which

    class Maximized(Message):
        """Двойной клик по вкладке — редактор во весь экран и обратно.

        Место выбрано по IDE: в VS Code и IntelliJ разворачивают именно
        двойным кликом по вкладке файла. По самому редактору так делать
        нельзя — там двойной клик выделяет слово, и это поведение текстового
        поля, которое ломать нечем оправдать.
        """

    def __init__(self, *args, **kw) -> None:
        super().__init__(*args, **kw)
        #: [(начало, конец, номер вкладки, есть ли ✕)] в клетках строки.
        self.spans: list[tuple[int, int, int, bool]] = []
        #: [(начало, конец, что переключает)] — кнопки панелей справа.
        self.toggles: list[tuple[int, int, str]] = []
        self._last_click = 0.0

    def on_click(self, event) -> None:
        # Кнопки панелей проверяем первыми: они лежат правее вкладок и их
        # зоны не пересекаются, но порядок делает намерение явным.
        for start, end, which in self.toggles:
            if start <= event.x < end:
                event.stop()
                self.post_message(self.Toggled(which))
                return
        double, self._last_click = double_click(event, self._last_click)

        for start, end, index, closable in self.spans:
            if not (start <= event.x < end):
                continue
            event.stop()
            # ✕ занимает две последние клетки вкладки.
            if closable and event.x >= end - 2:
                self.post_message(self.Closed(index))
            elif double:
                self.post_message(self.Maximized())
            else:
                self.post_message(self.Picked(index))
            return


class SideItem(Static):
    """Строка каталога слева. Клик открывает файл, ✕ справа — удаляет.

    В сообщении едет и КОЛОНКА клика: строка каталога делает два разных
    дела, и какое именно — решает то, куда попали. Отдельным виджетом ✕
    сделать нельзя: строк в каталоге десятки, и каждая стала бы двумя
    виджетами вместо одного, с перемонтажом на каждую перерисовку.
    """

    class Picked(Message):
        def __init__(self, key: str, at_x: int = -1) -> None:
            super().__init__()
            self.key = key
            self.at_x = at_x

    def __init__(self, key: str, *args, **kw) -> None:
        super().__init__(*args, **kw)
        self.key = key

    def on_click(self, event) -> None:
        event.stop()
        self.post_message(self.Picked(self.key, getattr(event, "x", -1)))


class DockSplitter(Static):
    """Волосок между редактором и доком — он же ручка перетаскивания.

    В IDE границу между редактором и инструментальным окном тянут мышью, и
    это не украшение: сколько строк отдать доку, зависит от того, что в нём
    открыто. Расписание — это всегда шесть каналов, ему хватает восьми
    строк; журнал прогонов хочет половину экрана. Фиксированные 34% высоты
    были компромиссом, который не подходил ни тому ни другому: под решёткой
    оставалось четыре пустых строки, а в журнале не помещался один отчёт.

    Мышь захватывается на время перетаскивания (`capture_mouse`) — иначе
    события уходят тому виджету, над которым оказался курсор, и граница
    «срывается» на первом же быстром движении.
    """

    class Grabbed(Message):
        """За границу взялись — с этой высоты и пойдёт отсчёт."""

    class Dragged(Message):
        """Границу тянут: `delta` — на сколько строк вниз с начала жеста."""

        def __init__(self, delta: int) -> None:
            super().__init__()
            self.delta = delta

    def __init__(self, *args, **kw) -> None:
        super().__init__(*args, **kw)
        self._from = 0

    def on_mount(self) -> None:
        # Формы курсора в терминале нет, подсветки под мышью мало: что за
        # эту линию тянут, приходится говорить словами.
        self.tooltip = ("тянуть мышью — высота нижнего окна\n"
                        "F11 — развернуть его на весь экран\n"
                        "F12 — убрать совсем")

    def render(self):
        # Линия, а не полоса фона: граница окна должна выглядеть границей.
        # Ручка посередине — единственный намёк, что за неё берутся: формы
        # курсора в терминале нет.
        w = self.size.width or 0
        if w < 9:
            return Text("─" * w, style=palette.role_hex("border"))
        left = (w - 3) // 2
        t = Text()
        t.append("─" * left, style=palette.role_hex("border"))
        t.append("╍╍╍", style=palette.role_hex("dim"))
        t.append("─" * (w - left - 3), style=palette.role_hex("border"))
        return t

    def on_mouse_down(self, event) -> None:
        event.stop()
        self._from = event.screen_y
        self.capture_mouse()
        # Начало жеста объявляется отдельным сообщением, а не «концом
        # предыдущего»: конец приходит с захваченной мышью и до экрана не
        # доходит вовсе (событие останавливается здесь). Пока начало ловили
        # по отпусканию, второй жест подряд считал высоту от первой.
        self.post_message(self.Grabbed())

    def on_mouse_move(self, event) -> None:
        if self.app.mouse_captured is not self:
            return
        event.stop()
        self.post_message(self.Dragged(event.screen_y - self._from))

    def on_mouse_up(self, event) -> None:
        if self.app.mouse_captured is self:
            event.stop()
            self.release_mouse()


class DockTabs(Horizontal):
    """Полоса вкладок нижнего дока. Двойной клик по ней разворачивает док.

    Ровно как заголовок инструментального окна в IDE: одиночный клик по
    вкладке переключает, двойной по самой полосе — растягивает окно на
    полэкрана и обратно. Отдельной кнопки под это нет намеренно: в полосе
    и так живут четыре вкладки и переключатель расписания.
    """

    class Zoom(Message):
        pass

    def __init__(self, *children, **kw) -> None:
        super().__init__(*children, **kw)
        self._last_click = 0.0

    def on_click(self, event) -> None:
        double, self._last_click = double_click(event, self._last_click)
        if double:
            event.stop()
            self.post_message(self.Zoom())


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
    placeholder = "/doctor   ·   /code save my.s   ·   /example"
    hint = "«/» каталог   ·   ↑ история"
    # Каталог слева убирается по ^B — как дерево проекта в IDE. Полоса
    # подсказок не убирается: в редакторе она единственное место, где
    # написано про F5, а её ищут в первую очередь.
    SIDE_ID = "#code-side"
    TIPS_ID = ""

    BINDINGS = ModeScreen.BINDINGS + [
        Binding("f5", "run_code", "прогнать", priority=True),
        ("ctrl+s", "save_code", "сохранить"),
        # F6 рядом с F5 нарочно: прогнать и переписать — два шага одного
        # движения. ^R сюда просится, но он уже занят повтором запуска в
        # развёрнутом ОТЧЁТЕ (ConsoleJournal), а приоритетный биндинг экрана
        # отобрал бы его у журнала молча.
        Binding("f6", "rewrite", "переписать по оракулу", priority=True),
        # F12 — как ^` в IDE: убрать нижний док совсем и вернуть.
        # Панели независимы: без дока редактор занимает весь экран, и
        # ничего при этом не ломается.
        Binding("f12", "toggle_drawer", "док снизу", priority=True),
        # F11 — развернуть док на полэкрана (то же, что двойной клик по
        # полосе вкладок). Рядом с F12 нарочно: одна пара клавиш на всё
        # управление высотой окна снизу.
        Binding("f11", "zoom_dock", "развернуть док", priority=True),
        Binding("f2", "rename_buffer", "переименовать вкладку", priority=True),
        # ^P — открыть док на ВЫВОДЕ и начать команду. Не «/» и не «:»:
        # оба знака печатные и в ассемблере встречаются (`//` в комментарии,
        # двоеточие в метке `main:`), отбирать их у текста нельзя. Поэтому
        # набор команды начинается с клавиши, которой в тексте не бывает.
        Binding("ctrl+p", "command", "команда", priority=True),
        # А «/» остаётся быстрым входом там, где фокус НЕ в тексте — в
        # решётке расписания или в списке замечаний.
        Binding("slash", "slash", "команда", priority=True),
        # ^G — агент: спросить про то, на что смотришь. Не режим и не
        # четверть главного меню, а строка снизу, которая знает контекст.
        Binding("ctrl+g", "explain", "объяснить", priority=True),
        # ^E — проводник справа: найти свой .s, не выходя из работы.
        Binding("ctrl+e", "toggle_explorer", "проводник", priority=True),
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

    #: Вкладки нижнего дока: ключ → (подпись, id блока, id кнопки, тема ИИ).
    #: Порядок — порядок в полосе вкладок.
    #:
    #: ВЫВОД первым, дальше замечания, разбор, расписание. Раньше первым
    #: стояло расписание — как ответ на вопрос, ради которого экран
    #: открывают. Но вопрос «куда легли операции» человек задаёт, уже зная
    #: инструмент, а первый вопрос у всех другой: «я нажал — где результат?».
    #: В IDE на него отвечает окно вывода, и стоит оно первым слева; здесь
    #: вывод стоял четвёртым, и найти его было неоткуда. Порядок вкладок —
    #: это порядок вопросов, а не важности содержимого.
    TABS = {
        "term": ("вывод", "#dock-term", "#tab-term", "console"),
        "lint": ("замечания", "#dock-lint", "#tab-lint", "lint"),
        "line": ("разбор", "#dock-line", "#tab-line", "code"),
        "sched": ("расписание", "#dock-sched", "#tab-sched", "sched"),
        "core": ("ядро", "#dock-core", "#tab-core", "core"),
        "agent": ("агент", "#dock-agent", "#tab-agent", "code"),
    }

    #: ЗАГОТОВКИ УЧАСТКОВ — куски ассемблера, которые вставляются по «/».
    #:
    #: Не текст, а СБОРКА. Первая версия вставляла готовые строки с вбитыми
    #: `%r10, %r11, %r20`, и это было бесполезно: вторая же вставка писала в
    #: те же регистры, буфер получал конфликт по записи, и половину заготовки
    #: приходилось править руками. `nop 3` там тоже стоял константой — то
    #: есть заготовка соврала бы при первой правке модели машины.
    #:
    #: Здесь заготовка описана СМЫСЛОМ: сколько операций, каким классом, по
    #: каким каналам, кто чей результат читает. Регистры подбираются из тех,
    #: что в буфере ещё не заняты (`_free_regs`), а паузы считаются по
    #: латентности из модели (`_pause_for`). Ни того, ни другого обычный
    #: редактор со сниппетами сделать не может — у него нет ни разбора, ни
    #: модели машины.
    #:
    #: Каналы не выдуманы: формат `<мнемоника>,<канал> <аргументы>,
    #: <результат>` — руководство МЦСТ (выпуск 1.2, с. 19), `nop N` там же
    #: описан как задержка ПЕРЕД СЛЕДУЮЩЕЙ широкой командой. Допустимые
    #: каналы сошлись в трёх источниках: опрос ассемблера
    #: (`tools/probe_matrix.py`), руководство и таблица декодирования QEMU
    #: (`target/e2k/alop.decode`: `-0-` у умножения — alc0/1/3/4, `110` у
    #: деления — только alc5, `--0` у загрузки — alc0/2/3/5, `-10` у записи
    #: — alc2/5).
    #:
    #: Чего заготовки НЕ делают: не притворяются выводом компилятора.
    #: Адресация памяти у настоящего lcc записывается иначе
    #: (`ldw,3 0x0, [ _f64,_lts0 a ], %r3`); здесь короткая форма, понятная
    #: разбору, — полигон для расписания, а не готовый к ассемблированию код.
    SNIPPETS = (
        ("bundle", "пустая широкая команда — один такт", "bundle"),
        ("par4", "четыре умножения в одном такте: ,0 ,1 ,3 ,4", "par"),
        ("queue", "та же работа в один канал — очередь на ровном месте",
         "queue"),
        ("chain", "цепочка зависимых: пауза по латентности умножения",
         "chain"),
        ("div", "деление: единственный канал ,5 и его латентность", "div"),
        ("load", "загрузка и её потребитель: пауза по латентности", "load"),
        ("store", "запись — только каналы ,2 и ,5", "store"),
    )

    def _free_regs(self, count: int) -> list[str]:
        """Регистры, которых в буфере ещё нет.

        Вставленная заготовка не должна спорить с тем, что уже написано:
        вторая вставка с теми же `%r20` даёт конфликт по записи, а разбор
        честно показывает его ошибкой — на коде, которого человек не писал.
        """
        busy: set[str] = set()
        if self.parsed is not None:
            for op in self.parsed.ops:
                if op.dst:
                    busy.add(op.dst.lower())
                for src in getattr(op, "srcs", ()) or ():
                    busy.add(str(src).lower())
        # Плюс то, что просто написано в тексте: буфер мог не разобраться.
        text = self.query_one("#code-edit", AsmArea).text.lower()
        out: list[str] = []
        n = 0
        while len(out) < count and n < 200:
            name = f"r{n}"
            n += 1
            if name in busy or f"%{name}," in text or f"%{name} " in text:
                continue
            out.append(name)
        return out or [f"r{i}" for i in range(count)]

    def _pause_for(self, op_class: str) -> int:
        """Сколько тактов ждать результат — по модели, а не по памяти."""
        return max(0, self.app.session.model().latency(op_class) - 1)

    def _snippet_text(self, kind: str) -> str:
        """Собрать заготовку под текущий буфер и текущую модель машины."""
        model = self.app.session.model()

        def bundle(*lines: str) -> str:
            return "{\n" + "".join(f"  {l}\n" for l in lines) + "}\n"

        if kind == "bundle":
            return "{\n  \n}\n"

        if kind == "par":
            # По одному каналу на операцию — те, на которых умножение
            # вообще исполнимо.
            chans = model.channels_for("MUL")[:4]
            regs = self._free_regs(len(chans) * 3)
            lines = []
            for i, ch in enumerate(chans):
                a, b, d = regs[i * 3:i * 3 + 3]
                lines.append(f"muls,{ch} %{a}, %{b}, %{d}")
            return bundle(*lines)

        if kind == "queue":
            ch = model.channels_for("MUL")[0]
            regs = self._free_regs(12)
            out = []
            for i in range(4):
                a, b, d = regs[i * 3:i * 3 + 3]
                out.append(bundle(f"muls,{ch} %{a}, %{b}, %{d}"))
            return "".join(out)

        if kind == "chain":
            ch = model.channels_for("MUL")[0]
            a, b, d, e, f = self._free_regs(5)
            pause = self._pause_for("MUL")
            first = bundle(f"nop {pause}", f"muls,{ch} %{a}, %{b}, %{d}") \
                if pause else bundle(f"muls,{ch} %{a}, %{b}, %{d}")
            return first + bundle(f"muls,{ch} %{d}, %{e}, %{f}")

        if kind == "div":
            ch = model.channels_for("DIV")[0]
            add_ch = model.channels_for("ADD")[0]
            a, b, d, e, f = self._free_regs(5)
            pause = self._pause_for("DIV")
            first = bundle(f"nop {pause}", f"sdivs,{ch} %{a}, %{b}, %{d}") \
                if pause else bundle(f"sdivs,{ch} %{a}, %{b}, %{d}")
            return first + bundle(f"adds,{add_ch} %{d}, %{e}, %{f}")

        if kind == "load":
            ch = model.channels_for("LOAD")[0]
            add_ch = model.channels_for("ADD")[0]
            a, d, e, f = self._free_regs(4)
            pause = self._pause_for("LOAD")
            first = bundle(f"nop {pause}", f"ldw,{ch} %{a}, %{d}") \
                if pause else bundle(f"ldw,{ch} %{a}, %{d}")
            return first + bundle(f"adds,{add_ch} %{d}, %{e}, %{f}")

        if kind == "store":
            ch = model.channels_for("STORE")[0]
            a, b = self._free_regs(2)
            return bundle(f"stw,{ch} %{a}, %{b}")
        return ""

    #: Что можно завести в каталоге слева: (расширение, подпись, из чего
    #: состоит новый файл, что о нём сказать).
    #:
    #: Инструмент планирует широкие команды e2k, и разбирает он только `.s`.
    #: Заметка рядом с участком — не про планировщик, но про ту же работу:
    #: что уже пробовали и чем кончилось. Её и можно завести здесь.
    #:
    #: Скрипт `.py` отсюда УБРАН. Завести его инструмент умел, а запустить —
    #: нет, и «зачем он тут» не отвечал ни интерфейс, ни этот комментарий.
    #: Кнопка, которая делает файл и на этом кончается, — не функция, а
    #: обещание. Запуск скриптов вынесен в docs/REDESIGN.md, к следующему
    #: заходу: там у него есть смысл (скрипт порождает .s и сразу открывает
    #: его вкладкой), но это отдельная работа, а не строчка в списке типов.
    #:
    #: Врать про типы инструмент не станет и дальше: разбор, расписание и F5
    #: работают только на `.s`, у остальных в строке состояния написано, что
    #: их не разбирают.
    FILE_KINDS = (
        ("s", "участок e2k", "участок",
         "! новый участок — F5 прогнать, «/» команды\n"),
        ("md", "заметка", "заметка",
         "# что пробовал и что вышло\n"),
    )

    #: Расширения, которые инструмент действительно разбирает.
    ASM_SUFFIXES = (".s", ".asm")

    #: Сколько строк вкладке хватает, пока высоту не поставил человек.
    #:
    #: Раньше док держал 34% экрана при любой вкладке, и это не подходило ни
    #: одной: под решёткой расписания оставалось четыре пустые строки (каналов
    #: всегда шесть, больше взяться неоткуда), а в журнал прогонов не влезал
    #: один отчёт. Здесь у каждой вкладки своя мера — она же ответ на вопрос
    #: «сколько строк тут вообще бывает». Как только за границу потянули
    #: мышью, действует поставленная высота и ничего больше не прыгает.
    TAB_HEIGHT = {
        "sched": 8,    # полоса вкладок, строка тактов, шесть каналов
        "line": 15,    # разбор такта и каталог тактов буфера
        "lint": 10,    # замечания с советами
        "term": 15,    # лента вывода и строка команды
        "core": 15,    # консоль интерпретатора и панель имён
        "agent": 12,   # переписка, готовые вопросы и строка вопроса
    }

    #: Подсказка у кнопки вкладки: чем эта вкладка отвечает на «что здесь».
    TAB_TIPS = {
        "sched": "куда легли операции: каналы по строкам, такты по колонкам",
        "line": "такт под курсором, его цепочка и каталог тактов буфера",
        "lint": "что не так по машине и где теряются такты",
        "term": "сюда приходит результат: прогоны, история сессии, команды",
        "core": "консоль интерпретатора: собрать граф, не умея писать "
                "ассемблер",
        "agent": "переписка с агентом целиком: 2×клик — на весь экран",
    }

    #: Что остаётся видимым при встроенном развороте (его здесь не бывает,
    #: но панель ИИ и подвал обязаны переживать чужой maximize).
    ALLOW_IN_MAXIMIZED_VIEW = ("PanelChat, PanelPrompt, PromptBar, HintBar, "
                               "Footer, TopBar, #code-foot, #code-dock")

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        # Каталог слева закрыт: ^B открывает. См. compose.
        self.side_shown = False
        # Живой разбор: считается на каждую правку, стоит микросекунды.
        self.parsed = None
        self.local_dag = None
        self.comp = None              # расписание из самого исходника
        self.comp_problem = None      # почему его нет — парой (заголовок, суть)
        self.unknown_share = 0.0      # доля операций, неизвестных машине
        self.problems: list = []
        # Дорогое: точный поиск и диагностика — только по F5.
        self.base = None
        self.orc = None
        self.met = None
        self.findings: list = []
        self.findings_from = "буфер"
        self.run_text = ""            # текст буфера на момент прогона
        self._grid_cells: dict[tuple[str, int, int], int] = {}
        self._sched_left = None       # что сейчас в решётке
        self._sched_which = "src"
        self._lint_lines: list[int] = []
        self._code_expanded = False
        self._sched_expanded = False
        self._lint_expanded = False
        self._console_expanded = False
        self._debounce = None
        self.sched_view = "src"     # какое расписание в решётке
        self._cursor_line = 0
        self._example = ""          # какой пример сейчас в буфере
        # Открытые буферы: [{name, path, text, example}] и активный.
        self.files: list[dict] = []
        self.file_i = 0
        # Нижний док: ОТКРЫТ по умолчанию и стоит на расписании. Пока он
        # был выдвижным ящиком поверх второй панели, расписание занимало
        # место всегда, а всё остальное пряталось за клавишу — то есть
        # худшее из двух. Теперь окно одно: видно то, что выбрано, и оно
        # целиком убирается F12, когда нужен только код.
        self.drawer_open = True
        #: Что было открыто до разворота редактора; None — не развёрнут.
        self._maximized: tuple[bool, bool] | None = None
        self.drawer_tab = "sched"   # sched | line | lint | term
        # Разворот дока: "" или "dock". Не прячет редактор — отдаёт доку
        # больше высоты и добавляет то, чему в трети экрана места нет
        # (вторую решётку рядом, полные тексты замечаний, журнал сессии).
        self.zoom = ""
        #: Высота дока в строках, поставленная человеком; None — из CSS.
        #: Живёт на сессию: экран установлен одним экземпляром, и уход в
        #: ЯДРО с возвратом высоту не сбрасывает.
        self.dock_h: int | None = None
        #: Высота на момент начала перетаскивания (см. DockSplitter).
        self._drag_h: int | None = None
        #: Что агент делал перед ответами — трасса развёрнутого блока.
        self.ai_actions: list[str] = []
        #: Проводник справа: открыт ли, где стоит и что ищем.
        self.explorer_shown = False
        #: Чего человек ХОЧЕТ от колонок — отдельно от того, что влезло.
        self._want_explorer = False
        self._want_side = False
        self.explorer_dir = Path.cwd()
        self.explorer_query = ""
        #: На какой строке проводника стоит выделение (стрелки в поиске).
        self._explorer_at = 0
        #: Где недавно были — чтобы вернуться одним нажатием.
        self._explorer_hist: list[str] = []
        #: Отложенный поиск: ждём паузы в наборе (см. on_input_changed).
        self._find_timer = None
        #: Чем кончился обход, если кончился не сам собой (см. _find_rows).
        self._find_cut = ""
        #: Какая вкладка была открыта до АГЕНТА — про неё он и объясняет.
        self._prev_tab = ""
        #: Тема фактов для агента, снятая в момент его открытия.
        self._ai_from = "code"
        #: Просили показать расписание точного поиска, пока его не было:
        #: переключимся на него, когда прогон закончится (см. _sched_view).
        self._want_orc = False
        #: Файл каталога, у которого нажали ✕ и который ждёт подтверждения.
        #: Удаление необратимо, поэтому спрашиваем — но не модальным окном
        #: поверх работы, а двумя строками в самом каталоге, там же, где
        #: нажали.
        self._to_delete: str = ""


    # --- раскладка --------------------------------------------------------
    #
    # Каркас собран здесь целиком, а не взят у `ModeScreen`: строки ввода в
    # доке снизу нет, она живёт вкладкой ВЫВОД.
    #
    # Один экран и пристыкованные окна — как в IDE:
    #
    #     шапка режима                                        1 строка
    #     полоса файлов: какой буфер открыт                   1 строка
    #     РЕДАКТОР                                            всё остальное
    #     ── волосок ──
    #     расписание │ разбор │ замечания │ вывод             1 строка вкладок
    #     содержимое выбранной вкладки                        ~треть экрана
    #     строка состояния                                    1 строка
    #     подсказки клавиш                                    1 строка
    #
    # ОДНО окно снизу, а не два. Пока их было два (расписание отдельной
    # панелью и выдвижной ящик под ней), редактор оказывался самой маленькой
    # областью экрана, а строка состояния висела между ними — посреди
    # экрана, где строке состояния делать нечего.
    #
    # Рамок нет ни у одного блока. Три панели в рамках стоили шесть строк
    # только на бордюры и печатали свои имена капсом там, где место нужно
    # содержимому: имя вкладки уже написано в полосе вкладок, и второй раз
    # его повторять незачем. Границ ровно две — волосок над доком и подложка
    # строки состояния.

    def compose(self):
        # ОДНА верхняя строка на всё: марка, вкладки открытых файлов и
        # числа справа. Строк было две — шапка режима и полоса файлов, —
        # и они говорили одно и то же дважды: «КОД редактор» дублировало
        # то, что и так видно (в окне код), а «15→8 т. · 15 оп.» стояло
        # ещё и в строке состояния внизу. Одно число в двух местах на
        # экране — это не подстраховка, а шум.
        yield FileStrip(id="code-head")
        with Horizontal(id="code-body"):
            # Каталог слева: примеры машины и настоящие .s из репозитория.
            # ЗАКРЫТ по умолчанию (^B открывает). Открытым он отбирал у кода
            # двадцать колонок навсегда, чтобы показать восемь имён и полтора
            # экрана пустоты под ними — а нужен он ровно дважды: в первую
            # минуту знакомства и когда открываешь второй файл.
            with Vertical(id="code-side"):
                # Шапка окна — как у полосы вкладок дока. Прокрутка
                # живёт ВНУТРИ, под шапкой: имя окна не должно уезжать
                # вместе с содержимым, иначе через два оборота колеса
                # непонятно, на что смотришь.
                yield Static(id="side-head", classes="panel-head")
                yield VerticalScroll(id="code-side-list", can_focus=False)
            yield AsmArea(id="code-edit")
            # ПЕРВЫЙ ЭКРАН. Виден, пока человек ничего не принёс, и уходит
            # с первой же разобранной операцией.
            #
            # Заведён по единственной жалобе, которую нечем крыть: владелец
            # проекта спросил «что это вообще за окно и что тут делать».
            # Если это спрашивает тот, кто инструмент писал, то открывший его
            # впервые не поймёт тем более. Экран не объяснял себя нигде:
            # подсказки внизу говорят про клавиши, но не про то, зачем сюда
            # пришли.
            yield Static(id="code-hello")
            # ПРОВОДНИК справа. ЗАКРЫТ по умолчанию (^E открывает, ▐ в
            # верхней полосе переключает).
            #
            # АЛЬФА, к следующему заходу — см. docs/REDESIGN.md. Здесь он
            # решает ровно одну задачу, зато главную: инструмент про то, что
            # человек приносит СВОЙ `.s` от lcc, а принести его до сих пор
            # можно было двумя способами — положить в рабочий каталог или
            # знать `/code load`. Поиск по имени убирает этот барьер.
            #
            # Закрыт по умолчанию не из скромности: файловый менеджер есть в
            # любом редакторе и ничем не отличает этот инструмент от чужого.
            # Постоянная колонка папок отбирала бы ширину у планировщика,
            # ради которого экран и открывают.
            with Vertical(id="code-explorer"):
                yield Static(id="explorer-head", classes="panel-head")
                yield Horizontal(Static(" ⌕ ", id="explorer-mark"),
                                 Input(placeholder="имя файла или папки",
                                       id="explorer-find"),
                                 id="explorer-search")
                # can_focus=False: по списку ходят стрелками ИЗ строки
                # поиска, и фокус ему не нужен. Фокусируемым он забирал его
                # себе при перемонтаже детей — а список пересобирается на
                # каждый набранный знак, и первая же буква уезжала в код.
                yield VerticalScroll(id="explorer-list", can_focus=False)

            # Колонки агента справа здесь БОЛЬШЕ НЕТ. Она показывала ровно то
            # же, что вкладка АГЕНТ нижнего дока: тот же разговор
            # (`session.dialog`), те же факты буфера. Два окна в одно и то же
            # — это не два способа работать, а лишний вопрос «в котором из них
            # я сейчас спрашиваю». Осталась вкладка: у неё вся ширина дока,
            # разворот на весь экран по 2×клику и своя строка вопроса.
            #
            # ^G и кнопка ▐ в верхней полосе открывают её же.

        # --- нижний док -----------------------------------------------
        # Волосок над доком — отдельным виджетом, а не бордюром дока: за
        # бордюр не потянешь, а высоту дока ставит человек, а не проценты.
        yield DockSplitter(id="dock-split")

        with Vertical(id="code-dock"):
            with DockTabs(id="dock-tabs"):
                for key, (label, _box, tool_id, _topic) in self.TABS.items():
                    yield Tool(label, f"dock-{key}", self.TAB_TIPS[key],
                               id=tool_id.lstrip("#"))
                # Живой итог вкладки — справа в той же строке: сколько
                # тактов, сколько ошибок, сколько коммитов. Раньше это был
                # заголовок рамки, и на каждую цифру уходила целая рамка.
                yield Static(id="dock-note")
                # Волосок между итогом и переключателем вида. Без него в
                # одной строке подряд стояли три разные вещи — имена вкладок,
                # живой итог («15 т.») и две кнопки-тумблера, — и полоса
                # читалась как один ряд кнопок, где часть почему-то не
                # нажимается.
                yield Static("│", id="dock-sep")
                # Переключатель расписания — правыми кнопками полосы
                # вкладок, как настройки инструментального окна в IDE.
                # Своей строки он не стоит: она была третьим рядом подряд.
                yield Tool("как написано", "sched-src",
                           "расписание из самого буфера", id="tab-src")
                yield Tool("оракул", "sched-orc",
                           "расписание точного поиска (F5)", id="tab-orc")

            yield Horizontal(
                # cell_padding=0: шесть каналов и так впритык к ширине
                # колонки, а по умолчанию DataTable добавляет по два
                # пробела на клетку — канал ,5 уезжал за край.
                Vertical(DataTable(id="code-grid", cursor_type="cell",
                                   zebra_stripes=False, cell_padding=0,
                                   fixed_columns=1),
                         id="code-grid-wrap"),
                Vertical(Static(id="code-grid-orc-head"),
                         DataTable(id="code-grid-orc", cursor_type="cell",
                                   zebra_stripes=False, cell_padding=0,
                                   fixed_columns=1),
                         id="code-grid-orc-wrap"),
                # Разбор решётки (загрузка портов, «что переставить») — ТОЛЬКО
                # в развороте дока по F11. В трети экрана он отбирал у решётки
                # треть ширины, переносил свои строки на 34 колонках («т12 →
                # т5,» / «канал ,4») и вдобавок дублировал список перестановок,
                # который целиком лежит во вкладке ЗАМЕЧАНИЯ. Одно и то же в
                # двух вкладках сразу — это не два ответа, а один вопрос
                # «а это то же самое или другое?».
                VerticalScroll(Static(id="sched-side-body"), id="sched-side"),
                # Пустая решётка — самый частый первый экран (буфер не
                # разобрался, или каналы спорят с моделью), и до сих пор она
                # была просто пустым прямоугольником в треть экрана: вкладка
                # подписана «расписание», а расписания нет и почему — молчок.
                # Прямоугольник, который ничего не говорит, дороже строки,
                # которая говорит.
                Static(id="sched-empty"),
                id="dock-sched")

            # РАЗБОР: такт под курсором, его цепочка зависимостей и каталог
            # всех тактов буфера. Прежде это был отдельный РЕЖИМ и отдельная
            # колонка разворота редактора — два места под один и тот же
            # углублённый просмотр того, что и так на экране.
            yield Horizontal(
                VerticalScroll(Static(id="code-line-info"),
                               Static(id="code-chain-body"),
                               id="dock-line-col"),
                VerticalScroll(id="dock-bundles"),
                # Третья колонка — только в развороте: числа участка и
                # машина, по которой они посчитаны. В свёрнутом виде их
                # незачем повторять (числа стоят в строке состояния), а в
                # развороте разбор без них неполон: «такт пуст» и «канал
                # принимает ADD MUL» — это утверждения ПРО МАШИНУ, и
                # проверить их можно только рядом с её профилем.
                VerticalScroll(Static(id="line-side-body"), id="line-side"),
                id="dock-line")

            yield VerticalScroll(id="dock-lint")

            yield Vertical(
                # Мостик ПРЯМО во вкладке: выбрал прогон в истории —
                # отправил в другой режим двумя кликами.
                BridgeRow(prefix="dbridge", id="drawer-bridge"),
                Console(id="console", runs=self.app.session.journal_runs),
                ConsoleJournal(id="journal"),
                PromptBar(self.mode, self.placeholder,
                          list(self.app.commands) + self.extra_commands(),
                          hint=self.hint, id="prompt"),
                id="dock-term")

            # ЯДРО — консоль интерпретатора, аналог Python Console в IDE.
            # Было отдельным режимом на целый экран; его ценность в одном —
            # собрать граф, не умея писать ассемблер, — и целого экрана она
            # не стоит. Машина одна на сессию, поэтому имена и память здесь
            # те же самые, что в полноэкранном ЯДРЕ.
            # АГЕНТ вкладкой: разговор во всю ширину дока. Столбец справа,
            # с которого начинали, рвал ответ на каждом слове (34 клетки) и
            # показывал ту же переписку — держать оба смысла не было.
            #
            # В РАЗВОРОТЕ (2×клик по вкладке) у него появляется то, чему в
            # восьми строках места нет: колонка «что видит агент» с фактами
            # буфера, трасса его действий, готовые вопросы про этот участок и
            # кнопки очистки с повтором. Полный экран — это не «то же самое
            # покрупнее», а больше инструментов; что показывать, решает CSS
            # по классу zoom-dock, а не код.
            yield Horizontal(
                Vertical(
                    Horizontal(
                        Tool("↻ повторить", "agent-repeat",
                             "задать последний вопрос ещё раз"),
                        Tool("очистить", "agent-clear",
                             "стереть переписку — во всех трёх окнах сразу"),
                        Tool("что видит агент", "agent-facts",
                             "перечитать факты буфера в колонку справа"),
                        id="agent-tools"),
                    VerticalScroll(Static(id="agent-log"), id="agent-log-box"),
                    ItemGrid(id="agent-asks", min_column_width=36),
                    Horizontal(Static(" ❯ ", id="agent-mark"),
                               Input(placeholder="спросите обычным языком — "
                                     "агент отвечает по посчитанным числам",
                                     id="agent-input"),
                               id="agent-prompt"),
                    id="agent-main"),
                VerticalScroll(
                    Static("  что видит агент", classes="panel-head"),
                    Static(id="agent-seen"),
                    Static("  трасса", classes="panel-head"),
                    Static(id="agent-trace"),
                    id="agent-side"),
                id="dock-agent")

            yield Horizontal(
                Vertical(
                    RichLog(id="core-log", wrap=False, markup=False,
                            highlight=False, auto_scroll=True),
                    # Готовые ядра и глаголы — ВНИЗУ, над строкой ввода, и
                    # только в развороте. Сверху они читались как шапка окна
                    # и отбирали у ленты первые строки — то есть закрывали
                    # ответ ради подсказки, что можно спросить. Внизу они
                    # стоят там же, где рука: рядом с полем, куда это и
                    # попадёт по клику.
                    ItemGrid(id="core-chips", min_column_width=9),
                    Horizontal(Static(" ❯ ", id="core-mark"),
                               Input(placeholder="a = 10   ·   t = a*2   "
                                     "·   sum 8   ·   go", id="core-input"),
                               id="core-prompt"),
                    id="core-log-box"),
                VerticalScroll(Static(id="core-state"), id="core-state-col"),
                id="dock-core")

        # --- подвал: ОДНА строка состояния, в самом низу ------------------
        # Слева курсор (кликом раскрывается разбор), справа итог по буферу,
        # и два пункта-лаунчера — замечания с живым счётчиком ошибок и вывод
        # со счётчиком коммитов. Любой открывает свою вкладку одним кликом.
        with Vertical(id="code-foot"):
            with Horizontal(id="code-status-row"):
                yield LineChip(id="code-line-chip")
                # Клавиши — здесь же, а не отдельной полосой под строкой
                # состояния. Двух строк подвала на экране, где спорят за
                # место редактор и док, не бывает: принятое решение —
                # «ОДНА строка состояния, в самом низу», а полоса подсказок
                # была вторым подвалом под первым.
                yield Static(id="code-keys")
                yield Static(id="code-status")
                yield DrawerChip(
                    "lint", "▲ 0",
                    "замечания машины: клик — вкладка ЗАМЕЧАНИЯ",
                    id="status-lint")
                yield DrawerChip(
                    "term", "git 0",
                    "git сессии — история прогонов и мостик между режимами: "
                    "клик — вкладка ВЫВОД",
                    id="status-term")

        yield Suggest(id="suggest")

    def on_ready(self) -> None:
        self._load_layout()
        # Прочитать раскладку мало — её надо ПРИМЕНИТЬ. `_load_layout`
        # только заполняет поля (`drawer_open`, `drawer_tab`), а показывает
        # и прячет виджеты `_draw_drawer`: он гасит док, ручку и — в цикле по
        # TABS — все вкладки, кроме текущей. Без этого вызова сохранённое
        # «док закрыт» доезжало до поля, но не до экрана: полоса вкладок
        # оставалась нарисованной, содержимого расписания не было, а сквозь
        # неё проступали сразу АГЕНТ и ЯДРО — ни одна вкладка не была
        # спрятана. Ловилось после любого F12 с последующим перезапуском.
        self._draw_drawer()
        self._fit_columns(self.size.width or 120)
        edit = self.query_one("#code-edit", AsmArea)
        if not self.app.session.code_text:
            self.app.session.code_text = example_text("slots") or FALLBACK
            self._example = "slots"
        # Открытый буфер сессии становится первой вкладкой. Приезжает он
        # по-разному: пример по умолчанию, `/code load`, вставка из другого
        # режима, «в код» из журнала — а вкладка нужна всем одинаково.
        self.files = [{"name": self._buffer_name(),
                       "path": self.app.session.code_path,
                       "text": self.app.session.code_text,
                       "example": self._example}]
        self.file_i = 0
        edit.text = self.app.session.code_text
        # Подсказка у строки курсора: без неё кликабельность не видна ни
        # разу — а это вход в разбор такта.
        self.query_one("#code-line-chip", LineChip).tooltip = (
            "строка под курсором: такт, каналы, замечания\n"
            "клик — полный разбор (вкладка РАЗБОР снизу)")
        edit.tooltip = ("▷ у строки под курсором — прогнать буфер (F5)\n"
                        "тN в гуттере — в каком такте операция выдаётся\n"
                        "тN→M — точный поиск кладёт её в такт M")
        self._draw_side()
        self._seed_console()
        self._seed_core()
        self._take_pending_note()
        self.reparse()
        edit.focus()

    # --- открытые файлы ----------------------------------------------------

    def _buffer_name(self, rec: dict | None = None) -> str:
        """Как назвать буфер во вкладке.

        Имя выводится из источника: файл — по имени файла, пример — по имени
        примера. У своего участка источника нет, выводить не из чего, и тогда
        единственное его имя — то, что уже стоит в записи: так названа
        «+ новая вкладка», так же лежит имя после F2.

        Раньше `rec` не передавался и последняя ветка возвращала «буфер» всем
        безымянным. А зовут отсюда `_stash_current`, то есть при каждом уходе
        со вкладки: стоило завести вторую, как первая теряла имя.
        """
        path = self.app.session.code_path
        if path:
            return path.rsplit("/", 1)[-1]
        if self._example:
            return self._example + ".s"
        if rec is not None and rec.get("name"):
            return rec["name"]
        return "буфер"

    def _stash_current(self) -> None:
        """Сохранить текст и имя активной вкладки перед уходом с неё."""
        if not self.files:
            return
        rec = self.files[self.file_i]
        rec["text"] = self.query_one("#code-edit", AsmArea).text
        rec["path"] = self.app.session.code_path
        rec["example"] = self._example
        rec["name"] = self._buffer_name(rec)

    def open_file(self, text: str, name: str, path: str = "",
                  example: str = "") -> None:
        """Открыть текст новой вкладкой — или перейти на уже открытую.

        Второй раз тот же файл вкладкой НЕ открывается: две вкладки с одним
        именем и разным содержимым — способ потерять правки, а не удобство.
        """
        self._stash_current()
        for i, rec in enumerate(self.files):
            if rec["name"] == name:
                self.select_file(i)
                return
        self.files.append({"name": name, "path": path, "text": text,
                           "example": example})
        self.select_file(len(self.files) - 1, stash=False)

    def select_file(self, index: int, stash: bool = True) -> None:
        if not (0 <= index < len(self.files)):
            return
        if stash:
            self._stash_current()
        self.file_i = index
        rec = self.files[index]
        edit = self.query_one("#code-edit", AsmArea)
        edit.replace(rec["text"], (0, 0), edit.document.end)
        self.app.session.code_text = rec["text"]
        self.app.session.code_path = rec["path"]
        self._example = rec["example"]
        # Числа точного поиска принадлежат ТОМУ буферу, из которого их
        # считали. Переключение вкладки — не правка, но результат чужой:
        # оставить его значило бы показывать резерв одного файла на коде
        # другого.
        self.base = self.orc = self.met = None
        self.findings = []
        self.run_text = ""
        self.reparse()
        edit.focus()

    def close_file(self, index: int) -> None:
        """Закрыть вкладку. Последнюю не закрываем — правят всегда что-то."""
        if len(self.files) <= 1 or not (0 <= index < len(self.files)):
            return
        if index == self.file_i:
            self._stash_current()
        self.files.pop(index)
        self.select_file(min(self.file_i if index > self.file_i
                             else self.file_i - 1, len(self.files) - 1),
                         stash=False)

    def on_file_strip_picked(self, event) -> None:
        event.stop()
        self.select_file(event.index)

    def on_file_strip_closed(self, event) -> None:
        event.stop()
        self.close_file(event.index)

    def on_side_item_picked(self, event) -> None:
        """Клик по каталогу слева — файл открывается вкладкой."""
        event.stop()
        key = event.key
        if key.startswith("hist:"):
            self.explorer_dir = Path(key[5:])
            self.explorer_query = ""
            self._explorer_at = 0
            try:
                self.query_one("#explorer-find", Input).value = ""
            except Exception:
                pass
            self._draw_explorer()
            return
        if key.startswith("dir:"):
            # Заход в папку сбрасывает поиск: искали в прошлом каталоге, и
            # показывать те же находки в новом — врать про то, где они.
            self._remember_dir(self.explorer_dir)
            self.explorer_dir = Path(key[4:])
            self.explorer_query = ""
            self._explorer_at = 0
            try:
                self.query_one("#explorer-find", Input).value = ""
            except Exception:
                pass
            self._draw_explorer()
            return
        if key.startswith("new:"):
            self._new_buffer(key[4:])
            return
        if key == "del:no":
            self._to_delete = ""
            self._draw_explorer()
            return
        if key == "del:yes":
            self._delete_file(self._to_delete)
            return
        if key == self._to_delete:
            # Повторный клик по тому же файлу — отмена: передумать должно
            # быть так же дёшево, как начать.
            self._to_delete = ""
            self._draw_explorer()
            return
        if key == "buf:new":
            self._new_buffer()
            return
        if key.startswith("buf:"):
            self.select_file(int(key[4:]))
            self._draw_side()
            return
        if key.startswith("ex:"):
            name = key[3:]
            text = example_text(name)
            if text is not None:
                self.open_file(text, f"{name}.s", example=name)
            return
        # Клик по ✕ (правый край строки) — спросить про удаление.
        if getattr(event, "at_x", -1) >= self.DELETE_X and self._deletable(key):
            self._to_delete = key
            self._draw_explorer()
            return
        # Файл рядом: путь запоминаем, чтобы ^S писал туда.
        try:
            text = Path(key).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            con = self.console
            if con is not None:
                con.note(f"  {key}: {exc}", "error")
            return
        self.open_file(text, key.rsplit("/", 1)[-1], path=key)

    def _new_buffer(self, kind: str = "s") -> None:
        """Пустая вкладка выбранного типа.

        Имя даётся сразу и по порядку («участок 2»), а не спрашивается: пока
        в файле ничего нет, называть нечего, а диалог на пустом месте —
        лишний шаг. Переименовать можно в любой момент по F2.
        """
        suffix, _label, base, seed = next(
            (k for k in self.FILE_KINDS if k[0] == kind), self.FILE_KINDS[0])
        n = 1
        used = {rec["name"] for rec in self.files}
        while f"{base} {n}.{suffix}" in used:
            n += 1
        self.open_file(seed, f"{base} {n}.{suffix}")
        self._draw_side()
        self.query_one("#code-edit", AsmArea).focus()

    def _is_asm(self, name: str = "") -> bool:
        """Разбирается ли этот буфер планировщиком.

        Проверка по имени, а не по содержимому: расширение — это то, что
        человек СКАЗАЛ про файл, и спорить с ним догадкой по тексту значит
        однажды разобрать заметку как ассемблер и выдать на неё замечания.
        """
        if not name:
            name = self.files[self.file_i]["name"] if self.files else ""
        low = name.lower()
        return (not low) or low.endswith(self.ASM_SUFFIXES)

    def action_rename_buffer(self) -> None:
        """F2 — переименовать текущую вкладку.

        Имя вкладки — единственное, чем участки различаются на экране, когда
        их несколько. «участок 2.s» рядом с «участок 3.s» не различает
        ничего, поэтому переименование обязано быть под рукой, а не через
        сохранение в файл.
        """
        if not self.files:
            return
        # Модального окна ввода в проекте нет, и заводить его ради одного
        # имени незачем: строка команд уже есть, у неё история и каталог.
        # F2 просто открывает её с готовым «/rename » и текущим именем —
        # остаётся поправить.
        self.open_drawer("term")
        bar = self.query_one("#prompt", PromptBar)
        bar.focus_input()
        bar.set_value("/rename " + self.files[self.file_i]["name"])

    def _rename_buffer(self, name: str) -> None:
        name = (name or "").strip()
        if not name or not self.files:
            return
        if any(i != self.file_i and rec["name"] == name
               for i, rec in enumerate(self.files)):
            con = self.console
            if con is not None:
                con.note(f"  вкладка «{name}» уже есть", "error")
            return
        rec = self.files[self.file_i]
        was = rec["name"]
        rec["name"] = name
        # Путь снимаем: имя разошлось с файлом, и ^S не должен молча писать
        # в старый — это были бы чужие правки под чужим именем. Пример — по
        # той же причине: иначе имя вывелось бы из него обратно. И то же
        # самое в сессии: активная вкладка отражена там, а `_stash_current`
        # читает путь именно оттуда — оставить его значило бы вернуть старое
        # имя на первом же переключении вкладок.
        rec["path"] = rec["example"] = ""
        self._example = ""
        self.app.session.code_path = ""
        self.refresh_context()
        self._draw_side()
        con = self.console
        if con is not None:
            con.note(f"  вкладка «{was}» → «{name}»", "success")

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
            # В строке поиска проводника стрелки и Enter нужны всегда: там
            # они ходят по находкам, а подсказки мнемоник в ней не бывает.
            if self._explorer_has_focus():
                return True
            sug = self.suggest
            return bool(sug is not None and sug.display)
        return True

    @property
    def suggest(self):
        try:
            return self.query_one("#suggest", Suggest)
        except Exception:
            return None

    def _focus_find(self) -> None:
        """Курсор в строку поиска проводника, если она на экране."""
        try:
            self.query_one("#explorer-find", Input).focus()
        except Exception:
            pass

    def _explorer_has_focus(self) -> bool:
        try:
            return self.query_one("#explorer-find", Input).has_focus
        except Exception:
            return False

    def action_suggest_up(self) -> None:
        # Стрелки принадлежат тому окну, где сейчас курсор: в строке поиска
        # проводника они ходят по находкам, в редакторе — по подсказке.
        if self._explorer_has_focus():
            self._explorer_step(-1)
            return
        self.suggest.step(-1)

    def action_suggest_down(self) -> None:
        if self._explorer_has_focus():
            self._explorer_step(1)
            return
        self.suggest.step(1)

    def action_suggest_take(self) -> None:
        # Enter в строке поиска открывает выделенное. Перехватывать его здесь
        # приходится потому, что биндинг подсказки объявлен priority=True и
        # забирает клавишу раньше поля ввода: без этой ветки Enter в
        # проводнике не делал ничего.
        if self._explorer_has_focus():
            self._open_selected()
            return
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

    #: Строка, начатая со слэша, — набор команды, а не кода. В ассемблере
    #: e2k строка со слэша не начинается никогда (комментарий это «!»),
    #: поэтому спутать нельзя.
    #: Цифры в имени тоже считаются: заготовка `/par4` без них не находилась
    #: вовсе — список молчал, и жест выглядел как неработающий.
    _CMD_TAIL = re.compile(r"^\s*/([a-zа-я0-9_]*)$", re.I)

    def _suggest_items(self, line: str, row: int):
        model = self.app.session.model()

        # Команды — первым делом: «/» люди жмут, ожидая список, как в любом
        # современном редакторе. Раньше каталог жил только на ^P, про который
        # надо знать, и найти /gen или /fill было неоткуда.
        m = self._CMD_TAIL.match(line)
        if m:
            return self._cmd_items(m.group(1))

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

    #: Команды, которые ПИШУТ в буфер. Только они и место здесь: список по
    #: «/» всплывает посреди набора кода, и «/ai — состояние языковой
    #: модели» отвечает на вопрос, которого человек в этот момент не задавал.
    #: Всё остальное никуда не делось — оно на ^P, где команды и живут.
    WRITES_BUFFER = ("gen", "fill", "example", "rewrite", "load", "code")

    def _cmd_items(self, prefix: str):
        """Что предложить после «/» в тексте: заготовки, потом команды.

        Заготовки первыми, потому что они и есть ответ на «как это написать»:
        вставляют готовый кусок ассемблера, который остаётся поправить.
        Команды — те, что пишут в буфер; остальные (состояние модели, сводные
        таблицы) сюда не идут, см. WRITES_BUFFER.
        """
        low = prefix.lower()
        rows: list[tuple[str, str, str, str]] = []
        for name, note, kind in self.SNIPPETS:
            if name.startswith(low):
                # Текст собирается ПРИ ПОКАЗЕ: свободные регистры зависят от
                # того, что уже в буфере, а паузы — от модели машины.
                rows.append((self._snippet_text(kind), "/" + name, note,
                             "accent2"))
        # Пока ничего не набрано, заготовки не должны выдавить команды: в
        # окне помещается восемь строк, а заготовок семь — и `/fill`,
        # `/example`, `/rewrite` пропадали из виду совсем. С первой же буквы
        # список фильтруется, и предел снимается.
        if not low:
            rows = rows[:5]

        cmds = list(self.app.commands) + self.extra_commands()
        seen: set[str] = set()
        order = self.WRITES_BUFFER
        for cmd in sorted(cmds, key=lambda c: (
                order.index(c["name"]) if c["name"] in order else 99,
                c["name"])):
            name = cmd["name"]
            if name not in order or name in seen or not name.startswith(low):
                continue
            seen.add(name)
            arg = cmd.get("arg", "")
            rows.append((name[len(prefix):] + (" " if arg else ""),
                         "/" + name + (" " + arg if arg else ""),
                         cmd.get("help", ""), "text"))
        return rows[:12]

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
        insert, _label, _note, role = sug.items[sug.index]
        if role == "accent2" and insert.startswith("{"):
            # Заготовка участка. Набранное «/имя» стираем: это был запрос, а
            # не текст программы, и оставлять его в ассемблере нельзя —
            # строка со слэша не разберётся и даст замечание.
            row, col = edit.cursor_location
            line = edit.document.get_line(row)[:col]
            slash = line.rfind("/")
            if slash >= 0:
                edit.replace("", (row, slash), (row, col))
            edit.insert(insert)
        else:
            edit.insert(insert)
        sug.hide()
        return True

    # --- нижний док --------------------------------------------------------
    #
    # Имена методов оставлены прежними (`open_drawer`, `drawer_tab`): это
    # то же самое пристыкованное окно, только теперь оно одно и расписание
    # живёт в нём вкладкой, а не отдельной панелью над ним.

    def action_toggle_drawer(self) -> None:
        if self.drawer_open:
            self.close_drawer()
        else:
            self.open_drawer(self.drawer_tab)

    def action_slash(self) -> None:
        """«/» в редакторе печатается, а список команд всплывает у курсора.

        Раньше каталог жил только на ^P, про который надо знать, и найти
        /gen или /fill было неоткуда. Теперь строка, начатая со слэша,
        подхватывается тем же всплывающим списком, что дополняет мнемоники:
        видно имя, аргументы и пояснение, Enter вставляет. В ассемблере e2k
        строка со слэша не начинается никогда, поэтому спутать набор команды
        с набором кода нельзя.

        «/» в любом поле ввода тоже ПЕЧАТАЕТСЯ, а не сносит команду.
        Биндинг приоритетный, поэтому клавиша доходит сюда раньше виджета:
        когда фокус в строке ввода, печатаем слэш сами в тот Input, где
        стоит курсор. Каталог при этом остаётся: на пустом поле это всё тот
        же «/» с палитрой, на непустом — допечатка к набранному.
        """
        edit = self.query_one("#code-edit", AsmArea)
        if edit.has_focus:
            # Слэш ПЕЧАТАЕТСЯ всегда, и каталог показывает всплывающий список
            # (см. _cmd_items) — прямо у курсора, как дополнение кода в IDE.
            # Перехватывать клавишу и открывать нижнюю панель было хуже вдвойне:
            # список команд уезжал вниз экрана, а набранное «/» пропадало, и
            # дописать «/gen 8 muls» одной строкой становилось нельзя.
            edit.insert("/")
            return
        # Фокус в поле ввода — печатать, а не открывать каталог заново.
        # Иначе набранный путь со слэшами (`/code load /home/.../a.s`)
        # сносился бы каждым «/» обратно до «/»: action_command() делал
        # set_value("/"), и от команды оставался только последний сегмент.
        try:
            focused = self.app.focused
        except Exception:
            focused = None
        if isinstance(focused, Input):
            try:
                self._clear_selection(focused)
                focused.insert_text_at_cursor("/")
            except Exception:
                try:
                    pos = focused.cursor_position or len(focused.value or "")
                    val = focused.value or ""
                    focused.value = val[:pos] + "/" + val[pos:]
                    focused.cursor_position = pos + 1
                except Exception:
                    pass
            return
        # Фокус не во вводе (решётка, замечания): открыть каталог, не теряя
        # уже набранное. Пустое поле — классический «/» с палитрой.
        self.open_drawer("term")
        bar = self.query_one("#prompt", PromptBar)
        bar.focus_input()
        try:
            cur = bar.input.value or ""
        except Exception:
            cur = ""
        if not cur:
            bar.set_value("/")
            self._clear_selection(bar.input)
            # Фокус выделяет всё поле АСИНХРОННО, уже после этого метода:
            # синхронного снятия мало, первый знак всё равно заменил бы «/».
            try:
                self.call_after_refresh(self._clear_selection, bar.input)
            except Exception:
                pass
        else:
            try:
                self._clear_selection(bar.input)
                bar.input.insert_text_at_cursor("/")
            except Exception:
                bar.set_value(cur + "/")

    @staticmethod
    def _clear_selection(inp) -> None:
        """Снять выделение, оставив курсор где был.

        Фокус в Textual выделяет всё поле целиком: после ^P выделение —
        (0, 1) на префилле «/», и первый же набранный знак ЗАМЕНЯЕТ его.
        Из «/code load ...» получалось «code load ...» без ведущего слэша —
        команда переставала быть командой. set_value(cursor_position) само
        выделение не снимает, поэтому делаем это явно здесь, а не в общем
        PromptBar.set_value (точечный фикс, без затрагивания остальных).
        """
        try:
            from textual.widgets._input import Selection

            pos = inp.cursor_position or len(inp.value or "")
            inp.selection = Selection(pos, pos)
        except Exception:
            pass

    def action_command(self) -> None:
        """^P — док на вкладке ВЫВОД с уже введённым слэшем."""
        self.open_drawer("term")
        bar = self.query_one("#prompt", PromptBar)
        bar.focus_input()
        try:
            cur = bar.input.value or ""
        except Exception:
            cur = ""
        if not cur:
            bar.set_value("/")
            self._clear_selection(bar.input)
            # См. выше: выделение от фокуса приходит позже метода.
            try:
                self.call_after_refresh(self._clear_selection, bar.input)
            except Exception:
                pass
        else:
            # Непустое поле не трогаем: ^P — это «идти в строку», а не «стереть
            # набранное и начать заново». Снос здесь давал тот же эффект, что и
            # старый action_slash: путь со слэшами невозможно было дописать.
            # Выделение при этом снимаем, иначе первый знак заменит всё поле.
            self._clear_selection(bar.input)
            try:
                self.call_after_refresh(self._clear_selection, bar.input)
            except Exception:
                pass

    def open_drawer(self, tab: str) -> None:
        tab = tab if tab in self.TABS else "sched"
        # Откуда пришли в АГЕНТА — это и есть «на что человек смотрит».
        # Пока агент был колонкой справа, он смотрел на фокус: курсор в коде
        # — вопрос про код, фокус во вкладке — про её содержимое. Теперь он
        # сам вкладка и забирает фокус себе, поэтому предыдущую запоминаем.
        if tab == "agent" and self.drawer_tab != "agent":
            # Тему берём ЗДЕСЬ, пока фокус ещё не ушёл в строку вопроса:
            # мгновением позже «на что смотрит человек» уже не спросишь —
            # он смотрит на поле ввода агента.
            self._prev_tab = self.drawer_tab
            try:
                in_code = self.query_one("#code-edit", AsmArea).has_focus
            except Exception:
                in_code = True
            self._ai_from = ("code" if in_code
                             else self.TABS[self.drawer_tab][3])
        self.drawer_tab = tab
        self._save_layout()
        self.drawer_open = True
        self._draw_drawer()
        if self.drawer_tab == "term":
            self.query_one("#prompt", PromptBar).focus_input()
        elif self.drawer_tab == "core":
            self.query_one("#core-input", Input).focus()
        elif self.drawer_tab == "agent":
            self.query_one("#agent-input", Input).focus()

    def close_drawer(self) -> None:
        self.drawer_open = False
        self._save_layout()
        self._draw_drawer()
        self.query_one("#code-edit", AsmArea).focus()

    def _draw_drawer(self) -> None:
        """Показать нужную вкладку и убрать остальные.

        Здесь же пересчитываются признаки «этот блок развёрнут»: раньше их
        ставил только `set_zoom`, то есть смена РАЗВОРОТА. Но вкладку
        переключают и внутри разворота, и тогда признак оставался от
        прошлой: решётка считала ширину клетки как для одной решётки,
        а места ей досталось на половину экрана — два канала за краем.
        """
        self._sched_expanded = bool(self.zoom) and self.drawer_tab == "sched"
        self._lint_expanded = bool(self.zoom) and self.drawer_tab == "lint"
        self._console_expanded = bool(self.zoom) and self.drawer_tab == "term"
        dock = self.query_one("#code-dock", Vertical)
        dock.display = self.drawer_open
        self._apply_dock_height(dock)
        # Ручка живёт вместе с доком: тянуть границу спрятанного окна не за
        # что, а полоса под редактором осталась бы висеть ни к чему.
        self.query_one("#dock-split", DockSplitter).display = self.drawer_open
        # Класс на экране: в узком окне открытый док забирает высоту у
        # редактора умереннее, чем на широком.
        self.set_class(self.drawer_open, "drawer")
        for key, (_label, box, tool, _t) in self.TABS.items():
            self.query_one(box).display = key == self.drawer_tab
            self.query_one(tool, Tool).set_on(key == self.drawer_tab)
        # Переключатель расписания принадлежит одной вкладке и вне её не
        # висит: кнопка, которая ничего не делает, хуже отсутствующей.
        on_sched = self.drawer_tab == "sched"
        for tool_id in ("#tab-src", "#tab-orc"):
            self.query_one(tool_id, Tool).display = on_sched
        self.query_one("#dock-sep", Static).display = on_sched
        self._draw_journal()
        if self.drawer_tab == "sched":
            # Форма решётки зависит от разворота (см. _tall_grid), а
            # заполнялась она только при разборе и при смене разворота. Если
            # док развернули на другой вкладке и переключились сюда, решётка
            # оставалась в форме для маленького дока: такты уезжали вбок, а
            # под ними стояли тридцать пустых строк.
            self._draw_grids()
            if self.zoom:
                self.call_after_refresh(self._draw_grids)
        if self.drawer_tab == "lint":
            self._draw_lint()
        elif self.drawer_tab == "line":
            # Три секции вкладки: разбор такта под курсором и его цепочка
            # слева, каталог тактов всего буфера справа.
            line = self._cursor_line or 1
            self._draw_line_info(line)
            self._draw_chain(line)
            self._draw_bundles()
            self._draw_line_side()
        elif self.drawer_tab == "core":
            self._seed_core_chips()
            self._draw_core_state()
        elif self.drawer_tab == "agent":
            self._draw_dialog()
            self._draw_agent_extras()
        self._draw_dock_note()
        self.refresh_hints()

    def _draw_dock_note(self) -> None:
        """Итог открытой вкладки — справа в полосе вкладок.

        Раньше это была подпись рамки, и ради одной живой цифры («15 т.»,
        «3 ошибки», «7 коммитов») экран платил рамкой в две строки. Цифра
        осталась, рамка ушла.
        """
        try:
            note = self.query_one("#dock-note", Static)
        except Exception:
            return
        t = Text()
        dim = palette.role_hex("dim")
        if self.drawer_tab == "sched":
            t = self._sched_note()
        elif self.drawer_tab == "lint":
            errs = sum(1 for p in self.problems if p.severity == "error")
            if errs:
                t.append(f"{errs} {plural(errs, 'ошибка', 'ошибки', 'ошибок')} ",
                         style=palette.role_hex("error"))
            elif self.findings and not self._stale():
                k = len(self.findings)
                t.append(f"{k} {plural(k, 'находка', 'находки', 'находок')} ",
                         style=palette.role_hex("warning"))
            else:
                t.append("чисто ", style=palette.role_hex("success"))
        elif self.drawer_tab == "term":
            n = len(self.query_one("#console", Console).runs)
            if n:
                t.append(f"{n} {plural(n, 'коммит', 'коммита', 'коммитов')} ",
                         style=dim)
            else:
                t.append("пусто — F5 станет коммитом #1 ", style=dim)
        elif self.drawer_tab == "agent":
            t = self._dialog_note()
        elif self.drawer_tab == "core":
            ws = self.app.session.workspace()
            n = ws.graph_size()
            t.append(f"{len(ws.regs)} имён   ·   {n} "
                     f"{plural(n, 'операция', 'операции', 'операций')} "
                     f"в графе ", style=dim)
        else:
            n = self.parsed.bundles if self.parsed is not None else 0
            t.append(f"{n} {plural(n, 'команда', 'команды', 'команд')}"
                     f"   ·   стр.{self._cursor_line or 1} ", style=dim)
        note.update(t)

    # --- агент: вкладка дока, а не режим и не колонка ----------------------
    #
    # АГЕНТ занимал целый экран и четверть главного меню, хотя по замерам
    # проекта это его слабейшая часть: подсказка обученной модели оракулу
    # дала 5% даже с идеальной подсказкой, а интервальная нижняя граница —
    # 89% отсечённых узлов. Позиционирование «алгоритмы с ИИ, а не
    # наоборот» подтверждено числами, и место в интерфейсе должно совпадать
    # с этими числами.
    #
    # Поэтому здесь он — строка снизу, которая знает, на что человек
    # смотрит: фокус в редакторе значит вопрос про код, открытая вкладка —
    # вопрос про её содержимое. Отвечает НАСТОЯЩИЙ агент (тот же
    # `Agent.ask_stream`, что ведёт диалог в АГЕНТЕ), а не облегчённая
    # копия — см. `ModeScreen._panel_prompt_worker`.

    class _Subject:
        """Про что спрашивают. Подставляется вместо развёрнутой панели.

        `open_panel_prompt` ждёт объект с `topic` и `_title` — раньше им
        всегда была Panel. Панелей с рамками на этом экране не осталось, а
        механика справочника осталась и работает; отдавать ей две строки
        описания дешевле, чем заводить рамку ради совместимости.
        """

        def __init__(self, topic: str, title: str) -> None:
            self.topic = topic
            self._title = title

    #: Сколько файлов показываем в поиске и как глубоко ищем. Пределы не
    #: от бедности: рекурсивный обход по большому дереву в интерфейсе — это
    #: замерший экран, а список на тысячу имён не читает никто.
    FIND_LIMIT = 60
    FIND_DEPTH = 4

    #: Сколько записей разрешено ПРОСМОТРЕТЬ за один поиск. Предел по
    #: находкам от зависания не спасает: под каталогом без единого
    #: совпадения обход всё равно доходит до конца.
    FIND_SCAN = 4000

    #: Куда не спускаемся. `.venv` в этом проекте — 35 681 путь из 40 497,
    #: то есть почти весь обход уходил в чужие библиотеки, чтобы затем всё
    #: выбросить фильтром «имя начинается с точки». Своего кода человек там
    #: не ищет.
    SKIP_DIRS = frozenset({"__pycache__", "node_modules", "site-packages",
                           "dist-info", "egg-info"})

    #: Сколько записей каталога показываем без поиска.
    LIST_LIMIT = 300

    #: Пауза перед поиском. Обход запускается не на каждую букву, а когда
    #: набор остановился: «slots» — это пять обходов вместо одного.
    FIND_DEBOUNCE = 0.2

    #: С какой колонки в строке проводника начинается ✕ удаления. Клик левее
    #: — это «открыть файл»: удаление не должно случаться от промаха.
    DELETE_X = 24

    #: Сколько клеток редактору нужно, чтобы в нём можно было работать.
    #: Строка ассемблера e2k — это мнемоника с каналом и три регистра
    #: (`muls,0 %r10, %r11, %r20`), плюс гуттер с номером и тактом: короче
    #: шестидесяти клеток строки начинают переноситься, и код перестаёт
    #: читаться как код.
    EDIT_MIN_W = 60

    def action_toggle_explorer(self) -> None:
        """^E — проводник справа. Второе нажатие убирает.

        Открывает не напрямую, а через `_fit_columns`: тот же путь, что у
        изменения размера окна. Иначе клавиша ставила колонку в обход
        правила «редактору не меньше EDIT_MIN_W» — и на узком окне открывала
        её поверх здравого смысла.
        """
        self._want_explorer = not self.explorer_shown
        self._fit_columns(self.size.width or 120)
        self._save_layout()
        if self.explorer_shown:
            self._draw_explorer()
            # Фокус ставится ДВАЖДЫ, и это не перестраховка ради красоты.
            # Колонку только что показали (`display = True`): пока Textual
            # не перерисовал экран, она считается невидимой, а `focus()` на
            # невидимом виджете молча не срабатывает — и первые набранные
            # буквы уходили в редактор, то есть прямо в код. Немедленный
            # вызов срабатывает, когда колонка уже была видна; отложенный —
            # когда её только что открыли.
            self._focus_find()
            self.call_after_refresh(self._focus_find)
        else:
            self.query_one("#code-edit", AsmArea).focus()
            self._say_no_room("проводнику", 30, self._want_explorer)
        self.refresh_context()
        self.refresh_hints()

    def action_toggle_side(self) -> None:
        """^B — колонка вкладок слева. Запоминаем НАМЕРЕНИЕ, а не факт.

        Факт может разойтись с намерением: на узком окне колонки уступают
        редактору (см. `_fit_columns`). Возвращать их при расширении надо
        ровно те, что человек открывал, — иначе окно решает за него.
        """
        self._want_side = not self.side_shown
        self._fit_columns(self.size.width or 120)
        self._save_layout()
        if not self.side_shown:
            self._say_no_room("колонке вкладок", 22, self._want_side)
        self.refresh_hints()
        self.refresh_context()

    def _say_no_room(self, what: str, need: int, wanted: bool) -> None:
        """Объяснить, почему колонка не открылась.

        Нажатие, которое молча ничего не делает, читается как поломка
        клавиши. Здесь оно означает «места нет», и это надо сказать.
        """
        if not wanted:
            return
        con = self.console
        if con is None:
            return
        width = self.size.width or 120
        con.note(f"  {what} нужно {need} клеток, а окну хватает "
                 f"{width}: редактору оставлено {self.EDIT_MIN_W}", "warning")

    #: Где живёт раскладка между запусками. Рядом с ключом модели
    #: (`~/.config/nex/key`) — у инструмента уже есть этот каталог, заводить
    #: второй незачем.
    LAYOUT_FILE = Path.home() / ".config" / "nex" / "layout.json"

    def _save_layout(self) -> None:
        """Запомнить раскладку: высоту дока, колонки, открытую вкладку.

        Не украшение: человек ставит высоту дока под свою работу — и терял
        её при каждом запуске. Настройка, которую надо задавать заново
        каждый день, перестаёт быть настройкой.
        """
        import json

        try:
            self.LAYOUT_FILE.parent.mkdir(parents=True, exist_ok=True)
            self.LAYOUT_FILE.write_text(json.dumps({
                "dock_h": self.dock_h,
                "drawer_open": self.drawer_open,
                "drawer_tab": self.drawer_tab,
                "side": self._want_side,
                "explorer": self._want_explorer,
                "dirs": self._explorer_hist,
            }, ensure_ascii=False), encoding="utf-8")
        except OSError:
            # Не смогли записать — не беда: раскладка вернётся к умолчанию.
            # Падать из-за настройки, без которой инструмент работает, нельзя.
            pass

    def _load_layout(self) -> None:
        """Поднять раскладку прошлой сессии, если она была."""
        import json

        try:
            data = json.loads(self.LAYOUT_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(data, dict):
            return
        height = data.get("dock_h")
        if isinstance(height, int) and self.DOCK_MIN <= height <= 60:
            self.dock_h = height
        tab = data.get("drawer_tab")
        if tab in self.TABS:
            self.drawer_tab = tab
        if isinstance(data.get("drawer_open"), bool):
            self.drawer_open = data["drawer_open"]
        self._want_side = bool(data.get("side"))
        self._want_explorer = bool(data.get("explorer"))
        dirs = data.get("dirs")
        if isinstance(dirs, list):
            self._explorer_hist = [str(d) for d in dirs[:5]
                                   if isinstance(d, str)]

    def _fit_columns(self, width: int) -> None:
        """Уложить колонки в ширину, не задушив редактор.

        Правило одно: редактору не меньше `EDIT_MIN_W`. Первым уступает
        проводник — он справочный и открывается под задачу; следом колонка
        вкладок. Возвращаются они сами, как только место появилось.

        Почему это делает КОД, а не CSS: колонки показываются inline-стилем
        (`_toggle` пишет `display` прямо в виджет), а inline сильнее любого
        правила таблицы стилей. Правило `.tight #code-explorer {display:none}`
        стояло в nex.tcss и не работало вовсе — на 80 клетках редактору
        оставалось 27, то есть ровно там, где место дороже всего.
        """
        room = width - (22 if self._want_side else 0) \
            - (30 if self._want_explorer else 0)
        show_explorer = self._want_explorer
        show_side = self._want_side
        if room < self.EDIT_MIN_W and show_explorer:
            show_explorer = False
            room += 30
        if room < self.EDIT_MIN_W and show_side:
            show_side = False
        for selector, want, attr in (("#code-explorer", show_explorer,
                                      "explorer_shown"),
                                     ("#code-side", show_side, "side_shown")):
            if getattr(self, attr) == want:
                continue
            try:
                self.query_one(selector).display = want
            except Exception:
                continue
            setattr(self, attr, want)

    def _apply_width(self, width: int) -> None:
        super()._apply_width(width)
        self._fit_columns(width)

    def _explorer_rows(self) -> list[tuple[str, str, bool]]:
        """Что показать: [(ключ, подпись, это ли папка)].

        Без запроса — содержимое ОДНОГО каталога: папки, потом файлы. Именно
        одного, а не дерева целиком: развёрнутое дерево превращает колонку в
        коридор из папок, в котором свой файл ищут глазами дольше, чем
        набирают его имя.

        С запросом — поиск по имени вглубь, с пределами (см. FIND_LIMIT).
        """
        folder = self.explorer_dir
        query = self.explorer_query.strip().lower()
        rows: list[tuple[str, str, bool]] = []
        if query:
            return self._find_rows(folder, query)

        import os

        self._find_cut = ""
        if folder.parent != folder:
            rows.append((str(folder.parent), "..", True))
        # Недавние каталоги — сразу под «..», по одному нажатию. Показываем
        # только те, где мы сейчас не стоим.
        for path in self._explorer_hist[:3]:
            if path == str(folder):
                continue
            name = Path(path).name or path
            rows.append(("hist:" + path, "↩ " + name, True))
        try:
            with os.scandir(folder) as it:
                entries = list(it)
        except OSError as exc:
            self._find_cut = f"каталог не читается: {exc.strerror}"
            return rows
        # Предел и здесь, не только в поиске: каталог на десять тысяч файлов
        # бывает не только у сборочных систем, а колонка всё равно покажет
        # первые строки. Дороже всего не показ, а сортировка всего списка.
        if len(entries) > self.LIST_LIMIT:
            self._find_cut = (f"в папке {len(entries)} файлов, показаны "
                              f"первые {self.LIST_LIMIT} — ищите по имени")
        def sort_key(entry):
            try:
                return (not entry.is_dir(follow_symlinks=False),
                        entry.name.lower())
            except OSError:
                return (True, entry.name.lower())

        for entry in sorted(entries, key=sort_key)[:self.LIST_LIMIT]:
            if entry.name.startswith(".") or entry.name in self.SKIP_DIRS:
                continue
            try:
                is_dir = entry.is_dir(follow_symlinks=False)
            except OSError:
                continue
            rows.append((entry.path,
                         entry.name + "/" if is_dir else entry.name, is_dir))
        return rows

    def _remember_dir(self, folder) -> None:
        """Запомнить, откуда ушли: вернуться туда — одно нажатие.

        Ходить от корня каждый раз дороже всего в проводнике: свой каталог у
        человека один и тот же, а путь к нему длинный.
        """
        path = str(folder)
        hist = [p for p in self._explorer_hist if p != path]
        hist.insert(0, path)
        self._explorer_hist = hist[:5]
        self._save_layout()

    @staticmethod
    def _find_hit(query: str, name: str, rel: str) -> bool:
        """Совпал ли запрос: по имени, а с разделителем — по пути.

        Вставить путь целиком — первое, что делает человек, у которого файл
        уже открыт в проводнике системы. Раньше это молча не находило
        ничего: сравнение шло только с ИМЕНЕМ файла, а
        `examples/stress/deep/hard_mix.s` именем не бывает. Обратные слэши
        приводим к прямым — на Windows путь копируется из адресной строки
        именно с ними.
        """
        q = query.replace("\\", "/").strip().lower()
        if not q:
            return False
        if "/" in q:
            return q.strip("/") in rel.replace("\\", "/").lower()
        return q in name.lower()

    def _find_rows(self, folder, query: str) -> list[tuple[str, str, bool]]:
        """Поиск по имени вглубь: обход вширь, с отсечением на ходу.

        Раньше здесь стоял `sorted(folder.rglob("*"))`, и это была самая
        дорогая строка экрана: в корне проекта она разворачивала 40 497
        путей за секунду — НА КАЖДУЮ набранную букву. Из них 35 681 лежал в
        `.venv`: обход честно спускался в чужие библиотеки, чтобы потом
        выбросить их фильтром «имя начинается с точки». Отсекать надо было
        до спуска, а не после.

        Обход вширь, а не вглубь, ещё и по делу: свой файл лежит ближе к
        корню, и первые находки должны быть оттуда, а не из недр `vendor`.
        """
        import os

        rows: list[tuple[str, str, bool]] = []
        seen = 0
        self._find_cut = ""
        queue: list[tuple[str, int]] = [(str(folder), 0)]
        base = str(folder)
        while queue and len(rows) < self.FIND_LIMIT and seen < self.FIND_SCAN:
            here, depth = queue.pop(0)
            try:
                with os.scandir(here) as it:
                    entries = sorted(it, key=lambda e: e.name.lower())
            except OSError:
                continue
            for entry in entries:
                seen += 1
                if seen >= self.FIND_SCAN:
                    break
                name = entry.name
                if name.startswith(".") or name in self.SKIP_DIRS:
                    continue
                try:
                    is_dir = entry.is_dir(follow_symlinks=False)
                except OSError:
                    continue
                # Спуск в папку не зависит от совпадения имени: искомое
                # лежит ГЛУБЖЕ, даже если сама папка называется иначе.
                if is_dir and depth + 1 < self.FIND_DEPTH:
                    queue.append((entry.path, depth + 1))

                shown = entry.path[len(base) + 1:] or name
                if not self._find_hit(query, name, shown):
                    continue
                # Папки в выдаче: раньше их не было вовсе — `continue` стоял
                # ДО проверки имени, и строка поиска, обещающая «имя файла
                # ИЛИ ПАПКИ», папку не находила никогда. Клик по такой
                # строке заходит внутрь, как и в обычном списке.
                rows.append((entry.path, shown + "/" if is_dir else shown,
                             is_dir))
                if len(rows) >= self.FIND_LIMIT:
                    break
        # Обход мог кончиться не потому, что всё просмотрено. Молчать об
        # этом нельзя: человек видит короткий список и думает, что его файла
        # нет, а на самом деле поиск остановился на полпути.
        if len(rows) >= self.FIND_LIMIT:
            self._find_cut = f"показаны первые {self.FIND_LIMIT}"
        elif seen >= self.FIND_SCAN:
            self._find_cut = (f"просмотрено {self.FIND_SCAN} файлов — "
                              "уточните запрос или зайдите в папку")
        elif queue:
            self._find_cut = f"глубже {self.FIND_DEPTH} уровней не искали"
        return rows

    def _draw_explorer(self) -> None:
        """Перерисовать проводник: где стоим, что нашли."""
        try:
            head = self.query_one("#explorer-head", Static)
            box = self.query_one("#explorer-list", VerticalScroll)
        except Exception:
            return
        dim = palette.role_hex("dim")
        faint = palette.role_hex("faint")
        rows = self._explorer_rows()

        where = self._rel(self.explorer_dir)
        if where in ("", "."):
            where = self.explorer_dir.name or str(self.explorer_dir)
        t = Text()
        t.append("ПАПКИ", style=palette.role_hex("title"))
        if self.explorer_query:
            # Во время поиска важно не «где стоим», а «сколько нашлось»:
            # короткий список без числа читается как «больше ничего нет».
            n = len(rows)
            t.append(f"   {n} " + plural(n, "находка", "находки", "находок"),
                     style=palette.role_hex("dim" if n else "faint"))
        else:
            # Имя папки режем СПРАВА: слева у него отличительная часть, и
            # «…ai-scheduler-demo» не отвечает, где мы, — таких хвостов
            # много, а начало имени одно.
            t.append("   " + (where if len(where) <= 17
                              else where[:16] + "…"), style=faint)
        head.update(t)
        head.tooltip = f"{self.explorer_dir}\n^E — убрать колонку"

        # Кто держал фокус до перерисовки. Список пересобирается на каждый
        # набранный знак, и снос его детей уводил фокус из строки поиска в
        # редактор: буквы уходили в КОД, а не в поиск. Проверено руками —
        # «probe» оказывалось в начале буфера.
        keep_focus = self._explorer_has_focus()
        box.remove_children()
        items: list = []
        if not rows:
            items.append(Static(Text(
                "  ничего не нашлось" if self.explorer_query
                else "  каталог пуст", style=faint)))
        if self._find_cut:
            items.append(Static(self._wrapped(self._find_cut, 28,
                                              style=faint)))
        for key, label, is_dir in rows[:200]:
            rel = self._rel(Path(key))
            mine = (not is_dir) and self._deletable(rel)
            t = Text()
            t.append("  " + ("▸ " if is_dir else "  "),
                     style=palette.role_hex("accent2" if is_dir else "faint"))
            short = label if len(label) <= 19 else "…" + label[-18:]
            t.append(short, style=palette.role_hex("text") if is_dir else dim)
            # Экспонат подписан прямо в списке. В репозитории такой один —
            # probe_ILLUSTRATION_OBSOLETE.s, и он сам про себя пишет: «ЭТО НЕ
            # ВЫВОД КОМПИЛЯТОРА, рисованная от руки иллюстрация». Прятать его
            # из проводника нельзя: проводник показывает то, что лежит на
            # диске, и редактировать эту правду — тоже враньё. А выдать
            # экспонат за вывод lcc — ровно то враньё, от которого проект
            # защищается пометками источника у каждого числа.
            if "OBSOLETE" in Path(key).name.upper():
                t.append("  экспонат", style=palette.role_hex("warning"))
            if mine:
                # ✕ — только у файлов рабочего каталога: примеры лежат в
                # пакете, и стереть их промахом мимо имени нельзя.
                t.append(" " * max(1, self.DELETE_X - t.cell_len), style=faint)
                # ✕ виден ВСЕГДА, приглушённым: кнопка, которая появляется
                # только после нажатия, — не кнопка. Красным он становится,
                # когда ждёт подтверждения.
                t.append("✕", style=palette.role_hex(
                    "error" if self._to_delete == rel else "faint"))
            cls = "side-item"
            if len(items) - (1 if not rows else 0) == self._explorer_at:
                cls += " side-item-on"
            item = SideItem(("dir:" + key) if is_dir else (rel if mine else key),
                            t, classes=cls)
            item.tooltip = (f"{key}\n" + ("клик — зайти в папку" if is_dir
                                          else "клик — открыть вкладкой"
                                          + ("\n✕ справа — удалить файл"
                                             if mine else "")))
            items.append(item)
        if self._to_delete:
            t = Text()
            t.append("  удалить ", style=palette.role_hex("error"))
            t.append(self._to_delete.rsplit("/", 1)[-1][:14],
                     style=palette.role_hex("title"))
            t.append("?", style=palette.role_hex("error"))
            items.append(Static(t))
            row = Text()
            row.append("   да, удалить", style=palette.role_hex("error"))
            item = SideItem("del:yes", row, classes="side-item")
            item.tooltip = "файл будет стёрт с диска — отменить нельзя"
            items.append(item)
            row = Text()
            row.append("   отмена", style=dim)
            items.append(SideItem("del:no", row, classes="side-item"))
        if items:
            box.mount(*items)
        if keep_focus:
            try:
                self.query_one("#explorer-find", Input).focus()
            except Exception:
                pass

    def action_toggle_ai(self) -> None:
        """Открыть/закрыть вкладку АГЕНТ. Колонки справа больше нет.

        Кнопка ▐ и ^G ведут туда же, куда и вкладка: разговор с агентом на
        экране один, и вход в него тоже должен быть один.
        """
        if self.drawer_open and self.drawer_tab == "agent":
            self.close_drawer()
            return
        self.open_drawer("agent")

    @property
    def ai_shown(self) -> bool:
        """Виден ли сейчас агент. Раньше это была своя колонка, теперь —
        вкладка дока: свойство осталось, чтобы «показан ли агент» спрашивали
        в одном месте, а не сверяли два признака."""
        return self.drawer_open and self.drawer_tab == "agent"

    def _answer_in_ai(self, question: str) -> None:
        """Задать вопрос агенту — из колонки справа или из вкладки АГЕНТ.

        Вопрос и ответ ложатся в ОДНУ переписку сессии (`session.dialog`), а
        не в виджет того места, откуда спросили: колонка, вкладка и
        полноэкранный АГЕНТ показывают один и тот же разговор. Пока история
        жила в виджете, спросить в колонке и уйти на весь экран значило
        потерять ответ, ради которого уходишь.

        ЖДАТЬ ЗДЕСЬ ДОЛГО, и молчать об этом нельзя. Локальная модель на
        холодную поднимает сервер и считает системный промпт: замерено — 70
        секунд до первого куска. Панель всё это время показывала пустоту, и
        выглядело это ровно как «не работает»; так и было доложено. Поэтому
        состояние прогрева пишется сразу, ДО первого токена, и с честной
        оценкой, сколько ждать.
        """
        facts = self.panel_facts(self._ai_topic())
        dialog = self.app.session.dialog
        dialog.append({"role": "you", "text": question, "facts": facts})
        dialog.append({"role": "nex", "text": "", "facts": [],
                       "waiting": True})
        self._draw_dialog()
        self._ai_worker(question, facts)

    def _dialog_note(self) -> Text:
        """Итог вкладки АГЕНТ: сколько вопросов задано и где ещё смотреть."""
        n = sum(1 for m in self.app.session.dialog if m["role"] == "you")
        t = Text()
        if not n:
            t.append("вопросов не было ", style=palette.role_hex("faint"))
        else:
            t.append(f"{n} ", style=palette.role_hex("text"))
            t.append(plural(n, "вопрос", "вопроса", "вопросов") + " ",
                     style=palette.role_hex("dim"))
        return t

    #: Готовые вопросы развёрнутого АГЕНТА. Не «про VLIW вообще», а про то,
    #: что сейчас в буфере: разворачивают агента, стоя в своём коде, и
    #: спрашивают про него. Общие вопросы про машину живут в полноэкранном
    #: АГЕНТЕ, у него другой контекст.
    ASKS = (
        "почему этот такт пустой?",
        "где теряются такты?",
        "что мешает переставить выше?",
        "откуда такая латентность?",
        "объясни замечания буфера",
        "что даст F6?",
    )

    def _draw_agent_extras(self) -> None:
        """Содержимое, которое есть только у РАЗВЁРНУТОГО агента.

        Рисуется всегда, а показывается по классу `zoom-dock`: перерисовка
        трёх текстов стоит микросекунды, а согласовывать два пути отрисовки
        («в развороте рисуем, в свёрнутом нет») — это гарантированно
        разъехавшееся состояние при первом же переключении.
        """
        try:
            seen = self.query_one("#agent-seen", Static)
            trace = self.query_one("#agent-trace", Static)
        except Exception:
            return
        dim = palette.role_hex("dim")
        faint = palette.role_hex("faint")
        # Ширина колонки известна — по ней и переносим. Пока текст рвался
        # сам, перенос попадал в середину слова и одинокое «команд» висело
        # у левого края, будто это новый пункт.
        # Пока раскладка не посчитана, ширина нулевая — берём проектную и
        # перерисовываем после отрисовки (см. set_zoom). Без этого перенос
        # считался по 20 клеткам, и колонка выглядела рваной лесенкой.
        width = (self.query_one("#agent-side").size.width or 46) - 3

        t = Text()
        for fact in self.panel_facts(self._ai_topic()):
            t.append_text(self._wrapped(fact, width, style=dim))
        seen.update(t)

        t = Text()
        if not self.ai_actions:
            t.append_text(self._wrapped("агент ещё ничего не делал", width,
                                        style=faint))
            t.append_text(self._wrapped("здесь будет видно, что он считал "
                                        "и какие команды звал перед ответом",
                                        width, style=faint))
        else:
            for act in self.ai_actions[-12:]:
                t.append_text(self._wrapped("⚙ " + act, width,
                                            style=palette.role_hex("accent2")))
        trace.update(t)

        # Готовые вопросы — виджетами, поэтому пересобираем только когда их
        # ещё нет: перемонтаж на каждую перерисовку мигал бы сеткой.
        try:
            grid = self.query_one("#agent-asks", ItemGrid)
        except Exception:
            return
        if not list(grid.children):
            for q in self.ASKS:
                grid.mount(Chip("› " + q, q, classes="chip chip-question"))

    def _ai_topic(self) -> str:
        """Про что агент объясняет: про код или про вкладку, с которой пришли.

        Курсор в редакторе — значит вопрос про код. Пришли из ЗАМЕЧАНИЙ или
        РАСПИСАНИЯ — значит про них: спрашивают всегда о том, на что только
        что смотрели, и переспрашивать об этом человека незачем.
        """
        if self.drawer_tab != "agent":
            # Спрашивают не из агента (например, ^G из развёрнутой вкладки) —
            # тема прямо перед глазами.
            return self.TABS[self.drawer_tab][3]
        return self._ai_from or "code"

    @staticmethod
    def _wrapped(text: str, width: int, style: str = "",
                 indent: int = 2) -> Text:
        """Строка, перенесённая ПО СЛОВАМ, с отступом у продолжения.

        Отступ у второй строки — не украшение: без него перенос читается как
        новый пункт списка, и колонка фактов превращалась в кашу из обрывков.
        """
        limit = max(8, width - indent)
        out = Text()
        line = ""
        for word in text.split():
            if line and len(line) + 1 + len(word) > limit:
                out.append(" " * indent + line + "\n", style=style)
                line = word
                indent = max(indent, 4)
                limit = max(8, width - indent)
            else:
                line = f"{line} {word}".strip()
        if line:
            out.append(" " * indent + line + "\n", style=style)
        return out

    def on_chip_picked(self, event) -> None:
        """Чип сразу делает своё дело: вопрос — спрашивает, ядро — считает.

        Чип обычно ПОДСТАВЛЯЕТ текст в строку ввода, но здесь подставлять
        некуда и незачем: и вопрос, и команда ядра написаны целиком, а
        второй шаг «теперь нажмите Enter» только добавляет работы.

        Кому адресован клик, решает открытая вкладка: чипы видны лишь в
        своей и только в развороте, поэтому спутать нельзя.
        """
        event.stop()
        if self.drawer_tab == "core":
            self._exec_core(event.value)
            return
        self._answer_in_ai(event.value)

    def _draw_dialog(self) -> None:
        """Перерисовать переписку в обоих местах, где она видна.

        Колонка справа и вкладка АГЕНТ — два ОКНА в один разговор, поэтому
        рисуются из одного списка одним методом. Разница только в ширине: в
        колонке 34 клетки, во вкладке — вся ширина дока.
        """
        self._draw_agent_extras()
        for target_id in ("#agent-log",):
            try:
                target = self.query_one(target_id, Static)
            except Exception:
                continue
            target.update(self._dialog_text())
        try:
            box = self.query_one("#agent-log-box", VerticalScroll)
            box.scroll_end(animate=False)
        except Exception:
            pass

    def _dialog_text(self) -> Text:
        """Сама лента: вопросы, ответы и честное состояние ожидания."""
        dim = palette.role_hex("dim")
        faint = palette.role_hex("faint")
        mind = palette.role_hex("accent2")
        t = Text()
        if not self.app.session.dialog:
            t.append("\nагент объясняет ПОСЧИТАННОЕ выше\n", style=dim)
            t.append("числа считает точный поиск, слова — модель.\n",
                     style=faint)
            t.append("любой ответ проверяется командой: /doctor, "
                     "/compare, /bounds.\n", style=faint)
            # Что он видит прямо сейчас — здесь же. Пустая лента на
            # тринадцать строк не отвечала ни на «о чём его спрашивать», ни
            # на «а он вообще смотрит на мой код».
            facts = self.panel_facts(self._ai_topic())
            if facts:
                t.append("\nсейчас он видит:\n", style=dim)
                for fact in facts[:4]:
                    t.append(f"  {fact}\n", style=faint)
            return t
        for msg in self.app.session.dialog:
            if msg["role"] == "you":
                t.append("\n▌ вы\n", style=dim)
                t.append(msg["text"] + "\n", style=palette.role_hex("title"))
                continue
            t.append("\n▌ nex", style=mind)
            t.append("   по числам выше\n", style=faint)
            if msg["text"]:
                t.append(msg["text"] + "\n", style=palette.role_hex("text"))
            elif msg.get("waiting"):
                t.append(self._waiting_text())
        return t

    def _waiting_text(self) -> Text:
        """Что писать, пока ответа нет: состояние модели, а не пустота."""
        from ...agent import local as agent_local

        t = Text()
        state, note = agent_local.warm_state()
        if state == "ready":
            t.append("  считаю…\n", style=palette.role_hex("dim"))
        elif state == "failed":
            t.append(f"  модель недоступна: {note}\n",
                     style=palette.role_hex("error"))
            t.append("  числа выше посчитаны без неё и остаются верны.\n",
                     style=palette.role_hex("dim"))
        else:
            t.append("  модель прогревается — поднимается сервер и\n",
                     style=palette.role_hex("warning"))
            t.append("  считается системный промпт. Первый ответ\n",
                     style=palette.role_hex("warning"))
            t.append("  примерно через минуту, дальше секунды.\n",
                     style=palette.role_hex("warning"))
            t.append("\n  Числа выше уже посчитаны и модели не ждут.\n",
                     style=palette.role_hex("dim"))
        return t

    @work(thread=True, exclusive=True, group="ai-side")
    def _ai_worker(self, question: str, facts: list[str]) -> None:
        """Тот же агент, что в остальных панелях, — не облегчённая копия.

        Факты экрана уходят вместе с вопросом (`panel=`), поэтому модель
        отвечает по ПОСЧИТАННЫМ числам, а не по своим представлениям о том,
        как устроен Эльбрус. Это и есть та рамка, ради которой объяснятель
        вообще уместен: числа не его, его — только слова вокруг них.
        """
        agent = self.app.session.agent()
        try:
            for kind, value in agent.ask_stream(question,
                                                panel=("код", facts)):
                if kind == "text":
                    self.app.call_from_thread(self._ai_piece, value)
                elif kind == "action":
                    # Что агент СДЕЛАЛ перед ответом — в трассу развёрнутого
                    # блока. Это и есть проверяемость: ответ можно сверить с
                    # тем, что он для него посчитал, а не верить на слово.
                    self.app.call_from_thread(self._ai_action, value)
                elif kind == "error":
                    self.app.call_from_thread(self._ai_piece, "\n" + value)
        except Exception as e:
            self.app.call_from_thread(self._ai_piece, f"\nне вышло: {e}")

    def _ai_action(self, act: str) -> None:
        """Действие агента приехало — дописать в трассу."""
        self.ai_actions.append(act)
        self._draw_agent_extras()

    def _ai_piece(self, piece: str) -> None:
        """Кусок ответа приехал — дописать в последнюю реплику переписки.

        Дописываем именно в ленту, а не в отдельный блок «ОТВЕТ»: пока ответ
        рисовался сам по себе, первый же кусок затирал вопрос, и через минуту
        ожидания человек переставал видеть, на что ему вообще отвечают.
        """
        dialog = self.app.session.dialog
        if not dialog or dialog[-1]["role"] != "nex":
            dialog.append({"role": "nex", "text": "", "facts": []})
        dialog[-1]["text"] += piece
        dialog[-1]["waiting"] = False
        self._draw_dialog()

    def action_explain(self) -> None:
        """^G — вкладка АГЕНТ и курсор в строке вопроса. Второе нажатие убирает.

        Один ключ — одно поведение, каким бы ни был фокус. Раньше ^G открывал
        всплывающую строку внизу, потом отдельный столбец справа; теперь
        агент — вкладка дока, такая же, как остальные. Столбец показывал
        ровно тот же разговор и держал ширину у кода даром.

        КОНТЕКСТ берётся в момент открытия: курсор в коде — вопрос про код,
        открыта вкладка — про её содержимое (см. `open_drawer`). Снимать его
        позже нельзя: агент забирает фокус себе, и «на что человек смотрит»
        через мгновение уже не спросишь.
        """
        if self.ai_shown:
            self.action_toggle_ai()
            return
        self.action_toggle_ai()
        try:
            self.query_one("#agent-input", Input).focus()
        except Exception:
            pass

    def action_ai_or_complete(self) -> None:
        """Tab: в редакторе — отступ. Справочник живёт на ^G, не на Tab.

        Tab отбирать нельзя: в ассемблере им расставляют отступы, а
        развёрнутых панелей с рамками, у которых Tab открывал справочник, на
        этом экране больше нет.
        """
        if self._accept_suggest():
            return
        edit = self.query_one("#code-edit", AsmArea)
        if edit.has_focus:
            edit.insert("\t")
            return
        try:
            self.query_one("#prompt", PromptBar).tab()
        except Exception:
            pass

    # --- вкладка ЯДРО: консоль интерпретатора ------------------------------
    #
    # Целого экрана эта работа не стоит: у неё одна ценность — собрать граф
    # выражениями, не умея писать ассемблер e2k, и посмотреть, во сколько
    # тактов он укладывается. Ровно это и делает вкладка. Полноэкранное
    # ЯДРО с лентой, коммитами и снимками машины никуда не делось; машина
    # одна на сессию, поэтому имена и память здесь те же самые.

    def _seed_core_chips(self) -> None:
        """Готовые ядра и глаголы ядра — кликом, а не по памяти."""
        from ...core.interp import kernel_help

        try:
            row = self.query_one("#core-chips", ItemGrid)
        except Exception:
            return
        if list(row.children):
            return
        row.mount(Static("ядра", classes="chip-label"))
        for name, default, hint in kernel_help():
            chip = Chip(name, f"{name} {default}", classes="chip chip-kernel")
            chip.tooltip = f"{hint}  ·  по умолчанию {default}"
            row.mount(chip)
        row.mount(Static("ещё", classes="chip-label"))
        for word, hint in (("names", "показать имена и значения"),
                           ("mem", "показать память"),
                           ("list", "показать накопленный граф"),
                           ("reset", "очистить имена и память"),
                           ("go", "посчитать накопленный граф точным поиском")):
            chip = Chip(word, classes="chip chip-verb")
            chip.tooltip = hint
            row.mount(chip)

    def _seed_core(self) -> None:
        log = self.query_one("#core-log", RichLog)
        dim = palette.role_hex("dim")
        log.write(Text("выражения строят граф — как в Python Console",
                       style=dim))
        for line, note in (
            ("a = 10", "имя со значением"),
            ("t = a*2 + 3", "выражение: каждая операция — узел графа"),
            ("sum 8", "готовое ядро: сумма восьми чисел"),
            ("go", "посчитать накопленный граф точным поиском"),
        ):
            row = Text()
            row.append("  " + line.ljust(14), style=palette.role_hex("accent2"))
            row.append(note, style=dim)
            log.write(row)

    def on_input_changed(self, event) -> None:
        """Поиск в проводнике идёт по мере набора, без Enter.

        Но не на каждую букву: обход диска ждёт паузы в наборе. «slots» —
        это пять обходов вместо одного, и на большом каталоге экран замирал
        ровно в тот момент, когда человек печатает.
        """
        if getattr(event.input, "id", "") != "explorer-find":
            return
        event.stop()
        self.explorer_query = event.value
        self._explorer_at = 0
        if self._find_timer is not None:
            self._find_timer.stop()
        self._find_timer = self.set_timer(self.FIND_DEBOUNCE,
                                          self._draw_explorer)

    def _explorer_step(self, delta: int) -> None:
        """Ходить по списку проводника стрелками, не отпуская клавиатуру.

        Мышью открывать файл можно было с самого начала, а вот набрать имя и
        тут же выбрать из нескольких находок — нет: приходилось тянуться к
        мыши посреди набора.
        """
        rows = self._explorer_rows()
        if not rows:
            return
        self._explorer_at = max(0, min(len(rows) - 1,
                                       self._explorer_at + delta))
        self._draw_explorer()
        try:
            box = self.query_one("#explorer-list", VerticalScroll)
            items = list(box.query(SideItem))
            if self._explorer_at < len(items):
                box.scroll_to_widget(items[self._explorer_at], animate=False)
        except Exception:
            pass

    def _open_selected(self) -> None:
        """Enter в проводнике — открыть то, на чём стоит выделение."""
        rows = self._explorer_rows()
        if not rows:
            return
        at = min(self._explorer_at, len(rows) - 1)
        key, _label, is_dir = rows[at]
        self.post_message(SideItem.Picked(("dir:" + key) if is_dir else key))

    def _open_first_found(self) -> None:
        """Enter в строке поиска — открыть первую находку.

        Без этого проводник работал только мышью: нашёл файл — тянись к
        мыши, чтобы его открыть. Первая находка и есть та, ради которой
        набирали имя.
        """
        rows = [r for r in self._explorer_rows() if not r[2]]
        if not rows:
            return
        key = rows[0][0]
        self.post_message(SideItem.Picked(key))

    def on_input_submitted(self, event) -> None:
        """ОДИН обработчик на все поля ввода экрана, разводка по id.

        Метод обязан быть ровно один: Python оставляет в классе последнее
        определение, и второй такой же молча убивает первый — обработчик
        просто перестаёт вызываться, без единой ошибки. Ровно так и вышло,
        когда строку вопроса к ИИ завели отдельным методом: панель
        открывалась, поле принимало текст, а Enter не делал ничего.
        """
        which = getattr(event.input, "id", "")
        if which == "explorer-find":
            event.stop()
            self._open_selected()
            return
        if which == "core-input":
            event.stop()
            line = event.value.strip()
            event.input.value = ""
            if line:
                self._exec_core(line)
            return
        if which == "agent-input":
            event.stop()
            question = event.value.strip()
            event.input.value = ""
            if question:
                self._answer_in_ai(question)
            return

    def _exec_core(self, line: str) -> None:
        """Выполнить строку интерпретатора и показать её ответ."""
        from ...core.interp import InterpError
        from ...ui import interp_view

        log = self.query_one("#core-log", RichLog)
        ws = self.app.session.workspace()
        echo = Text()
        echo.append("❯ ", style=palette.role_hex("faint"))
        echo.append(line, style=palette.role_hex("title"))
        log.write(echo)
        try:
            result = ws.exec(line)
        except InterpError as exc:
            log.write(Text("  " + str(exc), style=palette.role_hex("error")))
            return
        except Exception as exc:
            log.write(Text(f"  {type(exc).__name__}: {exc}",
                           style=palette.role_hex("error")))
            return

        width = max(24, self.query_one("#core-log-box").size.width - 2)
        for out in interp_view.render_result(ws, result, width=width):
            log.write(Text.from_ansi(out))
        # Граф ЯДРА становится текущим участком сессии: дальше про него
        # говорят и РАЗБОР, и АГЕНТ. Без этого консоль была бы калькулятором.
        if result.kind != "reset" and not ws.empty():
            self.app.session.set_dag(ws.snapshot(), "interp")
        self._draw_core_state()
        self._draw_dock_note()
        self.refresh_context()
        if result.kind == "go":
            self._core_handoff()

    def _core_handoff(self) -> None:
        """`go` — посчитать накопленный граф точным поиском.

        Ассемблер отсюда НЕ сочиняется, хотя соблазн есть: у узлов графа
        есть класс операции, но нет ни мнемоники, ни операндов, и выдумать
        их значило бы выдать за код e2k текст, который никто не мерил. Ответ
        честный — числа и участок, к которому они относятся.
        """
        ws = self.app.session.workspace()
        log = self.query_one("#core-log", RichLog)
        if ws.empty():
            log.write(Text("  графа нет — считали без записи в программу",
                           style=palette.role_hex("warning")))
            return
        self.set_busy(True)
        self.run_worker(self._core_go_worker, thread=True, exclusive=True,
                        group="core")

    def _core_go_worker(self) -> None:
        """Точный поиск идёт в отдельном потоке — экран не замирает."""
        try:
            base, orc, met = self.app.session.results()
        except Exception as exc:
            self.app.call_from_thread(self._core_go_done, None, None, str(exc))
            return
        self.app.call_from_thread(self._core_go_done, base, orc, met, "")

    def _core_go_done(self, base, orc, met, err: str = "") -> None:
        self.set_busy(False)
        log = self.query_one("#core-log", RichLog)
        if err or base is None:
            log.write(Text(f"  не посчиталось: {err}",
                           style=palette.role_hex("error")))
            return
        b, o = base.schedule.makespan, orc.schedule.makespan
        t = Text()
        t.append("  жадный ", style=palette.role_hex("dim"))
        t.append(f"{b} т.", style=palette.role_hex("text"))
        t.append("   точный поиск ", style=palette.role_hex("dim"))
        t.append(f"{o} т.", style=palette.role_hex("accent"))
        t.append("   нижняя граница ", style=palette.role_hex("dim"))
        t.append(f"{met.lower_bound} т.", style=palette.role_hex("dim"))
        log.write(t)
        if o == met.lower_bound:
            log.write(Text("  оптимум доказан: короче этого графа не уложить",
                           style=palette.role_hex("success")))
        log.write(Text("  участок сессии — этот граф: РАЗБОР и АГЕНТ теперь "
                       "про него", style=palette.role_hex("faint")))
        self.refresh_context()

    def _draw_core_state(self) -> None:
        """Панелька имён и памяти справа от консоли.

        Отвечает на «что сейчас в машине» — вопрос, который в консоли иначе
        задают командой `names` и получают ответ, уезжающий вверх с первой
        же следующей строкой.
        """
        try:
            target = self.query_one("#core-state", Static)
        except Exception:
            return
        ws = self.app.session.workspace()
        title = palette.role_hex("title")
        dim = palette.role_hex("dim")
        faint = palette.role_hex("faint")
        # В развороте панель показывает СОСТОЯНИЕ МАШИНЫ целиком, а не первые
        # строки: место под неё как раз и освобождают, разворачивая блок.
        wide = bool(self.zoom)
        n_names = 100 if wide else 12
        t = Text()
        t.append("ИМЕНА", style=title)
        t.append(f"  {len(ws.regs)}\n", style=dim)
        if not ws.regs:
            t.append("  пусто — набери  a = 10\n", style=faint)
        for name, value in list(ws.regs.items())[:n_names]:
            t.append(f"  {name[:12]:<13}", style=palette.role_hex("text"))
            t.append(f"{value}\n", style=palette.role_hex("accent2"))
        if len(ws.regs) > n_names:
            t.append(f"  ещё {len(ws.regs) - n_names}\n", style=faint)

        n = ws.graph_size()
        t.append("\nГРАФ", style=title)
        t.append(f"  {n} {plural(n, 'операция', 'операции', 'операций')}\n",
                 style=dim)
        t.append("  go — посчитать\n" if n else "  пусто\n", style=faint)
        if wide:
            # Что именно накопилось — построчно: иначе «12 операций»
            # приходится проверять командой list, а её ответ уезжает вверх с
            # первой же следующей строкой ленты.
            for line in ws.log[-12:]:
                t.append(f"  {line}\n", style=dim)

        used = [(i, v) for i, v in enumerate(ws.mem) if v]
        t.append("\nПАМЯТЬ", style=title)
        t.append(f"  ненулевых {len(used)} из {len(ws.mem)}\n", style=dim)
        if not used:
            t.append("  пусто — store 0 42\n", style=faint)
        elif wide:
            # КАРТОЙ, а не списком: память с начала заполнена 1..64, и
            # столбик «яч.0 1 / яч.1 2 / …» — это сорок строк, которые
            # вытесняют всё остальное, ничего при этом не рассказывая.
            row = ""
            for i, v in used[:32]:
                row += f"{i}:{v}".ljust(9)
                if len(row) >= 36:
                    t.append(f"  {row}\n", style=palette.role_hex("accent2"))
                    row = ""
            if row:
                t.append(f"  {row}\n", style=palette.role_hex("accent2"))
            if len(used) > 32:
                t.append(f"  ещё {len(used) - 32}\n", style=faint)
        else:
            for i, v in used[:8]:
                t.append(f"  яч.{i:<9}", style=faint)
                t.append(f"{v}\n", style=palette.role_hex("accent2"))
            if len(used) > 8:
                t.append(f"  ещё {len(used) - 8}\n", style=faint)
        target.update(t)

    def _draw_line_side(self) -> None:
        """Числа участка и профиль машины — правая колонка развёрнутого РАЗБОРА."""
        try:
            target = self.query_one("#line-side-body", Static)
        except Exception:
            return
        model = self.app.session.model()
        dim = palette.role_hex("dim")
        faint = palette.role_hex("faint")
        title = palette.role_hex("title")
        t = Text()

        t.append("ЧИСЛА\n", style=title)
        if self.comp is not None:
            t.append("как написано".ljust(15), style=dim)
            t.append(f"{self.comp.makespan} т.\n",
                     style=palette.role_hex("text"))
            t.append("слоты".ljust(15), style=dim)
            t.append(f"{self.comp.slot_utilization * 100:.0f}%\n",
                     style=palette.role_hex("text"))
        else:
            t.append("  расписание из буфера не строится\n", style=faint)
        if self._have_orc():
            orc = self.orc.schedule.makespan
            t.append("оракул".ljust(15), style=dim)
            t.append(f"{orc} т.\n", style=palette.role_hex("success"))
            if self.comp is not None and self.comp.makespan > orc:
                gap = self.comp.makespan - orc
                t.append("резерв".ljust(15), style=dim)
                t.append(f"−{gap} т.  "
                         f"({100 * gap / self.comp.makespan:.0f}%)\n",
                         style=palette.role_hex("success"))
        else:
            t.append("оракул".ljust(15), style=dim)
            t.append("F5 — посчитать\n", style=faint)

        t.append("\nМАШИНА\n", style=title)
        t.append("профиль".ljust(15), style=dim)
        t.append(f"{model.name}\n", style=palette.role_hex("text"))
        t.append("каналов".ljust(15), style=dim)
        t.append(f"{model.width}\n", style=palette.role_hex("text"))
        for port, ops in sorted(model.sole_host_ops().items()):
            t.append("  " + "/".join(ops), style=palette.op_style(ops[0]))
            t.append(f" → только {model.port_label(port)}\n", style=dim)
        t.append("/model — матрица целиком\n",
                 style=palette.role_hex("accent_soft"))
        target.update(t)

    def _sched_note(self) -> Text:
        """Итог вкладки РАСПИСАНИЕ: во сколько тактов уложено показанное."""
        t = Text()
        left = self._sched_left
        if self.parsed is None or not self.parsed.ops:
            t.append("пусто ", style=palette.role_hex("faint"))
        elif left is None:
            t.append("не по модели ", style=palette.role_hex("warning"))
        elif self._sched_which == "src":
            t.append(f"{left.makespan} т. ", style=palette.role_hex("text"))
            if self._have_orc():
                gap = left.makespan - self.orc.schedule.makespan
                if gap > 0:
                    t.append(f" −{gap} ", style=palette.role_hex("success"))
        else:
            t.append(f"{left.makespan} т. ", style=palette.role_hex("accent"))
        return t

    #: Пределы высоты дока при перетаскивании: доку — хотя бы вкладки и три
    #: строки содержимого, редактору — хотя бы восемь строк кода. Ручка,
    #: которой можно стереть одно из двух окон, — не настройка, а ловушка.
    DOCK_MIN = 5
    EDIT_MIN = 8

    def _apply_dock_height(self, dock) -> None:
        """Высота дока: поставленная мышью — или мера открытой вкладки."""
        if self.zoom:
            return
        want = self.dock_h
        if want is None:
            want = self.TAB_HEIGHT.get(self.drawer_tab, 12)
        # Редактору всегда остаётся хотя бы восемь строк кода: вкладка,
        # которой много надо, разворачивается на весь экран (2×клик), а не
        # съедает то, ради чего экран открыт.
        room = max(self.DOCK_MIN, (self.size.height or 40) - self.EDIT_MIN - 4)
        dock.styles.height = max(self.DOCK_MIN, min(want, room))

    def on_dock_splitter_grabbed(self, event) -> None:
        """Взялись за границу — запомнить, от какой высоты считать."""
        event.stop()
        self._drag_h = self.query_one("#code-dock", Vertical).size.height

    def on_dock_splitter_dragged(self, event) -> None:
        """Границу тянут: пересчитать высоту дока и запомнить её на сессию."""
        event.stop()
        if self.zoom or not self.drawer_open or self._drag_h is None:
            return
        dock = self.query_one("#code-dock", Vertical)
        # Доку — не меньше вкладок и трёх строк содержимого, редактору — не
        # меньше восьми строк кода. Ручка, которой можно стереть одно из
        # двух окон, — не настройка, а ловушка.
        room = max(self.DOCK_MIN, self.size.height - self.EDIT_MIN - 4)
        want = max(self.DOCK_MIN, min(self._drag_h - event.delta, room))
        if want == self.dock_h:
            return
        self.dock_h = want
        dock.styles.height = want
        self._draw_grids()
        self._save_layout()

    def on_dock_tabs_zoom(self, event) -> None:
        """Двойной клик по голой полосе вкладок — то же, что по вкладке.

        Один жест — один результат, куда бы ни попал курсор. Пока полоса и
        сама вкладка вели себя по-разному, разворот срабатывал «через раз»:
        попал в букву — одно, попал в зазор между кнопками — другое, и
        объяснить это человеку нечем.
        """
        event.stop()
        self.open_block(self.drawer_tab)

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
        """Текст редактора → сессия и в запись активной вкладки.

        Зовётся перед прогоном и при уходе с экрана. Вкладка обязана хранить
        то же самое, что сессия: иначе переключение туда-обратно вернёт
        текст на момент открытия и молча съест правки.
        """
        self.app.session.code_text = self.query_one("#code-edit", AsmArea).text
        if self.files:
            self.files[self.file_i]["text"] = self.app.session.code_text

    def on_asm_area_run_here(self, event) -> None:
        """Клик по стрелке в гуттере — то же, что F5."""
        event.stop()
        self.action_run_code()

    def context_bits(self) -> str:
        return "   ·   ".join(self.context_parts())

    #: Кнопки панелей в правом краю верхней полосы: (что, значок, подпись).
    #: Порядок и место — как в VS Code: три переключателя в правом верхнем
    #: углу. Заодно это ответ на «верхняя полоса пустая»: там теперь не
    #: воздух, а единственные органы управления раскладкой, до которых иначе
    #: надо было помнить клавиши ^B и F12.
    #: Кнопки панелей: (что, значок, клавиша). Клавиша написана ПРЯМО на
    #: кнопке, а не спрятана в подсказку: полоса подсказок вмещает пять
    #: пунктов, а клавиш восемь, и панельные из неё вылетали первыми —
    #: узнать про ^B было неоткуда. Кнопка со своей клавишей объясняет себя
    #: сама и заодно освобождает место в подсказках тому, у чего кнопки нет.
    #: Кнопки окон в правом краю верхней полосы: (что, значок, подпись,
    #: клавиша). Значок показывает СТОРОНУ, с которой стоит окно, подпись —
    #: что это за окно. Раньше рядом со значком стояла клавиша («▌^B ▄F12
    #: ▐^G»), и правый край строки читался как строка мусора: три значка и
    #: три сочетания подряд не говорят ни что это, ни что нажать. Клавиша
    #: ушла во всплывающую подсказку, где ей и место.
    #: Три кнопки — три ОКНА экрана: слева вкладки, снизу док, справа
    #: проводник. Агента здесь нет намеренно: он вкладка дока, и его кнопка
    #: живёт в полосе вкладок, вместе с остальными вкладками.
    TOGGLES = (
        ("side", "▌", "файлы", "^B"),
        ("dock", "▄", "док", "F12"),
        ("explorer", "▐", "папки", "^E"),
    )

    def _toggles_wide(self) -> bool:
        """Хватает ли ширины на подписи кнопок или остаются одни значки.

        Считается по факту, а не по круглому порогу: подписи занимают
        столько-то клеток, числа участка — столько-то, и вкладке нужно место
        хотя бы на одно имя. Порог «от 132 клеток» был взят на глаз и
        обманывал ровно посередине: на 120 колонках место под подписи было,
        а стояли голые значки.

        Резать вкладки ради слова «файлы» при этом нельзя: вкладки — работа,
        кнопки — управление окнами.
        """
        width = self.size.width or 120
        labels = sum(4 + len(label) for _w, _g, label, _k in self.TOGGLES)
        tail = len("   ·   ".join(self.context_parts()))
        return width - labels - tail - 6 >= self.TAB_ROOM

    #: Сколько клеток обязано остаться вкладкам файлов. Одно короткое имя
    #: с крестиком — это примерно столько.
    TAB_ROOM = 18

    def _toggles_width(self) -> int:
        """Сколько клеток займут кнопки окон в конце верхней полосы."""
        if not self._toggles_wide():
            return len(self.TOGGLES) * 3
        return sum(4 + len(label) for _w, _g, label, _k in self.TOGGLES)

    def _append_toggles(self, line) -> list[tuple[int, int, str]]:
        """Дописать кнопки панелей в конец строки, вернуть их зоны клика.

        Значок закрашен, когда панель открыта, и приглушён, когда убрана, —
        состояние читается, не нажимая.
        """
        zones: list[tuple[int, int, str]] = []
        wide = self._toggles_wide()
        for which, glyph, label, _key in self.TOGGLES:
            shown = {"side": self.side_shown, "dock": self.drawer_open,
                     "explorer": self.explorer_shown}[which]
            begin = line.cell_len
            line.append("  " + glyph,
                        style=palette.role_hex("accent2" if shown else "faint"))
            if wide:
                line.append(" " + label, style=palette.role_hex(
                    "dim" if shown else "faint"))
            zones.append((begin, line.cell_len, which))
        return zones

    def _toggle_tip(self) -> str:
        """Всплывающая подсказка полосы: что за кнопки и какие у них клавиши."""
        return "   ·   ".join(f"{label} — {key}"
                              for _w, _g, label, key in self.TOGGLES)

    def on_file_strip_maximized(self, event) -> None:
        """Редактор во весь экран: убрать всё вокруг, вторым кликом вернуть.

        Состояние запоминаем, чтобы возврат отдавал ровно то, что было
        открыто до разворота, а не «всё подряд»: если каталог был закрыт, он
        и останется закрытым.
        """
        event.stop()
        if self._maximized is None:
            self._maximized = (self.side_shown, self.drawer_open)
            if self.side_shown:
                self.action_toggle_side()
            if self.drawer_open:
                self.action_toggle_drawer()
        else:
            side, drawer = self._maximized
            self._maximized = None
            if side and not self.side_shown:
                self.action_toggle_side()
            if drawer and not self.drawer_open:
                self.action_toggle_drawer()
        self.refresh_context()
        self.refresh_hints()

    def on_file_strip_toggled(self, event) -> None:
        """Кнопка панели нажата."""
        event.stop()
        if event.which == "side":
            self.action_toggle_side()
        elif event.which == "explorer":
            self.action_toggle_explorer()
        else:
            self.action_toggle_drawer()
        self.refresh_context()

    def context_parts(self) -> list[str]:
        """Числа участка для правого края верхней строки, по кускам.

        Куски, а не готовая строка: в узком окне хвост режется, и резать его
        надо по смысловым кускам, а не по буквам. Обрезок «examples/probe.s ·»
        читается как поломка, а не как «здесь не поместилось».

        Порядок — по убыванию важности НАРОЧНО.

        В узком окне шапка обрезается справа, и первой должна уезжать не
        главная цифра, а имя профиля машины: оно постоянно, а «15→8 т.»
        меняется от правки к правке. Раньше профиль стоял первым и на 90
        знаках вытеснял именно то, ради чего в шапку и смотрят.
        """
        s = self.app.session
        bits = []
        if not self._is_asm():
            # Скрипт и заметка не участок: числа участка тут были бы про
            # прошлый файл — то есть неправдой в самом видном месте экрана.
            name = self.files[self.file_i]["name"] if self.files else ""
            n = len(self.query_one("#code-edit", AsmArea).text.splitlines())
            bits.append(f"{n} {plural(n, 'строка', 'строки', 'строк')}")
            bits.append("не e2k")
            if s.code_path:
                bits.append(s.code_path)
            return bits
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
        return bits

    #: Сколько подсказок держим внизу. Их было семь, и они не помещались:
    #: на 120 колонках последняя обрезалась на полуслове. Полоса подсказок
    #: с обрезанной подсказкой — уже не подсказка, а бахрома.
    MAX_HINTS = 5

    def refresh_hints(self) -> None:
        """Подсказки клавиш — в строку состояния, своей строки у них нет.

        Режется по месту: сначала уходит хвост (^O, ^P), первым остаётся
        F5 — с него начинается работа. Обрезанной пары не бывает, только
        целые: полфразы «F11 разверн» читается как поломка.
        """
        try:
            keys = self.query_one("#code-keys", Static)
        except Exception:
            return
        # На узком окне строку делят трое — курсор, клавиши и итог буфера, —
        # и уступать должны клавиши: итог отвечает на вопрос, ради которого
        # экран открыт, а клавиши — справка, которую можно и не показывать.
        width = self.size.width or 120
        room = 12 if width < 110 else width // 2 - 10
        key_c = palette.role_hex("accent_soft")
        dim = palette.role_hex("faint")
        t = Text()
        used = 0
        for k, v in self.hint_pairs():
            piece = len(k) + len(v) + 1
            if used + piece + (3 if used else 0) > room:
                break
            if used:
                t.append("   ")
                used += 3
            t.append(k, style=key_c)
            t.append(" " + v, style=dim)
            used += piece
        keys.update(t)

    def hint_pairs(self) -> list[tuple[str, str]]:
        """Ровно то, без чего не начать. Остальное — в подсказках у кнопок.

        Порядок — по убыванию нужности: режется хвост, и первым уезжать
        должно наименее важное. F6 встаёт в список, только когда ему есть
        что делать: пока точного поиска нет, «переписать по оракулу» —
        обещание без покрытия.
        """
        # F5 и F6 — про участок e2k. В скрипте и заметке они не работают, и
        # предлагать их значило бы обещать действие, которого не будет.
        pairs = [("F5", "прогнать")] if self._is_asm() else []
        if self._is_asm() and self._have_orc():
            pairs.append(("F6", "переписать"))
        # Панели сюда НЕ идут: у них есть кнопки в верхней полосе, и клавиша
        # написана на самой кнопке. Здесь остаётся то, что иначе не найти
        # никак: разворот дока и выход к выбору режима — последнее особенно,
        # инструмент открывается сразу КОДОМ, и без этой строки непонятно,
        # как попасть в остальные три экрана.
        pairs.append(("F11", "свернуть" if self.zoom else "развернуть"))
        # F12 — единственный способ убрать док совсем, и узнать о нём
        # больше неоткуда: кнопка ▄ в шапке подписана словом «док», а не
        # клавишей.
        pairs.append(("F12", "убрать док" if self.drawer_open else "вернуть док"))
        # Главный жест окна: двойной клик по имени вкладки открывает её блок
        # целиком — ЯДРО, РАЗБОР и АГЕНТ уходят в свои полноэкранные экраны,
        # Esc возвращает сюда же. Мышиный жест нигде больше не написан, а
        # догадаться о нём неоткуда.
        pairs.append(("2×клик", "блок на весь экран"))
        pairs.append(("^P", "команда"))
        pairs.append(("^O", "режимы"))
        return pairs[:self.MAX_HINTS]

    def toggle_hints(self) -> list[tuple[str, str]]:
        """Всё нужное уже в hint_pairs, и там же ограничение по длине."""
        return []

    def extra_commands(self) -> list[dict]:
        return [
            {"name": "rewrite", "arg": "",
             "help": "переписать буфер по расписанию точного поиска (F6)",
             "local": True},
            {"name": "example", "arg": "[" + "|".join(
                k for k, _, _ in EXAMPLES) + "]",
             "help": "каталог примеров: без имени — список, с именем — в буфер",
             "local": True},
            {"name": "gen", "arg": "<сколько> <операция> [плотно]",
             "help": "сгенерировать ситуацию: /gen 8 muls · /gen цепочка 5 fmul",
             "local": True},
            {"name": "fill", "arg": "<тактов>",
             "help": "заполнитель на N тактов: /fill 20",
             "local": True},
            {"name": "rename", "arg": "<имя>",
             "help": "переименовать текущую вкладку (F2)",
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
        # Полный разбор пересчитываем, только если вкладка открыта: он стоит
        # куда дороже строки состояния, а курсор ездит на каждую стрелку.
        if self.drawer_open and self.drawer_tab == "line":
            self._draw_line_info(line)
            self._draw_chain(line)
            self._draw_bundles()
            # Итог вкладки несёт номер строки под курсором — он меняется
            # вместе с курсором, а не только при открытии вкладки.
            self._draw_dock_note()

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
        # Заметку и скрипт разбирать нечем и незачем: планировщик читает
        # широкие команды e2k. Пропускаем разбор целиком, а не показываем
        # сорок замечаний «строку не разобрать» — они были бы правдой,
        # которая ничего не значит.
        edit.runnable = self._is_asm()
        edit.refresh()
        if not self._is_asm():
            self.parsed = None
            self.local_dag = None
            self.comp = None
            self.comp_problem = None
            self.unknown_share = 0.0
            self.problems = []
            self.redraw()
            self.refresh_status()
            return
        try:
            parsed = asm_parser.parse_asm(text, source="<буфер>")
        except Exception:
            parsed = None
        self.parsed = parsed
        self.local_dag = None
        self.comp = None
        self.comp_problem = None
        self.unknown_share = 0.0
        # Замечания разбора живут ОТДЕЛЬНО от наличия операций: буфер, где
        # ни одна строка не разобралась, — самый частый случай у новичка, и
        # молчать в нём хуже всего. Линтер по модели нужен только там, где
        # есть что проверять.
        self.problems = list(parsed.problems) if parsed is not None else []
        if parsed is not None and parsed.ops:
            self.local_dag = asm_parser.build_dag(parsed, key="asm:буфер",
                                                  title="буфер")
            # Та же функция, что у построчного `/load`: раньше КОД показывал
            # makespan любого восстановленного расписания, а `/load` отбрасывал
            # непрошедшее validate() — один файл давал два разных вердикта.
            self.comp, self.comp_problem = asm_parser.compiler_schedule_checked(
                parsed, self.local_dag, model)
            self.unknown_share = asm_parser.unknown_share(parsed)
            self.problems += asm_parser.lint(parsed, model)
        self.redraw()
        self.refresh_status()

    # --- прогон -----------------------------------------------------------

    def _refuse_non_asm(self) -> bool:
        """Сказать, почему прогон не для этого файла. True — отказали."""
        if self._is_asm():
            return False
        con = self.console
        if con is not None:
            name = self.files[self.file_i]["name"] if self.files else "файл"
            con.note(f"  {name} — не e2k: планировщик читает широкие команды "
                     "в .s от lcc", "warning")
            self.open_drawer("term")
        return True

    def action_run_code(self) -> None:
        if self._refuse_non_asm():
            return
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
            # Просили показать расписание поиска, когда его ещё не было:
            # счёт кончился — показываем, как и обещала кнопка.
            if self._want_orc:
                self._want_orc = False
                self.sched_view = "orc"
                self.open_drawer("sched")
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
                # Спасибо просим ЗДЕСЬ и только здесь: человек прямо сейчас
                # получил то, зачем пришёл, — посчитанный резерв. В этот
                # момент строка читается как «пригодилось?», а не как
                # попрошайничество на пустом месте. Ровно один раз за
                # сессию (флаг `first` выше), приглушённым, ничего не
                # перекрывает и никуда не уводит.
                con.note("  проект бесплатный · "
                         "pay.cloudtips.ru/p/7809ff65", "dim")
        # `/code load` мог заменить буфер целиком — покажем его в редакторе
        # и переименуем вкладку: имя файла приехало вместе с текстом.
        edit = self.query_one("#code-edit", AsmArea)
        if self.app.session.code_text != edit.text:
            edit.text = self.app.session.code_text
            self._example = ""
            if self.files:
                rec = self.files[self.file_i]
                rec["path"] = self.app.session.code_path
                rec["example"] = ""
                rec["name"] = self._buffer_name(rec)
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

    def refresh_context(self) -> None:
        """Числа участка живут в верхней строке — шапки режима здесь нет."""
        self._draw_title()

    def on_resize(self, event) -> None:
        """Числа в верхней строке прижаты вправо, а «вправо» зависит от
        ширины окна: без перерисовки они после ресайза висят не у края.

        Подсказки клавиш — по той же причине: они делят строку состояния с
        итогом буфера, и сколько пар туда влезет, известно только по ширине.
        Первая отрисовка случается до того, как экран получил размер, — на
        ней в строке остаётся одна пара, и без этого вызова так бы и было."""
        super().on_resize(event)
        self._draw_title()
        self.refresh_hints()
        # Строка состояния тоже считает себя по ширине: и совет «F5 —
        # посчитать резерв», и подпись у стрелки разбора помещаются не
        # всегда. Без этой перерисовки они оставались от прошлого размера —
        # то есть ровно те обрубки, ради которых пороги и заводились.
        self._draw_status()
        self._draw_line_chip(self._cursor_line or 1)
        try:
            self._apply_dock_height(self.query_one("#code-dock", Vertical))
        except Exception:
            pass

    def _draw_title(self) -> None:
        """Полоса файлов: что открыто, что правится и во что обходится.

        Заменяет и рамку «ИСХОДНИК», и шапку режима. Имя рамки отвечало на
        вопрос, которого никто не задаёт (что это за прямоугольник — и так
        видно, в нём код), а шапка повторяла числа из строки состояния.

        Числа справа имеют ПРИОРИТЕТ над вкладками. Пока приоритета не было,
        шесть открытых файлов вытесняли их за край молча — и «15→8 т.»
        пропадало ровно тогда, когда открыто много всего и разобраться
        нужнее всего. Вкладки вместо этого сдвигаются окном вокруг активной:
        она видна всегда, а про уехавшие говорят «‹ 2».
        """
        try:
            strip = self.query_one("#code-head", FileStrip)
        except Exception:
            return
        raised = palette.SURFACES["raised"]
        dim = palette.role_hex("dim")
        faint = palette.role_hex("faint")
        title = palette.role_hex("title")
        mark_c = palette.mode_hex(self.mode)

        head = Text()
        head.append(" ▍", style=mark_c)
        head.append("NEX ", style=f"{mark_c} bold")
        width = strip.size.width or 120
        # Хвост ужимаем по кускам, пока он не станет длиннее половины
        # строки: вкладкам тоже нужно место, а имя профиля машины постоянно
        # и уезжает первым — числа участка меняются от правки к правке.
        parts = self.context_parts()
        tail = "   ·   ".join(parts)
        while len(parts) > 1 and len(tail) > width // 2:
            parts.pop()
            tail = "   ·   ".join(parts)
        # Место под вкладки — всё, что осталось от марки, чисел и кнопок
        # окон. Кнопки дописываются последними, но место под них считается
        # ЗДЕСЬ: пока их не учитывали, на 150 колонках последняя кнопка
        # («агент») уезжала за край — то есть первым пропадало ровно то, чем
        # окно и открывают.
        room = width - head.cell_len - len(tail) - self._toggles_width() - 3

        n = len(self.files)
        if not n:
            # `refresh_context` зовётся из on_mount, то есть ДО on_ready,
            # где заводится первая вкладка. Рисуем то, что уже есть.
            head.append(" " * max(1, width - head.cell_len - len(tail)
                                  - self._toggles_width() - 1))
            head.append(tail, style=dim)
            strip.spans = []
            strip.toggles = self._append_toggles(head)
            strip.tooltip = self._toggle_tip()
            strip.update(head)
            return
        # Последнюю вкладку закрыть нельзя: правят всегда что-то, и пустой
        # редактор без единого буфера — состояние, из которого не выйти.
        closable = n > 1
        chunks: list[Text] = []
        for i, rec in enumerate(self.files):
            on = i == self.file_i
            base = f"{title} bold on {raised}" if on else dim
            t = Text()
            t.append(f" {rec['name'][:22]}", style=base)
            # Признак «правлен после прогона» на самой вкладке: он про ЭТОТ
            # буфер, а в общей строке состояния был бы про какой-то.
            t.append(" ●" if (on and self._stale()) else "  ",
                     style=(f"{palette.role_hex('warning')} on {raised}"
                            if on else faint))
            t.append(" ✕ " if closable else " ",
                     style=(f"{dim} on {raised}" if on else faint))
            chunks.append(t)

        # Окно вкладок вокруг активной: растём от неё в обе стороны, пока
        # помещается. Активная в окне по построению — с неё и начали.
        lo = hi = self.file_i
        used = chunks[self.file_i].cell_len
        while True:
            grew = False
            if hi + 1 < n and used + chunks[hi + 1].cell_len + 1 <= room:
                hi += 1
                used += chunks[hi].cell_len + 1
                grew = True
            if lo - 1 >= 0 and used + chunks[lo - 1].cell_len + 1 <= room:
                lo -= 1
                used += chunks[lo].cell_len + 1
                grew = True
            if not grew:
                break

        line = head
        spans: list[tuple[int, int, int, bool]] = []
        if lo:
            line.append(f" ‹{lo} ", style=faint)
        for i in range(lo, hi + 1):
            begin = line.cell_len
            line.append_text(chunks[i])
            spans.append((begin, line.cell_len, i, closable))
            line.append(" ", style=faint)
        if hi < n - 1:
            line.append(f"› {n - 1 - hi} ", style=faint)

        pad = max(1, width - line.cell_len - len(tail)
                  - self._toggles_width() - 2)
        line.append(" " * pad)
        line.append(tail, style=dim)
        strip.spans = spans
        strip.toggles = self._append_toggles(line)
        strip.tooltip = self._toggle_tip()
        strip.update(line)

    def _draw_side(self) -> None:
        """Каталог слева: примеры машины и настоящие `.s` репозитория.

        Дерево из двух веток, а не одна свалка файлов. Примеры — учебные
        участки, у каждого своя дыра машины и своя подпись; `examples/*.s` —
        настоящий вывод lcc, ради которого инструмент и написан. Смешивать
        их значит спрятать разницу между «показательным» и «настоящим», а
        она здесь главная.
        """
        try:
            box = self.query_one("#code-side-list", VerticalScroll)
        except Exception:
            return
        try:
            head = self.query_one("#side-head", Static)
            t = Text()
            t.append("ФАЙЛЫ", style=palette.role_hex("title"))
            n = len(self.files)
            # Счётчик — только когда есть что считать: «1 вкладка» над
            # списком из одной строки ничего не сообщает.
            if n > 1:
                t.append(f"   {n} "
                         f"{plural(n, 'вкладка', 'вкладки', 'вкладок')}",
                         style=palette.role_hex("faint"))
            head.update(t)
        except Exception:
            pass
        box.remove_children()
        rows: list = []
        title = palette.role_hex("title")
        dim = palette.role_hex("dim")
        faint = palette.role_hex("faint")

        # ОТКРЫТОЕ — первым. Каталог был только списком того, что можно
        # открыть, и молчал о том, что уже открыто: имена буферов жили лишь
        # в узкой полосе вкладок сверху, где после третьего файла начинается
        # прокрутка. Работа же идёт с несколькими участками сразу — ради
        # этого вкладки и заводились.
        # Заголовка «открыто» здесь нет: шапка окна уже называется ФАЙЛЫ, и
        # первый же список под ней — открытые. Строка-подпись под строкой-
        # подписью на колонке в 22 клетки стоит дороже, чем объясняет.
        for i, rec in enumerate(self.files):
            t = Text()
            here = i == self.file_i
            t.append("  " + ("▸ " if here else "  "),
                     style=palette.role_hex("accent2" if here else "faint"))
            nm = rec["name"]
            t.append(nm if len(nm) <= 16 else nm[:15] + "…",
                     style=title if here else dim)
            item = SideItem(f"buf:{i}", t, classes="side-item")
            item.tooltip = (f"{rec['name']}\nклик — перейти"
                            "\nдвойной клик — переименовать")
            rows.append(item)


        # ЗАВЕСТИ НОВЫЙ. Раньше здесь была одна «+ новая вкладка», и она
        # всегда делала `.s`: рядом с участком живут ещё скрипт, который его
        # породил, и заметка о том, что уже пробовали, — их приходилось
        # держать в чужом окне и терять контекст при каждом возврате.
        rows.append(Static(Text("\n завести", style=title)))
        for suffix, label, _base, _seed in self.FILE_KINDS:
            t = Text()
            t.append("  + " + label, style=palette.role_hex("accent2"))
            item = SideItem(f"new:{suffix}", t, classes="side-item")
            item.tooltip = (f"новый .{suffix} вкладкой"
                            + ("" if suffix in ("s", "asm")
                               else "\nразбор и F5 работают только на .s"))
            rows.append(item)

        # Списка файлов рядом здесь больше НЕТ: он показывал один каталог
        # плоским перечнем и отвечал только на вопрос «что вообще лежит
        # вокруг». Его место занял проводник справа (^E) — там папки, поиск
        # по имени и своё окно, которое убирается целиком.

        # Подписи короче ширины колонки (20 клеток под текст). Прежние
        # («^B убрать эту колонку») переносились посреди фразы, и колонка
        # объясняла себя обрывками: «убрать эту» / «колонку».
        for key, what in (("^B ", "скрыть колонку"),
                          ("F12", "скрыть док"),
                          ("F2 ", "переименовать")):
            t = Text()
            t.append(" " + key + " ", style=palette.role_hex("accent_soft"))
            t.append(what, style=faint)
            rows.append(Static(t))
        box.mount(*rows)

    def _deletable(self, rel: str) -> bool:
        """Наш ли это файл. Удалять можно только внутри рабочего каталога.

        Примеры машины лежат в пакете, и путь к ним абсолютный — стереть их
        из каталога значило бы испортить установку инструмента промахом
        мимо имени.
        """
        if not rel or rel.startswith("new:") or rel.startswith("buf:"):
            return False
        path = Path(rel)
        if path.is_absolute():
            return False
        try:
            path.resolve().relative_to(Path.cwd().resolve())
        except (ValueError, OSError):
            return False
        return True

    def _delete_file(self, rel: str) -> None:
        """Стереть файл с диска и закрыть его вкладку, если она открыта.

        Открытый буфер закрывается вместе с файлом: вкладка, которая
        указывает на несуществующий путь, — это Ctrl+S, воскрешающий
        удалённое, и «сохранено» там, где ничего не сохранено.
        """
        self._to_delete = ""
        if not self._deletable(rel):
            return
        con = self.console
        try:
            Path(rel).unlink()
        except OSError as exc:
            if con is not None:
                con.note(f"  не удалось удалить {rel}: {exc}", "error")
            self._draw_side()
            return
        if con is not None:
            con.note(f"  удалён {rel}", "warning")
        for i, rec in list(enumerate(self.files)):
            if rec.get("path") == rel and len(self.files) > 1:
                self.close_file(i)
                break
        else:
            for rec in self.files:
                if rec.get("path") == rel:
                    rec["path"] = ""
                    if self.app.session.code_path == rel:
                        self.app.session.code_path = ""
        self._draw_side()
        self._draw_explorer()
        self.refresh_context()

    def _rel(self, path) -> str:
        """Путь относительно рабочего каталога, если файл внутри него."""
        try:
            return str(path.relative_to(Path.cwd()))
        except ValueError:
            return str(path)

    def redraw(self) -> None:
        self._draw_hello()
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
            t.append(f"  такт {op.cycle}", style=palette.role_hex("dim"))
            orc = self._orc_cycle(op.index)
            if orc is not None and orc != op.cycle:
                # Расшифровка метки гуттера. В гуттере она короткая («т1→0»)
                # по месту, и что значит стрелка, оттуда не узнать. Здесь
                # место есть — и написано словами.
                role = "success" if orc < op.cycle else "warning"
                t.append(f" → {orc} у поиска", style=palette.role_hex(role))
        else:
            t.append("  не операция", style=palette.role_hex("faint"))
        mine = [x for x in self.problems if x.line == line]
        if mine:
            t.append(f"  ▲{len(mine)}", style=palette.role_hex("error"))
        # На широком окне у стрелки есть подпись: догадаться, что строка
        # состояния кликабельна, иначе неоткуда.
        if (self.size.width or 120) >= 120:
            t.append("  разбор ▸", style=palette.role_hex("faint"))
        else:
            t.append("  ▸", style=palette.role_hex("faint"))
        chip.tooltip = ("что под курсором: строка, класс операции, "
                        "латентность, такт выдачи\n"
                        "«→ N у поиска» — в какой такт её кладёт точный "
                        "поиск (метка т1→0 в гуттере про то же)\n"
                        "клик — открыть вкладку РАЗБОР")
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
                    # Точный поиск оставил операцию там же. Знака «=» здесь
                    # нет нарочно: он стоял бы у большинства строк, занимал
                    # колонку гуттера на всём файле и сообщал «делать
                    # нечего». Молчание сообщает то же самое бесплатно.
                    label = f"т{o.cycle}"
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

    def _draw_hello(self) -> None:
        """Первый экран: что это за окно и три шага работы.

        Прячется, как только в буфере появляется хоть одна операция e2k:
        приветствие поверх чужого кода — это не приветствие, а помеха.
        """
        try:
            hello = self.query_one("#code-hello", Static)
        except Exception:
            return
        has_ops = self.parsed is not None and bool(self.parsed.ops)
        text = self.query_one("#code-edit", AsmArea).text
        # Порог по длине, а не только по операциям: пока человек пишет
        # первые строки и они ещё не разбираются, подсказка мешать не должна.
        hello.display = (not has_ops) and len(text.strip()) < 200
        if not hello.display:
            return
        # Слой overlay считает смещение от ЭКРАНА, а не от редактора, и с
        # открытой колонкой вкладок приветствие наезжало на неё: «^B скрыть»
        # читалось поверх «NEX · КОД». Ставим его по левому краю редактора.
        try:
            edit = self.query_one("#code-edit", AsmArea)
            hello.styles.offset = (edit.region.x + 6, 2)
            hello.styles.width = max(40, min(64, edit.region.width - 8))
        except Exception:
            pass
        title = palette.role_hex("title")
        dim = palette.role_hex("dim")
        faint = palette.role_hex("faint")
        key = palette.role_hex("accent2")
        t = Text()
        t.append("\n  NEX · КОД", style=title)
        t.append("   планировщик широких команд Эльбруса\n\n", style=dim)
        # Строки короче ширины виджета: перенос у Static начинается с его
        # левого края, и продолжение уезжает под отступ — читается как новый
        # пункт. Здесь длина каждой строки подобрана под 60 клеток.
        t.append("  сюда приносят ", style=dim)
        t.append(".s от lcc -O3", style=palette.role_hex("accent"))
        t.append(",\n  чтобы увидеть, где потеряны такты\n\n", style=dim)

        for k, what in (("^E", "проводник — найти свой .s на диске"),
                        ("F5", "посчитать: как лёг компилятор и как можно"),
                        ("2×клик", "по вкладке внизу — блок на весь экран")):
            t.append(f"  {k:<8}", style=key)
            t.append(what + "\n", style=dim)

        t.append("\n  нет своего .s? ", style=faint)
        t.append("/example slots", style=key)
        t.append("  — учебный участок\n", style=faint)
        hello.update(t)

    def _draw_status(self) -> None:
        """Правый край строки состояния: чего этот код стоит.

        Здесь ТОЛЬКО то, чего нет в верхней строке. Раньше стояло «15 оп. ·
        15 команд · исходник 15 т. → поиск 8 т.», и ровно те же «15→8 т. ·
        15 оп.» стояли в шапке — одно число в двух местах экрана это не
        подстраховка, а шум. Наверху осталось «сколько и во сколько», здесь
        — «что с этим делать»: сколько машины простаивает и сколько тактов
        лежит на полу.
        """
        line = Text()
        dim = palette.role_hex("dim")
        # Файл не для планировщика — говорим об этом прямо. Иначе строка
        # состояния показывает «буфер пуст» над полным текстом скрипта, и
        # это читается как поломка разбора, а не как «его тут и не должно
        # быть».
        if not self._is_asm():
            name = self.files[self.file_i]["name"] if self.files else ""
            suffix = name.rsplit(".", 1)[-1] if "." in name else "?"
            line.append(f".{suffix} — не e2k", style=palette.role_hex("warning"))
            line.append("   ·   разбор и F5 — только для .s", style=dim)
            self.query_one("#code-status", Static).update(line)
            return
        if self.parsed is None or not self.parsed.ops:
            if self.problems:
                bad = len(self.problems)
                line.append(f"ни одной операции: {bad} "
                            f"{plural(bad, 'строка', 'строки', 'строк')} "
                            f"не разобрать", style=palette.role_hex("warning"))
            else:
                line.append("буфер пуст", style=dim)
            self.query_one("#code-status", Static).update(line)
            return
        if self.comp is not None:
            slots = self.comp.slot_utilization
            line.append(f"слоты {slots * 100:.0f}%", style=dim)
            if self._have_orc():
                line.append(f" → {self.orc.schedule.slot_utilization * 100:.0f}%",
                            style=palette.role_hex("success"))
        else:
            # Дальше про резерв не говорим: сравнивать не с чем, а длинная
            # фраза на 80 колонках обрезалась бы посреди слова. Обрезанная
            # подсказка хуже отсутствующей — она выглядит как поломка.
            line.append("не по модели", style=palette.role_hex("warning"))
            self.query_one("#code-status", Static).update(line)
            return
        if self._have_orc():
            orc = self.orc.schedule.makespan
            src = self.comp.makespan if self.comp is not None else None
            # Резерв — только когда машина знает, из чего он складывается.
            # При заметной доле UNKNOWN точный поиск обыгрывает компилятор не
            # планом, а незнанием цены операций (латентность-заглушка 1), и
            # называть разницу резервом — неправда. Тот же порог, что в
            # построчном разборе: правило живёт в ядре, не в двух интерфейсах.
            if src is not None and self.unknown_share >= asm_parser.UNKNOWN_SHARE_LIMIT:
                line.append(f"   ·   сравнивать нельзя: "
                            f"{self.unknown_share:.0%} операций машине неизвестны",
                            style=palette.role_hex("warning"))
            elif src is not None and src > orc:
                gap = src - orc
                line.append(f"   ·   резерв {gap} т. "
                            f"({100 * gap / src:.0f}%)",
                            style=palette.role_hex("success"))
            elif src is not None:
                line.append("   ·   резерва нет", style=dim)
        elif self._stale():
            line.append("   ·   буфер правили — F5",
                        style=palette.role_hex("warning"))
        elif (self.size.width or 120) >= 110:
            # Совет — только там, где он влезает целиком. На узком окне эта
            # же строка обрезалась до «F5 —», и обрубок в строке состояния
            # читается как поломка, а не как нехватка места. Клавиша при
            # этом не теряется: она стоит в подсказках слева.
            line.append("   ·   F5 — посчитать резерв",
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
        # После разворота решётки колонка — это ТАКТ, а тактов много, и они
        # прокручиваются вбок. Значит ужимать клетку под ширину панели больше
        # не нужно: раньше шесть каналов обязаны были влезть одновременно,
        # теперь одновременно обязаны влезть шесть КАНАЛОВ ПО ВЕРТИКАЛИ, а с
        # этим проблем нет — их всегда ровно шесть.
        #
        # Восемь символов: столько занимают самые длинные мнемоники, которые
        # реально встречаются в выводе lcc (`fdtoistr`, `fmul_add`). Меньше —
        # и обрезка снова начинает съедать смысл.
        return 8

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

        self._sched_left = left
        self._sched_which = which
        if self.drawer_tab == "sched":
            self._draw_dock_note()
        self._draw_sched_side()
        self._draw_sched_empty(left)

        wrap = self.query_one("#code-grid-orc-wrap")
        # В развороте место под вторую решётку держим ВСЕГДА. Пока точного
        # поиска нет, там стоит приглашение его посчитать — а не пустая
        # половина экрана, которая молчит о том, что здесь вообще бывает.
        # Заодно решётка не прыгает в ширине после F5: место уже занято.
        wrap.display = both or bool(self.zoom and self.drawer_tab == "sched")
        head = self.query_one("#code-grid-orc-head", Static)
        if both:
            head.update(
                Text(f"  точный поиск   ·   {self.orc.schedule.makespan} т.",
                     style=palette.role_hex("accent")))
            self._fill_grid("code-grid-orc", self.orc.schedule, "orc")
        elif wrap.display:
            t = Text()
            t.append("  точный поиск\n", style=palette.role_hex("faint"))
            if self.parsed is None or not self.parsed.ops:
                t.append("  считать нечего: в буфере нет операций e2k\n",
                         style=palette.role_hex("faint"))
            else:
                t.append("  F5", style=palette.role_hex("accent2"))
                t.append("  посчитать, как этот же граф может лечь\n",
                         style=palette.role_hex("dim"))
                t.append("  здесь встанет вторая решётка — такт в такт "
                         "рядом с первой\n", style=palette.role_hex("faint"))
            head.update(t)
            self.query_one("#code-grid-orc", DataTable).clear(columns=True)

    def _draw_sched_empty(self, left) -> None:
        """Вместо пустого прямоугольника — почему пусто и что делать."""
        try:
            note = self.query_one("#sched-empty", Static)
            wrap = self.query_one("#code-grid-wrap")
        except Exception:
            return
        t = Text()
        if self.parsed is None or not self.parsed.ops:
            t.append("  в буфере нет ни одной операции e2k.\n\n",
                     style=palette.role_hex("dim"))
            t.append("  ^B", style=palette.role_hex("accent2"))
            t.append("  открыть каталог и взять пример или настоящий .s\n",
                     style=palette.role_hex("dim"))
            if self.problems:
                bad = len(self.problems)
                t.append(f"  вкладка ЗАМЕЧАНИЯ  почему не разобрались "
                         f"{bad} "
                         f"{plural(bad, 'строка', 'строки', 'строк')}\n",
                         style=palette.role_hex("warning"))
        elif left is None:
            t.append("  расписание из буфера не восстановилось: "
                     "раскладка по каналам спорит с моделью машины.\n\n",
                     style=palette.role_hex("warning"))
            t.append("  вкладка ЗАМЕЧАНИЯ", style=palette.role_hex("accent2"))
            t.append("  что именно не сошлось\n",
                     style=palette.role_hex("dim"))
            t.append("  F5", style=palette.role_hex("accent2"))
            t.append("  точный поиск всё равно посчитает: он строит "
                     "расписание сам, а не читает написанное\n",
                     style=palette.role_hex("dim"))
        else:
            note.display = False
            wrap.display = True
            return
        note.update(t)
        note.display = True
        # Решётку прячем: пустая таблица с одной шапкой тактов рядом с
        # объяснением читается как «что-то сломалось наполовину».
        wrap.display = False

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

        # Панель теперь низкая и широкая (раскладка как в IDE: расписание
        # пристыковано снизу), поэтому разбор ужат под высоту, а не под
        # ширину. Загрузка портов занимала семь строк таблицей — свёрнута в
        # одну: она отвечает на вопрос «где тесно», и для этого достаточно
        # видеть числа в ряд.
        try:
            avail = max(4, self.query_one("#sched-side").size.height - 1)
        except Exception:
            avail = 9

        t.append("ПОРТЫ  ", style=palette.role_hex("title"))
        for port in range(model.width):
            src = self._port_load(self.comp, port)
            t.append(f"{model.port_label(port)}:", style=palette.role_hex("faint"))
            t.append(f"{src} ", style=palette.role_hex("text" if src else "faint"))
        t.append("\n")
        if self._have_orc():
            t.append("поиск  ", style=palette.role_hex("faint"))
            for port in range(model.width):
                src = self._port_load(self.comp, port)
                orc = self._port_load(self.orc.schedule, port)
                role = "success" if orc > src else ("dim" if orc == src
                                                    else "warning")
                t.append(f"{model.port_label(port)}:",
                         style=palette.role_hex("faint"))
                t.append(f"{orc} ", style=palette.role_hex(role))
            t.append("\n")
        if self.comp is not None:
            t.append(f"слоты {self.comp.slot_utilization * 100:.0f}%", style=dim)
            if self._have_orc():
                t.append(f"  →  "
                         f"{self.orc.schedule.slot_utilization * 100:.0f}%",
                         style=palette.role_hex("success"))
            t.append("\n")

        # Разбор клетки — ВЫШЕ списка перестановок: курсором ходят прямо
        # сейчас, а список читают один раз. Внизу колонки он оказывался под
        # четырнадцатью строками перестановок, то есть за краем.
        if self.zoom:
            t.append_text(self._sched_cursor_text())

        moves = self._moves()
        if moves:
            # Сколько строк осталось под список после шапки портов и разбора
            # клетки. В развороте разбор занимает верх колонки, и список
            # должен ужаться, а не вытолкнуть его за край.
            room = max(1, avail - (4 if self._have_orc() else 3)
                       - (12 if self.zoom else 0))
            t.append(f"\nПЕРЕСТАВИТЬ   {len(moves)}\n",
                     style=palette.role_hex("title"))
            shown = moves[:room]
            for line, text in shown:
                t.append_text(text)
                t.append("\n")
            if len(moves) > len(shown):
                t.append(f"      ещё {len(moves) - len(shown)}"
                         f"  —  F12 развернёт панель\n",
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

    def _sched_cursor_text(self) -> Text:
        """Разбор клетки под курсором и загрузка каналов — в развороте.

        Разворачивают решётку, чтобы РАБОТАТЬ в ней: ходить курсором по
        тактам и спрашивать «а почему тут пусто». Пока разворот показывал
        ту же решётку крупнее, ответа на этот вопрос в нём не было — за ним
        уходили в полноэкранный РАЗБОР и теряли из виду свой код. Тот же
        разбор здесь, рядом с клеткой, на которой стоит курсор.
        """
        dim = palette.role_hex("dim")
        faint = palette.role_hex("faint")
        t = Text()
        sched = self._sched_left
        if sched is None:
            return t
        model = self.app.session.model()
        try:
            table = self.query_one("#code-grid", DataTable)
            row, col = table.cursor_coordinate
        except Exception:
            return t
        # Нулевая колонка — закреплённая подпись, и курсор стоит на ней,
        # пока по решётке не ходили. Молчать в этот момент нельзя: разбор
        # клетки нужен ПЕРВЫМ делом, а не после первого нажатия стрелки.
        col = max(col, 1)
        cycle, port = ((row, col - 1) if self._tall_grid()
                       else (col - 1, row))

        t.append("\nКУРСОР\n", style=palette.role_hex("title"))
        t.append(f"такт {cycle}   канал {model.port_label(port)}\n",
                 style=dim)
        instr = self._grid_cells.get((self._sched_which, cycle, port))
        if instr is not None and self.parsed is not None \
                and instr < len(self.parsed.ops):
            op = self.parsed.ops[instr]
            t.append(f"  {op.mnemonic}", style=palette.op_style(op.op))
            t.append(f"   стр.{op.line}\n", style=dim)
            t.append(f"  {op.op} · латентность {model.latency(op.op)} т.",
                     style=dim)
            if model.occupancy(op.op) > 1:
                t.append(f" · держит порт {model.occupancy(op.op)} т.",
                         style=dim)
            t.append("\n")
        else:
            t.append("  слот пуст\n", style=faint)
            takes = [n for n in model.ops if port in model.channels_for(n)]
            if takes:
                t.append("  канал принимает: ", style=faint)
                t.append(" ".join(sorted({n for n in takes})[:6]), style=dim)
                t.append("\n")

        t.append("\nКАНАЛЫ\n", style=palette.role_hex("title"))
        span = max(sched.span_cycles, 1)
        for p_i in range(model.width):
            load = self._port_load(sched, p_i)
            filled = round(10 * load / span) if span else 0
            t.append(f"{model.port_label(p_i)} ", style=faint)
            t.append("█" * filled, style=palette.role_hex(
                "warning" if filled >= 8 else "accent2"))
            t.append("·" * (10 - filled), style=faint)
            t.append(f" {load}\n", style=dim if load else faint)
        return t

    def _port_load(self, sched, port: int) -> int:
        """Сколько операций выдано в этот канал за всё расписание."""
        if sched is None:
            return 0
        return sum(1 for p in sched.placements.values() if p.channel == port)

    def _tall_cell_w(self, channels: int) -> int:
        """Ширина клетки развёрнутой решётки — от места, а не константой.

        Считаем сами, а не спрашиваем таблицу: `table.size.width` известна
        только после раскладки, и первое заполнение шло по старой ширине —
        два последних канала уезжали за край ровно в развороте, ради
        которого решётку и открывают. Место делится на число решёток: рядом
        может стоять вторая, «как посчитал поиск».
        """
        side = 40 if self.zoom else 0
        # В развороте место делится надвое всегда: справа либо вторая
        # решётка, либо приглашение её посчитать. Иначе клетки прыгали бы в
        # ширине от F5 — то есть расписание перерисовывалось бы другим.
        grids = 2 if self._sched_expanded else 1
        room = max(24, ((self.size.width or 120) - side) // grids)
        return max(6, min(11, (room - 10) // max(1, channels)))

    def _tall_grid(self) -> bool:
        """Растить решётку вниз (такты — строки) или вбок (такты — колонки).

        Форма выбирается по тому, чего на экране больше. В доке высотой в
        восемь строк такты обязаны идти ВБОК: шесть каналов — это шесть
        строк, они всегда влезают, а тактов бывает под сотню.

        В развороте всё наоборот, и прежняя форма там врала о размере:
        решётка держала одну восьмую высоты, тянулась за правый край
        экрана — и половина расписания оставалась за кадром при пустом
        экране под ней. Развернули, чтобы увидеть ЦЕЛИКОМ; значит расти
        надо в ту сторону, где место, — вниз.
        """
        return bool(self.zoom) and self.drawer_tab == "sched"

    def _fill_grid(self, table_id: str, sched, which: str) -> None:
        table = self.query_one("#" + table_id, DataTable)
        table.clear(columns=True)
        if sched is None or self.parsed is None:
            return
        if self._tall_grid():
            self._fill_grid_tall(table, sched, which)
            return
        model = self.app.session.model()
        dag = sched.dag
        busy = sched.busy_map()
        used = {p.channel for p in sched.placements.values()}
        cw = self._cell_w()
        span = max(sched.span_cycles, 1)

        # Канал — ЗАКРЕПЛЁННАЯ первая колонка, а не подпись строки
        # (`add_row(label=...)`). Подпись строки у DataTable уезжает вместе
        # с содержимым при прокрутке вбок — а вбок здесь прокручивают
        # всегда, тактов много. Стоило уехать трём знакам `,0`, и решётка
        # переставала отвечать на свой единственный вопрос: в какой канал
        # встала операция. Плюс ширина подписи считается лениво и в узком
        # окне схлопывалась в ноль — подписи пропадали совсем.
        table.add_column(Text(""), width=3, key="chan")

        # РЕШЁТКА РАЗВЁРНУТА: такты по горизонтали, каналы по вертикали.
        #
        # Было наоборот, и форма не совпадала с содержимым. Настоящее
        # расписание разрежено: в обычном участке 34 такта на 9 операций, то
        # есть 204 клетки при девяти занятых — интерфейс сам печатал «слоты
        # заняты на 4%». В прежней раскладке это давало три десятка почти
        # пустых строк, а шесть каналов ютились по ширине и обрезались.
        #
        # Развёрнутая решётка всегда ровно шесть строк — по числу каналов, и
        # это число не растёт. Простой делителя виден одной длинной полосой
        # вместо одиннадцати пустых строк, а прокрутка идёт вбок по тактам,
        # то есть по той оси, вдоль которой расписание и длинное.
        for cycle in range(span):
            head = Text(f"т{cycle}", style=palette.role_hex("dim"))
            table.add_column(head, width=cw, key=str(cycle))

        # Красная клетка значит «так написано и так нельзя». В решётке
        # точного поиска раскладка законна по построению — красить там
        # нечего, иначе метка обвиняет поиск в чужой ошибке.
        bad = ({p.op for p in self.problems
                if p.severity == "error" and p.op >= 0}
               if which == "src" else set())

        for port in range(model.width):
            cells = []
            for cycle in range(span):
                slot = busy.get((cycle, port))
                if slot is None:
                    cells.append(Text(f" {EMPTY}",
                                      style=palette.role_hex("faint")))
                    continue
                instr, head_cell = slot
                self._grid_cells[(which, cycle, port)] = instr
                style = palette.op_style(dag[instr].op)
                if not head_cell:
                    # Продолжение длинной операции тянется теперь ВПРАВО, а не
                    # вниз: занятость порта во времени — это горизонталь.
                    cells.append(Text(" " + CONT * max(1, cw - 2), style=style))
                    continue
                cells.append(self._cell_text(instr, cw, instr in bad))
            idle = port not in used
            head = Text(model.port_label(port),
                        style=palette.role_hex("faint" if idle else "dim"))
            table.add_row(head, *cells)

    def _fill_grid_tall(self, table, sched, which: str) -> None:
        """Развёрнутая решётка: такт — строка, канал — колонка.

        Подпись строки несёт и занятость такта («2/6»): в этой форме такт —
        строка целиком, и сказать про него, насколько он плотный, стоит
        ровно двух знаков. Именно так решётку показывает полноэкранный
        РАЗБОР, и два разных вида одного расписания в одном инструменте —
        лишний повод сверять глазами, что это одно и то же.
        """
        model = self.app.session.model()
        dag = sched.dag
        busy = sched.busy_map()
        span = max(sched.span_cycles, 1)
        # Шесть каналов обязаны быть видны ЦЕЛИКОМ — решётка отвечает на
        # вопрос «в какой канал это встало», и обрезанный ,5 (тот самый
        # монопольный делитель) делает её бесполезной. Поэтому ширину клетки
        # считаем от места: рядом может стоять вторая решётка, и тогда на
        # каждую приходится половина экрана.
        cw = self._tall_cell_w(model.width)

        table.add_column(Text(""), width=8, key="cycle")
        for port in range(model.width):
            table.add_column(Text(model.port_label(port),
                                  style=palette.role_hex("dim")),
                             width=cw, key=f"p{port}")

        bad = ({p.op for p in self.problems
                if p.severity == "error" and p.op >= 0}
               if which == "src" else set())

        for cycle in range(span):
            cells = []
            taken = 0
            for port in range(model.width):
                slot = busy.get((cycle, port))
                if slot is None:
                    cells.append(Text(f" {EMPTY}",
                                      style=palette.role_hex("faint")))
                    continue
                taken += 1
                instr, head_cell = slot
                self._grid_cells[(which, cycle, port)] = instr
                style = palette.op_style(dag[instr].op)
                if not head_cell:
                    # Продолжение длинной операции в этой форме — вертикаль:
                    # порт занят следующим тактом, и это видно столбиком.
                    cells.append(Text(" │", style=style))
                    continue
                cells.append(self._cell_text(instr, cw, instr in bad))
            head = Text(f"т{cycle}".ljust(4),
                        style=palette.role_hex("dim" if taken else "faint"))
            head.append(f"{taken}/{model.width}",
                        style=palette.role_hex(
                            "warning" if taken * 2 <= model.width else "text")
                        if taken else palette.role_hex("faint"))
            table.add_row(head, *cells)

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

    # _row_label удалён вместе с разворотом решётки. Он подписывал строку
    # номером такта и долей занятых слотов («т12 2/6»). После разворота строка
    # — это канал, а доля занятости и так видна глазами: в развёрнутой решётке
    # плотный такт выглядит как вертикальный столбик заполненных клеток.
    # Дробь дублировала то, что решётка показывает без слов, и съедала место.

    def _sync_grid_cursor(self, line: int) -> None:
        """Курсор в коде → клетка в решётке. Связь в обе стороны."""
        op = self._op_at_line(line)
        if op is None:
            return
        for (which, cycle, port), instr in self._grid_cells.items():
            if which != "src" or instr != op.index:
                continue
            table = self.query_one("#code-grid", DataTable)
            # Какая ось где — зависит от формы решётки (см. _tall_grid).
            # Первая колонка всегда закреплённая подпись, отсюда +1.
            row, col = ((cycle, port) if self._tall_grid() else (port, cycle))
            if row < table.row_count and col + 1 < len(table.columns):
                table.move_cursor(row=row, column=col + 1)
            return

    def on_data_table_cell_highlighted(self, event) -> None:
        """Курсор поехал по решётке — обновить разбор клетки рядом."""
        if self.zoom and self.drawer_tab == "sched":
            self._draw_sched_side()

    def on_data_table_cell_selected(self, event) -> None:
        """Клик по клетке — курсор на строку этой операции в исходнике."""
        event.stop()
        which = "orc" if event.data_table.id == "code-grid-orc" else "src"
        # Минус один: нулевая колонка занята закреплённой подписью. Что
        # означают строка и колонка, зависит от формы решётки (_tall_grid).
        if self._tall_grid():
            cycle, port = event.coordinate.row, event.coordinate.column - 1
        else:
            cycle, port = event.coordinate.column - 1, event.coordinate.row
        instr = self._grid_cells.get((which, cycle, port))
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
        scroll = self.query_one("#dock-lint", VerticalScroll)
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
            widgets.append(Static(self._checked_text()))

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

    def _checked_text(self) -> Text:
        """Что именно проверено ДО прогона — раз замечаний нет.

        «Замечаний нет» на весь блок в двенадцать строк не отвечает на
        главный вопрос: а проверял ли ты вообще? Линтер к этому моменту уже
        прошёл по каналам, готовности операндов и загрузке машины — и всё
        это посчитано без F5. Сказать, что именно сошлось, стоит трёх строк
        и снимает вопрос.
        """
        dim = palette.role_hex("dim")
        faint = palette.role_hex("faint")
        model = self.app.session.model()
        parsed = self.parsed
        t = Text()
        n = len(parsed.ops)
        t.append(f"\n  {n} ", style=palette.role_hex("text"))
        t.append(f"{plural(n, 'операция', 'операции', 'операций')} "
                 f"в {parsed.bundles} "
                 f"{plural(parsed.bundles, 'широкой команде', 'широких командах', 'широких командах')}\n",
                 style=dim)
        t.append("  каналы законны, операнды готовы вовремя\n", style=dim)

        # Что в этом буфере дорого по времени — тоже известно без прогона:
        # латентности сняты измерением и лежат в модели.
        heavy: dict[str, int] = {}
        for op in parsed.ops:
            if model.latency(op.op) > 1:
                heavy[op.op] = heavy.get(op.op, 0) + 1
        for cls, count in sorted(heavy.items(), key=lambda kv: -kv[1])[:3]:
            chans = ",".join(str(c) for c in model.channels_for(cls))
            t.append(f"  {cls}", style=palette.op_style(cls))
            t.append(f" ×{count}   ждать {model.latency(cls)} т.   "
                     f"каналы {chans}\n", style=faint)
        if self.comp is not None:
            free = model.width - round(
                self.comp.slot_utilization * model.width)
            t.append(f"  слоты заняты на "
                     f"{self.comp.slot_utilization * 100:.0f}% — "
                     f"{free} из {model.width} каналов простаивают\n",
                     style=palette.role_hex(
                         "warning" if free >= 4 else "dim"))
        return t

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
            return self.query_one("#code-dock", Vertical).size.width - 4
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
        # Развёрнутый док прячет половину кода: раз уж прыгаем на строку,
        # её надо и увидеть.
        if self.zoom:
            self.set_zoom("")
        edit.goto_line(line)
        edit.focus()

    # --- разбор такта под курсором ----------------------------------------

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
        у #dock-bundles: разбор такта под курсором (#code-line-info)
        живёт выше и курсором же обновляется, стирать его нельзя.
        """
        box = self.query_one("#dock-bundles", VerticalScroll)
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

    # --- разворот дока ------------------------------------------------------

    def open_block(self, tab: str) -> None:
        """Развернуть блок вкладки на весь экран, оставаясь в КОДЕ.

        Полный экран здесь — НЕ «то же самое покрупнее» и не уход в другой
        режим. Уводить нельзя: в другом экране нет ни файла, ни курсора, ни
        строки состояния буфера, а вопрос человек задаёт про то, что перед
        ним. А просто растянуть блок мало: место, которое освободилось,
        должно чем-то стать. Поэтому разворот ДОБАВЛЯЕТ блоку инструменты,
        которым в восьми строках не было места, — см. `set_zoom` и правила
        `ModeScreen.zoom-dock` в nex.tcss.
        """
        # Тот же жест сворачивает: двойной клик по вкладке, уже занимающей
        # экран, возвращает раскладку. Двойной клик по ДРУГОЙ вкладке в
        # развороте переключает на неё, не сворачивая, — как переключение
        # инструментальных окон в IDE, когда одно из них раскрыто.
        same = self.zoom and self.drawer_open and self.drawer_tab == tab
        self.open_drawer(tab)
        self.set_zoom("" if same else "dock")

    def action_zoom_dock(self) -> None:
        """Док на весь экран и обратно: F11 или двойной клик по вкладке.

        Развёрнутая вкладка получает то, чему в трети экрана места не было, —
        вторую решётку рядом с первой, полные тексты замечаний с советами,
        журнал сессии вместо ленты вывода. Редактор на это время уходит
        совсем: расписание в шесть каналов на сотню тактов читается только во
        всю ширину, а половинка не давала ни того ни другого.
        """
        self.set_zoom("" if self.zoom else "dock")

    def set_zoom(self, zoom: str) -> None:
        self.zoom = zoom
        self.set_class(bool(zoom), "zoom-dock")
        # Поставленная мышью высота — inline-стиль, а он сильнее любого CSS:
        # с ней разворот на весь экран не срабатывал бы вовсе. На время
        # разворота снимаем, при возврате отдаём обратно.
        try:
            dock = self.query_one("#code-dock", Vertical)
            dock.styles.height = None if zoom else self.dock_h
        except Exception:
            pass
        # Развёрнутый док обязан быть виден.
        if zoom and not self.drawer_open:
            self.open_drawer(self.drawer_tab)
        if self.drawer_tab == "core":
            self._draw_core_state()
        if zoom and self.drawer_tab == "agent":
            # Ширина колонки известна только после раскладки, а по ней
            # считается перенос текста — перерисовываем вторым проходом.
            self.call_after_refresh(self._draw_agent_extras)
        if zoom and self.drawer_tab == "sched":
            # Ширина клетки решётки считается от ширины таблицы, а она
            # известна только после раскладки — заполняем ещё раз, когда
            # экран уже перестроился. Иначе в развороте шесть каналов
            # считались по старой ширине и последние два уезжали за край.
            self.call_after_refresh(self._draw_grids)
        self._sched_expanded = bool(zoom) and self.drawer_tab == "sched"
        self._lint_expanded = bool(zoom) and self.drawer_tab == "lint"
        self._console_expanded = bool(zoom) and self.drawer_tab == "term"
        self._draw_grids()
        if self.drawer_open:
            self._draw_drawer()
        self.refresh_hints()

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
        """Ряд мостика во вкладке ВЫВОД — по выбору в истории сессии."""
        try:
            row = self.query_one("#drawer-bridge", BridgeRow)
            journal = self.query_one("#journal", ConsoleJournal)
        except Exception:
            return
        row.sync(self.app.session.journal_runs, journal.pos)

    # --- инструменты панелей ----------------------------------------------

    def on_tool_twice(self, event) -> None:
        """Двойной клик по названию вкладки — открыть её блок целиком.

        Считает двойной сам `Tool` (см. `Tool.Twice`): экрану сюда приходит
        уже готовый жест, а не пара нажатий, которую надо разбирать по
        часам.
        """
        event.stop()
        if event.tool.startswith("dock-"):
            self.open_block(event.tool.split("-", 1)[1])

    def panel_tool(self, tool: str) -> None:
        if tool.startswith("dock-"):
            # Одиночный клик только переключает вкладку. Двойной приходит
            # отдельным сообщением — см. `on_tool_twice`.
            self.open_drawer(tool.split("-", 1)[1])
        elif tool == "agent-repeat":
            last = next((m["text"] for m in reversed(self.app.session.dialog)
                         if m["role"] == "you"), "")
            if last:
                self._answer_in_ai(last)
        elif tool == "agent-clear":
            self.app.session.dialog.clear()
            self.ai_actions.clear()
            self._draw_dialog()
        elif tool == "agent-facts":
            self._draw_agent_extras()
        elif tool == "code-save":
            self.action_save_code()
        elif tool == "code-rewrite":
            self.action_rewrite()
        elif tool == "code-broken":
            self._load_example_named("broken")
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

    def _generate(self, kind: str, arg: str) -> None:
        """`/gen` и `/fill` — ситуация одной командой вместо ручного набора.

        Отличие от `/example`: там пять готовых текстов, здесь любая ситуация
        нужного размера. И она заведомо законна — каналы берутся из модели
        машины, поэтому `muls,2` (где умножение не исполняется) сгенерировать
        физически нельзя.

            /gen 8 muls          восемь независимых, по одной в такт
            /gen 8 muls плотно   они же, разложенные по всем каналам
            /gen цепочка 5 fmul  пять зависимых подряд
            /fill 20             двадцать тактов заполнителя
        """
        from ...core import asmgen

        model = self.app.session.model()
        con = self.console
        words = arg.split()

        def fail(text: str) -> None:
            if con is not None:
                con.note("  " + text, "error")

        try:
            if kind == "fill":
                cycles = int(words[0]) if words else 10
                text = asmgen.filler(model, max(1, min(cycles, 200)))
                name = f"заполнитель {cycles}"
            else:
                chain_mode = bool(words) and words[0] in ("цепочка", "chain")
                if chain_mode:
                    words = words[1:]
                packed = any(w in ("плотно", "packed") for w in words)
                words = [w for w in words if w not in ("плотно", "packed")]
                if len(words) < 2:
                    fail("нужно: /gen <сколько> <операция>   ·   "
                         "например /gen 8 muls")
                    fail("операции: " + ", ".join(asmgen.known_names()).lower())
                    return
                count = max(1, min(int(words[0]), 200))
                op = asmgen.resolve(words[1])
                if op is None:
                    fail(f"операция «{words[1]}» неизвестна")
                    fail("известны: " + ", ".join(asmgen.known_names()).lower())
                    return
                if chain_mode:
                    text = asmgen.chain(model, op, count)
                    name = f"цепочка {count} {words[1]}"
                else:
                    text = asmgen.independent(model, op, count, packed=packed)
                    name = f"{count} {words[1]}" + (" плотно" if packed else "")
        except ValueError as e:
            fail(str(e) if str(e) else "не понял число")
            return

        # Своей вкладкой, как пример: набранное человеком не затирается.
        self.open_file(text, f"{name}.s")
        if con is not None:
            con.note(f"  сгенерировано: {name} — F5 прогнать", "success")

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
        """Пример — своей вкладкой, а не поверх того, что открыто.

        `code_path` НЕ трогаем нарочно: иначе ^S молча перезапишет файл
        примера в репозитории вместо работы человека. Имя стоит на вкладке —
        видно, что правишь пример, а не свой файл.

        Раньше пример затирал буфер: набрал участок, посмотрел пример «а как
        это выглядит правильно» — и своего кода больше нет. Отдельной
        вкладкой оба остаются на экране, и переключение между ними стоит
        одного клика.
        """
        self.open_file(text, f"{name or 'пример'}.s", example=name)
        con = self.console
        if con is not None:
            con.note(f"  пример «{name or 'без имени'}» открыт вкладкой — F5",
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
        if self._refuse_non_asm():
            return
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
            # Проверяем СВОЙ результат и говорим правду. Планировщик строит
            # граф только по истинным зависимостям (чтение после записи) —
            # антизависимости и выходные в нём не заведены намеренно, их
            # снимает переименование регистров. Но переписывание кладёт
            # операции обратно С ТЕМИ ЖЕ ИМЕНАМИ регистров, и тогда
            # законная для графа перестановка ломает текст: оракул ставит
            # `muls …→%r8` раньше того, кто `%r8` читает, и читатель берёт
            # затёртое значение. На examples/probe.s это два случая.
            # Пока переименования нет, честный выход один — не рапортовать
            # успех, когда собственный линтер нашёл ошибки.
            bad = len(self.problems)
            if bad:
                con.note(f"  буфер переписан   {gain}   ·   но проверка "
                         f"нашла {bad}: перестановка законна для графа "
                         f"зависимостей, а в тексте регистры не "
                         f"переименованы   ·   ^Z вернёт как было",
                         "warning")
            else:
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
        """Переключить решётку между «как написано» и точным поиском.

        Если поиска ещё нет — ЗАПУСКАЕМ его, а не отказываем. Кнопка
        «оракул» просит показать расписание точного поиска; ответ «его нет»
        человек уже видит по пустой решётке, а вот что делать дальше —
        приходилось знать. Теперь клик по ней и есть «посчитать и показать»,
        а вид переключится сам, когда счёт кончится.
        """
        if which == "orc" and not self._have_orc():
            if self.parsed is None or not self.parsed.ops:
                con = self.console
                if con is not None:
                    con.note("  считать нечего: в буфере нет операций e2k",
                             "warning")
                return
            self._want_orc = True
            self.action_run_code()
            return
        self.sched_view = which
        self._draw_grids()

    def _cell_to_code(self) -> None:
        table = self.query_one("#code-grid", DataTable)
        instr = self._grid_cells.get(("src", table.cursor_column - 1,
                                      table.cursor_row))
        if instr is not None and self.parsed is not None:
            self._goto_line(self.parsed.ops[instr].line)

    # --- факты для ИИ ------------------------------------------------------

    def panel_facts(self, topic: str) -> list[str]:
        if topic == "code":
            return self._code_facts()
        if topic == "sched":
            return self._sched_facts()
        if topic == "lint":
            return self._lint_facts()
        if topic == "core":
            return self._core_facts()
        if topic == "console":
            runs = self.app.session.journal_runs
            return ([f"{r.get('cmd', '')} — участок "
                     f"{r.get('scenario') or '—'}" for r in runs[-6:]]
                    or ["прогонов в этой сессии ещё не было"])
        return []

    def _core_facts(self) -> list[str]:
        ws = self.app.session.workspace()
        out = [f"в машине {len(ws.regs)} имён, в графе {ws.graph_size()} "
               "операций"]
        out += [f"{n} = {v}" for n, v in list(ws.regs.items())[:8]]
        return out

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
        if topic == "core":
            return ["что сейчас в графе?",
                    "как записать это же ассемблером e2k?"]
        if topic == "console":
            return ["что показал последний прогон?"]
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
        if head in ("gen", "fill"):
            self._generate(head, arg.strip())
            return
        if head == "rename":
            self._rename_buffer(arg)
            return
        super().handle_line(line)

    def action_back(self) -> None:
        """Esc — шаг наружу: подсказка, разворот дока, курсор в код, режим.

        Док по Esc НЕ закрывается: он открыт по умолчанию и является частью
        обычного вида, а не всплывшим окном. Закрывать умолчание клавишей
        «назад» значило бы каждый раз возвращать его руками.
        """
        sug = self.suggest
        if sug is not None and sug.display:
            sug.hide()
            return
        # Проводник — всплывшая колонка, а не часть обычного вида (в отличие
        # от дока ниже), поэтому Esc его закрывает. Без этой ступени первое
        # нажатие уходило впустую, второе выкидывало из режима, а проводник
        # оставался открытым и переживал перезапуск — `"explorer": true`
        # сохранялось в layout.json.
        if self.explorer_shown:
            self.action_toggle_explorer()
            return
        # Агент — вкладка дока, а док по Esc не закрывается: он часть
        # обычного вида, а не всплывшее окно. Esc из вкладки просто
        # возвращает курсор в код (см. ниже), как из любой другой.
        if list(self.query(PanelPrompt)):
            self.close_panel_prompt()
            self.refresh_hints()
            return
        self._sync_buffer()
        if self.zoom:
            self.set_zoom("")
            return
        edit = self.query_one("#code-edit", AsmArea)
        if not edit.has_focus:
            edit.focus()
            return
        super().action_back()

    def action_save_code(self) -> None:
        """Ctrl+S: сохранить. Имя берём у вкладки, а не спрашиваем заново.

        Раньше буфер без пути отправлял человека в строку команд дописывать
        `/code save <имя>` — при том, что имя у вкладки уже есть, он сам его
        и задал (F2 или тип файла при создании). Спрашивать второй раз то,
        что уже сказано, — не осторожность, а лишний шаг.

        Осторожность нужна в одном месте: если файл с таким именем на диске
        УЖЕ есть, молча его переписать нельзя. Тогда — прежний путь через
        строку команд, с подставленным именем: решает человек.
        """
        self._sync_buffer()
        last = getattr(self.app.session, "code_path", "")
        if last:
            self.handle_line(f"/code save {last}")
            return
        name = (self.files[self.file_i]["name"] if self.files else "").strip()
        # Пробелы в имени вкладки («участок 2.s») в имени файла неудобны:
        # такой путь придётся кавычить в каждой команде.
        name = name.replace(" ", "_")
        bar = self.query_one("#prompt", PromptBar)
        if not name:
            bar.focus_input()
            bar.set_value("/code save ")
            return
        if Path(name).exists():
            con = self.console
            if con is not None:
                con.note(f"  {name} уже есть на диске — допишите имя или "
                         "подтвердите", "warning")
            self.open_drawer("term")
            bar.focus_input()
            bar.set_value(f"/code save {name}")
            return
        self.handle_line(f"/code save {name}")
        self._draw_side()
