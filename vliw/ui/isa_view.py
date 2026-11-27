"""ISA reference renderer: terminal summary and Markdown document.

The same facts feed both outputs. In the terminal, a compact table without
leaving the tool; in Markdown, a generated document that never drifts from
`vliw/core/model.py`.
"""

from __future__ import annotations

from ..core.isa import CLUSTERS, COMBINATION_BANS, IsaClass, gaps
from .render import Style, paint, rule

_CH = "ALC"


def _chan(channels: tuple[int, ...]) -> str:
    return ",".join(str(c) for c in channels)


def _src_short(source: str) -> str:
    """One-word provenance label for the narrow terminal column."""
    low = source.lower()
    if "assembler" in low:
        return "assembler"
    if "chain" in low:
        return "chain"
    if "burst" in low or "stream" in low:
        return "burst"
    return "assumed"


def render_terminal(rows: list[IsaClass]) -> list[str]:
    out = [paint("title", "  e2k ISA: measured subset"), ""]
    out.append("  " + Style.dim(
        "channels correspond to Intel execution ports; peak is max ops accepted per cycle"))
    out.append("")
    head = (f"  {'class':<9}{'channels':<14}{'lat.':>5}{'occ.':>7}"
            f"{'peak/cyc':>10}   {'mnem.':>8}  latency source")
    out.append(paint("lab", head))
    for r in rows:
        colour = "success" if r.latency_measured else "warning"
        mark = "" if r.latency_measured else " ·"
        out.append(
            f"  {r.name:<9}{_chan(r.channels):<14}"
            f"{r.latency:>5}{r.occupancy:>7}{r.peak_per_cycle:>10.1f}   "
            f"{len(r.mnemonics):>8}  " + paint(colour, _src_short(r.latency_source)) + mark)
    holes = gaps(rows)
    out.append("")
    out.append("  " + paint("warning",
                            f"latency measured for {len(rows) - len(holes)} of "
                            f"{len(rows)} classes") + Style.dim(
        " — remaining classes default to 1 by assumption"))
    out.append("  " + Style.dim("full document: /isa --out docs/ISA.md"))
    return out


