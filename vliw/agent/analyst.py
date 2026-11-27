"""Typed analyst agent: structured system analysis under a fixed contract.

Architectural difference from the chat agent (not cosmetic):

  * NO conversation and NO history — every call is independent;
  * the answer is returned as a JSON STRUCTURE matching a schema (verdict,
    root_cause, plan, risk, confidence), so it can be rendered as a table,
    diffed across runs, and saved to a report;
  * because of the schema, the model skips filler and pleasantries — token
    usage is much lower and output is far more deterministic.

Numbers are still computed by the core: precomputed facts arrive here and the
model only synthesizes the verdict and plan. If the model is unavailable, we
assemble the exact same contract deterministically from `core.doctor`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from . import context, llm

SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string"},
        "root_cause": {"type": "string"},
        "plan": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "step": {"type": "string"},
                    "gain_cycles": {"type": "integer"},
                    "command": {"type": "string"},
                },
                "required": ["step", "gain_cycles"],
            },
        },
        "risk": {"type": "string"},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    },
    "required": ["verdict", "root_cause", "plan", "confidence"],
}

SYSTEM = """\
You are the typed analytical module of NEX for the Elbrus (e2k) VLIW processor.
You do NOT hold a conversation. You return only a structured object matching the schema.

RULES:
1. Write in clear, concise technical English. All fields must be in English.
2. Take numbers ONLY from the FACTS block. Never invent figures.
3. verdict — one line: how many cycles the block takes and what matters most.
4. root_cause — the root cause of cycle losses. If there are no losses, state
   directly that the block hits a machine lower bound and name that bound.
5. plan — concrete steps. gain_cycles — expected cycle gain, only if it follows
   from FACTS; otherwise 0. command — tool command when appropriate
   (/compare, /doctor, /explain N, /asm).
6. risk — what this analysis does NOT model (the machine model is simplified:
   no register pressure, speculation, predicates, or complex memory effects).
7. Zero filler, intros, or pleasantries. Strictly factual.
"""


@dataclass
class Step:
    step: str
    gain_cycles: int = 0
    command: str = ""


@dataclass
class Analysis:
    verdict: str = ""
    root_cause: str = ""
    plan: list[Step] = field(default_factory=list)
    risk: str = ""
    confidence: str = "low"
    offline: bool = False
    error: str = ""
    tokens: int = 0

    @property
    def total_gain(self) -> int:
        return sum(s.gain_cycles for s in self.plan)


def analyze(session) -> Analysis:
    """Analyze the current block and return a structured Analysis."""
    # Facts must be computed first — otherwise there is nothing to analyze.
    if session.peek() is None:
        session.results()
    facts = context.build(session, include_layout=True)
    prompt = (facts + "\n\nTASK: produce a structured analysis of this block "
                      "matching the schema. Use only the facts above.")
    try:
        raw, used = _ask_structured(prompt)
    except llm.LLMError as e:
        a = _offline(session)
        a.offline, a.error = True, str(e)
        return a

    try:
        d = json.loads(raw)
    except ValueError:
        a = _offline(session)
        a.offline, a.error = True, "model did not return valid JSON"
        return a

    return Analysis(
        verdict=str(d.get("verdict", "")).strip(),
        root_cause=str(d.get("root_cause", "")).strip(),
        plan=[Step(str(s.get("step", "")).strip(),
                   int(s.get("gain_cycles", 0) or 0),
                   str(s.get("command", "")).strip())
              for s in d.get("plan", []) if isinstance(s, dict)],
        risk=str(d.get("risk", "")).strip(),
        confidence=str(d.get("confidence", "low")).strip(),
        tokens=used,
    )


def _ask_structured(prompt: str) -> tuple[str, int]:
    """Schema-constrained request. The client picks the provider-specific format."""
    return llm.structured(SYSTEM, prompt, SCHEMA)


def _offline(session) -> Analysis:
    """Same contract assembled from deterministic diagnostics."""
    from ..core.doctor import diagnose

    base, orc, met = session.peek()
    d = diagnose(session.dag_obj, session.model(), base.schedule, met)
    losses = [f for f in d.findings if f.recoverable]
    limits = [f for f in d.findings if not f.recoverable]
    b, o = base.schedule.makespan, orc.schedule.makespan

    a = Analysis(confidence="high")
    a.verdict = (f"{session.scenario}: {b} cycles, achievable {o}, "
                 f"lower bound {met.lower_bound}.")
    if losses:
        f = losses[0]
        a.root_cause = f"{f.title}. {f.why}"
        a.plan.append(Step(f.fix, b - o, "/compare"))
    else:
        a.root_cause = ("No ordering losses: the block hits the machine "
                        "lower bound.")
        if limits:
            a.root_cause += f" Bound by: {limits[0].title}."
    a.plan.append(Step("Inspect full diagnostics", 0, "/doctor"))
    a.risk = ("Simplified machine model: excludes register pressure, speculation, "
              "predicates, and complex memory hierarchy effects.")
    return a
