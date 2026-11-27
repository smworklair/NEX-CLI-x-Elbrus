"""Per-basic-block report on real lcc `.s` files (all cycles in machine-model units).

Usage:
    python3 tools/block_report.py
    python3 tools/block_report.py real_candidates_100_400/asm/poly_gemm.s --oracle 0
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vliw.core.baseline import GreedyListScheduler  # noqa: E402
from vliw.core.blocks import BUCKETS, block_graphs_of_file  # noqa: E402
from vliw.core.dag import compute_metrics  # noqa: E402
from vliw.core.model import DEFAULT_PROFILE, get_profile  # noqa: E402
from vliw.core.oracle import OracleScheduler  # noqa: E402
from vliw.tiny.fast import TinyFlashScheduler  # noqa: E402

BUCKET_NAMES = [b for b, _ in BUCKETS]


def collect(paths: list[Path], model, min_ops: int, mode: str, oracle_s: float):
    base = GreedyListScheduler()
    tiny = TinyFlashScheduler(mode=mode, with_trace=False)
    rows = []
    for p in paths:
        for g in block_graphs_of_file(p):
            n = g.n
            row = {"file": p.stem, "block": g.block.index, "label": g.block.label, "n": n,
                   "bundles": g.block.bundles, "loop": g.block.loop, "bucket": g.bucket,
                   "lcc": None, "lcc_why": "", "base": None, "tiny": None, "oracle": None,
                   "proved": None, "lb": None, "hit": None,
                   "t_base_ms": None, "t_tiny_ms": None, "t_oracle_ms": None}
            lcc, why = g.lcc_schedule(model)
            row["lcc"] = lcc.makespan if lcc is not None else None
            row["lcc_why"] = why[0] if why else ""
            t0 = time.perf_counter()
            row["base"] = base.schedule(g.dag, model).schedule.makespan
            row["t_base_ms"] = 1000 * (time.perf_counter() - t0)
            row["lb"] = compute_metrics(g.dag, model).lower_bound
            if n >= min_ops:
                t0 = time.perf_counter()
                res = tiny.schedule(g.dag, model)
                row["t_tiny_ms"] = 1000 * (time.perf_counter() - t0)
                row["tiny"] = res.schedule.makespan
                row["hit"] = res.search_stats.get("bound_hit_at")
                if oracle_s > 0:
                    t0 = time.perf_counter()
                    ro = OracleScheduler(budget_s=oracle_s,
                                         portfolio_s=max(oracle_s / 3.0, 0.02)).schedule(g.dag, model)
                    row["t_oracle_ms"] = 1000 * (time.perf_counter() - t0)
                    row["oracle"] = ro.schedule.makespan
                    row["proved"] = bool(ro.optimal)
            rows.append(row)
    return rows


def best(r) -> int:
    return min(v for v in (r["base"], r["tiny"], r["oracle"]) if v is not None)


def report(rows, min_ops: int, oracle_s: float, top: int, mode: str) -> None:
    tot_ops = sum(r["n"] for r in rows)
    loop_ops = sum(r["n"] for r in rows if r["loop"])
    print(f"[1] blocks {len(rows)}, ops {tot_ops}; in loop_mode blocks "
          f"{sum(1 for r in rows if r['loop'])} blocks, {loop_ops} ops "
          f"({100 * loop_ops / max(tot_ops, 1):.0f} %)")
    print(f"    {'bucket':9}{'blocks':>8}{'ops':>10}")
    for bk in BUCKET_NAMES:
        rs = [r for r in rows if r["bucket"] == bk]
        print(f"    {bk:9}{len(rs):>8}{sum(r['n'] for r in rs):>10}")

    big = [r for r in rows if r["n"] >= min_ops]
    print(f"\n[2] blocks n >= {min_ops}: greedy -> tiny[{mode}]"
          + (f" -> oracle {oracle_s:g} s" if oracle_s > 0 else "") + " (model cycles)")
    head = f"    {'kind':9}{'bucket':9}{'blocks':>7}{'ops':>7}{'greedy':>8}{'tiny':>8}"
    if oracle_s > 0:
        head += f"{'oracle':>8}"
    head += f"{'best':>8}{'gain %':>10}{'improved':>9}"
    if oracle_s > 0:
        head += f"{'proven':>9}"
    print(head)
    for kind in ("linear", "loops"):
        for bk in BUCKET_NAMES:
            rs = [r for r in big if r["bucket"] == bk and r["loop"] == (kind == "loops")]
            if not rs:
                continue
            sb = sum(r["base"] for r in rs)
            st = sum(r["tiny"] for r in rs)
            sbest = sum(best(r) for r in rs)
            imp = sum(1 for r in rs if best(r) < r["base"])
            line = (f"    {kind:9}{bk:9}{len(rs):>7}{sum(r['n'] for r in rs):>7}{sb:>8}{st:>8}")
            if oracle_s > 0:
                line += f"{sum(r['oracle'] for r in rs):>8}"
            line += f"{sbest:>8}{100 * (sb - sbest) / sb:>10.1f}{imp:>9}"
            if oracle_s > 0:
                line += f"{sum(1 for r in rs if r['proved']):>9}"
            print(line)
    if big:
        sb = sum(r["base"] for r in big)
        sbest = sum(best(r) for r in big)
        print(f"    TOTAL n >= {min_ops}: blocks {len(big)}, greedy {sb}, best {sbest}, "
              f"gain {100 * (sb - sbest) / sb:.1f} %, improved blocks "
              f"{sum(1 for r in big if best(r) < r['base'])}"
              + (f", proven optimal in {sum(1 for r in big if r['proved'])}" if oracle_s > 0 else ""))

        print(f"\n[3] blocks n >= {min_ops} where lcc schedule was reconstructed and validated")
        rl = [r for r in big if r["lcc"] is not None]
        print(f"    reconstructed {len(rl)} of {len(big)}; loops among them: {sum(1 for r in rl if r['loop'])}")
        if rl:
            sl = sum(r["lcc"] for r in rl)
            sbest = sum(best(r) for r in rl)
            print(f"    sum lcc {sl}, best {sbest}: lcc / best = {sl / sbest:.2f}x")
            for kind in ("linear", "loops"):
                rr = [r for r in rl if r["loop"] == (kind == "loops")]
                if rr:
                    sl2 = sum(r["lcc"] for r in rr)
                    sb2 = sum(best(r) for r in rr)
                    print(f"      {kind}: blocks {len(rr)}, lcc {sl2}, best {sb2}, {sl2 / sb2:.2f}x")
        why = Counter(r["lcc_why"] for r in big if r["lcc"] is None)
        if why:
            print("    not reconstructed:", dict(why))

        print(f"\n[4] where makespan lower bound was reached (tiny[{mode}], blocks n >= {min_ops})")
        hit = Counter(str(r["hit"]) for r in big)
        for k, v in hit.most_common():
            what = {"greedy": "greedy already at lower bound — optimal proven without search",
                    "None": "lower bound not reached (optimality not proven by bound)"}.get(
                        k, "proven after searching this group")
            print(f"    {k:8}{v:>5}  ({100 * v / len(big):.0f} %)  {what}")
        gap = [r["tiny"] - r["lb"] for r in big if r["hit"] is None]
        if gap:
            print(f"    among blocks above lower bound: mean (best - bound) gap is "
                  f"{sum(gap) / len(gap):.1f} cycles (bound not always tight)")

        print("\n[5] mean time per block, ms")
        tb = [r["t_base_ms"] for r in big]
        tt = [r["t_tiny_ms"] for r in big]
        print(f"    greedy {sum(tb) / len(tb):.2f}   tiny[{mode}] {sum(tt) / len(tt):.2f}", end="")
        if oracle_s > 0:
            to = [r["t_oracle_ms"] for r in big]
            print(f"   oracle {sum(to) / len(to):.1f}", end="")
        print()

    print(f"\n[6] {top} largest blocks")
    print(f"    {'block':24}{'kind':8}{'n':>5}{'wi':>5}{'lcc':>6}{'greedy':>8}{'tiny':>8}"
          f"{'oracle':>8}{'lb':>8}")
    for r in sorted(rows, key=lambda r: -r["n"])[:top]:
        print(f"    {r['file'] + '#' + str(r['block']):24}{'loop' if r['loop'] else 'linear':8}{r['n']:>5}"
              f"{r['bundles']:>5}{str(r['lcc']):>6}{r['base']:>8}{str(r['tiny']):>8}"
              f"{str(r['oracle']):>8}{r['lb']:>8}")


def main() -> int:
    # Avoid UnicodeEncodeError on narrow Windows console encodings
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(errors="replace")
        except Exception:  # noqa: BLE001 — stream replaced (tests/redirect)
            pass
    ap = argparse.ArgumentParser(description="Basic-block report for real lcc .s files")
    ap.add_argument("files", nargs="*", help=".s files (default: all in --dir)")
    ap.add_argument("--dir", default=str(ROOT / "real_candidates_100_400" / "asm"))
    ap.add_argument("--min-ops", type=int, default=10, help="skip blocks shorter than this")
    ap.add_argument("--profile", default=DEFAULT_PROFILE)
    ap.add_argument("--mode", choices=("exact", "asm"), default="exact",
                    help="exact: full portfolio parity; asm: skip hold/defer (see docs/archive/TINY_FAST.md)")
    ap.add_argument("--oracle", type=float, default=3.0, help="exact search budget per block, s (0 = disable)")
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--json", help="write per-block rows to JSON")
    a = ap.parse_args()

    paths = [Path(f) for f in a.files] or sorted(Path(a.dir).glob("*.s"))
    if not paths:
        print("no .s files found", file=sys.stderr)
        return 2
    model = get_profile(a.profile)
    t0 = time.time()
    rows = collect(paths, model, a.min_ops, a.mode, a.oracle)
    print(f"files {len(paths)}, blocks {len(rows)}, profile {a.profile}, "
          f"elapsed {time.time() - t0:.0f} s\n")
    report(rows, a.min_ops, a.oracle, a.top, a.mode)
    if a.json:
        Path(a.json).write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\nper-block rows saved: {a.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
