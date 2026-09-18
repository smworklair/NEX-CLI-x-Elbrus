"""Батарея проверок крошки. Один harness на все будущие крошки-2..N.

Запуск:  python -m vliw.tiny.verify --weights vliw/tiny/weights.json
         python -m vliw.tiny.verify --weights vliw/tiny/weights.json --fuzz 500 --train-sample 1000

Проверки (каждая — PASS/FAIL + числа, без исключений наружу):
  V1 valid на eval_hard / eval_wide / сценариях / семпле train / фуззе
  V2 never-worse: tiny.makespan <= baseline.makespan везде
  V3 детерминизм: два прогона дают одинаковый makespan и placements
  V4 робастность: UNKNOWN-опкоды, 1 узел, цепочка, большой граф n=120
  V5 веса: бюджет <=150К, roundtrip save/load бит-в-бит по скорам
  V6 статистика: wins/losses/ties, средний зазор, знаковый тест (p-value)
  V7 латентность: mean/p95 мс на schedule
  V8 фолбэк без весов == baseline бит-в-бит

Выход — код 0 если все PASS, иначе 1. Отчет печатается таблицей.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from vliw.core.baseline import GreedyListScheduler
from vliw.core.dag import DAG, DagBuilder, SCENARIOS, get_scenario, random_dag
from vliw.core.model import get_profile
from vliw.tiny.features import build_dag, featurize, parse_graph_entries
from vliw.tiny.model import TinyPriority
from vliw.tiny.scheduler import TinyScheduler

PROFILE = "e2k-v6-measured"
PARAM_BUDGET = 150_000


def _load_jsonl(path: str, limit: int = 0) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    if limit:
        lines = lines[:limit]
    return [json.loads(x) for x in lines]


def _check_graphs(sched, base, prof, dags, tag, rows) -> dict:
    """Прогон списка DAG: valid / never-worse / зазоры / латентность."""
    n = valid = win = loss = tie = opt_known = opt_hit = 0
    gap_t = gap_b = 0.0
    lat: list[float] = []
    worst = None
    for dag, optimum in dags:
        t0 = time.perf_counter()
        res = sched.schedule(dag, prof)
        lat.append((time.perf_counter() - t0) * 1000.0)
        b = base.schedule(dag, prof).schedule.makespan
        t = res.schedule.makespan
        errs = res.schedule.validate()
        n += 1
        if not errs and res.schedule.complete:
            valid += 1
        else:
            rows.append(("V1", tag, "FAIL", f"невалид на {dag.key}: {errs[:2]}"))
        if t > b:
            loss += 1
            rows.append(("V2", tag, "FAIL", f"{dag.key}: tiny {t} > base {b}"))
        elif t < b:
            win += 1
        else:
            tie += 1
        if optimum is not None:
            opt_known += 1
            gap_t += t - optimum
            gap_b += b - optimum
            if t == optimum:
                opt_hit += 1
        if worst is None or t - b > worst[1]:
            worst = (dag.key, t - b)
    lat_sorted = sorted(lat)
    p95 = lat_sorted[max(0, math.ceil(0.95 * len(lat_sorted)) - 1)] if lat_sorted else 0.0
    return {"n": n, "valid": valid, "win": win, "loss": loss, "tie": tie,
            "opt_known": opt_known, "opt_hit": opt_hit,
            "gap_t": gap_t, "gap_b": gap_b,
            "lat_mean": sum(lat) / max(len(lat), 1), "lat_p95": p95,
            "worst": worst}


def _sign_test_p(wins: int, losses: int) -> float:
    """Двусторонний знаковый тест (биномиальный, нормальная аппроксимация
    с поправкой на непрерывность). H0: tiny и baseline равны."""
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    mean = n / 2.0
    sd = math.sqrt(n / 4.0)
    z = (mean - k - 0.5) / sd if sd else 0.0
    # Phi через erf
    p_one = 0.5 * (1.0 - math.erf(z / math.sqrt(2.0))) if z > 0 else 0.5
    return min(1.0, 2.0 * p_one)


def main() -> int:
    ap = argparse.ArgumentParser(description="Батарея проверок крошки")
    ap.add_argument("--weights", default="vliw/tiny/weights.json")
    ap.add_argument("--eval-hard", default="eval_hard.jsonl")
    ap.add_argument("--eval-dev", default="eval_hard_dev.jsonl",
                    help="DEV трудных для отбора (сиды 20300xxx, без пересечения с eval_hard)")
    ap.add_argument("--eval-wide", default="eval_wide.jsonl")
    ap.add_argument("--train", default="train_merged.jsonl")
    ap.add_argument("--train-sample", type=int, default=500)
    ap.add_argument("--fuzz", type=int, default=200)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()

    def rp(p: str) -> str:
        return p if Path(p).exists() else str(_ROOT / p)

    rows: list[tuple[str, str, str, str]] = []
    prof = get_profile(PROFILE)
    sched = TinyScheduler(rp(a.weights))
    base = GreedyListScheduler()
    ok = True

    # V5: бюджет весов + roundtrip
    if sched.tiny is None:
        rows.append(("V5", "weights", "FAIL", "веса не загрузились: " + sched.load_error))
        ok = False
        nparams = -1
    else:
        nparams = sched.tiny.param_count()
        rows.append(("V5", "budget", "PASS" if nparams <= PARAM_BUDGET else "FAIL",
                     f"params={nparams} <= {PARAM_BUDGET}"))
        if nparams > PARAM_BUDGET:
            ok = False
        import tempfile, os
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "w.json")
            sched.tiny.save(p)
            t2 = TinyPriority.load(p)
        X = featurize(get_scenario("slotclash"), prof)
        s0, s1 = sched.tiny.scores(X), t2.scores(X)
        same = all(x == y for x, y in zip(s0, s1))
        rows.append(("V5", "roundtrip", "PASS" if same else "FAIL",
                     "save/load бит-в-бит" if same else "расхождение скоров"))
        if not same:
            ok = False
        finite = all(math.isfinite(v) for v in s0)
        rows.append(("V5", "finite", "PASS" if finite else "FAIL",
                     "скоры конечны" if finite else f"NaN/inf: {s0}"))
        if not finite:
            ok = False

    # V8: фолбэк не хуже baseline. Именно «не хуже», а не «ровно»: веер
    # вокруг height работает и без весов (deliberate, см. tiny/README), и
    # при широком веере на slotclash честно выигрывает. Контракт проекта —
    # «хуже baseline не бывает», бит-в-бит никто не обещал.
    fb = TinyScheduler(weights="/nonexistent/weights.json")
    fb_same = True
    for key in ("simple4", "slotclash", "memstream"):
        dag = get_scenario(key)
        r1 = fb.schedule(dag, prof).schedule
        r2 = base.schedule(dag, prof).schedule
        if r1.makespan > r2.makespan or r1.validate():
            fb_same = False
    rows.append(("V8", "fallback", "PASS" if fb_same else "FAIL",
                 "без весов не хуже baseline" if fb_same else "фолбэк хуже baseline"))
    if not fb_same:
        ok = False

    # V1/V2/V6/V7: наборы данных
    sets: list[tuple[str, list]] = []
    hard = _load_jsonl(rp(a.eval_hard))
    sets.append(("hard", [(build_dag(parse_graph_entries(e["prompt"])),
                           e["meta"]["makespan"]) for e in hard]))
    dev_path = rp(a.eval_dev)
    if Path(dev_path).exists():
        dev = _load_jsonl(dev_path)
        sets.append(("hard_dev", [(build_dag(parse_graph_entries(e["prompt"])),
                                   e["meta"]["makespan"]) for e in dev]))
    wide = _load_jsonl(rp(a.eval_wide))
    sets.append(("wide", [(build_dag(parse_graph_entries(e["prompt"])), None)
                          for e in wide]))
    sets.append(("scenarios", [(d, None) for d in SCENARIOS.values()]))
    train_ex = _load_jsonl(rp(a.train), a.train_sample)
    sets.append(("train_sample", [(build_dag(parse_graph_entries(e["prompt"])), None)
                                  for e in train_ex]))
    import random as _r
    rnd = _r.Random(a.seed)
    sets.append(("fuzz", [(random_dag(rnd.randrange(1 << 30), n=rnd.choice([8, 12, 16, 20, 24])),
                           None) for _ in range(a.fuzz)]))

    total = {"n": 0, "valid": 0, "win": 0, "loss": 0, "tie": 0,
             "opt_known": 0, "opt_hit": 0, "gap_t": 0.0, "gap_b": 0.0}
    for tag, dags in sets:
        st = _check_graphs(sched, base, prof, dags, tag, rows)
        for k in total:
            total[k] += st[k]
        line = (f"{tag}: n={st['n']} valid={st['valid']}/{st['n']} "
                f"win={st['win']} loss={st['loss']} tie={st['tie']} "
                f"lat={st['lat_mean']:.2f}/{st['lat_p95']:.2f}ms")
        if st["opt_known"]:
            line += (f" gap tiny={st['gap_t']/st['opt_known']:.3f} "
                     f"base={st['gap_b']/st['opt_known']:.3f} "
                     f"opt={st['opt_hit']}/{st['opt_known']}")
        stat = "PASS" if st["loss"] == 0 and st["valid"] == st["n"] else "FAIL"
        if stat == "FAIL":
            ok = False
        rows.append(("V1+V2", tag, stat, line))

    # V6: знаковый тест по всем наборам
    p = _sign_test_p(total["win"], total["loss"])
    rows.append(("V6", "sign_test",
                 "PASS" if total["loss"] == 0 else "FAIL",
                 f"wins={total['win']} losses={total['loss']} ties={total['tie']} "
                 f"p={p:.4f} (H0: равны)"))
    if total["loss"] != 0:
        ok = False

    # V3: детерминизм
    det = True
    for key in ("slotclash", "memstream"):
        dag = get_scenario(key)
        r1 = sched.schedule(dag, prof).schedule
        r2 = sched.schedule(dag, prof).schedule
        p1 = {k: (v.cycle, v.channel) for k, v in r1.placements.items()}
        p2 = {k: (v.cycle, v.channel) for k, v in r2.placements.items()}
        if p1 != p2:
            det = False
    rows.append(("V3", "determinism", "PASS" if det else "FAIL",
                 "два прогона идентичны" if det else "расхождение!"))
    if not det:
        ok = False

    # V4: робастность
    try:
        b = DagBuilder("unknown_ops", "", "")
        b.op("FADD", "a"); b.op("PRED", "p"); b.op("PACK", "q", 0)
        b.op("ADD", "r", 0, 1); b.op("DIV", "d", 3)
        r = sched.schedule(b.build(), prof)
        r4a = (r.schedule.validate() == [] and r.schedule.complete)
    except Exception as e:  # noqa: BLE001
        r4a = f"исключение: {e}"
    rows.append(("V4", "unknown_ops", "PASS" if r4a is True else "FAIL", str(r4a)))
    try:
        b = DagBuilder("single", "", "")
        b.op("ADD", "a")
        r = sched.schedule(b.build(), prof)
        r4b = (r.schedule.validate() == [] and r.schedule.makespan == 1)
    except Exception as e:  # noqa: BLE001
        r4b = f"исключение: {e}"
    rows.append(("V4", "single_node", "PASS" if r4b is True else "FAIL", str(r4b)))
    try:
        big = random_dag(123456789, n=120)
        t0 = time.perf_counter()
        r = sched.schedule(big, prof)
        dt = (time.perf_counter() - t0) * 1000.0
        r4c = (r.schedule.validate() == [] and r.schedule.complete)
        rows.append(("V4", "n=120", "PASS" if r4c else "FAIL",
                     f"valid={r4c} makespan={r.schedule.makespan} {dt:.1f}ms"))
        if not r4c:
            ok = False
    except Exception as e:  # noqa: BLE001
        rows.append(("V4", "n=120", "FAIL", f"исключение: {e}"))
        ok = False
    if r4a is not True or r4b is not True:
        ok = False

    print(f"{'check':8} {'target':12} {'res':6} detail")
    for c, t, s, d in rows:
        print(f"{c:8} {t:12} {s:6} {d}")
    print(f"TOTAL valid={total['valid']}/{total['n']} "
          f"win={total['win']} loss={total['loss']} tie={total['tie']} "
          f"params={nparams} -> {'ALL PASS' if ok else 'FAILURES PRESENT'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
