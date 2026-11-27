"""Core terminal rendering primitives: color, width, boxes, tables, panels.

Foundation of `vliw.ui`. Contains no scheduling logic — only turns data from
`vliw.core` into terminal lines. Uses raw ANSI by default and `rich` panels
when installed (graceful fallback).
"""

from __future__ import annotations

import io
import os
import shutil
import sys

from . import theme as _theme

# --------------------------------------------------------------------------
# Optional rich (the only optional dependency for plain UI)
# --------------------------------------------------------------------------

try:
    import rich  # noqa: F401
    from rich import box as _rich_box
    from rich.console import Console as _RichConsole
    from rich.panel import Panel as _RichPanel

    HAS_RICH = True
except Exception:  # pragma: no cover - environment-dependent
    HAS_RICH = False


# --------------------------------------------------------------------------
# Report width adapted to the actual terminal
# --------------------------------------------------------------------------

W = 96  # updated for the terminal in setup_output()
W_MIN = 56
W_MAX = 100


def detect_width(default: int = 96) -> int:
    """Clamped terminal width so tables and boxes don't wrap awkwardly."""
    try:
        cols = shutil.get_terminal_size((default, 24)).columns
    except Exception:
        cols = default
    if not cols or cols <= 0:
        cols = default
    return max(W_MIN, min(W_MAX, cols))


def term_cols() -> int:
    """Actual unclamped terminal width (for interactive input)."""
    try:
        return max(20, shutil.get_terminal_size((80, 24)).columns)
    except Exception:
        return 80


# --------------------------------------------------------------------------
# Color & theme
# --------------------------------------------------------------------------

THEME = _theme.load_theme()


def apply_theme(name: str | None) -> None:
    """Switch active theme and rebuild derived color constants."""
    global THEME, OP_CODE, CRIT_CODE, DIVERGE_CODE
    if name:
        THEME = _theme.load_theme(name)
    OP_CODE = {op: st.ansi for op, st in THEME.ops.items()}
    CRIT_CODE = THEME.ansi("crit")
    DIVERGE_CODE = THEME.ansi("diverge")


def c(role: str) -> str:
    """ANSI code for a theme role ('accent', 'border', 'error', ...)."""
    return THEME.ansi(role)


class Style:
    """Named terminal styles backed by the active theme."""

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
    """Colorize a string using a theme role name or raw ANSI code."""
    if not Style.enabled:
        return s
    return f"\033[{_resolve_color(code)}m{s}\033[0m"


def utf8_console() -> None:
    """Switch Windows console input/output code pages to UTF-8 (TTY only)."""
    if os.name != "nt":
        return
    try:
        if not sys.stdout.isatty():
            return
        import ctypes

        k = ctypes.windll.kernel32
        if k.GetConsoleOutputCP() != 65001:
            k.SetConsoleOutputCP(65001)
        if k.GetConsoleCP() != 65001:
            k.SetConsoleCP(65001)
    except Exception:
        pass


def enable_vt() -> bool:
    """Enable ANSI VT processing on Windows consoles."""
    if os.name != "nt":
        return True
    try:
        import ctypes

        k = ctypes.windll.kernel32
        return bool(k.SetConsoleMode(k.GetStdHandle(-11), 7))
    except Exception:
        return False


def setup_output(color: bool | None = None, theme_name: str | None = None) -> None:
    """Configure encoding, color support, active theme, and terminal width."""
    global W
    if theme_name:
        apply_theme(theme_name)
    utf8_console()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    if color is None:
        color = sys.stdout.isatty() and os.environ.get("TERM") != "dumb"
    if color and os.name == "nt":
        color = enable_vt()
    Style.enabled = bool(color)
    W = detect_width()


# --------------------------------------------------------------------------
# Operation-type accents (expensive MUL/DIV stand out most)
# --------------------------------------------------------------------------

OP_CODE: dict[str, str] = {}
CRIT_CODE = ""     # critical path
DIVERGE_CODE = ""  # baseline vs oracle divergence

apply_theme(None)  # populate derived constants from default theme


def op_code(op: str) -> str:
    return OP_CODE.get(op, c("text"))


def paint_op(op: str, s: str) -> str:
    return paint(op_code(op), s)


def op_legend() -> str:
    parts = [
        paint_op("DIV", "DIV"),
        paint_op("MUL", "MUL"),
        paint_op("LOAD", "LOAD/STORE"),
        paint_op("ADD", "ADD/SUB/logic"),
    ]
    return Style.dim("ops: ") + "  ".join(parts)


# --------------------------------------------------------------------------
# ANSI-aware string widths and layout primitives
# --------------------------------------------------------------------------


def _plain_len(s: str) -> int:
    """Visible length excluding ANSI escape sequences."""
    out, i = 0, 0
    while i < len(s):
        if s[i] == "\033":
            j = s.find("m", i)
            i = len(s) if j < 0 else j + 1
            continue
        out += 1
        i += 1
    return out


vlen = _plain_len  # short alias


def pad(s: str, n: int, align: str = "<") -> str:
    gap = max(0, n - _plain_len(s))
    if align == ">":
        return " " * gap + s
    if align == "^":
        left = gap // 2
        return " " * left + s + " " * (gap - left)
    return s + " " * gap


def plural(n: int, one: str, few: str, many: str) -> str:
    """Pluralization helper (keeps 3-form signature for backward compatibility)."""
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
    return f"{n} {'cycle' if abs(n) == 1 else 'cycles'}"


def h1(title: str) -> str:
    return "\n" + Style.bold("─" * W) + "\n" + Style.bold(title) + "\n" + Style.bold("─" * W)


def h2(title: str) -> str:
    return "\n" + Style.bold(title) + "\n" + Style.dim("─" * W)


def rule(title: str) -> str:
    width = min(W, 80)
    return "\n" + paint("accent", _truncate(title, width)) + "\n" + Style.dim("─" * width)


def wrap(text: str, width: int, indent: str = "") -> list[str]:
    """Word wrap preserving explicit newlines. `width` includes `indent`."""
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
    """Truncate visible text to n chars with '…' while preserving ANSI codes."""
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
    """Table that automatically shrinks wide columns to fit terminal width."""
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
# Boxes and panels
# --------------------------------------------------------------------------


def _resolve_color(color: str) -> str:
    """Accept either a theme role name ('border', 'success') or a raw ANSI code."""
    if not color:
        return c("border")
    if color in THEME.roles:
        return c(color)
    return color  # raw ANSI code


def ansi_box(lines: list[str], title: str = "", color: str = "border", double: bool = False) -> list[str]:
    """Draw a box around lines (content may contain its own ANSI codes)."""
    color = _resolve_color(color)
    if double:
        tl, tr, bl, br, hz, vt = "┌", "┐", "└", "┘", "─", "│"
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


# Legacy ANSI codes -> rich color names; 256-color theme roles use color(N).
_RICH_STYLE = {
    "32": "green", "33": "yellow", "36": "cyan",
    "31": "red", "35": "magenta", "1;36": "cyan", "1;35": "magenta",
}


def _rich_color(color: str) -> str:
    if color in THEME.roles:
        return f"color({THEME.role(color).color})"
    return _RICH_STYLE.get(color, "cyan")


def rich_markup_panel(markup: str, title: str = "", color: str = "border", double: bool = False):
    """Render rich markup into a panel -> list of lines, or None if rich is absent."""
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
    """Render a panel from PLAIN text (no embedded ANSI). Uses rich if available."""
    rich_lines = rich_markup_panel("\n".join(lines), title, color, double)
    if rich_lines is not None:
        return rich_lines
    return ansi_box(lines, title, color, double)
