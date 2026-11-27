"""HQ: background agents running on verified connections.

Standard chat is a single conversation with the active model. HQ lets you
dispatch several agents on different tasks in parallel: each has its own
connection (a backend snapshot from the MODELS catalog), its own focus area,
and its own mission script.

Fair-play rules (same as chat):
  * an agent only READS state (facts, schedule, diagnostics) — it never
    switches the session, loads files, or writes anything;
  * numbers come from the same `agent.context` as chat, so every answer
    can be cross-checked with the same commands;
  * the script is appended to the system prompt and can be edited on the fly
    for re-runs: without a script the agent works freely, with one it follows
    the script strictly.

Pure logic only (areas, prompt assembly, backend call). Threads and widgets
live in `AgentScreen`; task storage lives there too (HQ lasts one session,
just like keys).
"""

from __future__ import annotations

AREAS: tuple[tuple[str, str, str], ...] = (
    ("doctor", "losses", "where are cycles lost and what should change?"),
    ("compare", "compare", "compare baseline against the exact oracle search"),
    ("bounds", "lower bound", "what is the lower bound of this block and why can't it go faster?"),
    ("layout", "layout", "break down the schedule by cycles and ports"),
    ("free", "custom question", ""),
)
"""(id, label, default question). Only 'free' has an empty default question,
taking its text from the task input field."""

AREA_LABEL = {aid: label for aid, label, _ in AREAS}
AREA_QUESTION = {aid: q for aid, _, q in AREAS}


def mission_system(session, area: str, script: str) -> str:
    from . import context

    system = context.system_prompt(session, include_layout=True)
    label = AREA_LABEL.get(area, area)
    system += (f"\n\nFOCUS AREA: {label}. Answer only about this area; "
               "do not summarize unrelated topics.")
    script = (script or "").strip()
    if script:
        system += ("\n\nMISSION SCRIPT (instructions for this run, "
                   "takes priority over general formatting rules):\n" + script)
    return system


def run_mission(backend, system: str, question: str) -> str:
    return backend.complete(system, question, temperature=0.3)
