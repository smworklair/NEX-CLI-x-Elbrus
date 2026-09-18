"""Обучение крошки-1: клонирование порядка оракула (behavioral cloning).

Учитель — не Phi и не Qwen, а точный CP-SAT из train_merged.jsonl
(completion там доказуемо оптимален, см. tools/vliw_gen.py).
Учим MLP повторять порядок оракула: цель узла = (n - rank)/n, лосс MSE.

Тяжелые по DIV/STORE графы (ловушки slotclash/memstream) апсемплим весом,
иначе их 1-6% утонут в легких, где baseline и так оптимален (см. CAB.md).

Нужен numpy ТОЛЬКО для обучения. Инференс (model.py) — stdlib.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import numpy as np

from vliw.core.model import get_profile
from vliw.tiny.features import (
    N_FEATURES,
    build_dag,
    featurize,
    oracle_order,
    parse_graph_entries,
    parse_placements,
)
from vliw.tiny.model import TinyPriority


def load_samples(path: str, max_graphs: int, seed: int, target: str = "rank",
                 extra_path: str = "", extra_repeat: int = 0):
    prof = get_profile("e2k-v6-measured")
    Xs, ys, ws = [], [], []
    n_graphs = 0
    n_div_heavy = 0
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    if extra_path and extra_repeat > 0:
        # Подмес тяжёлого набора (train_hard: DIV 25% против 5% в merged).
        # Вес ×4 в лоссе не спасает, когда ловушек одна на двадцать:
        # повторяем строки ДО шаффла, чтобы доля в батче стала честной.
        # max_graphs режет общий пул — бюджет как у базового рецепта.
        with open(extra_path, encoding="utf-8") as f:
            extra = f.readlines()
        lines += extra * extra_repeat
    rnd = random.Random(seed)
    rnd.shuffle(lines)
    for line in lines:
        if n_graphs >= max_graphs:
            break
        try:
            ex = json.loads(line)
            entries = parse_graph_entries(ex["prompt"])
            if len(entries) < 4:
                continue
            dag = build_dag(entries)
            pl = parse_placements(ex["completion"])
            if len(pl) != len(dag):
                continue  # битый пример — пропускаем, не чиним
            n = len(dag)
            if target == "rank":
                order = oracle_order(pl, n)
                rank = {node: r for r, node in enumerate(order)}
                y_of = lambda i: (n - rank[i]) / n
            elif target == "cycle":
                # Абсолютный такт оракула: на инференсе станет defer_until
                # (запрет «не раньше»), c клипом по жадному makespan.
                y_of = lambda i: float(pl[i][0])
            elif target == "hold":
                # Длительность держки: насколько позже раннего старта
                # оракул ставит узел. Абсолютный такт скачет от графа
                # к графу и по нормированным фичам не учится (сеть
                # underpredict'ит в safe-early — см. вскрытие графа 7
                # в docs/TINY.md); держка инвариантна к размеру графа,
                # у большинства узлов — честный ноль.
                from vliw.core.dag import compute_metrics as _cm
                asap = _cm(dag, prof).asap
                y_of = lambda i: float(max(0, pl[i][0] - asap[i]))
            else:
                raise SystemExit(f"неизвестный target {target!r}")
            X = featurize(dag, prof)
            n_div = sum(1 for _, op, _ in entries if op == "DIV")
            n_store = sum(1 for _, op, _ in entries if op == "STORE")
            w = 1.0 + 3.0 * (1.0 if n_div >= 2 else 0.0) + 1.0 * (1.0 if n_store >= 4 else 0.0)
            if n_div >= 2:
                n_div_heavy += 1
            for i in range(n):
                Xs.append(X[i])
                ys.append(y_of(i))
                ws.append(w)
            n_graphs += 1
        except Exception:
            continue
    X = np.asarray(Xs, dtype=np.float64)
    y = np.asarray(ys, dtype=np.float64)
    w = np.asarray(ws, dtype=np.float64)
    w *= len(w) / w.sum()  # средний вес 1
    return X, y, w, n_graphs, n_div_heavy


def train(X, y, w, hidden=(128, 64), epochs=25, lr=3e-3, seed=0, l2=1e-5):
    rng = np.random.default_rng(seed)
    F = X.shape[0] and X.shape[1]
    h1, h2 = hidden
    # He-иниц. — та же схема, что TinyPriority.init (с точностью до ГПСЧ).
    W1 = rng.normal(0, math.sqrt(2.0 / F), (F, h1))
    b1 = np.zeros(h1)
    W2 = rng.normal(0, math.sqrt(2.0 / h1), (h1, h2))
    b2 = np.zeros(h2)
    W3 = rng.normal(0, math.sqrt(2.0 / h2), (h2,))
    b3 = 0.0
    params = [W1, b1, W2, b2, W3, b3]
    m = [np.zeros_like(p) for p in params]
    v = [np.zeros_like(p) for p in params]
    b1c, b2c, eps = 0.9, 0.999, 1e-8
    N = X.shape[0]
    bs = 4096
    step = 0
    for ep in range(epochs):
        cur_lr = lr * (0.5 if ep >= 2 * epochs // 3 else 1.0)
        perm = rng.permutation(N)
        tot, cnt = 0.0, 0
        for s in range(0, N, bs):
            idx = perm[s:s + bs]
            xb, yb, wb = X[idx], y[idx], w[idx]
            # forward
            z1 = xb @ W1 + b1
            a1 = np.maximum(z1, 0)
            z2 = a1 @ W2 + b2
            a2 = np.maximum(z2, 0)
            pred = a2 @ W3 + b3
            err = pred - yb
            loss = float((wb * err * err).mean())
            tot += loss * len(idx)
            cnt += len(idx)
            # backward (MSE с весами + L2)
            g = (2.0 * wb * err / len(idx))  # dL/dpred
            gW3 = a2.T @ g + l2 * W3
            gb3 = float(g.sum())
            ga2 = np.outer(g, W3) * (z2 > 0)
            gW2 = a1.T @ ga2 + l2 * W2
            gb2 = ga2.sum(0)
            ga1 = ga2 @ W2.T * (z1 > 0)
            gW1 = xb.T @ ga1 + l2 * W1
            gb1 = ga1.sum(0)
            grads = [gW1, gb1, gW2, gb2, gW3, np.asarray(gb3)]
            step += 1
            for k in range(6):
                m[k] = b1c * m[k] + (1 - b1c) * grads[k]
                v[k] = b2c * v[k] + (1 - b2c) * (grads[k] ** 2)
                mh = m[k] / (1 - b1c ** step)
                vh = v[k] / (1 - b2c ** step)
                params[k] -= cur_lr * mh / (np.sqrt(vh) + eps)
            W1, b1, W2, b2, W3, b3 = params[0], params[1], params[2], params[3], params[4], float(params[5])
            params = [W1, b1, W2, b2, W3, b3]
        print(f"epoch {ep + 1}/{epochs} loss={tot / max(cnt, 1):.5f} lr={cur_lr:.1e}", flush=True)
    return TinyPriority(W1.tolist(), b1.tolist(), W2.tolist(), b2.tolist(),
                        W3.tolist(), float(b3))


def main() -> None:
    ap = argparse.ArgumentParser(description="Обучение крошки-1 (numpy, CPU)")
    ap.add_argument("--train", default="train_merged.jsonl")
    ap.add_argument("--train-extra", default="",
                    help="второй файл (напр. train_hard.jsonl), подмешать повторами")
    ap.add_argument("--extra-repeat", type=int, default=0,
                    help="сколько раз повторить train-extra в пуле до шаффла")
    ap.add_argument("--out", default="vliw/tiny/weights.json")
    ap.add_argument("--max-graphs", type=int, default=8000)
    ap.add_argument("--epochs", type=int, default=25)
    ap.add_argument("--hidden", type=int, nargs=2, default=[128, 64])
    ap.add_argument("--lr", type=float, default=3e-3)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--target", choices=["rank", "cycle", "hold"], default="rank",
                    help="rank: порядок оракула (priority); cycle: такт оракула "
                         "(defer, legacy); hold: держка после раннего старта (defer)")
    a = ap.parse_args()
    train_path = a.train if Path(a.train).is_absolute() or Path(a.train).exists() \
        else str(_ROOT / a.train)
    print(f"load {train_path} (max {a.max_graphs}) ...", flush=True)
    extra = a.train_extra
    if extra and not (Path(extra).is_absolute() or Path(extra).exists()):
        extra = str(_ROOT / extra)
    if extra:
        print(f"extra {extra} x{a.extra_repeat} ...", flush=True)
    X, y, w, ng, ndiv = load_samples(train_path, a.max_graphs, a.seed,
                                      a.target, extra, a.extra_repeat)
    print(f"graphs={ng} nodes={len(y)} div_heavy={ndiv} feats={X.shape[1]}", flush=True)
    tiny = train(X, y, w, hidden=tuple(a.hidden), epochs=a.epochs, lr=a.lr, seed=a.seed)
    tiny.target = a.target
    print(f"params={tiny.param_count()}", flush=True)
    out = a.out if Path(a.out).is_absolute() or Path(a.out).parent.exists() \
        else str(_ROOT / a.out)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    tiny.save(out)
    print(f"saved {out}", flush=True)


if __name__ == "__main__":
    main()
