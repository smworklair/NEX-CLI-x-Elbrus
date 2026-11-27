"""Measure MLP top-1/top-2 score gap vs prio-path outcome on eval_hard.

Usage:
    .venv/bin/python tools/tiny_gap.py [limit]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vliw.core.baseline import GreedyListScheduler  # noqa: E402
from vliw.core.model import get_profile  # noqa: E402
from vliw.tiny.features import build_dag, parse_graph_entries  # noqa: E402
from vliw.tiny.scheduler import TinyScheduler  # noqa: E402


def main() -> None:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    prof = get_profile("e2k-v6-measured")
    base = GreedyListScheduler()
    sched = TinyScheduler(beam=0)  # learned path without beam: prio + prio_defer
    if sched.tiny is None:
        print("priority weights missing — nothing to measure")
        raise SystemExit(1)
    lines = open(ROOT / "eval_hard.jsonl", encoding="utf-8").readlines()
    if limit:
        lines = lines[:limit]
    rows = []
    for line in lines:
        ex = json.loads(line)
        dag = build_dag(parse_graph_entries(ex["prompt"]))
        scores = sorted(sched.priority(dag, prof), reverse=True)
        gap = scores[0] - scores[1] if len(scores) > 1 else 0.0
        b = base.schedule(dag, prof).schedule.makespan
        res = sched.schedule(dag, prof)
        t = res.schedule.makespan
        rows.append((gap, "win" if t < b else ("tie" if t == b else "loss")))
    rows.sort()
    n = len(rows)
    wins = sum(1 for _, o in rows if o == "win")
    print(f"n={n} prio wins: {wins} ({wins / max(n, 1):.0%})")
    print(f"{'gap_thr':>10} {'n<thr':>8} {'wins':>7} {'rate':>6}  note")
    for thr in (0.01, 0.02, 0.05, 0.1, 0.2):
        sub = [o for g, o in rows if g < thr]
        w = sum(1 for o in sub if o == "win")
        print(f"{thr:>10} {len(sub):>8} {w:>7} {w / max(len(sub), 1):>5.0%}  "
              f"{'small gap -> prio loses more often?' if w / max(len(sub), 1) < wins / n else ''}")
    los = [(g, o) for g, o in rows if o == "loss"]
    print(f"losses (worse than baseline): {len(los)} (filtered out by portfolio min)")


if __name__ == "__main__":
    main()
