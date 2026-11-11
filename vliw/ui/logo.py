"""Баннер: пиксельные буквы NEX + гора Эльбрус."""

from __future__ import annotations

from . import render
from .render import Style, paint

# Буквы набраны штрихом в две клетки: клетка терминала вдвое выше своей
# ширины, и штрих в одну клетку выглядит волосяной линией рядом с горой.
# Шесть строк — ровно столько же, сколько у горы, чтобы знак стоял на одной
# линии, а не съезжал вниз.
_GLYPHS = {
    "N": [
        "██    ██",
        "███   ██",
        "████  ██",
        "██ ██ ██",
        "██  ████",
        "██   ███",
    ],
    "E": [
        "███████",
        "██     ",
        "██     ",
        "██████ ",
        "██     ",
        "███████",
    ],
    "X": [
        "██    ██",
        " ██  ██ ",
        "  ████  ",
        "  ████  ",
        " ██  ██ ",
        "██    ██",
    ],
}
_GLYPH_ROWS = 6
_LETTER_GAP = "  "

# Знак скрещения между NEX и горой: «NEX x Эльбрус». Он приглушённый —
# это связка между двумя знаками, а не третий знак.
# Одиночный знак умножения в средней строке. Нарисованный блоками крест, даже
# тонкий, весит наравне с буквами и читается третьим знаком; здесь нужен ровно
# соединитель — «NEX x Эльбрус».
#
# Строка 3 из шести: гора тяжелее книзу, и знак на строку выше зрительно
# всплывал над связкой.
_CROSS = ["", "", "", "x", "", ""]
_CROSS_W = 1

# Гора: двуглавый Эльбрус — западная вершина выше восточной, между ними
# седловина. Это его силуэт, по нему его и узнают.
#
# Рисунок задан двумя параллельными сетками одинаковой ширины: символы и
# маска тонов под ними. Так тон не привязан к строке целиком — снег может
# языками спускаться по склону, а подножие уходить в тень, и всё это остаётся
# читаемым текстом, который можно править глазами.
#
#   s — снег      r — освещённая скала      h — склон в тени
#
# Два правила, без которых гора выглядит нарисованной наспех:
#
#   1. Клетка терминала вдвое выше своей ширины, поэтому склон расширяется на
#      две колонки за строку — иначе получается игла, а не гора. Край склона
#      набран нижней половинкой блока (▄): она стыкуется с полным блоком
#      следующей строки и превращает лесенку в скат.
#   2. Снег сужается книзу и не отрывается от вершины. Пятно снега постоянной
#      ширины читается как белая колонна, приклеенная к скале, а не как язык
#      ледника — поэтому каждый следующий ряд снега уже предыдущего и целиком
#      лежит внутри него.
#
# Свет падает слева, поэтому правый склон уходит в тень (h) и тень книзу
# расширяется: это то, что даёт горе объём в шесть строк текста.
# Вершины смещены вправо от середины: левый склон длиннее правого (19 колонок
# против 17) и потому массивнее — гора перестаёт быть симметричной пирамидой.
_MOUNTAIN = [
    ("                 ▄█▄               ",
     "                 sss               "),
    ("               ▄█████▄ ▄█▄         ",
     "               sssssss sss         "),
    ("            ▄█████████▄█████▄      ",
     "            rrrsssssssrsssshh      "),
    ("        ▄██████████████████████▄   ",
     "        rrrrrrrrrssrrrrrsrrrhhhh   "),
    ("    ▄████████████████████████████▄ ",
     "    rrrrrrrrrrrrrrrrrrrrrrrrrhhhhh "),
    ("▄█████████████████████████████████▄",
     "rrrrrrrrrrrrrrrrrrrrrrrrrrrrrrhhhhh"),
]
_MOUNTAIN_W = max(len(g) for g, _ in _MOUNTAIN)
_MOUNTAIN_TONE = {"s": "snow", "r": "mountain", "h": "border"}

# --------------------------------------------------------------------------
# LEGO-заголовок «NNL» для экрана запуска.
#
# Буквы собраны как кирпичики LEGO: над каждой открытой сверху гранью стоит
# ряд шляпок (`▄` — нижняя половинка клетки, она прирастает к блоку ниже),
# а тело буквы набрано двумя тонами — двумя «слоями» кирпичей. В 256-цветной
# теме (`nnl-purple`) слои читаются как настоящая сборка; в теме без этих
# ролей буквы остаются просто крупным текстом.
# --------------------------------------------------------------------------

