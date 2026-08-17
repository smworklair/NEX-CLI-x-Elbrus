"""Мост между палитрой проекта (JSON, индексы 256 цветов) и Textual.

Темы живут в `vliw/ui/themes/*.json` и заданы индексами xterm-256: это
единственное представление, которое одинаково понимают ANSI-вывод, curses и
(после пересчёта здесь) Textual. Пересчёт нужен потому, что Textual красит
через CSS, а CSS индексов палитры не знает — только `#rrggbb`.

Роли не переименовываются: `accent`, `work`, `lab`, `mind`, `crit` и цвета
операций приходят из того же файла, что и раньше. Поэтому команда `/theme`
продолжает перекрашивать весь инструмент целиком, включая новый интерфейс.
"""

from __future__ import annotations

from ..ui import theme as _theme

# --------------------------------------------------------------------------
# xterm-256 -> #rrggbb
# --------------------------------------------------------------------------

_BASE16 = (
    "#000000", "#800000", "#008000", "#808000", "#000080", "#800080",
    "#008080", "#c0c0c0", "#808080", "#ff0000", "#00ff00", "#ffff00",
    "#0000ff", "#ff00ff", "#00ffff", "#ffffff",
)
_CUBE = (0, 95, 135, 175, 215, 255)


def hex_of(index: int) -> str:
    """Цвет из 256-цветной палитры терминала как #rrggbb."""
    i = max(0, min(255, int(index)))
    if i < 16:
        return _BASE16[i]
    if i < 232:
        n = i - 16
        r, g, b = _CUBE[n // 36], _CUBE[(n // 6) % 6], _CUBE[n % 6]
        return f"#{r:02x}{g:02x}{b:02x}"
    v = 8 + (i - 232) * 10
    return f"#{v:02x}{v:02x}{v:02x}"


# --------------------------------------------------------------------------
# Текущая палитра
# --------------------------------------------------------------------------

# Фоны не берутся из JSON: в старом интерфейсе фон был просто «фон терминала».
# Здесь поверхностей несколько (полотно, панель, выделение), и они должны
# держать иерархию, а не спорить с акцентом. Поэтому нейтральный ряд задан
# рядом с палитрой, а не внутри неё.
#
# Значения подобраны так, чтобы ряд оставался различимым и в 256 цветах: там
# всё это ложится на серую шкалу палитры (233 / 234 / 236 / 239), то есть
# ступени видны, даже если 24-битный цвет недоступен. Более тёмный набор
# сливался в один чёрный прямоугольник.
SURFACES = {
    "canvas":  "#0d0f15",   # полотно приложения
    "panel":   "#171b26",   # обычная панель
    "raised":  "#222839",   # панель под курсором / активная / поле ввода
    "line":    "#3a4257",   # разделители и рамки в покое
    "shadow":  "#080a10",   # подложка дока ввода
}

MODE_ROLE = {"work": "work", "lab": "lab", "mind": "mind"}


def role_hex(role: str, fallback: str = "#c8ccd4") -> str:
    from ..ui import render

    st = render.THEME.roles.get(role)
    return hex_of(st.color) if st else fallback


def op_hex(op: str) -> str:
    from ..ui import render

    st = render.THEME.ops.get(op)
    return hex_of(st.color) if st else role_hex("text")


def op_style(op: str) -> str:
    """Стиль rich для операции: цвет + жирность, как в теме."""
    from ..ui import render

    st = render.THEME.ops.get(op)
    if st is None:
        return role_hex("text")
    bold = " bold" if "bold" in st.attrs else ""
    return hex_of(st.color) + bold


def variables() -> dict[str, str]:
    """CSS-переменные `$nex-*` для таблицы стилей."""
    out = {f"nex-{k}": v for k, v in SURFACES.items()}
    for role in (
        "text", "dim", "faint", "accent", "accent_soft", "accent2",
        "accent2_soft", "success", "warning", "error", "title", "border",
        "border_hi", "crit", "diverge", "work", "work_soft", "lab", "lab_soft",
        "mind", "mind_soft", "banner", "mountain",
    ):
        out[f"nex-{role.replace('_', '-')}"] = role_hex(role)
    return out


def make_theme(mode: str = "lab") -> "object":
    """Тема Textual под текущий режим: акцент режима становится primary.

    Один и тот же набор поверхностей во всех режимах — меняется только
    акцент. Так три экрана читаются как один инструмент, но перепутать,
    в каком ты находишься, невозможно.
    """
    from textual.theme import Theme

    accent = role_hex(MODE_ROLE.get(mode, "accent"))
    return Theme(
        name=f"nex-{mode}",
        primary=accent,
        secondary=role_hex("accent2"),
        accent=accent,
        foreground=role_hex("text"),
        background=SURFACES["canvas"],
        surface=SURFACES["panel"],
        panel=SURFACES["raised"],
        boost="#ffffff08",
        success=role_hex("success"),
        warning=role_hex("warning"),
        error=role_hex("error"),
        dark=True,
        variables={
            "block-cursor-foreground": SURFACES["canvas"],
            "block-cursor-background": accent,
            "block-cursor-text-style": "bold",
            "input-selection-background": accent + " 35%",
            "footer-key-foreground": accent,
            "scrollbar": SURFACES["line"],
            "scrollbar-hover": role_hex("dim"),
            "scrollbar-active": accent,
            "scrollbar-background": SURFACES["canvas"],
            "border-blurred": SURFACES["line"],
        },
    )


def list_themes() -> list[str]:
    return _theme.list_themes()
