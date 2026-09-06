"""Независимая перепроверка model_eval (вызывается из VERIFY.sh).

Каждое число заново выводится из asm/*.s и сохранённых raw/*.txt средствами
проекта (parse_asm -> build_dag -> compute_metrics -> list_schedule;
decode_completion/clip_placements/build_schedule; LearnedScheduler со
ScriptedBackend для CAB-пути; rule.py как проверяемый артефакт) и
сравнивается с заявленным из manifest.json / results.json / decode.json.
Своих кэшей нет; model_eval-скрипты (layers_*, replay, merge_*) не
импортируются. Модель не запускается.
"""
import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from vliw.core import asm_parser  # noqa: E402
from vliw.core.dag import compute_metrics  # noqa: E402
from vliw.core.baseline import list_schedule  # noqa: E402
from vliw.core.model import get_profile, DEFAULT_PROFILE  # noqa: E402
from training.encode import (  # noqa: E402
    decode_completion, clip_placements, build_schedule)
from vliw.learned.scheduler import LearnedScheduler  # noqa: E402
from vliw.learned.runtime import ScriptedBackend  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "rule_under_test", str(ROOT / "real_candidates_100_400" / "rule" / "rule.py"))
rule_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rule_mod)

BASE = ROOT / "real_candidates_100_400"
ME = BASE / "model_eval"
GRAPHS13 = ["poly_covariance", "poly_gemm", "tsvc_s1111", "poly_adi",
            "poly_gesummv", "emb_iir", "poly_floyd_int", "poly_heat3d",
            "poly_gramschmidt", "poly_fdtd", "emb_fir", "poly_jacobi2d",
            "poly_symm"]
CONTROLS12 = ["poly_syrk", "poly_trmm", "poly_durbin", "poly_trisolv_int",
              "poly_seidel", "poly_jacobi1d", "poly_gemver", "poly_lu",
              "oblas_gemv", "cm_mul", "cm_bitextract", "cm_vect"]

out_lines = []
npass = nfail = 0


def emit(ok, what, claimed, recomputed):
    global npass, nfail
    if ok:
        out_lines.append(f"PASS  {what}  {claimed} == {recomputed}")
        npass += 1
    else:
        out_lines.append(f"FAIL  {what}  {claimed} != {recomputed}")
        nfail += 1


model = get_profile(DEFAULT_PROFILE)
manifest = {m["name"]: m
            for m in json.loads((BASE / "manifest.json").read_text())}
results = json.load(open(ME / "results.json"))
decode_cl = json.load(open(ME / "decode.json"))


def load_graph(name):
    res = asm_parser.parse_asm(open(BASE / f"asm/{name}.s").read(),
                               source=name)
    dag = asm_parser.build_dag(res, key=name, title=name)
    return dag, compute_metrics(dag, model)


def greedy_of(dag, met):
    h = [float(x) for x in met.height]
    g, _ = list_schedule(dag, model, priority=list(h), height=met.height)
    return g


# V1: база по 25 (сводно)
v1_bad = []
for name, m in manifest.items():
    dag, met = load_graph(name)
    g = greedy_of(dag, met)
    assert g.validate() == [], name
    if (len(dag), g.makespan, met.lower_bound) != (
            m["nodes"], m["greedy_makespan"], m["lower_bound"]):
        v1_bad.append(name)
if not v1_bad:
    emit(True, "base-25", "25/25", "25/25")
else:
    for name in v1_bad:
        emit(False, "base-25", name, "mismatch")

# V2: правило на 13 (по графам)
val_rule = json.load(open(BASE / "rule" / "validation.json"))
final_params = val_rule["families"][val_rule["champion"]]["final_params"]
for name in GRAPHS13:
    dag, met = load_graph(name)
    prio = rule_mod.priority(dag, model, met, final_params)
    s, _ = list_schedule(dag, model, prio, height=met.height)
    emit(s.makespan == results[name]["L1_rule"] and s.validate() == [],
         f"rule-{name}", results[name]["L1_rule"], s.makespan)

