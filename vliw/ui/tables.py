"""Tables: scenarios, summary results, capability matrix, sweep, selfcheck.

Pure formatting functions over precomputed `vliw.core`/`vliw.cli` data.
"""

from __future__ import annotations

from ..core import (
    SCENARIOS,
    MachineModel,
    SelfcheckResult,
    capability_matrix,
    describe_model,
)
from . import render
from .render import (
    Style,
    pad,
    paint,
    paint_op,
    table,
    wrap,
)


# --------------------------------------------------------------------------
# Scenario catalog
# --------------------------------------------------------------------------

# Tuple of (core_family_key, english_label, hint).
# Keys match `DAG.family` in `vliw/core/dag.py`.
_FAMILY_ORDER = [
    ("basics",         "basics",         "how a schedule looks — start here"),
    ("exclusive port", "exclusive port", "greedy heuristic loses cycles here: real gap to optimum"),
    ("model check",    "model check",    "what happens when the machine model is inaccurate"),
    ("graph shape",    "graph shape",    "scheduler is helpless — rewrite the source code"),
    ("op cost",        "op cost",        "cheaper to remove the expensive op than reschedule it"),
    ("loops",          "loops",          "unrolling, ILP growth, and its ceiling"),
    ("memory",         "memory",         "loads, pointer chasing, and data flow"),
    ("branching",      "branches",       "both paths precomputed without branching"),
    ("narrow class",   "narrow class",   "specialized functional units with limited ports"),
]

# "As written" -> "improved" pairs worth running back to back.
_PAIRS = [("seqreduce", "treereduce"), ("divpressure", "divstrength")]


