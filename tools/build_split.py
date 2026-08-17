"""Сборка обучающего слияния и широкого held-out эвала.

Зачем нужен второй эвал
-----------------------
Старый `eval.jsonl` собран под графы 6..14 инструкций — ровно диапазон
`dataset.jsonl`. Новые 20 000 примеров покрывают 4..24. Если мерить только
старым эвалом, прирост на крупных графах (18..24) не увидит никто: их там
физически нет. Поэтому режем held-out прямо из новых данных — CP-SAT уже
доказал на них оптимум, генерировать заново нечего.

Срез берётся послойно по числу инструкций (stratified), чтобы весь диапазон
4..24 был представлен, а не только середина, где примеров больше всего.
Отобранное ИСКЛЮЧАЕТСЯ из обучающего файла — иначе эвал измеряет запоминание.

Старый `eval.jsonl` при этом остаётся нетронутым: сравнение «до/после» с
прошлым замером должно идти на тех же данных, что и прошлый замер.

    python tools/build_split.py

Проверить результат:

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
    """Индексы k примеров, разложенных по числу инструкций поровну.

    Слои обходятся по кругу: пока в слое есть непотраченные примеры, он отдаёт
    по одному. Так редкие размеры (n=4, n=24 — их в разы меньше середины)
    попадают в эвал наравне с частыми, а не тонут в пропорции.
    """
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
        if not moved:            # примеров меньше, чем просят
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
                    help="столько же, сколько в старом eval.jsonl")
    ap.add_argument("--seed", type=int, default=20260817)
    args = ap.parse_args()

    base = load(args.base)
    extra = load(args.extra)
    print(f"{args.base}: {len(base)}   {args.extra}: {len(extra)}")

    held = set(stratified_sample(extra, args.eval_size, args.seed))
    eval_rows = [extra[i] for i in sorted(held)]
    extra_train = [r for i, r in enumerate(extra) if i not in held]

    # Дедуп по промпту. Внутри каждого файла дублей нет (проверено), но
    # пересечение между файлами никто не гарантировал: генераторы разные и
    # про друг друга не знают. Приоритет у base — он обучал текущий адаптер.
    seen = {r["prompt"] for r in base}
    merged = list(base)
    dropped = 0
    for r in extra_train:
        if r["prompt"] in seen:
            dropped += 1
            continue
        seen.add(r["prompt"])
        merged.append(r)

    # Эвал не должен пересекаться с обучением ни одним промптом — иначе
    # меряется запоминание, а не решение задачи.
    eval_prompts = {r["prompt"] for r in eval_rows}
    leak = sum(1 for r in merged if r["prompt"] in eval_prompts)
    assert leak == 0, f"утечка эвала в обучение: {leak}"

    random.Random(args.seed).shuffle(merged)
    dump(args.train_out, merged)
    dump(args.eval_out, eval_rows)

    def spread(rows: list[dict]) -> str:
        c = collections.Counter(r["meta"]["n"] for r in rows)
        return f"n={min(c)}..{max(c)}, слоёв {len(c)}, по слою {min(c.values())}..{max(c.values())}"

    print(f"\n{args.train_out}: {len(merged)} примеров "
          f"({len(base)} base + {len(extra_train) - dropped} extra, "
          f"дублей отброшено {dropped})")
    print(f"   {spread(merged)}")
    print(f"{args.eval_out}: {len(eval_rows)} примеров (held-out, в обучение не попали)")
    print(f"   {spread(eval_rows)}")


if __name__ == "__main__":
    main()
