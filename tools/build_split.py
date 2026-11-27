"""Build merged training set and stratified wide held-out eval split.

    python tools/build_split.py
    python tools/validate_jsonl.py train_merged.jsonl eval_wide.jsonl
"""

from __future__ import annotations

import argparse
import collections
import json
import random
from pathlib import Path


def load(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def dump(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def stratified_sample(rows: list[dict], k: int, seed: int) -> list[int]:
    """Select k indices stratified evenly across instruction-count buckets."""
    rng = random.Random(seed)
    by_n: dict[int, list[int]] = collections.defaultdict(list)
    for i, r in enumerate(rows):
        by_n[r["meta"]["n"]].append(i)
    for idxs in by_n.values():
        rng.shuffle(idxs)

    picked: list[int] = []
    layers = sorted(by_n)
    while len(picked) < k:
        moved = False
        for n in layers:
            if not by_n[n]:
                continue
            picked.append(by_n[n].pop())
            moved = True
            if len(picked) == k:
                break
        if not moved:            # fewer examples available than requested
            break
    return picked


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", type=Path, default=Path("dataset.jsonl"))
    ap.add_argument("--extra", type=Path, default=Path("vliw_train_extra_fixed.jsonl"))
    ap.add_argument("--train-out", type=Path, default=Path("train_merged.jsonl"))
    ap.add_argument("--eval-out", type=Path, default=Path("eval_wide.jsonl"))
    ap.add_argument("--eval-size", type=int, default=300,
                    help="same size as legacy eval.jsonl")
    ap.add_argument("--seed", type=int, default=20260817)
    args = ap.parse_args()

    base = load(args.base)
    extra = load(args.extra)
    print(f"{args.base}: {len(base)}   {args.extra}: {len(extra)}")

    held = set(stratified_sample(extra, args.eval_size, args.seed))
    eval_rows = [extra[i] for i in sorted(held)]
    extra_train = [r for i, r in enumerate(extra) if i not in held]

    # Deduplicate by prompt across input files (base takes priority).
    #
    #
    seen = {r["prompt"] for r in base}
    merged = list(base)
    dropped = 0
    for r in extra_train:
        if r["prompt"] in seen:
            dropped += 1
            continue
        seen.add(r["prompt"])
        merged.append(r)

    # Verify zero prompt leakage between eval and training splits.
    #
    eval_prompts = {r["prompt"] for r in eval_rows}
    leak = sum(1 for r in merged if r["prompt"] in eval_prompts)
    assert leak == 0, f"eval leakage into train: {leak}"

    random.Random(args.seed).shuffle(merged)
    dump(args.train_out, merged)
    dump(args.eval_out, eval_rows)

    def spread(rows: list[dict]) -> str:
        c = collections.Counter(r["meta"]["n"] for r in rows)
        return f"n={min(c)}..{max(c)}, strata {len(c)}, per stratum {min(c.values())}..{max(c.values())}"

    print(f"\n{args.train_out}: {len(merged)} examples "
          f"({len(base)} base + {len(extra_train) - dropped} extra, "
          f"duplicates dropped {dropped})")
    print(f"   {spread(merged)}")
    print(f"{args.eval_out}: {len(eval_rows)} examples (held-out, excluded from train)")
    print(f"   {spread(eval_rows)}")


if __name__ == "__main__":
    main()
