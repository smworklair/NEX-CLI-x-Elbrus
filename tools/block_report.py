"""Отчёт «по блокам»: настоящие `.s` от lcc, каждый базовый блок — отдельный граф.

Что показывает (всё в тактах МОДЕЛИ машины, а не Эльбруса):
  [1] сколько блоков и операций, какая доля — циклы `loop_mode`;
  [2] блоки с n >= --min-ops: жадный -> быстрые крошки -> точный поиск;
      сколько блоков улучшено, сколько доказано (оптимум = нижняя граница);
  [3] где расписание самого lcc восстановилось и прошло проверку — во сколько раз
      оно длиннее лучшего найденного (это признак «модели не хватает ограничений
      реальной машины», а не запас для ускорения);
  [4] где достигается нижняя граница: жадным, веером, дальше (кому вообще нужен поиск);
  [5] время на блок;
  [6] крупнейшие блоки.

Запуск (около минуты с точным поиском --oracle 3):
    python3 tools/block_report.py
    python3 tools/block_report.py real_candidates_100_400/asm/poly_gemm.s --oracle 0
    python3 tools/block_report.py --mode asm --json out.json

Только чтение: репозиторий не меняется. Граф блока и допущения — vliw/core/blocks.py.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vliw.core.baseline import GreedyListScheduler  # noqa: E402
from vliw.core.blocks import BUCKETS, block_graphs_of_file  # noqa: E402
from vliw.core.dag import compute_metrics  # noqa: E402
from vliw.core.model import DEFAULT_PROFILE, get_profile  # noqa: E402
from vliw.core.oracle import OracleScheduler  # noqa: E402
from vliw.tiny.fast import TinyFastScheduler  # noqa: E402

BUCKET_NAMES = [b for b, _ in BUCKETS]


def collect(paths: list[Path], model, min_ops: int, mode: str, oracle_s: float):
    base = GreedyListScheduler()
    tiny = TinyFastScheduler(mode=mode, with_trace=False)
    rows = []
    for p in paths:
        for g in block_graphs_of_file(p):
            n = g.n
            row = {"file": p.stem, "block": g.block.index, "label": g.block.label, "n": n,
                   "bundles": g.block.bundles, "loop": g.block.loop, "bucket": g.bucket,
                   "lcc": None, "lcc_why": "", "base": None, "tiny": None, "oracle": None,
                   "proved": None, "lb": None, "hit": None,
                   "t_base_ms": None, "t_tiny_ms": None, "t_oracle_ms": None}
            lcc, why = g.lcc_schedule(model)
            row["lcc"] = lcc.makespan if lcc is not None else None
            row["lcc_why"] = why[0] if why else ""
            t0 = time.perf_counter()
            row["base"] = base.schedule(g.dag, model).schedule.makespan
            row["t_base_ms"] = 1000 * (time.perf_counter() - t0)
            row["lb"] = compute_metrics(g.dag, model).lower_bound
            if n >= min_ops:
                t0 = time.perf_counter()
                res = tiny.schedule(g.dag, model)
                row["t_tiny_ms"] = 1000 * (time.perf_counter() - t0)
                row["tiny"] = res.schedule.makespan
                row["hit"] = res.search_stats.get("bound_hit_at")
                if oracle_s > 0:
                    t0 = time.perf_counter()
                    ro = OracleScheduler(budget_s=oracle_s,
                                         portfolio_s=max(oracle_s / 3.0, 0.02)).schedule(g.dag, model)
                    row["t_oracle_ms"] = 1000 * (time.perf_counter() - t0)
                    row["oracle"] = ro.schedule.makespan
                    row["proved"] = bool(ro.optimal)
            rows.append(row)
    return rows


def best(r) -> int:
    return min(v for v in (r["base"], r["tiny"], r["oracle"]) if v is not None)


def report(rows, min_ops: int, oracle_s: float, top: int, mode: str) -> None:
    tot_ops = sum(r["n"] for r in rows)
    loop_ops = sum(r["n"] for r in rows if r["loop"])
    print(f"[1] блоков {len(rows)}, операций {tot_ops}; в блоках loop_mode "
          f"{sum(1 for r in rows if r['loop'])} блоков, {loop_ops} операций "
          f"({100 * loop_ops / max(tot_ops, 1):.0f} %)")
    print(f"    {'корзина':9}{'блоков':>8}{'операций':>10}")
    for bk in BUCKET_NAMES:
        rs = [r for r in rows if r["bucket"] == bk]
        print(f"    {bk:9}{len(rs):>8}{sum(r['n'] for r in rs):>10}")

    big = [r for r in rows if r["n"] >= min_ops]
    print(f"\n[2] блоки n >= {min_ops}: жадный -> крошки[{mode}]"
          + (f" -> точный поиск {oracle_s:g} с" if oracle_s > 0 else "") + " (такты модели)")
    head = f"    {'вид':9}{'корзина':9}{'блоков':>7}{'опер.':>7}{'жадный':>8}{'крошки':>8}"
    if oracle_s > 0:
        head += f"{'точный':>8}"
    head += f"{'лучшее':>8}{'выигрыш %':>10}{'улучшено':>9}"
    if oracle_s > 0:
        head += f"{'доказано':>9}"
    print(head)
    for kind in ("прямые", "циклы"):
        for bk in BUCKET_NAMES:
            rs = [r for r in big if r["bucket"] == bk and r["loop"] == (kind == "циклы")]
            if not rs:
                continue
            sb = sum(r["base"] for r in rs)
            st = sum(r["tiny"] for r in rs)
            sbest = sum(best(r) for r in rs)
            imp = sum(1 for r in rs if best(r) < r["base"])
            line = (f"    {kind:9}{bk:9}{len(rs):>7}{sum(r['n'] for r in rs):>7}{sb:>8}{st:>8}")
            if oracle_s > 0:
                line += f"{sum(r['oracle'] for r in rs):>8}"
            line += f"{sbest:>8}{100 * (sb - sbest) / sb:>10.1f}{imp:>9}"
            if oracle_s > 0:
                line += f"{sum(1 for r in rs if r['proved']):>9}"
            print(line)
    if big:
        sb = sum(r["base"] for r in big)
        sbest = sum(best(r) for r in big)
        print(f"    ИТОГО n >= {min_ops}: блоков {len(big)}, жадный {sb}, лучшее {sbest}, "
              f"выигрыш {100 * (sb - sbest) / sb:.1f} %, улучшено блоков "
              f"{sum(1 for r in big if best(r) < r['base'])}"
              + (f", оптимум доказан в {sum(1 for r in big if r['proved'])}" if oracle_s > 0 else ""))

        print(f"\n[3] блоки n >= {min_ops}, где расписание lcc восстановлено и прошло проверку")
        rl = [r for r in big if r["lcc"] is not None]
        print(f"    восстановлено {len(rl)} из {len(big)}; циклов среди них {sum(1 for r in rl if r['loop'])}")
        if rl:
            sl = sum(r["lcc"] for r in rl)
            sbest = sum(best(r) for r in rl)
            print(f"    сумма lcc {sl}, лучшее {sbest}: lcc / лучшее = {sl / sbest:.2f}×")
            for kind in ("прямые", "циклы"):
                rr = [r for r in rl if r["loop"] == (kind == "циклы")]
                if rr:
                    sl2 = sum(r["lcc"] for r in rr)
                    sb2 = sum(best(r) for r in rr)
                    print(f"      {kind}: блоков {len(rr)}, lcc {sl2}, лучшее {sb2}, {sl2 / sb2:.2f}×")
        why = Counter(r["lcc_why"] for r in big if r["lcc"] is None)
        if why:
            print("    не восстановлено:", dict(why))

        print(f"\n[4] где достигнута нижняя граница makespan (крошки[{mode}], блоки n >= {min_ops})")
        hit = Counter(str(r["hit"]) for r in big)
        for k, v in hit.most_common():
            what = {"greedy": "жадный уже на границе — оптимум доказан без поиска",
                    "None": "граница не достигнута (оптимум не доказан границей)"}.get(
                        k, "доказано после поиска этой группой")
            print(f"    {k:8}{v:>5}  ({100 * v / len(big):.0f} %)  {what}")
        gap = [r["tiny"] - r["lb"] for r in big if r["hit"] is None]
        if gap:
            print(f"    у блоков без достигнутой границы: зазор лучшее - граница в среднем "
                  f"{sum(gap) / len(gap):.1f} такта (граница не обязательно достижима)")

        print("\n[5] время на блок, мс (в среднем)")
        tb = [r["t_base_ms"] for r in big]
        tt = [r["t_tiny_ms"] for r in big]
        print(f"    жадный {sum(tb) / len(tb):.2f}   крошки[{mode}] {sum(tt) / len(tt):.2f}", end="")
        if oracle_s > 0:
            to = [r["t_oracle_ms"] for r in big]
            print(f"   точный {sum(to) / len(to):.1f}", end="")
        print()

    print(f"\n[6] {top} крупнейших блоков")
    print(f"    {'блок':24}{'вид':8}{'n':>5}{'ш.к.':>5}{'lcc':>6}{'жадный':>8}{'крошки':>8}"
          f"{'точный':>8}{'граница':>8}")
    for r in sorted(rows, key=lambda r: -r["n"])[:top]:
        print(f"    {r['file'] + '#' + str(r['block']):24}{'цикл' if r['loop'] else 'прямой':8}{r['n']:>5}"
              f"{r['bundles']:>5}{str(r['lcc']):>6}{r['base']:>8}{str(r['tiny']):>8}"
              f"{str(r['oracle']):>8}{r['lb']:>8}")


def main() -> int:
    # Консоль Windows бывает в узкой кодировке (cp866/cp1251): не падать на «×», «→», «≈»
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(errors="replace")
        except Exception:  # noqa: BLE001 — поток подменён (тесты, перенаправление)
            pass
    ap = argparse.ArgumentParser(description="Отчёт по базовым блокам настоящих .s от lcc")
    ap.add_argument("files", nargs="*", help=".s файлы (по умолчанию все из --dir)")
    ap.add_argument("--dir", default=str(ROOT / "real_candidates_100_400" / "asm"))
    ap.add_argument("--min-ops", type=int, default=10, help="блоки короче не планируем (как в статье)")
    ap.add_argument("--profile", default=DEFAULT_PROFILE)
    ap.add_argument("--mode", choices=("exact", "asm"), default="exact",
                    help="exact: как полный портфель; asm: без hold/defer (см. docs/TINY_FAST.md)")
    ap.add_argument("--oracle", type=float, default=3.0, help="бюджет точного поиска на блок, с (0 = выключить)")
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--json", help="записать строки по блокам в JSON")
    a = ap.parse_args()

    paths = [Path(f) for f in a.files] or sorted(Path(a.dir).glob("*.s"))
    if not paths:
        print("нет .s файлов", file=sys.stderr)
        return 2
    model = get_profile(a.profile)
    t0 = time.time()
    rows = collect(paths, model, a.min_ops, a.mode, a.oracle)
    print(f"файлов {len(paths)}, блоков {len(rows)}, профиль {a.profile}, "
          f"прогон {time.time() - t0:.0f} с\n")
    report(rows, a.min_ops, a.oracle, a.top, a.mode)
    if a.json:
        Path(a.json).write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\nстроки по блокам записаны: {a.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
