"""Gap top-1/top-2 скоров MLP vs исход prio-пути: предсказывает ли разрыв провал.

Вопрос из разбора Jev-паттернов (confidence-gated routing): если два верхних
скора почти равны, порядку prio верить нельзя — и тогда либо шире веер,
либо сразу ничья greedy. Сначала проверяем, есть ли вообще связь, на
eval_hard: для каждого графа gap + исход (prio+defer без веера vs greedy).
Ничего не меняет в коде планировщика — только измеряет.

Запуск (секунды):
    .venv/bin/python tools/tiny_gap.py [limit]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vliw.core.baseline import GreedyListScheduler  # noqa: E402
from vliw.core.model import get_profile  # noqa: E402
from vliw.tiny.features import build_dag, parse_graph_entries  # noqa: E402
from vliw.tiny.scheduler import TinyScheduler  # noqa: E402


def main() -> None:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    prof = get_profile("e2k-v6-measured")
    base = GreedyListScheduler()
    sched = TinyScheduler(beam=0)  # learned-путь без веера: prio + prio_defer
    if sched.tiny is None:
        print("нет весов priority — мерить нечего")
        raise SystemExit(1)
    lines = open(ROOT / "eval_hard.jsonl", encoding="utf-8").readlines()
    if limit:
        lines = lines[:limit]
    rows = []
    for line in lines:
        ex = json.loads(line)
        dag = build_dag(parse_graph_entries(ex["prompt"]))
        scores = sorted(sched.priority(dag, prof), reverse=True)
        gap = scores[0] - scores[1] if len(scores) > 1 else 0.0
        b = base.schedule(dag, prof).schedule.makespan
        res = sched.schedule(dag, prof)
        t = res.schedule.makespan
        rows.append((gap, "win" if t < b else ("tie" if t == b else "loss")))
    rows.sort()
    n = len(rows)
    wins = sum(1 for _, o in rows if o == "win")
    print(f"n={n} побед prio-пути: {wins} ({wins / max(n, 1):.0%})")
    print(f"{'порог gap':>10} {'n<порог':>8} {'побед':>7} {'доля':>6}  смысл")
    for thr in (0.01, 0.02, 0.05, 0.1, 0.2):
        sub = [o for g, o in rows if g < thr]
        w = sum(1 for o in sub if o == "win")
        print(f"{thr:>10} {len(sub):>8} {w:>7} {w / max(len(sub), 1):>5.0%}  "
              f"{'малый gap → prio чаще проигрывает?' if w / max(len(sub), 1) < wins / n else ''}")
    los = [(g, o) for g, o in rows if o == "loss"]
    print(f"поражений (хуже baseline): {len(los)} (портфель их отсекает выбором min)")


if __name__ == "__main__":
    main()
