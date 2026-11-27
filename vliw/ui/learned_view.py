"""Learned scheduler report renderer.

Unlike `schedule_view`, a learned schedule MAY be invalid — that is a real
measurement outcome, not a tool crash. Output shows validity first, then exact
violations, and only then comparison with the oracle if valid.
"""

from __future__ import annotations

from . import render
from .render import Style, paint, wrap


def render_status(ready: bool, lines: list[str]) -> list[str]:
    """Local run readiness: weights, dependencies, memory."""
    out = [paint("lab", "* ") + paint("title", "learned scheduler")]
    out.append("  " + (paint("success", "ready to run") if ready
                       else paint("warning", "not ready yet")))
    out.append("")
    for l in lines:
        out.append("  " + (Style.dim(l) if l else ""))
    out.append("")
    out.append("  " + Style.dim("run:     /learned            — on current scenario"))
    out.append("  " + Style.dim("         /learned <adapter>  — with specific weights"))
    out.append("  " + Style.dim("         /learned --status   — status only"))
    return out


def render_result(res, dag, oracle_res=None, baseline_res=None) -> list[str]:
    """Render learned model output: verdict, violations, and oracle comparison."""
    st = res.search_stats
    valid = st.get("valid", False)
    out: list[str] = []

    repaired = st.get("repaired", 0)
    winner = st.get("cab_winner")
    if valid and winner and winner not in ("model", "model+channels"):
        out.append("  " + paint("success", "SCHEDULE VALID")
                   + Style.dim(f"  (CAB: {winner})"))
    elif valid and repaired:
        out.append("  " + paint("success", "SCHEDULE VALID")
                   + Style.dim("  (model + channel repair)"))
    elif valid:
        out.append("  " + paint("success", "SCHEDULE VALID")
                   + Style.dim("  (pure model output)"))
    else:
        out.append("  " + paint("error", "SCHEDULE INVALID"))
    out.append("")
    for n in res.notes:
        if n.startswith(("NOT ", "SCHEDULE")):
            out.append("  " + paint("warning", n))
        elif n.startswith(("REPAIRED", "PORTFOLIO")):
            out.append("  " + paint("lab", n))
        elif n.lstrip().startswith("<-"):
            out.append("  " + paint("success", n))
        else:
            out.append("  " + Style.dim(n))

    if valid and oracle_res is not None:
        out.append("")
        ms = res.schedule.makespan
        orc = oracle_res.schedule.makespan
        base = baseline_res.schedule.makespan if baseline_res is not None else None
        rows = [(winner or "model", ms), ("exact search (oracle)", orc)]
        if base is not None:
            rows.insert(1, ("greedy heuristic (baseline)", base))
        width = max(len(r[0]) for r in rows)
        for label, v in rows:
            out.append(f"  {label:<{width}}  {v:>4} cyc")
        gap = ms - orc
        out.append("")
        if gap == 0:
            out.append("  " + paint("success",
                                    "model HIT OPTIMUM — matches exact oracle"))
        elif base is not None and ms <= base:
            out.append("  " + paint("success", f"model beat greedy baseline, "
                                               f"{gap} cyc from optimum"))
        else:
            out.append("  " + Style.dim(f"{gap} cyc from optimum"))

    out.append("")
    out.append("  " + Style.dim("raw output: /learned --raw"
                                "   ·   without repair: /learned --pure"))
    if not winner:
        out.append("  " + Style.dim(
            "valid portfolio from this response: /learned --cab"))
    return out


def render_raw(res) -> list[str]:
    """Raw model output text."""
    raw = str(res.search_stats.get("raw", ""))
    out = [paint("title", "  raw model output"), ""]
    if not raw.strip():
        out.append("  " + Style.dim("(empty — model emitted no lines)"))
        return out
    for line in raw.splitlines()[:60]:
        out.append("  " + Style.dim(line))
    extra = len(raw.splitlines()) - 60
    if extra > 0:
        out.append("  " + Style.dim(f"… {extra} more lines"))
    return out


