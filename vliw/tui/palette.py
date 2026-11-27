"""Bridge between the project palette (JSON, 256-color indices) and Textual.

Themes live in `vliw/ui/themes/*.json` using xterm-256 indices — the one
representation understood uniformly by ANSI output, curses, and (after
conversion here) Textual. Conversion is needed because Textual styles through
CSS, which only accepts `#rrggbb` rather than palette indices.

Role names stay unchanged: `accent`, `work`, `lab`, `mind`, `crit`, and op
colors come from the same JSON files as before, so `/theme` continues to
recolor the entire tool including this UI.
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
    """Convert an xterm 256-color index to `#rrggbb`."""
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
# Active palette
# --------------------------------------------------------------------------

# Surfaces do not come from JSON: the legacy UI only had the terminal default
# background. Here we have multiple surfaces (canvas, panel, raised) that need
# clear visual hierarchy without competing with accents, so the neutral ramp is
# defined alongside the palette rather than inside it.
#
# Values are chosen so the ramp stays distinguishable even in 256-color mode,
# mapping onto the grayscale ramp (233 / 234 / 236 / 239) instead of collapsing
# into a single black rectangle when 24-bit color is unavailable.
SURFACES = {
    "canvas":  "#0d0f15",   # application canvas
    "panel":   "#171b26",   # standard panel
    "raised":  "#222839",   # hovered / active panel / input field
    "line":    "#3a4257",   # dividers and idle borders
    "shadow":  "#080a10",   # input dock backing
}

# Mode -> accent role. CODE previously used `accent2`, which matched `lab` in
# all four themes and made CODE and LAB indistinguishable by border color. The
# dedicated `code` role gives the fourth mode its own distinct accent color.
MODE_ROLE = {"work": "work", "lab": "lab", "mind": "mind", "code": "code"}


def role_hex(role: str, fallback: str = "#c8ccd4") -> str:
    from ..ui import render

    st = render.THEME.roles.get(role)
    return hex_of(st.color) if st else fallback


def mode_hex(mode: str) -> str:
    """Accent hex color for a mode; falls back to `accent2` if `code` is missing."""
    from ..ui import render

    role = MODE_ROLE.get(mode, "accent")
    if role not in render.THEME.roles:
        role = "accent2"
    return role_hex(role)


def op_hex(op: str) -> str:
    from ..ui import render

    st = render.THEME.ops.get(op)
    return hex_of(st.color) if st else role_hex("text")


def op_style(op: str) -> str:
    """Rich style string for an operation: color plus bold weight from theme."""
    from ..ui import render

    st = render.THEME.ops.get(op)
    if st is None:
        return role_hex("text")
    bold = " bold" if "bold" in st.attrs else ""
    return hex_of(st.color) + bold


def variables() -> dict[str, str]:
    """CSS variables `$nex-*` for the stylesheet."""
    out = {f"nex-{k}": v for k, v in SURFACES.items()}
    for role in (
        "text", "dim", "faint", "accent", "accent_soft", "accent2",
        "accent2_soft", "success", "warning", "error", "title", "border",
        "border_hi", "crit", "diverge", "work", "work_soft", "lab", "lab_soft",
        "mind", "mind_soft", "banner", "mountain",
    ):
        out[f"nex-{role.replace('_', '-')}"] = role_hex(role)
    # `code` is a newer role: if a third-party theme omits it, fall back to the
    # secondary accent rather than default gray.
    out["nex-code"] = role_hex("code", role_hex("accent2"))
    out["nex-code-soft"] = role_hex("code_soft", role_hex("accent2-soft"))
    return out


def make_theme(mode: str = "lab") -> "object":
    """Build a Textual theme for the active mode with its accent as primary.

    All modes share the same surface ramp; only the accent shifts so the
    screens feel like one cohesive tool while making the active mode obvious.
    """
    from textual.theme import Theme

    accent = mode_hex(mode)
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
            # Scrollbar acts as a subtle position indicator rather than a heavy
            # chrome bar. Matching the panel background avoids a dark stripe;
            # the thumb stays translucent until hovered or dragged.
            "scrollbar": SURFACES["line"] + " 18%",
            "scrollbar-hover": role_hex("dim") + " 45%",
            "scrollbar-active": accent + " 60%",
            "scrollbar-background": SURFACES["panel"],
            "scrollbar-background-hover": SURFACES["panel"],
            "scrollbar-background-active": SURFACES["panel"],
            "border-blurred": SURFACES["line"],
        },
    )


def list_themes() -> list[str]:
    return _theme.list_themes()