# V3: модель из сохранённого текста (сводно: decode + портфель + raw)
v3_bad = []
for name in GRAPHS13:
    raw = open(ME / f"raw/{name}.txt", encoding="utf-8").read()
    dag, met = load_graph(name)
    n = len(dag)
    decoded = decode_completion(raw)
    keep, _ = clip_placements(decoded, n)
    sched = build_schedule(dag, model, decoded)
    errs = sched.validate()
    sch = LearnedScheduler(backend=ScriptedBackend(raw), repair=True,
                           cab=True)
    got = sch.schedule(dag, model)
    w = got.search_stats["cab_winner"]
    wms = got.schedule.makespan if got.schedule.complete else None
    r = results[name]
    dc = decode_cl[name]
    ok = (len(decoded) == dc["n_matched_unique"]
          and abs(len(keep) / n - dc["coverage"]) < 1e-9
          and w == r["L3_portfolio_winner"] and wms == r["L3_ms"]
          and len(keep) == r["raw"]["placed"]
          and len(errs) == r["raw"]["legal_errs"]
          and sched.complete == r["raw"]["complete"]
          and (sched.makespan if sched.complete and not errs else None)
          == r["raw"]["makespan"])
    if not ok:
        v3_bad.append(name)
if not v3_bad:
    emit(True, "model-replay-13", "13/13", "13/13")
else:
    for name in v3_bad:
        emit(False, "model-replay-13", name, "mismatch")

# V4: вывод «L3 < L2» + реплей L2-победителей (сводно)
def replay_winner(dag, met, w):
    h = [float(x) for x in met.height]
    prio = list(h)
    for k, d in w["priority_delta"].items():
        prio[int(k)] += d
    s, _ = list_schedule(dag, model, prio, height=met.height)
    return s


v4_bad = []
for name in GRAPHS13:
    r = results[name]
    w = (r["L2_winners"] or {}).get("1000")
    if w is not None:
        dag, met = load_graph(name)
        s = replay_winner(dag, met, w)
        if not (s.validate() == [] and s.makespan == r["L2_1000"]):
            v4_bad.append((name, "L2_1000"))
    fair = r["L2_fair"]
    if fair["winner"] is not None:
        dag, met = load_graph(name)
        s = replay_winner(dag, met, fair["winner"])
        if not (s.validate() == [] and s.makespan == fair["best_ms"]):
            v4_bad.append((name, "fair"))
    headline = ((r["L3_ms"] < r["L2_1000"]) == r["model_beats_L2_1000"]
                and (r["L3_ms"] < fair["best_ms"]) == r["model_beats_L2_fair"])
    if not headline:
        v4_bad.append((name, "headline"))
if not v4_bad:
    emit(True, "L3-vs-L2-headline+L2-replay", "13/13", "13/13")
else:
    for name, tag in v4_bad:
        emit(False, "L3-vs-L2", f"{name}/{tag}", "mismatch")

# V5: контроль, все слои (сводно)
v5_bad = []
for name in CONTROLS12:
    r = results[name]
    dag, met = load_graph(name)
    g = greedy_of(dag, met)
    layers = {"L0": g.makespan, "L1": r["L1_rule"],
              "L2_1000": r["L2_1000"], "L3": r["L3_ms"]}
    if r.get("L2_fair"):
        layers["L2_fair"] = r["L2_fair"]["best_ms"]
    if any(v is not None and v < g.makespan for v in layers.values()):
        v5_bad.append(name)
if not v5_bad:
    emit(True, "control-12", "12/12", "12/12")
else:
    for name in v5_bad:
        emit(False, "control-12", name, "below-greedy")

# V6: L2-fair из T(g) (по графам)
for name in GRAPHS13:
    r = results[name]
    fair = r["L2_fair"]
    meta = json.load(open(ME / f"raw/{name}.meta.json"))
    expected = fair["T_gen_s"] / fair["t_eval_median_s"] \
        if fair["t_eval_median_s"] > 0 else 0
    k = fair["attempts_done"]
    ok = (k > 0 and fair["T_gen_s"] > 0
          and abs(meta["gen_s"] - fair["T_gen_s"]) < 1e-6
          and 0.2 <= k / expected <= 5.0)
    emit(ok, f"L2-fair-{name}",
         f"T={fair['T_gen_s']:.0f}s/K={k}", f"exp~{expected:.0f}")

out_lines.append(f"ИТОГО PASS={npass} FAIL={nfail}")
out_lines.append("VERIFY OK" if nfail == 0 else "VERIFY FAIL")
print("\n".join(out_lines))
sys.exit(1 if nfail else 0)
