"""Label which portfolio group is needed per DAG (best makespan per group).

Groups ordered cheapest to most expensive: greedy, prio, defer, hold, rule, beam.
Usage:
    python3 tools/portfolio_labels.py train_hard.jsonl ... --out labels/
"""

from __future__ import annotations

import argparse
import json
import sys
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vliw.core.baseline import GreedyListScheduler, list_schedule  # noqa: E402
from vliw.core.dag import compute_metrics  # noqa: E402
from vliw.core.model import get_profile  # noqa: E402
from vliw.tiny.features import build_dag, parse_graph_entries  # noqa: E402
from vliw.tiny.scheduler import TinyScheduler  # noqa: E402

ГРУППЫ = ("greedy", "prio", "defer", "hold", "rule", "beam")

_T = None
_MODEL = None


def _init() -> None:
    global _T, _MODEL
    _T = TinyScheduler()
    _MODEL = get_profile("e2k-v6-measured")


def группы_графа(dag, T=None, model=None) -> dict:
    """{group: best makespan or None if group is unavailable}."""
    T = T or _T
    model = model or _MODEL
    out: dict = {g: None for g in ГРУППЫ}

    def take(g: str, sched) -> None:
        if not sched.validate() and sched.complete:
            if out[g] is None or sched.makespan < out[g]:
                out[g] = sched.makespan

    metrics = compute_metrics(dag, model)
    base = GreedyListScheduler().schedule(dag, model)
    out["greedy"] = base.schedule.makespan
    lim = base.schedule.makespan
    prio = T.priority(dag, model)
    mh = max(metrics.height) if len(dag) else 1
    height_c = [float(h) / mh for h in metrics.height]
    if T.tiny is not None:
        s, _ = list_schedule(dag, model, priority=prio, height=metrics.height, collect_trace=False)
        take("prio", s)
        defer = T.defer_until(dag, model, lim)
        if defer:
            s, _ = list_schedule(dag, model, priority=prio, defer_until=defer,
                                 height=metrics.height, collect_trace=False)
            take("defer", s)
        hold = T.hold_until(dag, model, lim)
        if hold:
            s, _ = list_schedule(dag, model, priority=prio, defer_until=hold,
                                 height=metrics.height, collect_trace=False)
            take("hold", s)
            for hd in T._beam_holds(hold, len(dag), T.beam, 3000, lim):
                s, _ = list_schedule(dag, model, priority=prio, defer_until=hd,
                                     height=metrics.height, collect_trace=False)
                take("beam", s)
        for holds in (T.rule_holds(dag, model, lim), T.rule_holds_far(dag, model, lim)):
            if holds:
                s, _ = list_schedule(dag, model, priority=prio, defer_until=holds,
                                     height=metrics.height, collect_trace=False)
                take("rule", s)
        for bp in T._beam_orders(prio, T.beam, 2000):
            s, _ = list_schedule(dag, model, priority=bp, height=metrics.height, collect_trace=False)
            take("beam", s)
    for bp in T._beam_orders(height_c, T.beam, 1000):
        s, _ = list_schedule(dag, model, priority=bp, height=metrics.height, collect_trace=False)
        take("beam", s)
    return out


def строка(arg):
    key, prompt = arg
    dag = build_dag(parse_graph_entries(prompt))
    g = группы_графа(dag)
    best = min(v for v in g.values() if v is not None)
    ответы = [k for k in ГРУППЫ if g[k] == best]
    return {"key": key, "n": len(dag), "prompt": prompt, "best": best,
            "by_group": g, "answers": ответы, "cheapest": ответы[0]}


def main() -> int:
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(errors="replace")
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser(description="Portfolio group labels")
    ap.add_argument("inputs", nargs="+", help=".jsonl files containing a prompt field")
    ap.add_argument("--out", default="labels")
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--exclude", default="",
                    help="comma-separated .jsonl files whose prompts to exclude (eval sets)")
    ap.add_argument("--unique", action="store_true", help="deduplicate prompts within each file")
    a = ap.parse_args()
    запрещено: set = set()
    for name in [x.strip() for x in a.exclude.split(",") if x.strip()]:
        q = Path(name)
        запрещено.update(json.loads(x)["prompt"] for x in q.read_text(encoding="utf-8").splitlines() if x.strip())
    out_dir = Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in a.inputs:
        p = Path(name)
        rows = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
        if запрещено:
            rows = [r for r in rows if r["prompt"] not in запрещено]
        if a.unique:
            seen: set = set()
            rows = [r for r in rows if not (r["prompt"] in seen or seen.add(r["prompt"]))]
        if a.limit:
            rows = rows[:a.limit]
        args = [(f"{p.stem}#{i}", r["prompt"]) for i, r in enumerate(rows)]
        with Pool(a.jobs, initializer=_init) as pool:
            res = pool.map(строка, args, chunksize=8)
        dst = out_dir / (p.stem + ".labels.jsonl")
        with open(dst, "w", encoding="utf-8") as f:
            for r in res:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        from collections import Counter
        c = Counter(r["cheapest"] for r in res)
        print(f"{p.name}: {len(res)} graphs -> {dst}; cheapest group: {dict(c)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
