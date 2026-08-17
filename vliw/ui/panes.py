"""Три вкладки workstation: ядро, разбор, агент.

Раскладка — вкладки в tui.py. Здесь имена, маршрутизация вывода и дашборд
вкладки «ядро» (это не лог команд).
"""

from __future__ import annotations

from . import context, render
from .render import Style, paint, wrap

PANES = ("work", "lab", "mind")

META = {
    "work": {"title": "ЯДРО", "sub": "интерпретатор", "role": "work"},
    "lab":  {"title": "РАЗБОР", "sub": "исследование", "role": "lab"},
    "mind": {"title": "АГЕНТ", "sub": "диалог", "role": "mind"},
}

# Команды, чей stdout идёт в конкретную панель. Всё остальное распознанное —
# в разбор. Нераспознанный многословный ввод — в агента.
WORK_CMDS = {"work"}
MIND_CMDS = {"ask", "ai"}

FOCUS_ALIASES = {
    "work": "work", "ядро": "work", "core": "work", "interp": "work",
    "lab": "lab", "разбор": "lab", "explore": "lab", "research": "lab",
    "иссл": "lab", "команды": "lab",
    "mind": "mind", "агент": "mind", "chat": "mind", "agent": "mind",
    "ai": "mind", "чат": "mind",
}


def classify(raw: str, resolved_name: str | None, looks_work: bool,
             focus: str = "lab") -> str:
    """Куда класть вывод: интерпретатор, разбор или агент — разные вкладки."""
    s = raw.strip().lower()
    if looks_work:
        return "lab" if s == "go" else "work"
    if resolved_name in WORK_CMDS:
        return "work"
    if resolved_name in MIND_CMDS:
        return "mind"
    if resolved_name:
        return "lab"
    if focus == "work":
        return "work"
    return "mind"


def resolve_focus(name: str) -> str | None:
    return FOCUS_ALIASES.get(name.strip().lower())


def hud_bits(session) -> dict:
    """Куски верхней полосы. Сама полоса рисуется в curses, не ANSI."""
    model = session.model()
    dag = session.dag_obj
    bits = {
        "brand": "NEX",
        "scenario": session.scenario,
        "profile": model.name,
        "n": str(len(dag)),
        "metrics": "",
        "focus": META.get(getattr(session, "focus", "lab"), META["lab"])["title"],
    }
    cached = session.peek()
    if cached is not None:
        base, orc, _met = cached
        b, o = base.schedule.makespan, orc.schedule.makespan
        gap = b - o
        if gap > 0:
            bits["metrics"] = f"{b}→{o} −{gap}"
        else:
            bits["metrics"] = f"{b}={o}"
    return bits


def render_work(session, width: int = 36) -> list[str]:
    """Стартовая поверхность интерпретатора."""
    from . import interp_view

    _ = session
    return interp_view.render_welcome(width)


def render_lab_seed(session, width: int = 36) -> list[str]:
    """Стартовое содержимое разбора: контекст без запуска расчёта."""
    w = max(16, width)
    rows = context.context_rows(session, width=w)
    out = [
        paint("work", "NEX CLI") + Style.dim("  ·  ") + paint("lab", "Elbrus"),
        "",
    ]
    out += list(rows)
    out.append("")
    out += wrap(Style.dim("ещё пусто.  /run slotclash  ·  go — граф из ядра"), w, "")
    return out


def render_mind_seed(width: int = 36) -> list[str]:
    from . import agent_view

    return agent_view.render_intro(width=width)


def stamp(line: str, role: str) -> str:
    """Короткая метка выполненной команды в логе панели."""
    return paint(role, "▸ ") + Style.dim(line)
