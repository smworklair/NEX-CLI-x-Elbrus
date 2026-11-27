"""Evaluate Tiny vs baseline on 13 real assembly graphs from model_eval/REPORT.md.

Usage:
    .venv/bin/python tools/tiny_real_eval.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vliw.core import asm_parser  # noqa: E402
from vliw.core.baseline import GreedyListScheduler  # noqa: E402
from vliw.core.model import get_profile  # noqa: E402
from vliw.tiny.scheduler import TinyScheduler  # noqa: E402

# 13 target graphs from real_candidates_100_400/model_eval/REPORT.md (Task B)
# matching asm/<name>.s filenames.
TARGETS = ["poly_covariance", "poly_gemm", "tsvc_s1111", "poly_adi",
           "poly_gesummv", "emb_iir", "poly_floyd_int", "poly_heat3d",
           "poly_gramschmidt", "poly_fdtd", "emb_fir", "poly_jacobi2d",
           "poly_symm"]


def main() -> None:
    prof = get_profile("e2k-v6-measured")
    base = GreedyListScheduler()
    tiny = TinyScheduler()
    print(f"{'graph':16} {'n':>4} {'base':>5} {'tiny':>5} "
          f"{'winner':>10} {'valid':>8} {'time':>8}")
    wins = ties = bad = 0
    for name in TARGETS:
        p = ROOT / "real_candidates_100_400" / "asm" / (name + ".s")
        if not p.exists():
            print(f"{name:16} MISSING FILE")
            bad += 1
            continue
        dag = asm_parser.build_dag(
            asm_parser.parse_asm(p.read_text(encoding="utf-8")),
            key=name, title=name)
        b = base.schedule(dag, prof).schedule.makespan
        t0 = time.monotonic()
        res = tiny.schedule(dag, prof)
        dt = time.monotonic() - t0
        legal = not res.schedule.validate() and res.schedule.complete
        t = res.schedule.makespan
        w = res.search_stats.get("tiny_winner", "?")
        if not legal:
            mark = "INVALID"
            bad += 1
        elif t < b:
            mark = "tiny"
            wins += 1
        elif t == b:
            mark = "tie"
            ties += 1
        else:  # never worse than baseline by construction — seeing this is a bug
            mark = "baseline?!"
            bad += 1
        print(f"{name:16} {len(dag):>4} {b:>5} {t:>5} {w:>10} "
              f"{str(legal):>8} {dt:>7.1f}s  {mark}")
    print(f"summary: tiny wins {wins}/{len(TARGETS)}, ties {ties}, "
          f"losses/invalid {bad}")
    if bad:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
