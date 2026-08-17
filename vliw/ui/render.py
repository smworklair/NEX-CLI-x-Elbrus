"""Общий инструментарий отрисовки: цвет, ширина, рамки, таблицы, панели.

Это фундамент пакета `vliw.ui`. Здесь нет никакой логики планирования — только
превращение готовых данных (из `vliw.core`) в строки для терминала. Работает на
голом ANSI; если установлен `rich`, панели оформляются им (graceful fallback).
"""

from __future__ import annotations

import io
import os
import shutil
import sys

from . import theme as _theme

# --------------------------------------------------------------------------
# Опциональный rich (единственная опциональная зависимость проекта)
# --------------------------------------------------------------------------

try:
    import rich  # noqa: F401
    from rich import box as _rich_box
    from rich.console import Console as _RichConsole
    from rich.panel import Panel as _RichPanel

    HAS_RICH = True
except Exception:  # pragma: no cover - зависит от окружения
    HAS_RICH = False


# --------------------------------------------------------------------------
# Ширина отчёта под реальный терминал
# --------------------------------------------------------------------------

W = 96  # уточняется под терминал в setup_output()
W_MIN = 56
W_MAX = 100


def detect_width(default: int = 96) -> int:
    """Ширина отчёта под терминал, зажатая в разумные пределы.

    Без адаптации на узком терминале (80 колонок и меньше) таблицы, рамки и
    разбор переносятся по словам и весь вывод «сыпется».
    """
    try:
        cols = shutil.get_terminal_size((default, 24)).columns
    except Exception:
        cols = default
    if not cols or cols <= 0:
        cols = default
    return max(W_MIN, min(W_MAX, cols))


def term_cols() -> int:
    """Реальная ширина терминала (для интерактивного ввода), без зажима."""
    try:
        return max(20, shutil.get_terminal_size((80, 24)).columns)
    except Exception:
        return 80


# --------------------------------------------------------------------------
# Цвет
# --------------------------------------------------------------------------


# Текущая тема. Меняется через apply_theme(); всё оформление ниже спрашивает
# цвета у неё, поэтому одна строка в JSON перекрашивает весь инструмент.
THEME = _theme.load_theme()


def apply_theme(name: str | None) -> None:
    """Переключить тему оформления и пересобрать производные константы."""
    global THEME, OP_CODE, CRIT_CODE, DIVERGE_CODE
    if name:
        THEME = _theme.load_theme(name)
    OP_CODE = {op: st.ansi for op, st in THEME.ops.items()}
    CRIT_CODE = THEME.ansi("crit")
    DIVERGE_CODE = THEME.ansi("diverge")


def c(role: str) -> str:
    """ANSI-код роли темы («accent», «border», «error», …)."""
    return THEME.ansi(role)


class Style:
    """Именованные стили. Цвета берутся из активной темы, а не зашиты в код.

    `bold`/`dim` — это атрибуты начертания, а не цвета, поэтому они одинаковы
    в любой теме; остальное — роли палитры.
    """

    enabled = True

    @classmethod
    def _w(cls, code: str, s: str) -> str:
        return f"\033[{code}m{s}\033[0m" if cls.enabled else s

    @classmethod
    def bold(cls, s: str) -> str:
        return cls._w("1", s)

    @classmethod
    def dim(cls, s: str) -> str:
        return cls._w("2", s)

    @classmethod
    def red(cls, s: str) -> str:
        return cls._w(c("error"), s)

    @classmethod
    def green(cls, s: str) -> str:
        return cls._w(c("success"), s)

    @classmethod
    def yellow(cls, s: str) -> str:
        return cls._w(c("warning"), s)

    @classmethod
    def blue(cls, s: str) -> str:
        return cls._w(c("accent"), s)

    @classmethod
    def accent(cls, s: str) -> str:
        return cls._w(c("accent"), s)

    @classmethod
    def accent2(cls, s: str) -> str:
        return cls._w(c("accent2"), s)

    @classmethod
    def inv(cls, s: str) -> str:
        return cls._w(c("selection"), s)


def paint(code: str, s: str) -> str:
    """Покрасить строку. `code` — имя роли темы либо готовый ANSI-код."""
    if not Style.enabled:
        return s
    return f"\033[{_resolve_color(code)}m{s}\033[0m"


def setup_output(color: bool | None = None, theme_name: str | None = None) -> None:
    """Настроить кодировку, цвет, тему и ширину под текущий вывод."""
    global W
    if theme_name:
        apply_theme(theme_name)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    if color is None:
        color = sys.stdout.isatty() and os.environ.get("TERM") != "dumb"
    if color and os.name == "nt":
        try:
            import ctypes

            k = ctypes.windll.kernel32
            k.SetConsoleMode(k.GetStdHandle(-11), 7)
        except Exception:
            color = False
    Style.enabled = bool(color)
    W = detect_width()


