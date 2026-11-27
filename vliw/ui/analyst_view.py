"""Structured analysis renderer (typed analyst agent).

Fixed schema fields give a consistent report layout: verdict, root cause,
plan with expected cycle gains, and model caveats.
"""

from __future__ import annotations

from ..agent.analyst import Analysis
from . import render
from .render import Style, paint, wrap

BAR = "│"

_CONF = {
    "high": ("success", "high"),
    "medium": ("warning", "medium"),
    "low": ("dim", "low"),
}


def render_analysis(a: Analysis, scenario: str = "") -> list[str]:
    role, conf_word = _CONF.get(a.confidence, ("dim", a.confidence))
    bar = paint("accent2", BAR)
    out: list[str] = []

    out.append(f"  {bar} {paint('accent2', 'ANALYSIS')}"
               + Style.dim(f"   {scenario}" if scenario else ""))
    out.append(f"  {bar}")
    out += wrap(paint("title", a.verdict), render.W, f"  {bar} ")
    out.append(f"  {bar}")

    out.append(f"  {bar} {Style.dim('root cause')}")
    out += wrap(a.root_cause, render.W, f"  {bar}   ")

    if a.plan:
        out.append(f"  {bar}")
        out.append(f"  {bar} {Style.dim('plan')}")
        for i, s in enumerate(a.plan, 1):
            gain = (paint("success", f"-{s.gain_cycles} cyc")
                    if s.gain_cycles > 0 else Style.dim("—"))
            head = f"{i}. {s.step}"
            lines = wrap(head, render.W - 14, f"  {bar}   ")
            lines[0] = lines[0] + "  " + gain
            out += lines
            if s.command:
                out.append(f"  {bar}      {paint('accent', s.command)}")

    if a.risk:
        out.append(f"  {bar}")
        out.append(f"  {bar} {Style.dim('model caveats')}")
        out += wrap(Style.dim(a.risk), render.W, f"  {bar}   ")

    out.append(f"  {bar}")
    line = f"  {bar} {Style.dim('confidence')} {paint(role, conf_word)}"
    if a.total_gain > 0:
        line += Style.dim("   ·   total plan gain ") + paint("success", f"-{a.total_gain} cyc")
    if a.tokens:
        line += Style.dim(f"   ·   {a.tokens} tokens")
    if a.offline:
        line += paint("warning", "   ·   offline (model unavailable)")
    out.append(line)
    if a.offline and a.error:
        out += wrap(Style.dim(a.error), render.W, f"  {bar}   ")
    return out
