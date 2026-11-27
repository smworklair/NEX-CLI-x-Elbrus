"""Generate raw DAGs for portfolio labeling via tools/vliw_gen.py without oracle filtering.

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
    ap = argparse.ArgumentParser(description="Raw DAGs for portfolio labeling")
    ap.add_argument("--n", type=int, default=1000)
    ap.add_argument("--out", default="graphs.jsonl")
    ap.add_argument("--n-lo", type=int, default=8)
    ap.add_argument("--n-hi", type=int, default=32)
    ap.add_argument("--seed-base", type=int, default=31000000)
    ap.add_argument("--exclude", default="eval_hard.jsonl,eval_hard_dev.jsonl,eval_wide.jsonl,eval_real.jsonl",
                    help="comma-separated .jsonl files whose prompts must be excluded (eval sets)")
    a = ap.parse_args()
    model = get_profile("e2k-v6-measured")
    seen = set()
    excluded = set()
    for name in [x.strip() for x in a.exclude.split(",") if x.strip()]:
        p = Path(name) if Path(name).exists() else ROOT / name
        if p.exists():
            excluded.update(json.loads(l)["prompt"] for l in p.read_text(encoding="utf-8").splitlines() if l.strip())
    with open(a.out, "w", encoding="utf-8") as f:
        for k in range(a.n):
            seed = a.seed_base + k
            rnd = random.Random(seed)
            n = rnd.randint(a.n_lo, a.n_hi)
            shape = rnd.choice(SHAPES)
            raw = gen_graph(rnd, n, shape, PRESSURE_WEIGHTS)
            dag = DAG("gen", "", "", [Instr(x.id, f"n{x.id}", x.op, x.preds, f"n{x.id}") for x in raw])
            prompt = encode_prompt(dag, model)
            if prompt in seen or prompt in excluded:
                continue
            seen.add(prompt)
            f.write(json.dumps({"prompt": prompt, "meta": {"n": n, "shape": shape, "seed": seed}}, ensure_ascii=False) + "\n")
    print(f"wrote {len(seen)} graphs to {a.out} (excluded eval prompts: {len(excluded)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
