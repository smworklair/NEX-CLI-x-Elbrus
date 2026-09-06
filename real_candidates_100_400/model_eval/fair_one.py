"""L2-fair: S1-шум вокруг height, seed 510001+i, бюджет = T(g) генерации.

Детерминировано всё, кроме wall-clock: попытка s_idx полностью задана
(seed, s_idx); останавливаемся, когда часы перевалили за T(g).
Пишем: attempts_done, t_eval_median, best_ms, winner-вектор.
Выход: layers/fair.<graph>.json (part-файл для чанков).
"""
import argparse
import json
import pathlib
import random
import statistics
import sys
import time

sys.path.insert(0, "/home/shokha/vliw-ai-scheduler-demo")
from vliw.core import asm_parser
from vliw.core.dag import compute_metrics
from vliw.core.baseline import list_schedule
from vliw.core.model import get_profile, DEFAULT_PROFILE

BASE = "/home/shokha/vliw-ai-scheduler-demo/real_candidates_100_400"
ME = BASE + "/model_eval"
AMPS = (0.05, 0.15, 0.4, 1.0)


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--name", required=True)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--out", required=True)
    return p.parse_args()


def main():
    a = parse_args()
    model = get_profile(DEFAULT_PROFILE)
    res = asm_parser.parse_asm(open(f"{BASE}/asm/{a.name}.s").read(),
                               source=a.name)
    dag = asm_parser.build_dag(res, key=a.name, title=a.name)
    met = compute_metrics(dag, model)
    n = len(dag)
    h = [float(x) for x in met.height]
    hmax = max(met.height)
    greedy, _ = list_schedule(dag, model, priority=list(h),
                             height=met.height)
    assert greedy.validate() == []
    meta = json.load(open(f"{ME}/raw/{a.name}.meta.json"))
    budget = float(meta["gen_s"])
    t_end = time.monotonic() + budget
    best = greedy.makespan
    win = None
    s_idx = 0
    dt = []
    while time.monotonic() < t_end:
        rnd = random.Random(f"{a.seed}/S1/{s_idx}")
        amp = AMPS[s_idx % len(AMPS)] * hmax
        prio = [x + rnd.uniform(-amp, amp) for x in h]
        t0 = time.monotonic()
        s, _ = list_schedule(dag, model, prio, height=met.height)
        dt.append(time.monotonic() - t0)
        if s.makespan < best:
            best = s.makespan
            win = {"seed": a.seed, "s_idx": s_idx,
                   "priority_delta": {
                       str(i): round(prio[i] - h[i], 4) for i in range(n)
                       if round(prio[i] - h[i], 4) != 0},
                   "defer_until": {}}
        s_idx += 1
    t_med = statistics.median(dt) if dt else 0.0
    out = {"graph": a.name, "seed": a.seed, "T_gen_s": budget,
           "attempts_done": s_idx, "t_eval_median_s": t_med,
           "best_ms": best, "gain_vs_greedy": greedy.makespan - best,
           "winner": win, "greedy": greedy.makespan}
    pathlib.Path(a.out).write_text(json.dumps(out, ensure_ascii=False))
    print(f"[{a.name}] T={budget:.0f}s attempts={s_idx} "
          f"best={best} (greedy {greedy.makespan})", flush=True)


if __name__ == "__main__":
    main()
