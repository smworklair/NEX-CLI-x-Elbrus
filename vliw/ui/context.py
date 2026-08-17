"""Контекст сессии для боковой панели и команды `/status`.

Панель узкая (около 30 колонок), поэтому вёрстка здесь подчинена одному
правилу: НИЧЕГО НЕ РЕЗАТЬ ПОСРЕДИ СЛОВА. Длинные значения (имя профиля, имя
файла) ставятся на отдельную строку под ключом, а не вжимаются в остаток
строки — раньше из-за этого получались обрубки вида «расписание на 7 т. дли».

Панель НЕ считает расписание сама: если результата ещё нет, показывает
прочерки. Иначе простое открытие окна запускало бы точный поиск и подвешивало
интерфейс на секунды.
"""

from __future__ import annotations

from . import render
from .render import Style, paint, wrap


def _head(text: str) -> str:
    return paint("sidebar_head", "▼ " + text)


def _pair(key: str, val: str, width: int) -> str:
    """«ключ ⋯ значение» в одну строку — только если реально помещается."""
    gap = width - len(key) - len(val)
    if gap >= 2:
        return paint("sidebar_key", key) + " " * gap + paint("sidebar_val", val)
    return None  # не влезло — вызывающий поставит значение отдельной строкой


def _row(key: str, val: str, width: int) -> list[str]:
    one = _pair(key, val, width)
    if one is not None:
        return [one]
    # Значение длинное: ключ сверху, значение под ним с отступом.
    return [paint("sidebar_key", key),
            "  " + paint("sidebar_val", val[: max(4, width - 2)])]


def context_rows(session, width: int = 30) -> list[str]:
    model = session.model()
    dag = session.dag_obj
    cached = session.peek()
    out: list[str] = []

    # --- что загружено -------------------------------------------------
    out.append(_head("УЧАСТОК"))
    out += _row("имя", session.scenario, width)
    out += _row("инструкций", str(len(dag)), width)
    out.append("")

    # --- машина --------------------------------------------------------
    out.append(_head("МАШИНА"))
    out += _row("профиль", model.name, width)
    out += _row("портов", str(model.width), width)
    for port, ops in sorted(model.sole_host_ops().items()):
        out.append("  " + paint("accent2", f"{'/'.join(ops)} → {model.port_label(port)}")
                   + Style.dim("  единств."))
    out.append("")

    # --- такты ---------------------------------------------------------
    out.append(_head("ТАКТЫ"))
    if cached is None:
        out += _row("baseline", "—", width)
        out += _row("oracle", "—", width)
        out += _row("предел", "—", width)
        out.append("")
        out.append(Style.dim("  ещё не считалось"))
        out.append(paint("lab", "  /run") + Style.dim("  или  ") + paint("work", "sum 8"))
        return out

    base, orc, met = cached
    b, o = base.schedule.makespan, orc.schedule.makespan
    out += _row("baseline", f"{b}", width)
    out += _row("oracle", f"{o}", width)
    out += _row("предел", f"{met.lower_bound}", width)
    gap = b - o
    out.append(Style.dim("  " + "─" * (width - 2)))
    if gap > 0:
        out += _row("выигрыш", f"−{gap} ({100 * gap // b}%)", width)
    else:
        out += _row("выигрыш", "нет", width)
    out.append(paint("success", "  оптимум доказан") if orc.optimal
               else paint("warning", "  оптимум не доказан"))
    out.append("")

    # --- диагностика: самое ценное в панели ----------------------------
    try:
        from ..core.doctor import diagnose
        from .diagnostics import sidebar_rows

        diag = diagnose(dag, model, base.schedule, met)
        out.append(_head("ДИАГНОЗ BASELINE"))
        out += sidebar_rows(diag, width)
        out.append("")
        out.append(paint("accent", "  /doctor") + Style.dim(" — подробно"))
    except Exception:
        pass
    return out


def render_status(session) -> list[str]:
    """Тот же контекст для обычного построчного режима (команда /status)."""
    width = min(46, max(30, render.W - 24))
    return ["  " + r for r in context_rows(session, width=width)]