def render_scenarios(current: str | None = None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    groups = list(_FAMILY_ORDER)
    known = {g for g, _, _ in _FAMILY_ORDER}
    groups += [(f, f, "") for f in {d.family for d in SCENARIOS.values()}
               if f not in known]

    for family_key, family_label, hint in groups:
        keys = [k for k, d in SCENARIOS.items() if d.family == family_key]
        if not keys:
            continue
        if out:
            out.append("")
        out.append("  " + paint("lab", "* ") + paint("title", family_label)
                   + ("   " + Style.dim(hint) if hint else ""))
        for key in keys:
            dag = SCENARIOS[key]
            seen.add(key)
            mark = paint("work", "*") if key == current else " "
            head = (f"  {mark} " + paint("accent", pad(key, 13))
                    + Style.dim(pad(str(len(dag)), 4, ">") + "  ") + dag.title)
            out.append(head)
            if dag.lesson:
                out += wrap(Style.dim(dag.lesson), render.W, "       ")

    rest = [k for k in SCENARIOS if k not in seen]
    if rest:
        out.append("")
        for key in rest:
            dag = SCENARIOS[key]
            mark = paint("work", "*") if key == current else " "
            out.append(f"  {mark} " + paint("accent", pad(key, 13))
                       + Style.dim(pad(str(len(dag)), 4, ">") + "  ") + dag.title)

    out.append("")
    pairs = "  ·  ".join(f"/run {a} → /run {b}" for a, b in _PAIRS
                         if a in SCENARIOS and b in SCENARIOS)
    if pairs:
        out += wrap(Style.dim("compare pairs: " + pairs.replace("/run ", "")),
                    render.W, "  ")
    out.append(Style.dim("  run all: all    ·    random block: random 16"))
    return out


# --------------------------------------------------------------------------
# Port capability matrix + latencies
# --------------------------------------------------------------------------


def render_matrix(model: MachineModel) -> list[str]:
    op_names, grid = capability_matrix(model)
    sole = model.sole_host_ops()
    cw = max(len(o) for o in op_names) + 1
    header = Style.dim("port ") + " ".join(pad(paint_op(o, o), cw, "^") for o in op_names)
    out = [header, Style.dim("─" * (5 + len(op_names) * (cw + 1)))]
    for port in model.ports:
        cells = []
        for j, o in enumerate(op_names):
            mark = paint_op(o, "*") if grid[port.index][j] else Style.dim("·")
            cells.append(pad(mark, cw, "^"))
        tag = ""
        if port.index in sole:
            names = "/".join(sole[port.index])
            tag = "  " + paint_op(sole[port.index][0], f"< sole {names}")
        out.append(Style.dim(f"{model.port_label(port.index):>4} ") + " ".join(cells) + tag)
    return out


def render_model_view(model: MachineModel) -> list[str]:
    out = []
    out += wrap(model.description, render.W, "  ")
    out.append("")
    out.append("  " + Style.bold("capability matrix: port → supported operations"))
    out += ["  " + l for l in render_matrix(model)]
    out.append("")
    out.append("  " + Style.bold("latencies and exclusive occupancy:"))
    rows = [[p, v, Style.dim(src)] for p, v, src in describe_model(model)]
    out += ["  " + l for l in table(["parameter", "value", "source"], rows)]
    return out


# --------------------------------------------------------------------------
# Summary across all scenarios (`all` command)
# --------------------------------------------------------------------------


def render_summary(rows: list[dict]) -> list[str]:
    """rows: dict(key, n, model_name, lb, base_ms, oracle_ms, gap, optimal, seconds)."""
    disp = []
    n_gap = n_proven_equal = n_unproven = 0
    for r in rows:
        gap = r["gap"]
        if gap:
            n_gap += 1
        elif r["optimal"]:
            n_proven_equal += 1
        else:
            n_unproven += 1
        pct = 100.0 * gap / r["base_ms"] if r["base_ms"] else 0
        disp.append([
            r["key"], str(r["n"]), r["model_name"], str(r["lb"]),
            str(r["base_ms"]), str(r["oracle_ms"]),
            Style.green(f"-{gap} ({pct:.0f}%)") if gap else Style.dim("—"),
            Style.green("proven") if r["optimal"] else Style.yellow("unproven"),
            f"{r['seconds']:.1f}s",
        ])
    out = ["  " + l for l in table(
        ["scenario", "N", "model", "bound", "baseline", "oracle",
         "gain", "optimum", "time"],
        disp, aligns="<><>>><<>",
    )]
    out.append("")
    parts = [f"Out of {len(rows)} scenarios:"]
    if n_gap:
        parts.append(
            f"{n_gap} have a proven gap between greedy baseline and the oracle — "
            f"this is where a smarter scheduler has real headroom;"
        )
    if n_proven_equal:
        parts.append(
            f"in {n_proven_equal} the greedy heuristic is proven optimal — "
            f"nothing left to recover;"
        )
    if n_unproven:
        parts.append(
            f"in {n_unproven} exact search hit its budget: no gap found, "
            f"and optimality remains unproven."
        )
    out += wrap(" ".join(parts), render.W, "  ")
    return out


# --------------------------------------------------------------------------
# Random-DAG sweep (`sweep` command)
# --------------------------------------------------------------------------


def render_sweep(rows: list[dict], stopped: bool) -> list[str]:
    """rows: dict(model_name, width, uniform, n_gap, n_proven, avg_gap, worst)."""
    disp = []
    for r in rows:
        share = f"{r['n_gap']}/{r['n_proven']}" if r["n_proven"] else "—"
        disp.append([
            r["model_name"], str(r["width"]),
            Style.dim("uniform") if r["uniform"] else Style.yellow("asymmetric"),
            share,
            f"{100.0 * r['n_gap'] / r['n_proven']:.0f}%" if r["n_proven"] else "—",
            f"{r['avg_gap']:.0f}%" if r["avg_gap"] is not None else Style.dim("—"),
            f"{r['worst']}" if r["worst"] else Style.dim("—"),
        ])
    out = ["  " + l for l in table(
        ["model", "ch.", "slots", "with gap", "share", "avg gap", "max cyc"],
        disp, aligns="<><>>>>",
    )]
    out.append("")
    if stopped:
        out += wrap(Style.dim(
            "Some configurations were truncated by the time limit (--time-limit)."),
            render.W, "  ")
    out += wrap(
        "Takeaway: the more asymmetric the ports, the more often greedy list "
        "scheduling misses. On a uniform-port model the gap nearly vanishes; "
        "on the measured model it appears whenever a scarce channel "
        "(divider `,5`, store `,2`/`,5`) goes to a less urgent op.",
        render.W, "  ")
    out.append("")
    out += wrap(Style.dim(
        "For reference, profile e2k-v6-firstprobe is the disproven v1 model "
        "that mistakenly treated MUL as exclusive — showing how strongly "
        "conclusions depend on machine-model accuracy."), render.W, "  ")
    return out


# --------------------------------------------------------------------------
# Oracle brute-force verification (`selfcheck` command)
# --------------------------------------------------------------------------


def render_selfcheck(res: SelfcheckResult) -> list[str]:
    out = [
        Style.dim(
            f"Verifying exact oracle against independent brute-force search: "
            f"{res.seeds} graphs x {len(res.sizes)} sizes x {res.models} models."
        ),
        Style.dim("Brute-force runs on small graphs only — this is expected."),
        "",
    ]
    for tag, problems in res.problems:
        out.append(Style.red(f"  - {tag}"))
        out += [f"      {p}" for p in problems]
    if res.failed:
        out.append(Style.red(
            f"FAIL: {res.failed} mismatches out of {res.checked} checks "
            f"({res.seconds:.0f} s)"))
    else:
        note = " (partial, time limit reached)" if res.stopped_early else ""
        out.append(Style.green(
            f"OK: {res.checked} checks, 0 mismatches{note} ({res.seconds:.0f} s)."))
        out += wrap(
            "Optimality claimed by the oracle is confirmed by independent "
            "exhaustive search.", render.W, "  ")
    return out
