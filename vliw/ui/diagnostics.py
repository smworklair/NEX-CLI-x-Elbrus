"""Diagnostics renderer: dense, hierarchical, no wall of text.

Design goal: within three seconds the engineer sees the headline number and
one line for the costliest issue. Details are available on demand (`/doctor N`).
"""

from __future__ import annotations

from ..core.doctor import Diagnosis, Finding
from . import render
from .render import Style, paint, table, wrap


def _cost(f: Finding) -> str:
    return f"-{f.cycles_lost} cyc" if f.cycles_lost > 0 else "—"


def _bar(load: float, width: int = 12) -> str:
    filled = int(width * load)
    role = "error" if load > 0.8 else ("accent2" if load > 0.55 else "accent_soft")
    return paint(role, "▄" * filled) + Style.dim("_" * (width - filled))


# --------------------------------------------------------------------------
# Grouping identical findings
# --------------------------------------------------------------------------

# Overlapping operation stalls cannot be summed (total would exceed makespan).
# Only disjoint idle-stall spans are additive.
_ADDITIVE = {"idle-stall"}


def _group(findings: list[Finding]) -> list[tuple[Finding, int, int]]:
    """Return [(representative, count, group_cost)] grouped by rule code."""
    order: list[str] = []
    buckets: dict[str, list[Finding]] = {}
    for f in findings:
        if f.code not in buckets:
            buckets[f.code] = []
            order.append(f.code)
        buckets[f.code].append(f)
    out = []
    for code in order:
        group = buckets[code]
        costs = [g.cycles_lost for g in group]
        total = sum(costs) if code in _ADDITIVE else max(costs, default=0)
        out.append((group[0], len(group), total))
    out.sort(key=lambda t: -t[2])
    return out


def _group_title(f: Finding, count: int) -> str:
    if count == 1:
        return f.title
    if f.code == "idle-stall":
        return f"idle stalls: {count} region(s)"
    if f.code == "monopoly-queue":
        return f"exclusive port queue: {count} op(s)"
    if f.code == "monopoly-block":
        return f"exclusive port blocked by wrong op: {count} case(s)"
    return f"{f.title} (x{count})"


# --------------------------------------------------------------------------
# Compact report
# --------------------------------------------------------------------------


def render_diagnosis(d: Diagnosis, label: str = "") -> list[str]:
    out: list[str] = []
    losses = [f for f in d.findings if f.recoverable]
    limits = [f for f in d.findings if not f.recoverable]

    # --- headline line -------------------------------------------------
    if d.total_lost > 0:
        head = paint("error", f"* {d.total_lost} cyc") + paint("title", " recoverable")
    else:
        head = paint("success", "* hits machine lower bound")
    tail = Style.dim(f"{d.makespan} cyc  →  lower bound {d.lower_bound} cyc")
    out.append(f"  {head}    {tail}")

    busiest = max(d.ports, key=lambda p: p.load(d.span), default=None)
    if busiest is not None:
        out.append("  " + Style.dim(
            f"idle {d.idle_cycles} cyc  ·  slots {d.slot_utilization:.0%}  ·  "
            f"busiest port {busiest.label} {busiest.load(d.span):.0%}"))
    out.append("")

    # --- one compact row per active port -------------------------------
    rows = []
    for p in d.ports:
        load = p.load(d.span)
        if not load and not p.sole_ops:
            continue
        sole = paint("accent2", "sole " + "/".join(p.sole_ops)) if p.sole_ops else ""
        rows.append([p.label, _bar(load), f"{load:>4.0%}", f"{p.issued} ops", sole])
    if rows:
        for r in rows:
            out.append("   " + "  ".join([
                render.pad(r[0], 5), r[1], render.pad(r[2], 5, ">"),
                render.pad(r[3], 7, ">"), r[4]]))
        out.append("")

    # --- recoverable losses --------------------------------------------
    if losses:
        out.append("  " + paint("error", "RECOVERABLE"))
        for n, (f, cnt, total) in enumerate(_group(losses), 1):
            mark = paint("error", "*") if n == 1 else Style.dim("o")
            out.append(f"   {mark} {n}  {paint('warning', f'-{total} cyc'):>12}  "
                       f"{_group_title(f, cnt)}")
        out.append("")
        # Detailed explanation only for the costliest finding; others via /doctor N.
        top = _group(losses)[0][0]
        out += _detail(top, prefix="   ", with_title=False)
        out.append("")
    else:
        out.append("  " + paint("success", "RECOVERABLE: none"))
        out += wrap(Style.dim("issue order loses no cycles — everything that could "
                              "be issued earlier was issued earlier"), render.W, "   ")
        out.append("")

    # --- machine bounds: one line each ---------------------------------
    if limits:
        out.append("  " + Style.dim("MACHINE BOUNDS") + Style.dim(" — not scheduler errors"))
        for f, cnt, total in _group(limits):
            cost = f"-{total} cyc" if total > 0 else "—"
            out.append(f"   {Style.dim('·')}    {Style.dim(cost):>12}  "
                       f"{Style.dim(_group_title(f, cnt))}")
        out.append("")

    hint = "/doctor 2 — details for the next finding" if len(_group(losses)) > 1 else \
           "/doctor oracle — same diagnostics for the exact oracle"
    out.append("  " + Style.dim(hint))
    return out


