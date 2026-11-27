"""Four workstation panes: CORE, LAB, AGENT, CODE.

Only pane names and focus routing (`/mode`). Full-screen layouts live in
`vliw.tui`; plain-mode renderers live in sibling view modules.
"""

from __future__ import annotations

PANES = ("work", "lab", "mind", "code")

META = {
    "work": {"title": "CORE",  "sub": "interpreter", "role": "work"},
    "lab":  {"title": "LAB",   "sub": "analysis",    "role": "lab"},
    "mind": {"title": "AGENT", "sub": "dialogue",    "role": "mind"},
    "code": {"title": "CODE",  "sub": "editor",      "role": "code"},
}

FOCUS_ALIASES = {
    "work": "work", "ядро": "work", "core": "work", "interp": "work",
    "lab": "lab", "разбор": "lab", "explore": "lab", "research": "lab",
    "иссл": "lab", "команды": "lab",
    "mind": "mind", "агент": "mind", "chat": "mind", "agent": "mind",
    "ai": "mind", "чат": "mind",
    "code": "code", "код": "code", "edit": "code", "редактор": "code",
}


def resolve_focus(name: str) -> str | None:
    return FOCUS_ALIASES.get(name.strip().lower())