def render_bench(res, adapter_name: str) -> list[str]:
    """Benchmark summary: error breakdown and split by STORE presence."""
    n = len(res.rows)
    out = [paint("title", f"  bench · {adapter_name} · {n} samples "
                          f"· {res.seconds:.0f} s"), ""]
    if not n:
        out.append("  " + Style.dim("nothing to measure"))
        return out

    order = (
        ("valid", "valid"),
        ("tail", "tail"),
        ("resource", "resource"),
        ("other", "other"),
    )
    counts = res.by_kind()
    for k, label in order:
        v = counts.get(k, 0)
        if not v:
            continue
        colour = "success" if k == "valid" else "error" if k == "resource" else "warning"
        bar = "█" * max(1, round(20 * v / n))
        out.append(f"  {paint(colour, label):<20} {v:>3}  ({res.pct(v):>4.0f}%)  "
                   + Style.dim(bar))

    gaps = [r.gap for r in res.rows if r.gap is not None]
    if gaps:
        exact = sum(1 for g in gaps if g == 0)
        out.append("")
        out.append("  " + Style.dim(
            f"mean gap to optimum (valid only): {sum(gaps) / len(gaps):.2f} cyc, "
            f"exact optimum {exact}/{len(gaps)}"))

    bo = getattr(res, "best_of", None)
    if bo is not None and any(r.samples for r in res.rows):
        out.append("")
        out.append("  " + paint("title",
                                f"best-of: {bo.n} samples, "
                                f"temperature {bo.temperature:g}, seed {bo.seed}"))
        out.append("  " + Style.dim("valid = at least one of the first k samples"))
        for k in range(1, bo.n + 1):
            ok, total = res.best_of_valid(k)
            if not total:
                continue
            colour = "success" if ok >= total / 2 else "warning"
            bar = "█" * max(1, round(20 * ok / total))
            out.append(f"    k={k:<2} valid {paint(colour, f'{100 * ok / total:>4.0f}%')}"
                       + Style.dim(f"  ({ok}/{total})  {bar}"))
        sampled = sum(r.valid_samples for r in res.rows if r.samples)
        n_s = sum(len(r.samples) for r in res.rows if r.samples)
        if n_s:
            out.append("  " + Style.dim(
                f"total valid samples: {sampled}/{n_s} "
                f"({100 * sampled / n_s:.0f}%) — single-sample validity rate"))

    winners = res.cab_winners()
    if winners:
        out.append("")
        out.append("  " + paint("title", "CAB portfolio winners"))
        total = sum(w for w, _ in winners.values())
        gained = sum(b for _, b in winners.values())
        for name, (k, better) in sorted(winners.items(), key=lambda kv: -kv[1][0]):
            colour = "success" if better else "warning"
            note = (f"{better} strictly beat greedy" if better
                    else "all tied with greedy" if name != "greedy"
                    else "model added nothing")
            out.append(f"    {name:<15} {paint(colour, f'{k:>3}')}"
                       + Style.dim(f"/{total}  {note}"))
        out.append("    " + Style.dim(
            f"total graphs beating greedy baseline: {gained}/{total}"))

    split = res.split_store()
    out.append("")
    out.append("  " + paint("title", "split by STORE presence in graph"))
    for has, label in ((True, "with STORE"), (False, "no STORE")):
        ok, total = split[has]
        if not total:
            continue
        pct = 100.0 * ok / total
        colour = "error" if has and pct < 50 else "success" if pct >= 50 else "warning"
        out.append(f"    {label:<11} valid {paint(colour, f'{pct:>3.0f}%')}"
                   + Style.dim(f"  ({ok}/{total})"))
    ok_s, tot_s = split[True]
    ok_n, tot_n = split[False]
    if tot_s and tot_n and (ok_n / tot_n) - (ok_s / tot_s) > 0.2:
        out.append("")
        out += wrap(Style.dim(
            "Gap between rows reflects the training-set bias: STORE never "
            "appeared in run-1 training data, so the model does not know it "
            "only executes on channels ,2 and ,5."), render.W, "    ")
    return out


def render_compare_line(learned_res, base_res, oracle_res) -> list[str]:
    """Compact three-scheduler comparison table on the same graph."""
    st = learned_res.search_stats
    if not st.get("valid"):
        return ["  " + Style.dim("model produced no valid schedule — "
                                 "nothing to compare")]

    ms = learned_res.schedule.makespan
    b = base_res.schedule.makespan
    o = oracle_res.schedule.makespan
    tag = "  (+ channel repair)" if st.get("repaired") else ""

    rows = [
        ("greedy heuristic", b, "warning"),
        ("learned model" + tag, ms, "lab"),
        ("exact oracle", o, "success"),
    ]
    width = max(len(r[0]) for r in rows)
    out = ["  " + paint("title", "THREE SCHEDULERS ON THE SAME GRAPH"), ""]
    for label, v, colour in rows:
        out.append(f"  {paint(colour, label):<{width + 12}}  {v:>4} cyc")

    out.append("")
    if ms < b:
        out.append("  " + paint("success",
                                f"model beat greedy by {b - ms} cyc"
                                + (" and hit optimum" if ms == o else
                                   f", {ms - o} cyc from optimum")))
    elif ms == b == o:
        out.append("  " + Style.dim("all three tied — no headroom on this graph"))
    elif ms == b:
        out.append("  " + Style.dim(
            f"model matched greedy; {ms - o} cyc from optimum"))
    else:
        out.append("  " + Style.dim(
            f"model trailed greedy by {ms - b} cyc"))
    return out


class PlainRenderer:
    """Scheduler event stream -> lines for plain line-by-line output."""

    def __init__(self) -> None:
        self._line: list[str] = []
        self._opened = False

    def feed(self, ev) -> list[str]:
        """Event -> lines to print right now (empty list if buffering)."""
        from ..core import Done, Failed, Note, Started, Token

        if isinstance(ev, Started):
            return []
        if isinstance(ev, Note):
            return ["  " + (paint(ev.level, ev.text) if ev.level != "dim"
                            else Style.dim(ev.text))]
        if isinstance(ev, Token):
            out: list[str] = []
            if not self._opened:
                self._opened = True
                out.append("  " + Style.dim("── model generating ──"))
            out.extend(self._feed_text(ev.text))
            return out
        if isinstance(ev, (Done, Failed)):
            return self._feed_text("\n")
        return []

    def _feed_text(self, chunk: str) -> list[str]:
        out: list[str] = []
        for ch in chunk:
            if ch == "\n":
                text = "".join(self._line).replace("[end of text]", "").rstrip()
                self._line.clear()
                if text:
                    out.append("  " + Style.dim(text))
            else:
                self._line.append(ch)
        return out
