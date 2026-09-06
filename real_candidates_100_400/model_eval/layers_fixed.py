"""Слои L0/L1/L2-fixed(N=10,100,1000) на 25 графах. Без модели, быстро.

L0: жадный (priority=height). L1: rule/rule.py с финальными параметрами
чемпиона из rule/validation.json. L2: свежий S1-шум (сиды 500001+i, сетка
амплитуд как в поиске), лучшее из первых N; векторы победителей — в выход
(для перепроверки VERIFY). Выход: layers/fixed.json (один файл).
"""
import importlib.util
import json
import pathlib
import random
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

spec = importlib.util.spec_from_file_location(
    "rule_under_test", BASE + "/rule/rule.py")
rule_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rule_mod)

model = get_profile(DEFAULT_PROFILE)
manifest = {m["name"]: m for m in json.loads(open(BASE + "/manifest.json").read())}
val = json.load(open(BASE + "/rule/validation.json"))
final_params = val["families"][val["champion"]]["final_params"]
try:
    best_known = json.load(open(BASE + "/search/best_known.json"))
except OSError:
    best_known = {}

order = ([m["name"] for m in json.loads(open(BASE + "/manifest.json").read())
          if m["gap"] > 0]
         + [m["name"] for m in json.loads(open(BASE + "/manifest.json").read())
            if m["gap"] == 0])

out = {}
t_all = time.monotonic()
for idx, name in enumerate(order):
    m = manifest[name]
    res = asm_parser.parse_asm(open(f"{BASE}/asm/{name}.s").read(), source=name)
    dag = asm_parser.build_dag(res, key=name, title=name)
    met = compute_metrics(dag, model)
    n = len(dag)
    h = [float(x) for x in met.height]
    hmax = max(met.height)
    greedy, _ = list_schedule(dag, model, priority=list(h), height=met.height)
    assert greedy.validate() == []
    assert greedy.makespan == m["greedy_makespan"], name
    # L1
    prio_r = rule_mod.priority(dag, model, met, final_params)
    s1, _ = list_schedule(dag, model, prio_r, height=met.height)
    assert s1.validate() == [], name
    # L2 fresh S1 noise
    seed = 500001 + idx
    best = {10: greedy.makespan, 100: greedy.makespan, 1000: greedy.makespan}
    win = {}
    for s_idx in range(1000):
        rnd = random.Random(f"{seed}/S1/{s_idx}")
        amp = AMPS[s_idx % len(AMPS)] * hmax
        prio = [x + rnd.uniform(-amp, amp) for x in h]
        s, _ = list_schedule(dag, model, prio, height=met.height)
        for n_th in (10, 100, 1000):
            if s_idx < n_th and s.makespan < best[n_th]:
                best[n_th] = s.makespan
                win[n_th] = {
                    "seed": seed, "s_idx": s_idx,
                    "priority_delta": {
                        str(i): round(prio[i] - h[i], 4)
                        for i in range(n)
                        if round(prio[i] - h[i], 4) != 0},
                    "defer_until": {}}
    bk = best_known.get(name, {}).get("best_known", m["greedy_makespan"])
    out[name] = {"nodes": n, "greedy": greedy.makespan,
                 "lower_bound": met.lower_bound,
                 "L1_rule": s1.makespan,
                 "L2_10": best[10], "L2_100": best[100],
                 "L2_1000": best[1000], "L2_winners": win,
                 "best_known_search": bk}
    print(f"{name:20s} L0={greedy.makespan:4d} L1={s1.makespan:4d} "
          f"L2={best[10]}/{best[100]}/{best[1000]} best_known={bk}",
          flush=True)
pathlib.Path(ME + "/layers").mkdir(parents=True, exist_ok=True)
json.dump(out, open(ME + "/layers/fixed.json", "w"),
          ensure_ascii=False, indent=1)
print(f"TOTAL {time.monotonic() - t_all:.0f}s")
