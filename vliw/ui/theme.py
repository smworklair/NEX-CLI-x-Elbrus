"""Color themes: palette loader from JSON.

A theme defines named semantic roles ('accent', 'border', 'prompt', ...) and
operation colors using 256-color terminal indices (`38;5;N`). Both plain ANSI
output and the full-screen TUI (`vliw.tui`) share the same indices.

Operation colors (DIV/MUL/ADD/...) live in their own `ops` section because
they encode data, not decoration: they immediately show where division lands
(exclusive port `,5`) and how other ops distribute across channels.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

THEMES_DIR = Path(__file__).parent / "themes"
DEFAULT_THEME = "nex-dark"

# Attribute name -> ANSI SGR code
_ATTRS = {
    "bold": "1",
    "dim": "2",
    "underline": "4",
    "reverse": "7",
}


@dataclass(frozen=True)
class Style:
    """Single style: 256-color index plus text attributes."""

    color: int = 7
    attrs: tuple[str, ...] = ()

    @property
    def ansi(self) -> str:
        """ANSI SGR payload, e.g. `1;38;5;75`."""
        parts = [_ATTRS[a] for a in self.attrs if a in _ATTRS]
        parts.append(f"38;5;{self.color}")
        return ";".join(parts)


def _parse_style(raw) -> Style:
    if raw is None:
        return Style()
    if isinstance(raw, int):
        return Style(color=raw)
    return Style(
        color=int(raw.get("color", 7)),
        attrs=tuple(raw.get("attrs", ())),
    )


@dataclass
class Theme:
    name: str
    description: str = ""
    roles: dict[str, Style] = field(default_factory=dict)
    ops: dict[str, Style] = field(default_factory=dict)

    def role(self, name: str) -> Style:
        """Role style; unknown roles silently fall back to neutral text."""
        return self.roles.get(name) or self.roles.get("text") or Style()

    def op(self, name: str) -> Style:
        return self.ops.get(name) or self.role("text")

    def ansi(self, role_name: str) -> str:
        return self.role(role_name).ansi

    def op_ansi(self, op_name: str) -> str:
        return self.op(op_name).ansi


def list_themes() -> list[str]:
    """Available theme names (stems of JSON files in themes/)."""
    if not THEMES_DIR.is_dir():
        return []
    return sorted(p.stem for p in THEMES_DIR.glob("*.json"))


def load_theme(name: str = DEFAULT_THEME) -> Theme:
    """Load a theme by name, falling back to a safe 8-color default on error."""
    path = THEMES_DIR / f"{name}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _fallback_theme(name)

    try:
        return Theme(
            name=data.get("name", name),
            description=data.get("description", ""),
            roles={k: _parse_style(v) for k, v in data.get("roles", {}).items()},
            ops={k: _parse_style(v) for k, v in data.get("ops", {}).items()},
        )
    except Exception:
        return _fallback_theme(name)


def _fallback_theme(name: str) -> Theme:
    """Minimal built-in 8-color theme used when JSON is missing or corrupt."""
    return Theme(
        name=f"{name} (fallback)",
        description="Built-in fallback palette using basic 8 terminal colors.",
        roles={
            "text": Style(7),
            "dim": Style(7, ("dim",)),
            "faint": Style(7, ("dim",)),
            "accent": Style(6, ("bold",)),
            "accent_soft": Style(6),
            "accent2": Style(3, ("bold",)),
            "accent2_soft": Style(3),
            "success": Style(2),
            "warning": Style(3),
            "error": Style(1, ("bold",)),
            "banner": Style(4, ("bold",)),
            "banner_alt": Style(6, ("bold",)),
            "mountain": Style(6),
            "snow": Style(7, ("bold",)),
            "border": Style(6),
            "border_hi": Style(6, ("bold",)),
            "title": Style(7, ("bold",)),
            "prompt": Style(6, ("bold",)),
            "selection": Style(7, ("reverse",)),
            "sidebar_head": Style(6, ("bold",)),
            "sidebar_key": Style(7, ("dim",)),
            "sidebar_val": Style(7),
            "crit": Style(3, ("bold", "underline")),
            "diverge": Style(1, ("bold",)),
            "work": Style(4, ("bold",)),
            "work_soft": Style(4),
            "lab": Style(6, ("bold",)),
            "lab_soft": Style(6),
            "mind": Style(4, ("bold",)),
            "mind_soft": Style(6),
            "hud": Style(7, ("dim",)),
            "dock": Style(7),
        },
        ops={
            "DIV": Style(5, ("bold",)),
            "MUL": Style(6, ("bold",)),
            "ADD": Style(2),
            "SUB": Style(2),
            "LOAD": Style(3),
            "STORE": Style(3),
            "AND": Style(6, ("dim",)),
            "SHL": Style(6, ("dim",)),
        },
    )
