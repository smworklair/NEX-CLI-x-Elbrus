#!/usr/bin/env python3
"""Benchmark NEX CLI on hand-written e2k assembly snippets.

Parses `.s` files (default `benchmarks/snippets/`), builds dependency DAGs,
and runs baseline (greedy), TINY Flash, and oracle (exact search).

Usage:
    python tools/bench_snippets.py
    python tools/bench_snippets.py --budget 5
    python tools/bench_snippets.py benchmarks/snippets/03_predication.s
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vliw.core.asm_parser import (  # noqa: E402
    build_dag,
    compiler_schedule_checked,
    lint,
    parse_file,
    unknown_share,
)
from vliw.core.baseline import GreedyListScheduler  # noqa: E402
from vliw.core.dag import compute_metrics  # noqa: E402
from vliw.core.model import get_profile  # noqa: E402
from vliw.core.oracle import OracleScheduler  # noqa: E402
from vliw.tiny.fast import TinyFlashScheduler  # noqa: E402


def _timed(fn):
    t0 = time.perf_counter()
    res = fn()
    return res, (time.perf_counter() - t0) * 1000.0


def _legal(res) -> bool:
    return res.schedule.complete and not res.schedule.validate()


def run_one(path: Path, model, budget: float, portfolio: float, tiny) -> dict:
    parsed = parse_file(str(path))
    dag = build_dag(parsed, key=path.stem, title=path.name)
    met = compute_metrics(dag, model)
    problems = lint(parsed, model)
    csched, cproblem = compiler_schedule_checked(parsed, dag, model)

    base, t_base = _timed(lambda: GreedyListScheduler().schedule(dag, model))
    fast, t_fast = _timed(lambda: tiny.schedule(dag, model))
    orc, t_orc = _timed(lambda: OracleScheduler(
        budget_s=budget, portfolio_s=portfolio).schedule(dag, model))

    unknown = sum(1 for o in parsed.ops if o.op == "UNKNOWN")
    errors = [p for p in problems if p.severity == "error"]
    warns = [p for p in problems if p.severity == "warn"]

    return {
        "file": path.name,
        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "ops": len(parsed.ops),
        "bundles": parsed.bundles,
        "nop_cycles": parsed.nop_cycles,
        "skipped_lines": parsed.skipped_lines,
        "unknown_mnemonics": parsed.unknown_mnemonics,
        "unknown": unknown,
        "unknown_share": round(unknown_share(parsed), 4),
        "compiler_cycles": parsed.compiler_cycles,
        "compiler_schedule": csched is not None,
        "compiler_problem": list(cproblem) if cproblem else None,
        "lower_bound": met.lower_bound,
        "critical_path": met.critical_path_bound,
        "resource_bound": met.resource_bound,
        "binding": met.binding,
        "baseline": base.schedule.makespan,
        "tiny": fast.schedule.makespan,
        "oracle": orc.schedule.makespan,
        "oracle_optimal": bool(orc.optimal),
        "legal": {"baseline": _legal(base), "tiny": _legal(fast), "oracle": _legal(orc)},
        "ms": {"baseline": round(t_base, 3), "tiny": round(t_fast, 3),
               "oracle": round(t_orc, 1)},
        "problems": [{"line": p.line, "kind": p.kind, "severity": p.severity,
                      "text": p.text, "hint": p.hint} for p in problems],
        "errors": len(errors),
        "warns": len(warns),
    }


def _fmt_gain(baseline: int, best: int) -> str:
    if best >= baseline:
        return "-"
    return f"-{baseline - best} ({100 * (baseline - best) / baseline:.0f}%)"


def print_table(rows: list[dict]) -> None:
    head = (f"{'file':<28} {'N':>3} {'orig':>5} {'base':>5} {'TINY':>5} "
            f"{'oracle':>6} {'opt.':>5} {'UNK':>4} {'errs':>5}")
    print(head)
    print("-" * len(head))
    for r in rows:
        opt = "yes" if r["oracle_optimal"] else "no"
        print(f"{r['file']:<28} {r['ops']:>3} {r['compiler_cycles']:>5} "
              f"{r['baseline']:>5} {r['tiny']:>5} {r['oracle']:>6} {opt:>5} "
              f"{r['unknown']:>4} {r['errors']:>5}")


def print_details(rows: list[dict]) -> None:
    for r in rows:
        print()
        print(f"{r['file']}  ({r['path']})")
        print(f"  {r['ops']} ops, {r['bundles']} wide instructions, "
              f"nop cycles {r['nop_cycles']}; lower bound {r['lower_bound']} "
              f"({r['binding']})")
        if r["compiler_schedule"]:
            print(f"  compiler schedule: {r['compiler_cycles']} cycles (valid)")
        else:
            print("  compiler schedule: not reconstructed — "
                  + (r["compiler_problem"][1] if r["compiler_problem"] else "?"))
        print(f"  baseline {r['baseline']} | TINY Flash {r['tiny']} "
              f"({r['ms']['tiny']} ms) | oracle {r['oracle']} "
              f"({'proven optimal' if r['oracle_optimal'] else 'unproven'}, "
              f"{r['ms']['oracle']} ms)")
        print(f"  TINY Flash gain: {_fmt_gain(r['baseline'], r['tiny'])}; "
              f"UNKNOWN {r['unknown']} ({100 * r['unknown_share']:.0f}%)")
        status = ", ".join(f"{k}: {'valid' if v else 'INVALID'}"
                           for k, v in r["legal"].items())
        print(f"  schedule validation: {status}")
        for p in r["problems"][:4]:
            print(f"  ! line {p['line']}: {p['text']}")
        if len(r["problems"]) > 4:
            print(f"  ... {len(r['problems']) - 4} more issues")


def write_markdown(rows: list[dict], path: Path, model, budget: float) -> None:
    lines = [
        "# e2k Snippet Benchmark",
        "",
        f"Machine profile: `{model.name}` ({model.width} ports). "
        f"Exact search budget: {budget:g} s per file.",
        "",
        "| file | N | orig | baseline | TINY Flash | oracle | optimal | UNKNOWN | errors |",
        "|---|---:|---:|---:|---:|---:|---|---:|---:|",
    ]
    for r in rows:
        lines.append(
            f"| `{r['file']}` | {r['ops']} | {r['compiler_cycles']} | "
            f"{r['baseline']} | {r['tiny']} | {r['oracle']} | "
            f"{'yes' if r['oracle_optimal'] else 'no'} | {r['unknown']} | "
            f"{r['errors']} |")
    lines += [
        "",
        "`orig` is the schedule length as written in the file. It may be shorter",
        "than the valid minimum: the linter flags reads issued before producer",
        "latency elapses. `baseline`, `TINY Flash`, and `oracle` reschedule from",
        "scratch using the dependency DAG and machine model.",
        "",
        "## Details",
        "",
    ]
    for r in rows:
        lines.append(f"### `{r['file']}`")
        lines.append("")
        lines.append(f"- Lower bound: {r['lower_bound']} ({r['binding']}); "
                     f"critical path {r['critical_path']}, "
                     f"resources {r['resource_bound']}.")
        lines.append(f"- Time: baseline {r['ms']['baseline']} ms, "
                     f"TINY Flash {r['ms']['tiny']} ms, "
                     f"oracle {r['ms']['oracle']} ms.")
        if r["compiler_schedule"]:
            lines.append(f"- Compiler schedule: {r['compiler_cycles']} cycles.")
        else:
            lines.append("- Compiler schedule not reconstructed: "
                         + (r["compiler_problem"][1] if r["compiler_problem"] else "?"))
        if r["unknown"]:
            names = ", ".join(f"`{k}`" for k in r["unknown_mnemonics"])
            lines.append(f"- UNKNOWN: {r['unknown']} ops ({names}) — "
                         "latency 1 and any channel (placeholder, not measured).")
        if r["problems"]:
            lines.append("- Linter diagnostics:")
            for p in r["problems"][:6]:
                lines.append(f"  - line {p['line']}: {p['text']}")
        lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="NEX CLI benchmark on .s snippets")
    ap.add_argument("paths", nargs="*", help=".s files or directories (default: benchmarks/snippets)")
    ap.add_argument("--profile", default="e2k-v6-measured")
    ap.add_argument("--budget", type=float, default=1.5, help="oracle time budget, s")
    ap.add_argument("--portfolio", type=float, default=0.4, help="oracle portfolio time budget, s")
    ap.add_argument("--json", default="benchmarks/results.json")
    ap.add_argument("--md", default="benchmarks/RESULTS.md")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    targets = []
    for raw in (args.paths or ["benchmarks/snippets"]):
        p = Path(raw)
        if not p.is_absolute():
            p = ROOT / p
        if p.is_dir():
            targets.extend(sorted(p.glob("*.s")))
        else:
            targets.append(p)
    if not targets:
        print("no .s files found", file=sys.stderr)
        return 2

    model = get_profile(args.profile)
    tiny = TinyFlashScheduler(mode="exact")
    rows = []
    for path in targets:
        if not args.quiet:
            print(f"· {path.name}", file=sys.stderr, flush=True)
        rows.append(run_one(path, model, args.budget, args.portfolio, tiny))

    if not args.quiet:
        print()
        print_table(rows)
        print_details(rows)

    json_path = ROOT / args.json
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps({
        "profile": model.name,
        "budget_s": args.budget,
        "results": rows,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    md_path = ROOT / args.md
    md_path.parent.mkdir(parents=True, exist_ok=True)
    write_markdown(rows, md_path, model, args.budget)

    total = sum(r["ops"] for r in rows)
    wall = sum(r["ms"]["tiny"] + r["ms"]["oracle"] for r in rows)
    print()
    print(f"total: {len(rows)} files, {total} ops, "
          f"TINY Flash + oracle ~ {wall:.0f} ms")
    print(f"saved: {args.json}, {args.md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
