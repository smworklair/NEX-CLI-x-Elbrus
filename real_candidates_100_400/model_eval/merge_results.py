"""Слить слои в results.json + decode.json + таблицу задачи D.

L0/L1/L2-fixed: layers/fixed.json. L2-fair: layers/fair.<g>.json.
L3/decode/order: layers/l3.json (+ сырой ответ перечитывается здесь же
для блока raw: размещено/законность/полнота/makespan).
best_known: search/best_known.json.
v1: только 13 целей (контроль допишется позже тем же скриптом).
"""
import json
import pathlib
import sys

sys.path.insert(0, "/home/shokha/vliw-ai-scheduler-demo")
from vliw.core import asm_parser
from vliw.core.dag import compute_metrics
from vliw.core.model import get_profile, DEFAULT_PROFILE
from vliw.core.schedule import Schedule
from training.encode import decode_completion, clip_placements

BASE = "/home/shokha/vliw-ai-scheduler-demo/real_candidates_100_400"
ME = BASE + "/model_eval"
model = get_profile(DEFAULT_PROFILE)
manifest = {m["name"]: m for m in json.loads(open(BASE + "/manifest.json").read())}
fixed = json.load(open(ME + "/layers/fixed.json"))
l3 = json.load(open(ME + "/layers/l3.json"))
try:
    best_known = json.load(open(BASE + "/search/best_known.json"))
except OSError:
    best_known = {}
targets = [m["name"] for m in json.loads(open(BASE + "/manifest.json").read())
           if m["gap"] > 0]

results, decode = {}, {}
for name in targets:
    f = fixed[name]
    fair = json.load(open(f"{ME}/layers/fair.{name}.json"))
    r = l3[name]
    d = r["decode"]
    decode[name] = {"nodes": r["nodes"], **d}
    d = r["decode"]
    decode[name] = {"nodes": r["nodes"], **d}
    w = r["winner"]
    wms = r["winner_ms"]
    l2b = f["L2_1000"]
    # raw-блок: честный пересчёт из сохранённого текста (без модели)
    raw = open(f"{ME}/raw/{name}.txt", encoding="utf-8").read()
    res = asm_parser.parse_asm(open(f"{BASE}/asm/{name}.s").read(),
                               source=name)
    dag = asm_parser.build_dag(res, key=name, title=name)
    decoded = decode_completion(raw)
    keep, _ = clip_placements(decoded, len(dag))
    sched = Schedule(dag, model)
    for i, (cycle, channel) in sorted(keep.items()):
        sched.place(i, cycle, channel)
    errs = sched.validate()
    raw_block = {"placed": len(keep), "legal_errs": len(errs),
                 "complete": sched.complete,
                 "makespan": (sched.makespan
                              if sched.complete and not errs else None)}
    results[name] = {
        "nodes": r["nodes"], "greedy_L0": r["greedy"],
        "lower_bound": r["lower_bound"],
        "L1_rule": r["L1_rule_ms"],
        "L2_10": f["L2_10"], "L2_100": f["L2_100"], "L2_1000": l2b,
        "L2_1000_winner": f["L2_winners"].get("1000"),
        "L2_winners": f["L2_winners"],
        "L2_fair": {"T_gen_s": fair["T_gen_s"],
                    "attempts_done": fair["attempts_done"],
                    "t_eval_median_s": fair["t_eval_median_s"],
                    "best_ms": fair["best_ms"], "seed": fair["seed"],
                    "winner": fair["winner"]},
        "L3_portfolio_winner": w, "L3_ms": wms,
        "model_beats_L2_1000": (wms is not None and wms < l2b),
        "model_beats_L2_fair": (wms is not None
                                and wms < fair["best_ms"]),
        "order_ms": r["order_ms"], "order_coverage": r["order_coverage"],
        "gen_s": r["gen_s"], "prompt_tokens": r["prompt_tokens"],
        "out_tokens": r["out_tokens"],
        "best_known_search": best_known.get(name, {}).get("best_known"),
    }
    # raw stats from l3.json replay
    results[name]["raw"] = raw_block
json.dump(results, open(ME + "/results.json", "w"),
          ensure_ascii=False, indent=1)
json.dump(decode, open(ME + "/decode.json", "w"),
          ensure_ascii=False, indent=1)
print("graphs:", len(results))
for name in targets:
    r = results[name]
    print(f"{name:20s} L0={r['greedy_L0']:4d} L1={r['L1_rule']:4d} "
          f"L2={r['L2_10']}/{r['L2_100']}/{r['L2_1000']} "
          f"fair={r['L2_fair']['best_ms']} L3={r['L3_ms']}({r['L3_portfolio_winner']}) "
          f"order={r['order_ms']}@{r['order_coverage']:.2f}")
