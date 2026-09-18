"""Разбор проигрышей портфеля: где tiny не дотянул до оптимума.

Вопрос после tiny_gap.py: разрыв топ-1/топ-2 скоров провал не предсказывает,
ворота по gap'у отпадают. Тогда смотрим в лоб — какие графы остаются
неоптимальными и чем они похожи: shape из meta, размер, наличие DIV
(монопольный порт ,5), кто выиграл в портфеле.

Правда — meta из eval-файла (makespan=доказанный оптимум CP-SAT),
пересчитывать оракул не надо. Ничего не меняет в планировщике.

Запуск (около минуты на eval_hard):
    .venv/bin/python tools/tiny_losses.py [limit]
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vliw.core.model import get_profile  # noqa: E402
from vliw.tiny.features import build_dag, parse_graph_entries  # noqa: E402
from vliw.tiny.scheduler import TinyScheduler  # noqa: E402


def _has_div(prompt: str) -> bool:
    for line in prompt.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "DIV":
            return True
    return False


def main() -> None:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    prof = get_profile("e2k-v6-measured")
    sched = TinyScheduler()
    if sched.tiny is None:
        print("нет весов priority — разбирать нечего")
        raise SystemExit(1)
    lines = open(ROOT / "eval_hard.jsonl", encoding="utf-8").readlines()
    if limit:
        lines = lines[:limit]
    rows = []
    for idx, line in enumerate(lines):
        ex = json.loads(line)
        meta = ex["meta"]
        dag = build_dag(parse_graph_entries(ex["prompt"]))
        res = sched.schedule(dag, prof)
        t = res.schedule.makespan
        rows.append({
            "idx": idx,
            "shape": meta.get("shape", "?"),
            "n": meta.get("n", len(dag)),
            "opt": meta["makespan"],
            "base": meta.get("baseline", 0),
            "tiny": t,
            "loss": t - meta["makespan"],
            "winner": res.search_stats.get("tiny_winner", "?"),
            "div": _has_div(ex["prompt"]),
        })
    n = len(rows)
    bad = [r for r in rows if r["loss"] > 0]
    print(f"n={n} неоптимальных: {len(bad)} "
          f"({len(bad) / max(n, 1):.0%}), "
          f"суммарный перебор тактов: {sum(r['loss'] for r in bad)}")
    print()
    print(f"{'shape':>10} {'n':>4} {'opt%':>5} "
          f"{'ср.перебор':>10} {'кто выигрывал':>30}")
    for shape in sorted({r["shape"] for r in rows}):
        sub = [r for r in rows if r["shape"] == shape]
        opt = sum(1 for r in sub if r["loss"] == 0)
        avg = sum(r["loss"] for r in sub) / len(sub)
        wins = Counter(r["winner"] for r in sub
                       if r["loss"] > 0).most_common(3)
        print(f"{shape:>10} {len(sub):>4} {opt / len(sub):>5.0%} "
              f"{avg:>10.2f} {str(wins):>30}")
    print()
    for label, pred in (("с DIV", lambda r: r["div"]),
                        ("без DIV", lambda r: not r["div"]),
                        ("n<=20", lambda r: r["n"] <= 20),
                        ("n>20", lambda r: r["n"] > 20)):
        sub = [r for r in rows if pred(r)]
        if not sub:
            continue
        opt = sum(1 for r in sub if r["loss"] == 0)
        avg = sum(r["loss"] for r in sub) / len(sub)
        print(f"{label:>8}: n={len(sub):>4} opt={opt / len(sub):.0%} "
              f"ср.перебор={avg:.2f}")
    print()
    print(f"{'idx':>4} {'shape':>8} {'n':>3} {'opt':>4} "
          f"{'base':>4} {'tiny':>4} {'перебор':>7} {'winner':>10}")
    for r in sorted(bad, key=lambda r: -r["loss"])[:10]:
        print(f"{r['idx']:>4} {r['shape']:>8} {r['n']:>3} {r['opt']:>4} "
              f"{r['base']:>4} {r['tiny']:>4} {r['loss']:>7} "
              f"{r['winner']:>10}")


if __name__ == "__main__":
    main()
