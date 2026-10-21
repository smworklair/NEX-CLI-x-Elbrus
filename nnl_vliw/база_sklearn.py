# -*- coding: utf-8 -*-
"""Контрольная база: обычные классификаторы на ТЕХ ЖЕ токенах, том же отборе и том же разбиении.

Нужна, чтобы отличить «ядро NNL плохо» от «задача по этим признакам трудная». Необязательная зависимость: scikit-learn.

    python3 -m nnl_vliw.база_sklearn --метки <папка с *.labels.jsonl> [--зерно 1]
"""

from __future__ import annotations

import argparse
import glob
import sys

import numpy as np

from . import данные as Д
from .оценка import мс
from .язык import ЯзыкГрафов


def macro(pred, truth) -> float:
    g: dict = {}
    for p, t in zip(pred, truth):
        g.setdefault(t, [0, 0])
        g[t][0] += int(p == t)
        g[t][1] += 1
    return float(np.mean([a / b for a, b in g.values()]))


def main() -> int:
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(errors="replace", encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
    from sklearn.feature_extraction import DictVectorizer
    from sklearn.linear_model import LogisticRegression
    ap = argparse.ArgumentParser()
    ap.add_argument("--метки", required=True)
    ap.add_argument("--зерно", type=int, default=1)
    ap.add_argument("--наборы", default="eval_hard,eval_real")
    a = ap.parse_args()
    L = a.метки.rstrip("/\\") + "/"
    я = ЯзыкГрафов()
    метки = []
    for p in sorted(glob.glob(L + "train_*.labels.jsonl")):
        метки += Д.прочитать_метки(p)
    tr, dv = Д.разбить(Д.с_токенами(метки, я), доля_жадных=1.0, зерно=a.зерно)   # тот же отбор, что у ядер
    feat = lambda r: {t: 1.0 for t in r["токены"]}   # noqa: E731
    dvec = DictVectorizer(sparse=False)
    X = dvec.fit_transform([feat(r) for r in tr])
    y = [r["дешёвая"] for r in tr]
    keep = np.where((X > 0).sum(0) >= 20)[0]
    X = X[:, keep]
    Xdv = dvec.transform([feat(r) for r in dv])[:, keep]
    ydv = [r["дешёвая"] for r in dv]
    print(f"обучающих {len(tr)}, dev {len(dv)}, признаков {X.shape[1]}")
    модели = {"логрегрессия": LogisticRegression(max_iter=2000, C=0.5),
              "бустинг": HistGradientBoostingClassifier(max_iter=150, learning_rate=0.08, random_state=a.зерно),
              "лес": RandomForestClassifier(300, min_samples_leaf=2, random_state=a.зерно, n_jobs=2)}
    for k, m in модели.items():
        m.fit(X, y)
        print(f"{k}: dev macro-точность {macro(m.predict(Xdv), ydv):.3f}")
    for имя in a.наборы.split(","):
        ev = Д.с_токенами(Д.прочитать_метки(L + имя + ".labels.jsonl"), я)
        Xe = dvec.transform([feat(r) for r in ev])[:, keep]
        print(f"== {имя}: графов {len(ev)}, лишних тактов у «всегда жадный» {sum(r['по_группам']['greedy'] - r['лучший'] for r in ev)}")
        for k, m in модели.items():
            pr = m.predict(Xe)
            ex = sum(мс(r, g) - r["лучший"] for r, g in zip(ev, pr))
            ok = sum(мс(r, g) == r["лучший"] for r, g in zip(ev, pr))
            print(f"   {k:13} лишних тактов {ex:4d}  верно {ok / len(ev):.3f}  не-greedy предсказано {np.mean([g != 'greedy' for g in pr]):.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