_LEGO_GLYPHS = {
    "N": [
        "██    ██",
        "███   ██",
        "████  ██",
        "██ ██ ██",
        "██  ████",
        "██   ███",
    ],
    "L": [
        "██      ",
        "██      ",
        "██      ",
        "██      ",
        "██      ",
        "████████",
    ],
}
_LEGO_WORD = "NNL"
_LEGO_GAP = "  "  # зазор между собранными буквами


def _lego_stud_row(rows: list[str]) -> str:
    """Ряд шляпок над открытыми гранями верхней строки буквы.

    `▄` — нижняя половинка клетки: верхняя половина остаётся чёрной,
    и шляпка читается круглой. Шляпка ставится на каждую клетку
    кирпича и сидит точно над ней — колонка к колонке, как у LEGO.
    """
    return "".join(
        "▄" if клетка != " " else " " for клетка in rows[0]
    ).rstrip()


def render_title(indent: str = "  ") -> list[str]:
    """Готовые строки LEGO-заголовка «NNL» для экрана запуска.

    Тело буквы — два слоя кирпичей: верхний ярче, нижний глубже, через границу
    слоёв видно, что буква собрана. Цвета — роли темы (`nnl-purple`).
    """
    буквы = list(_LEGO_WORD)
    шапки = [paint("accent_soft", _lego_stud_row(_LEGO_GLYPHS[b])) for b in буквы]
    out: list[str] = [indent + _LEGO_GAP.join(шапки)]
    for r in range(_GLYPH_ROWS):
        тон = "banner" if r < 3 else "mountain"
        части = [paint(тон, _LEGO_GLYPHS[b][r]) for b in буквы]
        out.append(indent + _LEGO_GAP.join(части))
    return out


def _word_rows(word: str = "NEX") -> list[str]:
    rows = []
    for r in range(_GLYPH_ROWS):
        parts = [_GLYPHS[ch][r] for ch in word if ch in _GLYPHS]
        rows.append(_LETTER_GAP.join(parts))
    return rows


def _mountain_row(i: int) -> str:
    """Одна строка горы: соседние символы одного тона красятся одним куском.

    Маска короче или длиннее рисунка — не повод ронять инструмент: тон под
    неразмеченным символом считается скалой, и гора просто теряет объём.
    """
    if i >= len(_MOUNTAIN):
        return " " * _MOUNTAIN_W
    glyphs, mask = _MOUNTAIN[i]
    mask = mask.ljust(len(glyphs))[: len(glyphs)]
    tone = [
        " " if g == " " else (m if m in _MOUNTAIN_TONE else "r")
        for g, m in zip(glyphs, mask)
    ]
    out: list[str] = []
    start = 0
    for j in range(1, len(glyphs) + 1):
        if j == len(glyphs) or tone[j] != tone[start]:
            chunk = glyphs[start:j]
            role = _MOUNTAIN_TONE.get(tone[start])
            out.append(paint(role, chunk) if role else chunk)
            start = j
    return "".join(out) + " " * max(0, _MOUNTAIN_W - len(glyphs))


def render_mark(indent: str = "  ") -> list[str]:
    """Только знак: буквы NEX и гора, без подписей под ними.

    Нужен экранам, у которых своя подпись под логотипом (выбор режима),
    чтобы не разбирать готовую строку `render_logo()` обратно на части.
    """
    word = _word_rows()
    word_w = max(len(r) for r in word)
    gap = "   "
    rows = max(len(word), len(_CROSS), len(_MOUNTAIN))
    out: list[str] = []
    for i in range(rows):
        left = (word[i] if i < len(word) else "").ljust(word_w)
        cross = (_CROSS[i] if i < len(_CROSS) else "").ljust(_CROSS_W)
        out.append(
            indent
            + paint("banner", left)
            + gap
            + Style.dim(cross)
            + gap
            + _mountain_row(i)
        )
    return out


def render_logo() -> str:
    from .. import VERSION_LABEL

    lines = render_mark(indent="  ")
    lines.append("")
    lines.append("  " + paint("title", "NEX CLI")
                 + Style.dim("  ·  ") + paint("mountain", "Elbrus e2k")
                 + Style.dim("  ·  ") + paint("warning", VERSION_LABEL))
    lines.append("  " + Style.dim("ядро · разбор · агент"))
    return "\n".join(lines)


def print_logo() -> None:
    print(render_logo())


def status_line(mode: str, scenario: str, profile: str, extra: str = "") -> str:
    sep = Style.dim(" · ")
    role = {"work": "accent", "lab": "accent2", "mind": "accent",
            "explore": "accent", "chat": "accent2"}.get(mode, "accent")
    parts = [paint("accent", "nex"), paint(role, mode),
             paint("title", scenario), Style.dim(profile)]
    if extra:
        parts.append(Style.dim(extra))
    return sep.join(parts)
