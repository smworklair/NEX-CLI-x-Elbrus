"""Facts about the current state — used to ground the language model.

Design principle: the LLM must never INVENT numbers. Every metric (cycles,
port utilization, detected losses) is computed by the deterministic core
`vliw.core` and passed here as a structured summary in the system prompt.
The model only explains and reasons over these facts, so every answer can
be verified with `/doctor` or `/compare`.
"""

from __future__ import annotations

from ..core import compute_metrics
from ..core.doctor import diagnose

SYSTEM = """\
You are NEX, an engineering assistant for instruction scheduling on the
Elbrus (e2k) VLIW processor. You are embedded in a research CLI and help
engineers understand why a code block takes a given number of cycles and
where time is lost.

STRICT RULES:
1. Take ALL numbers ONLY from the FACTS block below. Never invent cycles,
   percentages, or operation names. If a requested number is missing from
   FACTS, say so directly and suggest the command that computes it.
2. Answer in concise, direct technical English — engineer to engineer.
   No marketing fluff or generic remarks about "optimization".
3. Rely on the measured machine model. The ONLY truly exclusive functional
   unit on e2k is the DIVIDER (port `,5` only). Multiplication runs on four
   ports, store on two, load on four. Never claim multiplication is exclusive:
   that was disproven by assembler verification.
4. Distinguish two things clearly: a "loss" (the scheduler issued operations
   in a suboptimal order and cycles can be recovered) vs. a "machine bound"
   (waiting was unavoidable and no faster schedule exists).
5. When appropriate, end with a single line `Next:` suggesting a concrete
   command (/doctor, /compare, /tiny, /asm, /explain N, /load file.s).
6. Do not use Markdown headings or tables — output is rendered in a terminal.
   Short bullet lists with "—" are fine.
"""


def machine_facts(model) -> list[str]:
    out = [f"Machine profile: {model.name}, ports: {model.width}."]
    sole = model.sole_host_ops()
    for port, ops in sorted(sole.items()):
        out.append(f"Port {model.port_label(port)} is the SOLE executor for "
                   f"{'/'.join(ops)} (exclusive).")
    lat = []
    for name in sorted(model.ops):
        op = model.ops[name]
        s = f"{name}={op.latency}c"
        if op.blocks_channel():
            s += f" (holds port {op.occupancy}c)"
        lat.append(s)
    out.append("Latencies: " + ", ".join(lat))
    for op_name in sorted(model.ops):
        chans = model.channels_for(op_name)
        if 1 < len(chans) < model.width:
            out.append(f"{op_name} executes on ports "
                       f"{', '.join(model.port_label(c) for c in chans)} "
                       f"({len(chans)} of {model.width}).")
    out.append("Model measured from lcc-1.29.16: port matrix verified with "
               "the assembler ('cannot be encoded in ALC' rejections), "
               "latencies via dependent chains, issue rates via independent streams.")
    return out


def schedule_facts(session) -> list[str]:
    """Numbers for the current block — only if already computed."""
    cached = session.peek()
    dag = session.dag_obj
    out = [f"Current block: {session.scenario}, instructions: {len(dag)}."]
    counts = ", ".join(f"{k}×{v}" for k, v in sorted(dag.op_counts().items()))
    out.append(f"Operation mix: {counts}.")
    if dag.note:
        out.append(f"Block note: {dag.note[:400]}")
    if cached is None:
        out.append("Schedule has NOT been computed yet (run /run).")
        return out

    base, orc, met = cached
    b, o = base.schedule.makespan, orc.schedule.makespan
    out.append(f"baseline (greedy heuristic): {b} cycles.")
    out.append(f"oracle (exact search, theoretical optimum): {o} cycles.")
    out.append(f"Lower bound: {met.lower_bound} cycles "
               f"(critical path {met.critical_path_bound}, "
               f"resource {met.resource_bound}; binding: {met.binding}).")
    out.append(f"Gap baseline->oracle: {b - o} cycles.")
    out.append("Oracle optimality is PROVEN." if orc.optimal
               else "Oracle optimality is NOT proven (best found).")
    return out


