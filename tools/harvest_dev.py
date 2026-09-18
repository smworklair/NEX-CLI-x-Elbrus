"""Набор трудных графов для DEV-отбора (валидация крошек).

Отличается от /hard --harvest только потоком сидов: начинаем с 20300000,
поэтому пересечения с eval_hard.jsonl (сиды 202608xx) нет по построению.
Формат строк — тот же (prompt/completion/meta), эталон доказан оракулом.

Использование:
    python tools/harvest_dev.py --n 120 --jobs 4 --out eval_hard_dev.jsonl

Windows: нужен guard __main__ (spawn), он есть.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from vliw.core.hardness import harvest_one

SEED_BASE = 20300000
N_LO, N_HI = 16, 24


def main() -> None:
    ap = argparse.ArgumentParser(description="Сбор DEV трудных графов")
    ap.add_argument("--n", type=int, default=120)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--out", default="eval_hard_dev.jsonl")
    ap.add_argument("--seed-base", type=int, default=SEED_BASE)
    a = ap.parse_args()

    profile = "e2k-v6-measured"
    tasks = ((seed, N_LO, N_HI, profile)
             for seed in itertools.count(a.seed_base))
    kept, seen, t0 = [], 0, time.monotonic()
    limit = a.n * 400

    if a.jobs > 1:
        import multiprocessing as mp
        with mp.Pool(a.jobs) as pool:
            for row in pool.imap_unordered(harvest_one, tasks, chunksize=4):
                seen += 1
                if row is not None:
                    kept.append(row)
                if len(kept) >= a.n or seen >= limit:
                    pool.terminate()
                    break
    else:
        for task in tasks:
            if len(kept) >= a.n or seen >= limit:
                break
            seen += 1
            row = harvest_one(task)
            if row is not None:
                kept.append(row)

    out = Path(a.out) if Path(a.out).is_absolute() else _ROOT / a.out
    with out.open("w", encoding="utf-8") as f:
        for row in kept:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    dt = time.monotonic() - t0
    print(f"найдено {len(kept)}/{a.n}, просмотрено {seen} "
          f"({100 * len(kept) / max(seen, 1):.1f}% годных) за {dt:.0f} с")
    print(f"записано в {out}")


if __name__ == "__main__":
    main()