def _detail(f: Finding, prefix: str = "  ", with_title: bool = True) -> list[str]:
    """Detailed explanation of a single finding."""
    w = render.W - len(prefix)
    out = [prefix + paint("title", f.title)] if with_title else []
    out += wrap(Style.dim("where  ") + f.where, w, prefix + "  ")
    out += wrap(Style.dim("why    ") + f.why, w, prefix + "  ")
    out += wrap(paint("accent_soft", "fix    ") + f.fix, w, prefix + "  ")
    return out


def render_detail(d: Diagnosis, n: int) -> list[str]:
    """Details for finding #N from the recoverable list."""
    losses = [f for f in d.findings if f.recoverable]
    groups = _group(losses)
    if not groups:
        return ["  " + Style.dim("no recoverable findings")]
    if n < 1 or n > len(groups):
        return ["  " + paint("error", f"no finding #{n}; total {len(groups)}")]
    f, cnt, total = groups[n - 1]
    out = [f"  {paint('error', f'-{total} cyc')}  {_group_title(f, cnt)}", ""]
    out += _detail(f, prefix="  ")
    return out


def sidebar_rows(d: Diagnosis, width: int) -> list[str]:
    """Two or three concise summary lines for the sidebar."""
    losses = [f for f in d.findings if f.recoverable]
    limits = [f for f in d.findings if not f.recoverable]
    out: list[str] = []
    if d.total_lost > 0:
        out.append(paint("error", f"  * {d.total_lost} cyc over bound"))
    else:
        out.append(paint("success", "  * hits lower bound"))
    groups = _group(losses)
    if groups:
        f, cnt, total = groups[0]
        out.append(Style.dim(f"  {len(groups)} loss(es) · {len(limits)} bound(s)"))
        title = _group_title(f, cnt)
        out.append(paint("warning", f"  -{total} cyc"))
        for line in wrap(Style.dim(title), width, "    ")[:2]:
            out.append(line)
    else:
        out.append(Style.dim(f"  no losses · {len(limits)} bound(s)"))
    return out


# --------------------------------------------------------------------------
# Parsed .s report
# --------------------------------------------------------------------------