def doctor_facts(session, limit: int = 6) -> list[str]:
    cached = session.peek()
    if cached is None:
        return []
    base, orc, met = cached
    try:
        d = diagnose(session.dag_obj, session.model(), base.schedule, met)
    except Exception:
        return []
    out = [f"BASELINE DIAGNOSTICS: makespan {d.makespan}c, "
           f"lower bound {d.lower_bound}c, idle cycles {d.idle_cycles}c, "
           f"slot utilization {d.slot_utilization:.0%}."]
    for p in d.ports:
        load = p.load(d.span)
        if load or p.sole_ops:
            sole = f" (sole {'/'.join(p.sole_ops)})" if p.sole_ops else ""
            out.append(f"  port {p.label}: load {load:.0%}, "
                       f"{p.issued} ops{sole}")
    losses = [f for f in d.findings if f.recoverable][:limit]
    limits = [f for f in d.findings if not f.recoverable][:limit]
    if losses:
        out.append("RECOVERABLE LOSSES:")
        for f in losses:
            out.append(f"  −{f.cycles_lost}c [{f.code}] {f.title}. "
                       f"Where: {f.where}. Why: {f.why}")
    else:
        out.append("No ordering losses detected.")
    if limits:
        out.append("MACHINE BOUNDS (not errors):")
        for f in limits:
            out.append(f"  {f.title} — {f.why}")
    return out


def schedule_layout(session, which: str = "baseline", max_rows: int = 40) -> list[str]:
    """Compact layout 'cycle: port=op' so the model can inspect exact placements."""
    cached = session.peek()
    if cached is None:
        return []
    base, orc, met = cached
    sched = base.schedule if which == "baseline" else orc.schedule
    model = session.model()
    dag = session.dag_obj
    by_cycle: dict[int, list[str]] = {}
    for p in sched.placements.values():
        by_cycle.setdefault(p.cycle, []).append(
            f"{model.port_label(p.channel)}={dag[p.instr].op} {dag[p.instr].name}")
    out = [f"SCHEDULE {which} (cycle: issued ops):"]
    cycles = sorted(by_cycle)
    for c in cycles[:max_rows]:
        out.append(f"  c.{c}: " + ", ".join(sorted(by_cycle[c])))
    # Truncation must be explicit so the model does not invent tail placements.
    if len(cycles) > max_rows:
        hidden = len(cycles) - max_rows
        out.append(f"  ... {hidden} more cycles omitted: layout truncated at "
                   f"{max_rows} rows. Data after c.{cycles[max_rows - 1]} is "
                   f"NOT shown — do not guess it; suggest /run or /explain N.")
    other = orc if which == "baseline" else base
    if other.schedule.makespan != sched.makespan:
        out.append(f"  (these are {which} cycles; "
                   f"{'oracle' if which == 'baseline' else 'baseline'} "
                   f"has a different layout — {other.schedule.makespan} cycles)")
    return out


def tiny_facts(session) -> list[str]:
    """TINY Flash vs baseline: third reference point in scheduler comparison."""
    cached = session.peek()
    if cached is None:
        return []
    try:
        from ..tiny.fast import TinyFlashScheduler

        res = TinyFlashScheduler().schedule(session.dag_obj, session.model())
    except Exception:
        return []
    errs = res.schedule.validate()
    if errs or not res.schedule.complete:
        return []
    base, orc, _met = cached
    b, o, t = base.schedule.makespan, orc.schedule.makespan, res.schedule.makespan
    winner = res.search_stats.get("tiny_winner", "?")
    if t >= b:
        return [f"TINY Flash ({winner}): {t} cycles — tied with baseline, "
                f"no regression (oracle: {o})."]
    return [f"TINY Flash ({winner}): {t} cycles — beats baseline ({b}), "
            f"oracle: {o}."]


