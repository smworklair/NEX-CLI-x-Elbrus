"""ES fine-tune крошки-1 — алгоритм Evolution Strategies из MLGO-статьи
(Trofin et al., arxiv 2101.04808: PG и ES как два алгоритма обучения политик).

Зачем: behavioral cloning копирует порядок оракула, но наша метрика —
makespan после list_schedule (недифференцируемо: сортировка + упаковка).
ES работает с такой наградой напрямую: шумим веса, меряем makespan,
шагаем в сторону лучших возмущений.

Фитнес = средний makespan STANDALONE prio-варианта (без веера: веер бы
размыл сигнал весов — его добавляет портфель сверху, см. scheduler.py).

Нужен numpy ТОЛЬКО для обучения. Формат весов — тот же JSON.
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
    prof = get_profile("e2k-v6-measured")
    data = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            ex = json.loads(line)
            dag = build_dag(parse_graph_entries(ex["prompt"]))
            X = np.asarray(featurize(dag, prof))
            m = compute_metrics(dag, prof)
            data.append((dag, prof, X, m.height))
    return data


def fitness(w: np.ndarray, shape: tuple, batch) -> float:
    """Средний makespan prio-варианта. Меньше = лучше."""
    t = unpack(w, shape)
    tot = 0.0
    for dag, prof, X, height in batch:
        prio = forward_np(X, t).tolist()
        s, _ = list_schedule(dag, prof, priority=prio, height=height)
        tot += s.makespan if (not s.validate() and s.complete) else 10_000.0
    return tot / max(len(batch), 1)


def main() -> None:
    ap = argparse.ArgumentParser(description="ES fine-tune (MLGO-style)")
    ap.add_argument("--train", default="train_hard.jsonl")
    ap.add_argument("--init", default="vliw/tiny/weights.json")
    ap.add_argument("--out", default="vliw/tiny/weights_es.json")
    ap.add_argument("--iters", type=int, default=20)
    ap.add_argument("--pop", type=int, default=16, help="четное: антитезные пары")
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
    rng = np.random.default_rng(a.seed)
    f0 = fitness(w, shape, data)
    print(f"init fitness={f0:.3f}", flush=True)
    best, best_f = w.copy(), f0

    for it in range(a.iters):
        idx = rng.choice(len(data), size=min(a.batch, len(data)), replace=False)
        batch = [data[i] for i in idx]
        half = a.pop // 2
        eps = rng.normal(0.0, a.sigma, (half, dim))
        fs = np.zeros(a.pop)
        for k in range(half):
            fs[2 * k] = fitness(w + eps[k], shape, batch)
            fs[2 * k + 1] = fitness(w - eps[k], shape, batch)
        adv = fs.mean() - fs  # плюс за улучшение (makespan ниже среднего)
        step = (adv[:, None] * np.vstack([eps, -eps])).sum(0) / (half * 2 * a.sigma)
        w = w + a.lr * step
        f = fitness(w, shape, batch)
        if f < best_f:
            best, best_f = w.copy(), float(f)
        print(f"iter {it + 1}/{a.iters} batch_fit={f:.3f} best={best_f:.3f} "
              f"min_pop={fs.min():.3f}", flush=True)

    out = rp(a.out)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    unpack(best, shape).save(out)
    print(f"saved {out} best={best_f:.3f} (init {f0:.3f})", flush=True)


if __name__ == "__main__":
    main()