def render_parsed(parsed, dag, compiler_cycles: int | None,
                  oracle_cycles: int | None, lower_bound: int | None,
                  compiler_problem: tuple[str, str] | None = None,
                  problems=None) -> list[str]:
    """Render summary of a loaded `.s` file.

    `compiler_problem` is (headline, detail) explaining why the compiler
    schedule could not be reconstructed cleanly.
    """
    out: list[str] = []

    # Share of UNKNOWN ops determines whether comparing against lcc is valid:
    # UNKNOWN defaults to latency=1 on any channel, which can artificially beat lcc.
    unknown_ops = sum(1 for o in parsed.ops if o.op == "UNKNOWN")
    unknown_share = unknown_ops / len(parsed.ops) if parsed.ops else 0.0

    if compiler_cycles is not None and oracle_cycles is not None:
        gap = compiler_cycles - oracle_cycles
        if unknown_share >= 0.05:
            out.append("  " + paint("warning", "* compiler comparison is invalid"))
            out += wrap(Style.dim(
                f"{unknown_ops} of {len(parsed.ops)} operations "
                f"({unknown_share:.0%}) are unknown to the machine model — their "
                f"latency defaults to 1 cycle as a placeholder. Exact search beats "
                f"the compiler here only because it lacks their true latencies"), render.W, "  ")
            out.append("  " + Style.dim(
                f"lcc {compiler_cycles} cyc  →  oracle {oracle_cycles} cyc "
                f"(reference only, not comparable)"))
        else:
            if gap > 0:
                pct = 100.0 * gap / compiler_cycles
                head = paint("success", f"* headroom {gap} cyc ({pct:.0f}%)")
            elif gap == 0:
                head = paint("dim", "* no headroom")
            else:
                head = paint("warning", f"* compiler is faster by {-gap} cyc")
            out.append(f"  {head}")
            out.append("  " + Style.dim(
                f"lcc {compiler_cycles} cyc  →  oracle {oracle_cycles} cyc"
                + (f"  →  lower bound {lower_bound} cyc" if lower_bound else "")))
            if unknown_ops:
                out += wrap(Style.dim(
                    f"(caveat: {unknown_ops} op(s) unknown to the model, "
                    f"assumed latency 1 cycle)"), render.W, "  ")
    else:
        head, detail = compiler_problem or (
            "compiler schedule could not be reconstructed",
            "channel layout does not match the machine model")
        out.append("  " + paint("warning", "* " + head))
        out += wrap(Style.dim(detail), render.W, "  ")
    out.append("")

    out += wrap(Style.dim(
        f"{len(parsed.ops)} ops · {parsed.bundles} wide instructions · "
        f"{parsed.nop_cycles} cyc in nop"), render.W, "  ")
    ops = "  ".join(f"{k}x{v}" for k, v in sorted(parsed.op_counts().items()))
    out += wrap(Style.dim(ops), render.W, "  ")

    if parsed.unknown_mnemonics:
        unk = ", ".join(f"{k}x{v}" for k, v in
                        sorted(parsed.unknown_mnemonics.items(),
                               key=lambda kv: -kv[1])[:6])
        out += wrap(paint("warning",
                          f"unrecognized (class UNKNOWN, latency 1): {unk}"),
                    render.W, "  ")
    if parsed.skipped_lines:
        out.append("  " + Style.dim(f"skipped lines: {parsed.skipped_lines}"))

    # Linter diagnostics (shown in both CODE mode and plain `/load`).
    errors = [pr for pr in problems or () if pr.severity == "error"]
    warns = [pr for pr in problems or () if pr.severity == "warn"]
    if errors or warns:
        out.append("")
        if errors:
            out.append("  " + paint("error", f"* errors: {len(errors)}"))
            for pr in errors[:5]:
                out += wrap(paint("error", f"line {pr.line}: {pr.text}"),
                            render.W, "    ")
            if len(errors) > 5:
                out.append("    " + Style.dim(f"…and {len(errors) - 5} more"))
        if warns:
            out.append("  " + Style.dim(f"warnings: {len(warns)}"))
            for pr in warns[:3]:
                out += wrap(Style.dim(f"line {pr.line}: {pr.text}"),
                            render.W, "    ")
            if len(warns) > 3:
                out.append("    " + Style.dim(f"…and {len(warns) - 3} more"))

    out.append("")
    out.append("  " + Style.dim("Next: /doctor — where cycles are lost · /compare · /asm"))
    return out