def render_markdown(rows: list[IsaClass], model, version: str) -> str:
    holes = gaps(rows)
    measured = len(rows) - len(holes)
    L: list[str] = []
    a = L.append

    a("# Elbrus e2k-v6: Operation Costs")
    a("")
    a(f"Profile `{model.name}`, {len(rows)} operation classes, "
      f"{sum(len(r.mnemonics) for r in rows)} annotated mnemonics. "
      f"Generated from `vliw/core/model.py` — NEX CLI {version}.")
    a("")
    a("## Scope and Limitations")
    a("")
    a("Intel splits documentation into two volumes that should not be confused:")
    a("")
    a("**SDM Volume 2** specifies instruction semantics: opcode encodings, operand")
    a("forms, pseudocode, flags, exceptions. **That is not here.**")
    a("")
    a("**Optimization Manual Appendix** specifies instruction COSTS: execution")
    a("ports, latency, and throughput (analogous to Agner Fog's tables and uops.info).")
    a("That is what this reference documents.")
    a("")
    a("**Correction (2026-09-02).** MCST publishes the *Elbrus Effective Programming")
    a("Guide* (CC BY 4.0, release 1.2), which covers ALU composition (ch. 4),")
    a("class latencies (sec. 6.1), and bypass/transfer delays (ch. 12).")
    a("")
    a("Why this reference still exists: (1) the official guide covers **E4C/E8C**,")
    a("whereas this toolchain targets **e2k-v6** and numbers differ (see comparison")
    a("below); (2) the guide groups by coarse classes, while this table maps 148")
    a("mnemonics individually with exact channel masks; (3) everything here is")
    a("measured locally and reproducible.")
    a("")
    a("## How to Read")
    a("")
    a("| column | meaning |")
    a("|---|---|")
    a("| **channels** | wide-instruction channels (`ALC0`..`ALC5`) where the op "
      "can execute (analogous to Intel execution ports) |")
    a("| **latency** | cycles until the result is visible to a consumer: "
      "a dependent op cannot issue before `t + latency` |")
    a("| **occupancy** | cycles the op exclusively holds its channel "
      "(1 = pipelined, free next cycle) |")
    a("| **peak/cyc** | channels / occupancy: theoretical peak issue rate "
      "(throughput in Agner Fog's tables) |")
    a("| **source** | how the value was obtained — "
      f"latency is measured for {measured} of {len(rows)} classes |")
    a("")
    a("## Summary Table")
    a("")
    a("Ordered from narrowest to widest channel masks: narrow classes are where "
      "the scheduler faces contention and loses cycles.")
    a("")
    a("| class | channels | latency | occupancy | peak/cyc | mnemonics | latency source |")
    a("|---|---|---:|---:|---:|---:|---|")
    for r in rows:
        src = r.latency_source if r.latency_measured else "**assumed**"
        a(f"| `{r.name}` | `{_chan(r.channels)}` | {r.latency} | {r.occupancy} | "
          f"{r.peak_per_cycle:.1f} | {len(r.mnemonics)} | {src} |")
    a("")
    mono = [r.name for r in rows if r.monopoly]
    a(f"Single-channel (exclusive) classes: {', '.join('`' + m + '`' for m in mono)}. "
      "Two operations from the same exclusive class can never issue in the same cycle.")
    a("")
    a("## Classes and Mnemonics")
    a("")
    for r in rows:
        a(f"### `{r.name}` — {_chan(r.channels)}")
        a("")
        a(f"Latency **{r.latency}** ({r.latency_source}), "
          f"channel occupancy **{r.occupancy}** ({r.occupancy_source}), "
          f"peak **{r.peak_per_cycle:.1f}** ops/cycle.")
        a("")
        if r.mnemonics:
            a("```")
            line = []
            for mn in r.mnemonics:
                line.append(mn)
                if len(line) == 8:
                    a(" ".join(line))
                    line = []
            if line:
                a(" ".join(line))
            a("```")
        else:
            a("_No mnemonics tagged._")
        a("")
    a("## Wide-Instruction Combination Bans")
    a("")
    a("Exhaustive pairwise assembler probing of individually valid operations")
    a(f"reveals exactly {len(COMBINATION_BANS)} forbidden combinations:")
    a("")
    a("```")
    for *_ignored, text in COMBINATION_BANS:
        a(text)
    a("```")
    a("")
    a("All other combinations are valid — including `STORE,2 + LOAD,0` and "
      "`STORE,5 + LOAD,3`. The ban targets specifically channel pairs `(2,3)` and `(5,0)`.")
    a("")
    ca, cb = CLUSTERS
    a(f"These are the seams between clusters `{_chan(ca)}` and `{_chan(cb)}`. "
      "**Clustering exists and is observable as a structural encoding ban in a "
      "wide instruction**, while inter-cluster bypass latency cannot be probed "
      "from the local toolchain alone.")
    a("")
    a("## Cross-Check Against Official MCST Documentation")
    a("")
    a("Source: *Elbrus Effective Programming Guide*, release 1.2 (2024-02-28),")
    a("CC BY 4.0, sec. 6.1 — [mcst.ru/elbrus_prog](http://www.mcst.ru/elbrus_prog).")
    a("Those numbers are NOT substituted into the model (E4C/E8C vs e2k-v6).")
    a("")
    a("| class | measured here | MCST doc | MCST name | verdict |")
    a("|---|---:|---:|---|---|")
    from ..core.isa import DOC_LATENCY
    agree = disagree = 0
    for r in rows:
        doc = DOC_LATENCY.get(r.name)
        if not doc:
            continue
        value, doc_name = doc
        same = str(r.latency) == value
        if same and r.latency_measured:
            verdict, agree = "**match** (measured & confirmed)", agree + 1
        elif same:
            verdict, agree = "assumption confirmed by doc", agree + 1
        elif r.latency_measured:
            verdict, disagree = "**mismatch**", disagree + 1
        else:
            verdict, disagree = "assumed here; doc gives different value", disagree + 1
        a(f"| `{r.name}` | {r.latency} | {value} | {doc_name} | {verdict} |")
    a("")
    a(f"Matches: **{agree}** classes; mismatches: **{disagree}**.")
    a("")
    a("**`LOAD`: 5 vs 3 — generational difference, not a bug.** The guide lists 3")
    a("cycles for L1 hits on E4C/E8C. Real `lcc -O3` output for e2k-v6 consistently")
    a("schedules dependent loads 5 cycles apart (both address and data chains).")
    a("")
    a("**Effects in the guide not modeled here** (pair-dependent, cannot be")
    a("expressed as a single scalar in `OpClass.latency`):")
    a("")
    a("* `fp→int` transfer penalty (+2 cycles);")
    a("* inter-cluster bypass delays (ch. 12: 1 cycle intra-cluster, 2 cross-cluster,")
    a("  3–4 via register file; clusters `,0 ,1 ,2` and `,3 ,4 ,5`).")
    a("")
    a("## Methodology")
    a("")
    a("Three black-box probing methods against the local toolchain:")
    a("")
    a("**Channels — assembler probing.** Assemble a minimal `.s` placing each op "
      "in each channel; invalid encodings return `cannot be encoded in ALCn`.")
    a("")
    a("**Latency — dependent chains.** `x = x * b` in a loop forces `lcc` to space "
      "adjacent dependent bundles by the exact latency.")
    a("")
    a("**Issue rate — independent streams.** 16 independent ops reveal minimum "
      "channel occupancy between consecutive issues.")
    a("")
    a("## Unmeasured Latencies")
    a("")
    a(f"Latency is measured for **{measured}** of **{len(rows)}** classes. The "
      f"remaining {len(holes)} default to 1 by assumption:")
    a("")
    a("| class | channels | mnemonics | needed measurement |")
    a("|---|---|---:|---|")
    for r in holes:
        a(f"| `{r.name}` | `{_chan(r.channels)}` | {len(r.mnemonics)} | "
          f"dependent-chain latency |")
    a("")
    a("Channels are measured for every class without exception via the assembler.")
    a("")
    return "\n".join(L) + "\n"
