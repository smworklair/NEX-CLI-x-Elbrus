"""Сырые графы для разметки портфелем: генератор проекта (tools/vliw_gen.py), БЕЗ отбора оракулом.

В отличие от tools/harvest_dev.py здесь нет проверки «жадный не оптимален» (она гоняет оракул до
6 с на граф): все графы сохраняются, а трудные потом выделяет tools/portfolio_labels.py — по тому,
что лучше жадного даёт портфель. Поток сидов задаётся --seed-base; сиды eval_hard (202608xx) и
eval_hard_dev (20300000+) не используются по умолчанию.

    python3 tools/gen_graphs.py --n 30000 --out graphs.jsonl [--n-lo 8 --n-hi 32 --seed-base 31000000]
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.vliw_gen import PRESSURE_WEIGHTS, SHAPES, gen_graph  # noqa: E402
from training.encode import encode_prompt  # noqa: E402
from vliw.core.dag import DAG, Instr  # noqa: E402
from vliw.core.model import get_profile  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Сырые графы для разметки портфелем")
    ap.add_argument("--n", type=int, default=1000)
    ap.add_argument("--out", default="graphs.jsonl")
    ap.add_argument("--n-lo", type=int, default=8)
    ap.add_argument("--n-hi", type=int, default=32)
    ap.add_argument("--seed-base", type=int, default=31000000)
    ap.add_argument("--exclude", default="eval_hard.jsonl,eval_hard_dev.jsonl,eval_wide.jsonl,eval_real.jsonl",
                    help="через запятую: файлы .jsonl, чьи prompt нельзя повторять (проверочные наборы)")
    a = ap.parse_args()
    model = get_profile("e2k-v6-measured")
    seen = set()
    запрещено = set()
    for name in [x.strip() for x in a.exclude.split(",") if x.strip()]:
        p = Path(name) if Path(name).exists() else ROOT / name
        if p.exists():
            запрещено.update(json.loads(l)["prompt"] for l in p.read_text(encoding="utf-8").splitlines() if l.strip())
    with open(a.out, "w", encoding="utf-8") as f:
        for k in range(a.n):
            seed = a.seed_base + k
            rnd = random.Random(seed)
            n = rnd.randint(a.n_lo, a.n_hi)
            shape = rnd.choice(SHAPES)
            raw = gen_graph(rnd, n, shape, PRESSURE_WEIGHTS)
            dag = DAG("gen", "", "", [Instr(x.id, f"n{x.id}", x.op, x.preds, f"n{x.id}") for x in raw])
            prompt = encode_prompt(dag, model)
            if prompt in seen or prompt in запрещено:
                continue
            seen.add(prompt)
            f.write(json.dumps({"prompt": prompt, "meta": {"n": n, "shape": shape, "seed": seed}}, ensure_ascii=False) + "\n")
    print(f"записано {len(seen)} графов в {a.out} (исключено проверочных prompt: {len(запрещено)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
