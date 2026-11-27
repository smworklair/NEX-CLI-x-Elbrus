"""Tiny-1 evaluation: valid% / gap to optimum / wins over baseline.

Ground truth comes from eval file meta (makespan=proven CP-SAT optimum,
baseline=greedy), so no oracle rerun is needed. Tiny schedules are checked
with the real Schedule.validate().
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from vliw.core.baseline import GreedyListScheduler
from vliw.core.model import get_profile
from vliw.tiny.features import build_dag, parse_graph_entries
from vliw.tiny.scheduler import TinyScheduler


def main() -> None:
    ap = argparse.ArgumentParser(description="Tiny-1 evaluation")
    ap.add_argument("--eval", default="eval_hard.jsonl")
    ap.add_argument("--weights", default="vliw/tiny/weights.json")
    ap.add_argument("--defer-weights", default="vliw/tiny/weights_defer.json")
    ap.add_argument("--hold-weights", default="vliw/tiny/weights_hold.json")
    ap.add_argument("--limit", type=int, default=0, help="0 = all")
    ap.add_argument("--beam", type=int, default=16,
                    help="beam width (defaults to /tiny setting)")
    ap.add_argument("--ignore-weights", action="store_true",
                    help="without trained weights: greedy + beam around "
                         "height only (pure search — for ablation)")
    a = ap.parse_args()
    ev = a.eval if Path(a.eval).exists() else str(_ROOT / a.eval)
    def _rp(p: str) -> str:
        return p if Path(p).is_absolute() or Path(p).exists() \
            else str(_ROOT / p)
    prof = get_profile("e2k-v6-measured")
    if a.ignore_weights:
        sched = TinyScheduler(weights="/nonexistent/weights.json",
                              defer_weights="/nonexistent/defer.json",
                              beam=a.beam)
    else:
        sched = TinyScheduler(_rp(a.weights),
                              defer_weights=_rp(a.defer_weights),
                              hold_weights=_rp(a.hold_weights),
                              beam=a.beam)
    base = GreedyListScheduler()
    n = valid = opt = beat = 0
    gap_tiny = gap_base = 0
    with open(ev, encoding="utf-8") as f:
        lines = f.readlines()
    if a.limit:
        lines = lines[:a.limit]
    for line in lines:
        ex = json.loads(line)
        dag = build_dag(parse_graph_entries(ex["prompt"]))
        optimum = ex["meta"]["makespan"]
        res = sched.schedule(dag, prof)
        errs = res.schedule.validate()
        b = base.schedule(dag, prof).schedule.makespan
        t = res.schedule.makespan
        n += 1
        gap_tiny += t - optimum
        gap_base += b - optimum
        if not errs and res.schedule.complete:
            valid += 1
        if t == optimum:
            opt += 1
        if t < b:
            beat += 1
    print(f"n={n} valid={valid}/{n} ({100.0 * valid / max(n, 1):.1f}%)")
    print(f"avg_gap tiny={gap_tiny / max(n, 1):.3f} baseline={gap_base / max(n, 1):.3f}")
    print(f"optimal tiny={opt}/{n} beat_baseline={beat}/{n}")


if __name__ == "__main__":
    main()
