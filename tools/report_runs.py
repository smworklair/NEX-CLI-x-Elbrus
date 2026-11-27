"""Aggregate validate_kaggle.py JSONL dumps into a run-comparison table.

Reclassifies legacy dump labels using current `classify()` logic by default.

    python tools/report_runs.py
    python tools/report_runs.py --run "0. no EOS" base_eval.jsonl base_eval_wide.jsonl
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Import classify()/_KIND from validate_kaggle.py to avoid drift.
#
#
#
#
#
#
#
#
from training.validate_kaggle import _KIND, classify              # noqa: E402

KINDS = tuple(_KIND)

# Labels where the 0..n-1 prefix is valid.
#
#
#
#
PREFIX_OK = ("valid", "tail", "\u0432\u0430\u043b\u0438\u0434\u043d\u043e", "\u0445\u0432\u043e\u0441\u0442")

# Substring matching extra-ID error from validate_kaggle.py.
#
#
#
#
_STRAY = "\u043d\u0435\u0441\u0443\u0449\u0435\u0441\u0442\u0432\u0443\u044e\u0449\u0438\u0435 id"


class Run:
    """Single eval dump: error breakdown, gaps, and graph-size buckets."""

    def __init__(self, path: Path, reclassify: bool = True):
        self.path = path
        self.total = 0
        self.counts: collections.Counter = collections.Counter()
        self.gaps: list[int] = []
        self.by_n: dict[int, list[bool]] = collections.defaultdict(list)
        self.relabelled: collections.Counter = collections.Counter()
        self.unreliable = 0

        for line in path.open(encoding="utf-8"):
            if not line.strip():
                continue
            rec = json.loads(line)
            self.total += 1
            n_graph = rec["n_graph"]
            errs = rec.get("errs", [])

            # Reconstruct out-of-range ID count for legacy dumps lacking "extra".
            #
            #
            #
            #
            #
            #
            #
            #
            #
            #
            #
            #
            if "extra" in rec:
                n_extra = len(rec["extra"])
                n_keep = max(0, rec["n_decoded"] - n_extra)
                reclassify_this = reclassify
            elif rec["n_decoded"] >= n_graph:
                n_extra = rec["n_decoded"] - n_graph
                n_keep = n_graph
                reclassify_this = reclassify
            else:
                n_extra = n_keep = 0   # unused when reclassify_this=False
                reclassify_this = False
                self.unreliable += 1

            if reclassify_this:
                # Extra-ID errors do not affect prefix validity.
                pref_errs = [e for e in errs if _STRAY not in e]
                # Flag legacy dumps where errors may reference hallucinated IDs.
                #
                #
                for e in pref_errs:
                    head = re.match(r"\D*(\d+)", e)
                    if head and int(head.group(1)) >= n_graph:
                        self.unreliable += 1
                        break
                kind = classify(pref_errs, n_keep, n_extra)
                if kind != rec.get("kind"):
                    self.relabelled[f"{rec.get('kind')} -> {kind}"] += 1
            else:
                kind = rec["kind"]

            self.counts[kind] += 1
            self.by_n[n_graph].append(kind in ("valid", "\u0432\u0430\u043b\u0438\u0434\u043d\u043e"))
            if kind in PREFIX_OK and rec.get("gap") is not None:
                self.gaps.append(rec["gap"])

    # --- derived metrics -------------------------------------------------

    @property
    def valid(self) -> int:
        return (self.counts["valid"] + self.counts["\u0432\u0430\u043b\u0438\u0434\u043d\u043e"])

    @property
    def prefix_ok(self) -> int:
        return sum(self.counts[k] for k in PREFIX_OK)

    def pct(self, n: int) -> float:
        return 100.0 * n / self.total if self.total else 0.0

    @property
    def exact(self) -> int:
        return sum(1 for g in self.gaps if g == 0)


def print_composition(name: str, run: Run) -> None:
    print(f"\n{name}  —  {run.path.name}  ({run.total} examples)")
    for k in KINDS:
        n = run.counts[k]
        if n:
            print(f"    {k:<14} {n:>4}  ({run.pct(n):>5.1f}%)")
    print(f"    {'-'*36}")
    print(f"    {'valid':<14} {run.valid:>4}  ({run.pct(run.valid):>5.1f}%)"
          f"   valid prefix: {run.prefix_ok} ({run.pct(run.prefix_ok):.1f}%)")
    if run.gaps:
        avg = sum(run.gaps) / len(run.gaps)
        print(f"    gap to optimum (valid prefixes): "
              f"{avg:.2f} cycles, exact optimal {run.exact}/{len(run.gaps)}")
    if run.relabelled:
        print("    RECLASSIFIED (stale dump label):")
        for change, n in run.relabelled.most_common():
            print(f"        {n:>4}  {change}")
    if run.unreliable:
        print(f"    !! {run.unreliable} rows with violations on out-of-range IDs — "
              f"prefix reclassification unreliable")


def print_matrix(rows: list[tuple[str, Run | None, Run | None]]) -> None:
    print("\n" + "=" * 78)
    print("SUMMARY TABLE: valid % (valid prefix %)")
    print("=" * 78)
    print(f"{'run':<34} {'eval.jsonl 6..14':>20} {'eval_wide 4..24':>20}")
    print("-" * 78)

    def cell(r: Run | None) -> str:
        if r is None:
            return f"{'—':>20}"
        return f"{r.pct(r.valid):>11.1f}% ({r.pct(r.prefix_ok):.0f}%)"

    for name, narrow, wide in rows:
        print(f"{name:<34} {cell(narrow):>20} {cell(wide):>20}")

    # Deltas between consecutive runs.
    print("-" * 78)
    labels = ["EOS-bug impact (0 -> 1)", "new-data gain (1 -> 2)"]
    for i in range(len(rows) - 1):
        (_, n0, w0), (_, n1, w1) = rows[i], rows[i + 1]
        lab = labels[i] if i < len(labels) else f"{i} -> {i+1}"

        def delta(a: Run | None, b: Run | None) -> str:
            if a is None or b is None:
                return f"{'—':>20}"
            d = b.pct(b.valid) - a.pct(a.valid)
            return f"{d:>+18.1f}pp"

        print(f"{lab:<34} {delta(n0, n1):>20} {delta(w0, w1):>20}")


def print_by_size(rows: list[tuple[str, Run | None, Run | None]]) -> None:
    """Wide eval breakdown by graph size bucket."""
    wides = [(name, w) for name, _, w in rows if w is not None]
    if not wides:
        return
    buckets = [(4, 7), (8, 11), (12, 15), (16, 19), (20, 24)]
    w = 30 + 12 * len(buckets)
    print("\n" + "=" * w)
    print("WIDE EVAL BY GRAPH SIZE: valid %")
    print("(legacy eval.jsonl covers 6..14 only)")
    print("=" * w)
    head = "".join(f"{f'{lo}..{hi}':>12}" for lo, hi in buckets)
    print(f"{'run':<30}{head}")
    print("-" * w)
    for name, run in wides:
        cells = ""
        for lo, hi in buckets:
            vals = [v for n, vs in run.by_n.items() if lo <= n <= hi for v in vs]
            cells += f"{'—':>12}" if not vals else \
                f"{100.0 * sum(vals) / len(vals):>11.0f}%"
        print(f"{name:<30}{cells}")
    print(f"{'(examples per bucket)':<30}" + "".join(
        f"{sum(1 for n, vs in wides[0][1].by_n.items() if lo <= n <= hi for _ in vs):>12}"
        for lo, hi in buckets))


# Default run names from RUNBOOK_EOS.md.
DEFAULT_RUNS = [
    ("0. baseline adapter (no EOS)", "base_eval.jsonl", "base_eval_wide.jsonl"),
    ("1. + EOS, old data", "eos_eval.jsonl", "eos_eval_wide.jsonl"),
    ("2. + EOS, merged data", "merged_eval.jsonl", "merged_eval_wide.jsonl"),
]


def build_rows(specs: list[tuple[str, Path | None, Path | None]], reclassify: bool
              ) -> tuple[list[tuple[str, Run | None, Run | None]], list[str]]:
    """Load dumps from specs while printing per-dump error breakdowns."""
    rows: list[tuple[str, Run | None, Run | None]] = []
    missing: list[str] = []
    for name, narrow, wide in specs:
        r_n = Run(narrow, reclassify) if narrow and narrow.exists() else None
        r_w = Run(wide, reclassify) if wide and wide.exists() else None
        if r_n is None and r_w is None:
            missing.append(name)
            continue
        rows.append((name, r_n, r_w))
        if r_n:
            print_composition(name + "  [eval 6..14]", r_n)
        if r_w:
            print_composition(name + "  [eval_wide 4..24]", r_w)
    return rows, missing


def report(specs: list[tuple[str, Path | None, Path | None]], reclassify: bool = True) -> bool:
    """Aggregate dumps into comparison tables with deltas (True if any found)."""
    rows, missing = build_rows(specs, reclassify)
    if not rows:
        return False

    print_matrix(rows)
    print_by_size(rows)

    if missing:
        print(f"\nnot yet run: {', '.join(missing)}")
    if reclassify:
        print("\nLabels were reclassified with current classify() — raw dump labels "
              "would skew comparison (see docstring).")
    return True


def default_specs(checkpoints_dir: Path) -> list[tuple[str, Path | None, Path | None]]:
    """Default dump specs matching RUNBOOK_EOS.md filenames."""
    specs = []
    for name, narrow, wide in DEFAULT_RUNS:
        p, w = checkpoints_dir / narrow, checkpoints_dir / wide
        specs.append((name, p if p.exists() else None, w if w.exists() else None))
    return specs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", action="append", nargs="+", metavar=("NAME DUMP"),
                    help="NAME eval_dump [eval_wide_dump]; repeatable")
    ap.add_argument("--dir", type=Path, default=Path("training/checkpoints"),
                    help="directory to search for dumps when --run is omitted")
    ap.add_argument("--as-dumped", action="store_true",
                    help="keep raw dump labels without reclassifying "
                         "(warning: legacy dumps conflate tail with hallucination)")
    args = ap.parse_args(argv)

    reclassify = not args.as_dumped
    specs: list[tuple[str, Path | None, Path | None]] = []

    if args.run:
        for item in args.run:
            if len(item) < 2:
                print(f"--run requires at least NAME and one dump: {item}", file=sys.stderr)
                return 1
            name, narrow, *rest = item
            specs.append((name, Path(narrow), Path(rest[0]) if rest else None))
    else:
        specs = default_specs(args.dir)

    if not report(specs, reclassify):
        print(f"no dumps found in {args.dir}. Download them from Kaggle "
              f"(validate_kaggle.py --dump) or pass paths via --run.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
