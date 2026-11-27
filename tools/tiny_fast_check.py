"""Verify TinyFlashScheduler parity with TinyScheduler and measure speedup.

Usage:
    python3 tools/tiny_fast_check.py
    python3 tools/tiny_fast_check.py --set eval_hard --limit 100
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vliw.core.baseline import GreedyListScheduler  # noqa: E402
from vliw.core.blocks import block_graphs_of_file, window_graphs  # noqa: E402
from vliw.core.model import get_profile  # noqa: E402
from vliw.tiny import fast  # noqa: E402
from vliw.tiny.features import build_dag, parse_graph_entries  # noqa: E402
from vliw.tiny.scheduler import TinyScheduler  # noqa: E402


def load_jsonl(name: str, limit: int):
    p = Path(name)
    if not p.exists():
        p = ROOT / (name if name.endswith(".jsonl") else name + ".jsonl")
    out = []
    with open(p, encoding="utf-8") as f:
        lines = f.readlines()
    if limit:
        lines = lines[:limit]
    for i, line in enumerate(lines):
        ex = json.loads(line)
        dag = build_dag(parse_graph_entries(ex["prompt"]))
        out.append((p.stem, p.stem, f"{p.stem}#{i}", dag, ex.get("meta", {}).get("makespan")))
    return out


def load_real(limit: int):
    out = []
    d = ROOT / "real_candidates_100_400" / "asm"
    for p in sorted(d.glob("*.s")):
        text = p.read_text(encoding="utf-8")
        for g in block_graphs_of_file(p, min_ops=10):
            out.append(("real", "block_loop" if g.block.loop else "block", g.dag.key, g.dag, None))
        for w in window_graphs(text, source=p.name):
            out.append(("real", "window_loop" if w.loop else "window", w.dag.key, w.dag, None))
    return out[:limit] if limit else out


def main() -> int:
    # Avoid UnicodeEncodeError on narrow Windows console encodings
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(errors="replace")
        except Exception:  # noqa: BLE001 — stream replaced (tests/redirect)
            pass
    ap = argparse.ArgumentParser(description="TinyFlashScheduler vs TinyScheduler")
    ap.add_argument("--set", default="eval_hard,eval_wide,real",
                    help="comma-separated root .jsonl names and/or real")
    ap.add_argument("--limit", type=int, default=0, help="at most N graphs per set (0 = all)")
    ap.add_argument("--no-reference", action="store_true", help="skip TinyScheduler reference (timing only)")
    ap.add_argument("--json", help="write summary to JSON")
    a = ap.parse_args()

    model = get_profile("e2k-v6-measured")
    ref = None if a.no_reference else TinyScheduler()
    variants = {
        "fast exact": fast.TinyFlashScheduler(mode="exact"),
        "fast exact, no trace": fast.TinyFlashScheduler(mode="exact", with_trace=False),
        "fast exact, no numpy": fast.TinyFlashScheduler(mode="exact", use_numpy=False, with_trace=False),
        "fast exact, no early stop": fast.TinyFlashScheduler(mode="exact", stop_at_bound=False,
                                                            with_trace=False),
        "fast asm (empirical)": fast.TinyFlashScheduler(mode="asm", with_trace=False),
    }
    guaranteed = [k for k in variants if "asm" not in k]
    greedy = GreedyListScheduler()
    print(f"numpy: {'yes' if fast._np is not None else 'no (pure Python)'}; "
          f"reference: {'none' if ref is None else 'TinyScheduler'}")

    graphs = []
    for name in [s.strip() for s in a.set.split(",") if s.strip()]:
        graphs += load_real(a.limit) if name == "real" else load_jsonl(name, a.limit)

    pc = time.perf_counter
    # (set, kind) -> metrics
    T: dict = defaultdict(lambda: defaultdict(float))
    N: dict = defaultdict(int)
    SZ: dict = defaultdict(int)
    mismatch: list = []
    invalid: list = []
    t_all = pc()
    for k, (setname, kind, gid, dag, opt) in enumerate(graphs):
        key = (setname, kind)
        N[key] += 1
        SZ[key] += len(dag)
        t0 = pc()
        g_ms = greedy.schedule(dag, model).schedule.makespan
        T[key]["greedy_t"] += pc() - t0
        T[key]["greedy_ms"] += g_ms
        r_ms = None
        if ref is not None:
            t0 = pc()
            r = ref.schedule(dag, model)
            T[key]["ref_t"] += pc() - t0
            r_ms = r.schedule.makespan
            T[key]["ref_ms"] += r_ms
        for name, sc in variants.items():
            t0 = pc()
            res = sc.schedule(dag, model)
            T[key][name + "_t"] += pc() - t0
            ms = res.schedule.makespan
            T[key][name + "_ms"] += ms
            if res.schedule.validate() or not res.schedule.complete or ms > g_ms:
                invalid.append((gid, name))
            if r_ms is not None and ms != r_ms:
                T[key][name + "_diff"] += 1
                if name in guaranteed:
                    mismatch.append((gid, name, r_ms, ms))
            if opt is not None:
                T[key][name + "_opt"] += int(ms == opt)
                T[key][name + "_gap"] += ms - opt
        if opt is not None:
            T[key]["greedy_opt"] += int(g_ms == opt)
            T[key]["greedy_gap"] += g_ms - opt
            if r_ms is not None:
                T[key]["ref_opt"] += int(r_ms == opt)
                T[key]["ref_gap"] += r_ms - opt
        if (k + 1) % 250 == 0:
            print(f"  ... {k + 1}/{len(graphs)}  {pc() - t_all:.0f} s", flush=True)

    summary = {}
    for key in sorted(N):
        n, m = N[key], T[key]
        print(f"\n== {key[0]} / {key[1]}: {n} graphs, mean size {SZ[key] / n:.1f} ops")
        has_opt = any(m.get(v + "_opt") is not None and (v + "_opt") in m for v in variants)
        head = f"   {'scheduler':28}{'ms/graph':>9}{'speedup':>11}{'total cycles':>14}{'ref mismatches':>20}"
        if has_opt:
            head += f"{'optimal':>12}{'excess cyc/graph':>20}"
        print(head)
        base_t = m.get("ref_t")
        rows = [("greedy", "greedy")] + ([("TinyScheduler (ref)", "ref")] if ref is not None else []) \
            + [(k2, k2) for k2 in variants]
        summary[f"{key[0]}/{key[1]}"] = {"n": n}
        for label, tag in rows:
            t = m[tag + "_t"]
            sp = f"×{base_t / t:.1f}" if (base_t and t) else "—"
            line = f"   {label:28}{1000 * t / n:>9.2f}{sp:>11}{int(m[tag + '_ms']):>14}"
            diff = int(m.get(tag + "_diff", 0)) if (ref is not None and tag in variants) else ""
            line += f"{diff:>20}"
            if has_opt:
                line += f"{int(m.get(tag + '_opt', 0)):>9}/{n:<3}{m.get(tag + '_gap', 0) / n:>20.3f}"
            print(line)
            summary[f"{key[0]}/{key[1]}"][label] = {"ms_per_graph": 1000 * t / n, "total_makespan": m[tag + "_ms"],
                                                    "diff_vs_reference": m.get(tag + "_diff", 0)}

    print(f"\ntotal graphs {len(graphs)}, {pc() - t_all:.0f} s")
    ok = not mismatch and not invalid
    if mismatch:
        print(f"MISMATCHES vs reference in exact mode: {len(mismatch)}; first: {mismatch[:5]}")
    if invalid:
        print(f"INVALID/WORSE THAN GREEDY: {len(invalid)}; first: {invalid[:5]}")
    if ok:
        print("result: exact mode matched TinyScheduler on all graphs; all valid, none worse than greedy"
              if ref is not None else "result: all valid, none worse than greedy (reference skipped)")
    if a.json:
        Path(a.json).write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