# --------------------------------------------------------------------------
# Акценты по типу операции (дорогие MUL/DIV — самыми яркими)
# --------------------------------------------------------------------------

# Цвета операций — это ДАННЫЕ, а не украшение: по ним в расписании сразу видно,
# куда попало деление (единственный порт `,5`) и как разошлись умножения по
# своим четырём каналам. Значения приходят из темы; здесь только производные.
OP_CODE: dict[str, str] = {}
CRIT_CODE = ""     # критический путь
DIVERGE_CODE = ""  # расхождение baseline/оракул

apply_theme(None)  # заполнить производные из темы по умолчанию


def op_code(op: str) -> str:
    return OP_CODE.get(op, c("text"))


def paint_op(op: str, s: str) -> str:
    return paint(op_code(op), s)


def op_legend() -> str:
    parts = [
        paint_op("DIV", "DIV"),
        paint_op("MUL", "MUL"),
        paint_op("LOAD", "LOAD/STORE"),
        paint_op("ADD", "ADD/SUB/лог."),
    ]
    return Style.dim("операции: ") + "  ".join(parts)


# --------------------------------------------------------------------------
# Ширины строк с учётом ANSI и базовые примитивы вёрстки
# --------------------------------------------------------------------------


def _plain_len(s: str) -> int:
    """Длина без ANSI-кодов."""
    out, i = 0, 0
    while i < len(s):
        if s[i] == "\033":
            j = s.find("m", i)
            i = len(s) if j < 0 else j + 1
            continue
        out += 1
        i += 1
    return out


vlen = _plain_len  # короткий алиас


def pad(s: str, n: int, align: str = "<") -> str:
    gap = max(0, n - _plain_len(s))
    if align == ">":
        return " " * gap + s
    if align == "^":
        left = gap // 2
        return " " * left + s + " " * (gap - left)
    return s + " " * gap


def plural(n: int, one: str, few: str, many: str) -> str:
    """Русское согласование: 1 такт, 2 такта, 5 тактов."""
    n = abs(n) % 100
    if 11 <= n <= 14:
        return many
    n %= 10
    if n == 1:
        return one
    if 2 <= n <= 4:
        return few
    return many


def cycles(n: int) -> str:
    return f"{n} {plural(n, 'такт', 'такта', 'тактов')}"


def h1(title: str) -> str:
    return "\n" + Style.bold("═" * W) + "\n" + Style.bold(title) + "\n" + Style.bold("═" * W)


def h2(title: str) -> str:
    return "\n" + Style.bold(title) + "\n" + Style.dim("─" * W)


def rule(title: str) -> str:
    width = min(W, 80)
    return "\n" + paint("accent", _truncate(title, width)) + "\n" + Style.dim("─" * width)


def wrap(text: str, width: int, indent: str = "") -> list[str]:
    """Перенос по словам. `width` — итоговая ширина ВМЕСТЕ с отступом.

    Явный `\\n` в тексте — граница абзаца, а не пробел: раньше он съедался
    вместе с остальными пробелами, и любое описание превращалось в сплошную
    простыню. Короткие абзацы читаются заметно лучше — особенно в описаниях
    сценариев, которые печатаются перед каждым расписанием.
    """
    inner = max(8, width - len(indent))
    lines: list[str] = []
    for para in text.split("\n"):
        if not para.strip():
            lines.append("")
            continue
        cur = ""
        for w in para.split():
            if cur and _plain_len(cur) + 1 + _plain_len(w) > inner:
                lines.append(indent + cur)
                cur = w
            else:
                cur = f"{cur} {w}" if cur else w
        if cur:
            lines.append(indent + cur)
    return lines or [indent]


def _truncate(s: str, n: int) -> str:
    """Обрезать видимый текст до n символов с «…», сохраняя ANSI-коды."""
    if n <= 0:
        return ""
    if _plain_len(s) <= n:
        return s
    keep = n - 1
    out: list[str] = []
    vis, i = 0, 0
    while i < len(s):
        if s[i] == "\033":
            j = s.find("m", i)
            if j < 0:
                break
            out.append(s[i : j + 1])
            i = j + 1
            continue
        if vis >= keep:
            break
        out.append(s[i])
        vis += 1
        i += 1
    tail = "\033[0m" if Style.enabled else ""
    return "".join(out) + "…" + tail


