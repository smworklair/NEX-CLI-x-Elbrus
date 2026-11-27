"""Banner: pixel-block NEX lettering + Mount Elbrus silhouette."""

from __future__ import annotations

from . import render
from .render import Style, paint

# Double-cell stroke width compensates for terminal cells being ~2x taller than wide.
# Six rows match the mountain height so both marks sit on the same baseline.
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

# Subtle connector between NEX and the mountain: "NEX x Elbrus".
_CROSS = ["", "", "", "x", "", ""]
_CROSS_W = 1

# Twin-peaked Mount Elbrus silhouette with a parallel tone mask:
#   s — snow      r — sunlit rock      h — shaded slope
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
# Brick-style "NNL" header for the setup/launch screen.
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
_LEGO_GAP = "  "  # gap between assembled letters


def _lego_stud_row(rows: list[str]) -> str:
    """Stud row above exposed top edges of the letter (`▄` half-blocks)."""
    return "".join(
        "▄" if cell != " " else " " for cell in rows[0]
    ).rstrip()


def render_title(indent: str = "  ") -> list[str]:
    """Render the brick-style 'NNL' title for the setup screen."""
    letters = list(_LEGO_WORD)
    studs = [paint("accent_soft", _lego_stud_row(_LEGO_GLYPHS[b])) for b in letters]
    out: list[str] = [indent + _LEGO_GAP.join(studs)]
    for r in range(_GLYPH_ROWS):
        tone = "banner" if r < 3 else "mountain"
        parts = [paint(tone, _LEGO_GLYPHS[b][r]) for b in letters]
        out.append(indent + _LEGO_GAP.join(parts))
    return out


def _word_rows(word: str = "NEX") -> list[str]:
    rows = []
    for r in range(_GLYPH_ROWS):
        parts = [_GLYPHS[ch][r] for ch in word if ch in _GLYPHS]
        rows.append(_LETTER_GAP.join(parts))
    return rows


def _mountain_row(i: int) -> str:
    """Render one mountain row, coalescing adjacent cells of the same tone."""
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
    """Just the mark: NEX lettering + Elbrus mountain, no captions below."""
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
    lines.append("  " + Style.dim("core · lab · agent"))
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
