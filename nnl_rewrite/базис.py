"""Правило и логрегрессия. На eval_* не учимся.

Разбиение фиксировано: файлы перемешиваются Random(seed), последние 30% — тест.
Сиды 0, 1, 2. Ядро NNL сюда не входит: его имеет смысл учить, только если
оба базиса промахнулись, и это решает прогон, а не этот модуль.
"""

from __future__ import annotations

import random

from vliw.core.dag import DAG

SEEDS = (0, 1, 2)
TEST_FRAC = 0.30


def _longest(dag: DAG, op: str) -> int:
    n = len(dag)
    succs: list[list[int]] = [[] for _ in range(n)]
    for ins in dag:
        for p in ins.preds:
            succs[p].append(ins.id)
    best = 0
    for ins in dag:
        if ins.op != op or any(dag[p].op == op for p in ins.preds):
            continue
        cur, length, seen = ins.id, 1, {ins.id}
        while True:
            nxt = [s for s in succs[cur] if dag[s].op == op and s not in seen]
            if len(nxt) != 1:
                break
            cur = nxt[0]
            seen.add(cur)
            length += 1
        best = max(best, length)
    return best


def признаки(dag: DAG) -> list[float]:
    c: dict[str, int] = {}
    arity = [0, 0, 0]
    for ins in dag:
        c[ins.op] = c.get(ins.op, 0) + 1
        if ins.op == "ADD":
            arity[min(len(ins.preds), 2)] += 1
    return [
        float(len(dag)),
        float(c.get("ADD", 0)),
        float(arity[0]),
        float(arity[1]),
        float(arity[2]),
        float(_longest(dag, "ADD")),
        float(c.get("FADD", 0)),
        float(_longest(dag, "FADD")),
        float(c.get("DIV", 0)),
        float(c.get("FDIV", 0)),
        float(c.get("LOAD", 0)),
    ]


def разбиение(files: list[str], seed: int) -> tuple[set[str], set[str]]:
    names = sorted(set(files))
    rng = random.Random(seed)
    rng.shuffle(names)
    n_test = max(1, int(round(len(names) * TEST_FRAC)))
    test = set(names[-n_test:])
    train = set(names) - test
    return train, test


def логрегрессия(rows: list[dict], seed: int) -> dict:
    """rows: file, x (list[float]), y (0/1), rule (0/1). Только train учится."""
    from sklearn.linear_model import LogisticRegression

    train_files, test_files = разбиение([r["file"] for r in rows], seed)
    train = [r for r in rows if r["file"] in train_files]
    test = [r for r in rows if r["file"] in test_files]
    y_train = [r["y"] for r in train]
    if len(set(y_train)) < 2:
        pred = [0] * len(test)
        note = "в обучении один класс, предсказание — нет"
    else:
        clf = LogisticRegression(max_iter=400, random_state=seed)
        clf.fit([r["x"] for r in train], y_train)
        pred = [int(v) for v in clf.predict([r["x"] for r in test])]
        note = "обучена"
    y = [r["y"] for r in test]
    rule = [r["rule"] for r in test]

    def correct(guess: list[int]) -> int:
        return sum(int(a == b) for a, b in zip(guess, y))

    return {
        "сид": seed,
        "файлов_тест": sorted(test_files),
        "блоков_тест": len(test),
        "положительных_в_тесте": sum(y),
        "правило_верно": correct(rule),
        "логрегрессия_верно": correct(pred),
        "всегда_нет_верно": correct([0] * len(test)),
        "примечание": note,
    }