def table(
    headers: list[str], rows: list[list[str]], aligns: str = "", max_width: int | None = None
) -> list[str]:
    """Таблица, автоматически ужимающая широкие столбцы под ширину терминала."""
    cols = len(headers)
    aligns = (aligns + "<" * cols)[:cols]
    widths = [_plain_len(h) for h in headers]
    for r in rows:
        for i, c in enumerate(r[:cols]):
            widths[i] = max(widths[i], _plain_len(c))

    budget = (max_width if max_width is not None else W) - 2
    gap = 2 * (cols - 1)
    guard = 0
    while sum(widths) + gap > budget and guard < 10000:
        guard += 1
        j = max(range(cols), key=lambda k: widths[k])
        if widths[j] <= 6:
            break
        widths[j] -= 1

    out = [
        "  ".join(
            Style.dim(pad(_truncate(h, widths[i]), widths[i], aligns[i]))
            for i, h in enumerate(headers)
        ),
        Style.dim("  ".join("─" * w for w in widths)),
    ]
    for r in rows:
        out.append(
            "  ".join(
                pad(_truncate(c, widths[i]), widths[i], aligns[i])
                for i, c in enumerate(r[:cols])
            )
        )
    return out


def two_columns(left: list[str], right: list[str], lw: int, gap: str = " │ ") -> list[str]:
    n = max(len(left), len(right))
    out = []
    for i in range(n):
        l = left[i] if i < len(left) else ""
        r = right[i] if i < len(right) else ""
        out.append(pad(l, lw) + Style.dim(gap) + r)
    return out


# --------------------------------------------------------------------------
# Рамки и панели
# --------------------------------------------------------------------------


def _resolve_color(color: str) -> str:
    """Принять ИМЯ РОЛИ темы («border», «success») либо готовый ANSI-код.

    Двойственность нужна для совместимости: старые вызовы передавали сырые
    коды вроде «36», новые — роли, которые перекрашиваются вместе с темой.
    """
    if not color:
        return c("border")
    if color in THEME.roles:
        return c(color)
    return color  # уже готовый ANSI-код


def ansi_box(lines: list[str], title: str = "", color: str = "border", double: bool = False) -> list[str]:
    """Рамка вокруг строк. Содержимое может нести собственные ANSI-коды."""
    color = _resolve_color(color)
    if double:
        tl, tr, bl, br, hz, vt = "╔", "╗", "╚", "╝", "═", "║"
    else:
        tl, tr, bl, br, hz, vt = "┌", "┐", "└", "┘", "─", "│"
    inner = max((vlen(l) for l in lines), default=0)
    if title:
        inner = max(inner, vlen(title) + 4)
    interior = inner + 2

    def c(s: str) -> str:
        return paint(color, s)

    if title:
        head = f"{hz} {title} "
        top = c(tl + head + hz * (interior - vlen(head)) + tr)
    else:
        top = c(tl + hz * interior + tr)
    out = [top]
    for l in lines:
        out.append(c(vt) + " " + pad(l, inner) + " " + c(vt))
    out.append(c(bl + hz * interior + br))
    return out


# Роли/старые коды -> цвета rich. rich работает своей палитрой, поэтому здесь
# отдельное соответствие; 256-цветные индексы темы передаём как «color(N)».
_RICH_STYLE = {
    "32": "green", "33": "yellow", "36": "cyan",
    "31": "red", "35": "magenta", "1;36": "cyan", "1;35": "magenta",
}


def _rich_color(color: str) -> str:
    if color in THEME.roles:
        return f"color({THEME.role(color).color})"
    return _RICH_STYLE.get(color, "cyan")


def rich_markup_panel(markup: str, title: str = "", color: str = "border", double: bool = False):
    """Отрендерить rich-разметку в панель → список строк, либо None если нет rich."""
    if not (HAS_RICH and Style.enabled):
        return None
    try:
        buf = io.StringIO()
        con = _RichConsole(
            file=buf, force_terminal=True, color_system="256",
            width=min(W, 100), highlight=False,
        )
        con.print(
            _RichPanel(
                markup,
                title=title or None,
                border_style=_rich_color(color),
                box=_rich_box.DOUBLE if double else _rich_box.ROUNDED,
                expand=False,
                padding=(0, 1),
            )
        )
        return buf.getvalue().rstrip("\n").split("\n")
    except Exception:
        return None


def panel(lines: list[str], title: str = "", color: str = "border", double: bool = False) -> list[str]:
    """Панель из ПЛОСКОГО текста (без ANSI внутри). С rich — его панель, иначе ANSI."""
    rich_lines = rich_markup_panel("\n".join(lines), title, color, double)
    if rich_lines is not None:
        return rich_lines
    return ansi_box(lines, title, color, double)
