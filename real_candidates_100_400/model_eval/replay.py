"""L3-реплей из сохранённых сырых ответов + статистика декодирования.

На каждом графе (13 целей):
  decode: decode_completion(raw) -> placements; clip_placements -> keep/extra;
    дубли id, вне диапазона, missing, первая битая строка, обрыв/стоп;
  raw_sched: place keep -> validate/complete/makespan;
  repair-вариант («модель+каналы») — зеркало scheduler._assemble при
    repair=True (берём fixed, только если не хуже);
  портфель: variants(dag, model, keep, extra=(mine,)) -> choose;
  order: order_from_model(keep, n, height) -> list_schedule.
Выход: layers/l3.json (по графам) — вход для results.json.
"""
import importlib.util
import json
import pathlib
import re
import sys

sys.path.insert(0, "/home/shokha/vliw-ai-scheduler-demo")
from vliw.core import asm_parser
from vliw.core.dag import compute_metrics
from vliw.core.baseline import list_schedule
from vliw.core.model import get_profile, DEFAULT_PROFILE
from vliw.core.schedule import Schedule
from training.encode import decode_completion, clip_placements
from training.encode import _LINE_RE
from vliw.learned.portfolio import Variant, variants, choose
from vliw.learned.portfolio import order_from_model
from vliw.learned.repair import repair as _repair

BASE = "/home/shokha/vliw-ai-scheduler-demo/real_candidates_100_400"
ME = BASE + "/model_eval"

spec = importlib.util.spec_from_file_location(
    "rule_under_test", BASE + "/rule/rule.py")
rule_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rule_mod)

model = get_profile(DEFAULT_PROFILE)
val = json.load(open(BASE + "/rule/validation.json"))
final_params = val["families"][val["champion"]]["final_params"]
manifest = {m["name"]: m for m in json.loads(open(BASE + "/manifest.json").read())}
targets = [m["name"] for m in json.loads(open(BASE + "/manifest.json").read())
           if m["gap"] > 0]

out = {}
for name in targets:
    m = manifest[name]
    raw = open(f"{ME}/raw/{name}.txt", encoding="utf-8").read()
    meta = json.load(open(f"{ME}/raw/{name}.meta.json"))
    res = asm_parser.parse_asm(open(f"{BASE}/asm/{name}.s").read(), source=name)
    dag = asm_parser.build_dag(res, key=name, title=name)
    n = len(dag)
    met = compute_metrics(dag, model)
    h = [float(x) for x in met.height]

    # --- decode stats ---
    matches = list(_LINE_RE.finditer(raw))
    decoded = decode_completion(raw)
    seen_ids = [int(x) for x in (mm.group(1) for mm in matches)]
    n_dup_ids = len(seen_ids) - len(set(seen_ids))
    keep, extra = clip_placements(decoded, n)
    missing = sorted(set(range(n)) - set(keep))
    lines = raw.splitlines()
    first_bad = None
    for ln_no, ln in enumerate(lines, 1):
        if ln.strip() and not _LINE_RE.search(ln):
            first_bad = ln_no
            break
    last = lines[-1] if lines else ""
    cut = bool(last.strip() and not _LINE_RE.search(last))
    trunc = (meta["prompt_tokens"] + meta["out_tokens"] >= 4096 - 16
             or meta["out_tokens"] >= meta["max_new_tokens"] - 2)

    # --- raw schedule ---
    sched = Schedule(dag, model)
    for i, (cycle, channel) in sorted(keep.items()):
        sched.place(i, cycle, channel)
    raw_errs = sched.validate()
    raw_complete = sched.complete
    raw_ms = sched.makespan if raw_complete and not raw_errs else None

    # --- repair (зеркало _assemble при repair=True) ---
    report = None
    sched_r, errs_r = sched, raw_errs
    if not missing:
        fixed, report = _repair(sched, model)
        fixed_errs = fixed.validate()
        if len(fixed_errs) <= len(raw_errs):
            sched_r, errs_r = fixed, fixed_errs
        else:
            report = None
    touched = report.touched if report is not None else 0
    mine = Variant("модель+каналы" if touched else "модель",
                   "починка каналов поверх ответа модели"
                   if touched else "сырой ответ модели",
                   sched_r, tuple(errs_r))

    # --- portfolio ---
    cands = variants(dag, model, keep, extra=(mine,))
    best = choose(cands)
    rows = [{"name": c.name, "legal": c.legal,
             "makespan": c.makespan if c.schedule.complete else None}
            for c in cands]

    # --- order candidate standalone ---
    prio_o = order_from_model(keep, n, met.height)
    s_ord, _ = list_schedule(dag, model, priority=prio_o, height=met.height)
    assert s_ord.validate() == []

    # --- L1 reference (rule) ---
    prio_r = rule_mod.priority(dag, model, met, final_params)
    s_rule, _ = list_schedule(dag, model, prio_r, height=met.height)

    out[name] = {
        "nodes": n, "greedy": m["greedy_makespan"],
        "lower_bound": met.lower_bound,
        "prompt_tokens": meta["prompt_tokens"],
        "out_tokens": meta["out_tokens"], "gen_s": meta["gen_s"],
        "decode": {
            "n_lines": len(lines), "n_matched_unique": len(decoded),
            "n_matches_total": len(matches), "n_dup_ids": n_dup_ids,
            "n_extra_ids": len(extra), "extra_ids_head": extra[:8],
            "n_missing": len(missing), "coverage": len(keep) / n,
            "first_bad_line": first_bad, "cut_midline": cut,
            "ctx_truncated": trunc},
        "raw": {"legal_errs": len(raw_errs), "complete": raw_complete,
                "makespan": raw_ms},
        "repaired_touched": touched,
        "portfolio": rows, "winner": best.name,
        "winner_ms": best.makespan if best.schedule.complete else None,
        "order_ms": s_ord.makespan, "order_coverage": len(keep) / n,
        "L1_rule_ms": s_rule.makespan,
    }
    print(f"{name:20s} placed={len(keep):4d}/{n} cov={len(keep)/n:.2f} "
          f"raw_ms={raw_ms} winner={best.name}:{best.makespan if best.schedule.complete else '-'} "
          f"order={s_ord.makespan} L1={s_rule.makespan}", flush=True)

pathlib.Path(ME + "/layers").mkdir(parents=True, exist_ok=True)
json.dump(out, open(ME + "/layers/l3.json", "w"),
          ensure_ascii=False, indent=1)
