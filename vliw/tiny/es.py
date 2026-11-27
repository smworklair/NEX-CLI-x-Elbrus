"""ES fine-tuning for Tiny-1 — Evolution Strategies from the MLGO paper
(Trofin et al., arXiv 2101.04808: PG and ES as two policy-training algorithms).

Why: behavioral cloning copies the oracle order, but our metric is
makespan after list_schedule (non-differentiable: sorting + packing).
ES optimizes this reward directly: perturb weights, measure makespan,
and step toward the better perturbations.

Fitness = mean makespan of the STANDALONE prio variant (no beam: beam would
dilute the weight signal — the portfolio adds it on top, see scheduler.py).

Requires numpy ONLY for training. Weight format is the same JSON.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import numpy as np

from vliw.core.baseline import list_schedule
from vliw.core.dag import compute_metrics
from vliw.core.model import get_profile
from vliw.tiny.features import build_dag, featurize, parse_graph_entries
from vliw.tiny.model import TinyPriority


def pack(t: TinyPriority) -> tuple[np.ndarray, tuple]:
    parts = [np.asarray(t.w1).ravel(), np.asarray(t.b1),
             np.asarray(t.w2).ravel(), np.asarray(t.b2),
             np.asarray(t.w3), np.asarray([t.b3], dtype=float)]
    return np.concatenate(parts), (len(t.w1), t.h1, t.h2)


def unpack(v: np.ndarray, shape: tuple) -> TinyPriority:
    F, h1, h2 = shape
    o = 0
    w1 = v[o:o + F * h1].reshape(F, h1); o += F * h1
    b1 = v[o:o + h1]; o += h1
    w2 = v[o:o + h1 * h2].reshape(h1, h2); o += h1 * h2
    b2 = v[o:o + h2]; o += h2
    w3 = v[o:o + h2]; o += h2
    b3 = float(v[o])
    return TinyPriority(w1.tolist(), b1.tolist(), w2.tolist(),
                        b2.tolist(), w3.tolist(), b3)


def forward_np(X: np.ndarray, t) -> np.ndarray:
    W1, b1, W2, b2, W3, b3 = (np.asarray(t.w1), np.asarray(t.b1),
                              np.asarray(t.w2), np.asarray(t.b2),
                              np.asarray(t.w3), t.b3)
    a1 = np.maximum(X @ W1 + b1, 0.0)
    a2 = np.maximum(a1 @ W2 + b2, 0.0)
    return a2 @ W3 + b3


def load_batch(path: str):
    from vliw.core.baseline import GreedyListScheduler

    prof = get_profile("e2k-v6-measured")
    base = GreedyListScheduler()
    data = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            ex = json.loads(line)
            dag = build_dag(parse_graph_entries(ex["prompt"]))
            X = np.asarray(featurize(dag, prof))
            m = compute_metrics(dag, prof)
            data.append((dag, prof, X, m.height, m.asap,
                         base.schedule(dag, prof).schedule.makespan))
    return data


def fitness(w: np.ndarray, shape: tuple, batch) -> float:
    """Mean makespan of the prio variant. Lower is better."""
    t = unpack(w, shape)
    tot = 0.0
    for row in batch:
        dag, prof, X, height = row[0], row[1], row[2], row[3]
        prio = forward_np(X, t).tolist()
        s, _ = list_schedule(dag, prof, priority=prio, height=height)
        tot += s.makespan if (not s.validate() and s.complete) else 10_000.0
    return tot / max(len(batch), 1)


def fitness_hold(w: np.ndarray, shape: tuple, batch) -> float:
    """Mean makespan of prio + candidate holds. Order is fixed
    (tuning only the hold head); holds are asap + hold clipped to greedy.
    Lower is better."""
    t = unpack(w, shape)
    tot = 0.0
    for dag, prof, X, height, asap, base_ms, prio in batch:
        holds = forward_np(X, t).tolist()
        defer = {i: c for i, v in enumerate(holds)
                 for c in (asap[i] + int(round(v)),)
                 if 0 < c <= base_ms}
        s, _ = list_schedule(dag, prof, priority=prio, defer_until=defer,
                             height=height)
        tot += s.makespan if (not s.validate() and s.complete) else 10_000.0
    return tot / max(len(batch), 1)


def main() -> None:
    ap = argparse.ArgumentParser(description="ES fine-tune (MLGO-style)")
    ap.add_argument("--train", default="train_hard.jsonl")
    ap.add_argument("--init", default="vliw/tiny/weights.json")
    ap.add_argument("--out", default="vliw/tiny/weights_es.json")
    ap.add_argument("--mode", choices=["prio", "hold"], default="prio",
                    help="prio: tune ordering (standalone); hold: tune "
                         "holds with a fixed ordering (--prio-weights)")
    ap.add_argument("--prio-weights", default="vliw/tiny/weights.json")
    ap.add_argument("--iters", type=int, default=20)
    ap.add_argument("--pop", type=int, default=16, help="even: antithetic pairs")
    ap.add_argument("--sigma", type=float, default=0.01)
    ap.add_argument("--lr", type=float, default=0.1)
    ap.add_argument("--batch", type=int, default=96)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()

    def rp(p: str) -> str:
        return p if Path(p).exists() else str(_ROOT / p)

    data = load_batch(rp(a.train))
    print(f"graphs={len(data)}", flush=True)
    t0 = TinyPriority.load(rp(a.init))
    w, shape = pack(t0)
    dim = w.size
    print(f"params={dim}", flush=True)
    if a.mode == "hold":
        # Keep ordering fixed (current prio weights); evolve holds.
        pt = TinyPriority.load(rp(a.prio_weights))
        data = [row + (forward_np(row[2], pt).tolist(),) for row in data]
        fit = fitness_hold
    else:
        fit = fitness
    rng = np.random.default_rng(a.seed)
    f0 = fit(w, shape, data)
    print(f"init fitness={f0:.3f}", flush=True)
    best, best_f = w.copy(), f0

    for it in range(a.iters):
        idx = rng.choice(len(data), size=min(a.batch, len(data)), replace=False)
        batch = [data[i] for i in idx]
        half = a.pop // 2
        eps = rng.normal(0.0, a.sigma, (half, dim))
        fs = np.zeros(a.pop)
        for k in range(half):
            fs[2 * k] = fit(w + eps[k], shape, batch)
            fs[2 * k + 1] = fit(w - eps[k], shape, batch)
        adv = fs.mean() - fs  # positive for improvement (makespan below mean)
        step = (adv[:, None] * np.vstack([eps, -eps])).sum(0) / (half * 2 * a.sigma)
        w = w + a.lr * step
        f = fit(w, shape, batch)
        if f < best_f:
            best, best_f = w.copy(), float(f)
        print(f"iter {it + 1}/{a.iters} batch_fit={f:.3f} best={best_f:.3f} "
              f"min_pop={fs.min():.3f}", flush=True)

    out = rp(a.out)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    net = unpack(best, shape)
    if a.mode == "hold":
        # Without this marker the scheduler would read holds as legacy cycle.
        net.target = "hold"
    net.save(out)
    print(f"saved {out} best={best_f:.3f} (init {f0:.3f})", flush=True)


if __name__ == "__main__":
    main()
