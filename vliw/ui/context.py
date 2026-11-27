"""Session context for the sidebar pane and `/status` command.

The sidebar is narrow (~30 columns), so layout follows one rule: NEVER
truncate mid-word. Long values (profile name, file path) wrap onto their own
indented line beneath the key.

The sidebar NEVER computes schedules on its own: if no cached result exists,
it displays dashes so opening the UI stays instant.
"""

from __future__ import annotations

from . import render
from .render import Style, paint, wrap


def _head(text: str) -> str:
    return paint("sidebar_head", "v " + text)


def _pair(key: str, val: str, width: int) -> str | None:
    """Single-line 'key ... value' — only if it fits cleanly."""
    gap = width - len(key) - len(val)
    if gap >= 2:
        return paint("sidebar_key", key) + " " * gap + paint("sidebar_val", val)
    return None  # caller places value on its own line


def _row(key: str, val: str, width: int) -> list[str]:
    one = _pair(key, val, width)
    if one is not None:
        return [one]
    # Long value: key on top, indented value below.
    return [paint("sidebar_key", key),
            "  " + paint("sidebar_val", val[: max(4, width - 2)])]


def context_rows(session, width: int = 30) -> list[str]:
    model = session.model()
    dag = session.dag_obj
    cached = session.peek()
    out: list[str] = []

    # --- loaded block --------------------------------------------------
    out.append(_head("BLOCK"))
    out += _row("name", session.scenario, width)
    out += _row("instructions", str(len(dag)), width)
    out.append("")

    # --- machine -------------------------------------------------------
    out.append(_head("MACHINE"))
    out += _row("profile", model.name, width)
    out += _row("ports", str(model.width), width)
    for port, ops in sorted(model.sole_host_ops().items()):
        out.append("  " + paint("accent2", f"{'/'.join(ops)} → {model.port_label(port)}")
                   + Style.dim("  sole"))
    out.append("")

    # --- cycles --------------------------------------------------------
    out.append(_head("CYCLES"))
    if cached is None:
        out += _row("baseline", "—", width)
        out += _row("oracle", "—", width)
        out += _row("lower bound", "—", width)
        out.append("")
        out.append(Style.dim("  not computed yet"))
        out.append(paint("lab", "  /run") + Style.dim("  or  ") + paint("work", "sum 8"))
        return out

    base, orc, met = cached
    b, o = base.schedule.makespan, orc.schedule.makespan
    out += _row("baseline", f"{b}", width)
    out += _row("oracle", f"{o}", width)
    out += _row("lower bound", f"{met.lower_bound}", width)
    gap = b - o
    out.append(Style.dim("  " + "─" * (width - 2)))
    if gap > 0:
        out += _row("gain", f"-{gap} ({100 * gap // b}%)", width)
    else:
        out += _row("gain", "none", width)
    out.append(paint("success", "  optimum proven") if orc.optimal
               else paint("warning", "  optimum unproven"))
    out.append("")

    # --- diagnostics: highest-value info in the sidebar ----------------
    try:
        from ..core.doctor import diagnose
        from .diagnostics import sidebar_rows

        diag = diagnose(dag, model, base.schedule, met)
        out.append(_head("BASELINE DIAGNOSIS"))
        out += sidebar_rows(diag, width)
        out.append("")
        out.append(paint("accent", "  /doctor") + Style.dim(" — details"))
    except Exception:
        pass
    return out


def render_status(session) -> list[str]:
    """Same context for plain line-by-line mode (`/status`)."""
    width = min(46, max(30, render.W - 24))
    return ["  " + r for r in context_rows(session, width=width)]
