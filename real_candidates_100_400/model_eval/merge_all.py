"""Дописать 12 контрольных графов в results.json / decode.json.

L0/L1/L2-fixed: layers/fixed.json. L3/decode/order: layers/l3_controls.json.
best_known на контроле = greedy (зазор 0). L2-fair на контроле нет
(незачем: бюджет честности привязан к генерации, которой там нет в L-слое).
"""
import json

BASE = "/home/shokha/vliw-ai-scheduler-demo/real_candidates_100_400"
ME = BASE + "/model_eval"
manifest = {m["name"]: m for m in json.loads(open(BASE + "/manifest.json").read())}
fixed = json.load(open(ME + "/layers/fixed.json"))
l3c = json.load(open(ME + "/layers/l3_controls.json"))
results = json.load(open(ME + "/results.json"))
decode = json.load(open(ME + "/decode.json"))
controls = [m["name"] for m in json.loads(open(BASE + "/manifest.json").read())
            if m["gap"] == 0]

for name in controls:
    f = fixed[name]
    r = l3c[name]
    d = r["decode"]
    decode[name] = {"nodes": r["nodes"], **d}
    assert r["winner_ms"] is not None
    assert r["winner_ms"] >= r["greedy"], name
    results[name] = {
        "nodes": r["nodes"], "greedy_L0": r["greedy"],
        "lower_bound": r["lower_bound"],
        "L1_rule": r["L1_rule_ms"],
        "L2_10": f["L2_10"], "L2_100": f["L2_100"], "L2_1000": f["L2_1000"],
        "L2_1000_winner": f["L2_winners"].get("1000"),
        "L2_winners": f["L2_winners"],
        "L2_fair": None,
        "L3_portfolio_winner": r["winner"], "L3_ms": r["winner_ms"],
        "model_beats_L2_1000": False,
        "model_beats_L2_fair": None,
        "order_ms": r["order_ms"], "order_coverage": r["order_coverage"],
        "gen_s": r["gen_s"], "prompt_tokens": r["prompt_tokens"],
        "out_tokens": r["out_tokens"],
        "best_known_search": r["greedy"],
        "raw": {"placed": r["raw"]["placed"],
                "legal_errs": None, "complete": None, "makespan": None},
    }
    # raw legal/complete/ms — короткие поля из l3_controls
    results[name]["raw"] = r["raw"]

json.dump(results, open(ME + "/results.json", "w"),
          ensure_ascii=False, indent=1)
json.dump(decode, open(ME + "/decode.json", "w"),
          ensure_ascii=False, indent=1)
print("results graphs:", len(results), "decode graphs:", len(decode))
n_beat = sum(1 for g, r in results.items() if r["model_beats_L2_1000"])
n_beat_fair = sum(1 for g, r in results.items()
                 if r["model_beats_L2_fair"] is True)
print(f"L3 strictly < L2_1000: {n_beat}/13 targets")
print(f"L3 strictly < L2_fair: {n_beat_fair}/13 targets")
tot_gain = sum(results[g]["greedy_L0"] - results[g]["L3_ms"]
               for g in results if results[g]["L3_ms"] is not None
               and results[g]["greedy_L0"] > results[g]["L3_ms"])
print("total L3 gain vs greedy: +", tot_gain)