def build(session, include_layout: bool = False) -> str:
    """Assemble the FACTS block for the system prompt."""
    parts: list[str] = ["FACTS (sole source of numbers):", ""]
    parts += machine_facts(session.model())
    parts.append("")
    parts += schedule_facts(session)
    from ..ai_hints import core_facts
    # TINY AI runs inside NEX core ("scheduler" block); fall back to direct call if absent.
    tiny = core_facts(session) or tiny_facts(session)
    if tiny:
        parts += tiny
    doc = doctor_facts(session)
    if doc:
        parts.append("")
        parts += doc
    if include_layout:
        lay = schedule_layout(session)
        if lay:
            parts.append("")
            parts += lay
    parts.append("")
    parts.append("Available scenarios: see /scenarios. "
                 "Commands: /run /compare /doctor /asm /explain /path /bounds "
                 "/model /load /probe.")
    return "\n".join(parts)


PANEL_SYSTEM = """\
You are NEX, an engineering assistant for instruction scheduling on the
Elbrus (e2k) VLIW processor. The user is looking at ONE panel of the tool
and asking about its contents.

STRICT RULES:
1. Answer ONLY from the PANEL lines below. Everything needed is there.
2. Do not extrapolate beyond those lines. If the answer isn't there, say so
   and suggest a command (/doctor, /compare, /run, /bounds).
3. Never invert statements. "Executes only on ,2 and ,5" means it does NOT
   execute on other ports — nothing else.
4. Answer in concise technical English, 2–4 sentences, engineer to engineer.
   No Markdown tables or headings: output goes to a terminal.
"""


CELL_SYSTEM = """\
You are NEX. The tool has already analyzed one scheduled operation step by step.
Your job is to restate the same conclusion in ONE plain-English sentence,
as if explaining to a colleague seeing VLIW for the first time.

STRICT RULES:
1. One sentence, two at most. This is a caption under a panel, not a report.
2. ZERO numbers that do not appear in the breakdown below. Do not add,
   subtract, or estimate. Numbers are already computed; your job is phrasing.
3. Do not invent causes. If the breakdown says "waits for no operands", then
   there was nothing to wait for and no queue.
4. Do not re-list the breakdown bullets: they are already visible right above.
5. Plain English. No Markdown.
"""

_NUM = __import__("re").compile(r"\d+")


def cell_answer_is_grounded(answer: str, facts: list[str]) -> bool:
    """Verify no number appeared in the answer that wasn't in the source facts.

    Acts as a hard guard against small-model hallucinations: every digit
    sequence in `answer` must appear verbatim in `facts`.
    """
    src = set(_NUM.findall(" ".join(facts)))
    return all(n in src for n in _NUM.findall(answer))


def cell_prompt(facts: list[str]) -> str:
    """Prompt for the one-line cursor caption — paraphrase, not open reasoning."""
    return "\n".join([CELL_SYSTEM, "", "TOOL BREAKDOWN:", ""]
                     + ["  " + f for f in facts])


def panel_prompt(title: str, facts: list[str]) -> str:
    """Narrow prompt for single-panel Q&A — fast and resistant to hallucination."""
    out = [PANEL_SYSTEM, "", f'PANEL "{title}" — sole source:', ""]
    out += ["  " + f for f in facts]
    return "\n".join(out)


def system_prompt(session, include_layout: bool = False,
                  panel: tuple[str, list[str]] | None = None,
                  smalltalk: bool = False) -> str:
    """Build the full system prompt. `panel` is (title, facts) of the active pane.

    ORDER MATTERS: panel and smalltalk modifiers are appended as SUFFIXES after
    the shared FACTS prefix so llama.cpp's `cache_prompt` hits on the ~1450-token
    prefix instead of recomputing it on every pane switch.
    """
    out = SYSTEM + "\n\n" + build(session, include_layout)
    if smalltalk:
        out += ("\n\nTHIS IS NOT A QUESTION ABOUT THE BLOCK, just casual "
                "small talk. Reply briefly and naturally. Do NOT add a 'Next:' "
                "line and do not pull in numbers or scheduling jargon.")
    if panel is not None:
        title, facts = panel
        out += (f'\n\nTHE USER IS CURRENTLY VIEWING PANEL "{title}". '
                "Answer only about what is shown in this panel.\n")
        out += "\n".join("  " + f for f in facts)
    return out
