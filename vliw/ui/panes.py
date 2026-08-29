"""Четыре рабочих места workstation: ядро, разбор, агент, код.

Здесь только имена и маршрутизация фокуса (`/mode`). Раскладки экранов —
в пакете `vliw.tui`, построчный вывод — в соседних view-модулях.
"""

from __future__ import annotations

PANES = ("work", "lab", "mind", "code")

META = {
    "work": {"title": "ЯДРО", "sub": "интерпретатор", "role": "work"},
    "lab":  {"title": "РАЗБОР", "sub": "исследование", "role": "lab"},
    "mind": {"title": "АГЕНТ", "sub": "диалог", "role": "mind"},
    "code": {"title": "КОД", "sub": "редактор", "role": "code"},
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
