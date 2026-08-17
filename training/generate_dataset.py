"""Генератор обучающего датасета: пары (граф+модель) → оптимальное расписание.

Данные берутся из ТОГО ЖЕ движка, что и `/sweep` в CLI — оракул точного поиска
(`vliw.core.OracleScheduler`) на случайных графах (`vliw.core.random_dag`).
Оставляются только графы, где оптимальность ДОКАЗАНА (`orc.optimal`) — учить
модель на недоказанном «лучшем найденном» портфельного перебора нет смысла,
это не гарантированный эталон.

Только CPU, только `vliw.core` — никаких ML-зависимостей. Гонять здесь же,
локально, или бесплатно на Deepnote (Basic-машина, 2 vCPU/5 ГБ хватает).
Дообучение (нужен GPU) — отдельным шагом на Kaggle, см. training/README.md.

    python3 training/generate_dataset.py --count 20000 --out dataset.jsonl
    python3 training/generate_dataset.py --count 500 --out smoke.jsonl --budget 1.0  # быстрый прогон

Профиль машины — ТОЛЬКО e2k-v6-measured (проверенная модель) и её сужения по
ширине. Специально НЕ используется e2k-v6-firstprobe (опровергнутая первая
версия) — учить модель на неверной модели машины значит учить её неверным
урокам, ровно та ошибка, из-за которой чинили vliw/core/model.py.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vliw.core import DEFAULT_PROFILE, OracleScheduler, get_profile, random_dag  # noqa: E402
from training.encode import encode_completion, encode_prompt  # noqa: E402


def generate(count: int, seed0: int, sizes: list[int], widths: list[int],
             budget_s: float, max_tries: int):
    base = get_profile(DEFAULT_PROFILE)
    rnd = random.Random(seed0)
    made = tried = 0
    t0 = time.monotonic()
    while made < count and tried < max_tries:
        tried += 1
        seed = rnd.randint(1, 10**9)
        n = rnd.choice(sizes)
        width = rnd.choice(widths)
        model = base if width == base.width else base.with_width(width)
        dag = random_dag(seed, n=n)

        orc = OracleScheduler(budget_s=budget_s, portfolio_s=0.0).schedule(dag, model)
        if not orc.optimal:
            continue                      # не доказанный оптимум — не эталон
        if orc.schedule.validate():
            continue                      # подстраховка: не должно случаться

        made += 1
        yield {
            "prompt": encode_prompt(dag, model),
            "completion": encode_completion(orc.schedule),
            "meta": {"seed": seed, "n": n, "width": width,
                     "makespan": orc.schedule.makespan},
        }
        if made % 200 == 0:
            rate = made / max(0.001, time.monotonic() - t0)
            print(f"  {made}/{count} готово (перебрано {tried} графов, "
                  f"{rate:.1f}/с)", file=sys.stderr)

    if made < count:
        print(f"ВНИМАНИЕ: набрано только {made}/{count} за {tried} попыток "
              f"(лимит --max-tries). Увеличьте --max-tries или --budget, "
              f"либо смягчите --sizes.", file=sys.stderr)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--count", type=int, default=5000, help="сколько примеров набрать")
    ap.add_argument("--seed", type=int, default=1, help="сид генератора сидов")
    ap.add_argument("--sizes", default="6,8,10,12,14",
                    help="размеры графов через запятую (инструкций)")
    ap.add_argument("--widths", default="6",
                    help="ширины машины через запятую (портов); 6 = полная e2k-v6-measured")
    ap.add_argument("--budget", type=float, default=1.5,
                    help="бюджет точного поиска на ОДИН граф, секунд")
    ap.add_argument("--max-tries", type=int, default=10**9,
                    help="сколько графов максимум перебрать (защита от зависания)")
    ap.add_argument("--out", default="dataset.jsonl")
    args = ap.parse_args()

    sizes = [int(x) for x in args.sizes.split(",")]
    widths = [int(x) for x in args.widths.split(",")]

    out_path = Path(args.out)
    n_written = 0
    with out_path.open("w", encoding="utf-8") as f:
        for row in generate(args.count, args.seed, sizes, widths,
                            args.budget, args.max_tries):
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            n_written += 1

    print(f"готово: {n_written} примеров → {out_path}")


if __name__ == "__main__":
    main()
