#!/usr/bin/env python3
"""Бейчмарк NEX CLI на рукописных фрагментах e2k.

Берёт `.s`-файлы (по умолчанию `benchmarks/snippets/`), разбирает их тем же
разбором, что и настоящий вывод lcc, строит граф зависимостей и прогоняет
три планировщика:

  * baseline   — жадный list scheduler;
  * TINY Flash — быстрый планировщик проекта (тот же makespan, что TINY AI);
  * oracle     — точный поиск с бюджетом времени.

Для каждого файла печатается makespan, нижняя граница, доля UNKNOWN и
замечания линтера. Результаты сохраняются в JSON и Markdown.

Запуск:
    python tools/bench_snippets.py
    python tools/bench_snippets.py --budget 5
    python tools/bench_snippets.py benchmarks/snippets/03_predication.s
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vliw.core.asm_parser import (  # noqa: E402
    build_dag,
    compiler_schedule_checked,
    lint,
    parse_file,
    unknown_share,
)
from vliw.core.baseline import GreedyListScheduler  # noqa: E402
from vliw.core.dag import compute_metrics  # noqa: E402
from vliw.core.model import get_profile  # noqa: E402
from vliw.core.oracle import OracleScheduler  # noqa: E402
from vliw.tiny.fast import TinyFlashScheduler  # noqa: E402


def _timed(fn):
    t0 = time.perf_counter()
    res = fn()
    return res, (time.perf_counter() - t0) * 1000.0


def _legal(res) -> bool:
    return res.schedule.complete and not res.schedule.validate()


def run_one(path: Path, model, budget: float, portfolio: float, tiny) -> dict:
    parsed = parse_file(str(path))
    dag = build_dag(parsed, key=path.stem, title=path.name)
    met = compute_metrics(dag, model)
    problems = lint(parsed, model)
    csched, cproblem = compiler_schedule_checked(parsed, dag, model)

    base, t_base = _timed(lambda: GreedyListScheduler().schedule(dag, model))
    fast, t_fast = _timed(lambda: tiny.schedule(dag, model))
    orc, t_orc = _timed(lambda: OracleScheduler(
        budget_s=budget, portfolio_s=portfolio).schedule(dag, model))

    unknown = sum(1 for o in parsed.ops if o.op == "UNKNOWN")
    errors = [p for p in problems if p.severity == "error"]
    warns = [p for p in problems if p.severity == "warn"]

    return {
        "file": path.name,
        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "ops": len(parsed.ops),
        "bundles": parsed.bundles,
        "nop_cycles": parsed.nop_cycles,
        "skipped_lines": parsed.skipped_lines,
        "unknown_mnemonics": parsed.unknown_mnemonics,
        "unknown": unknown,
        "unknown_share": round(unknown_share(parsed), 4),
        "compiler_cycles": parsed.compiler_cycles,
        "compiler_schedule": csched is not None,
        "compiler_problem": list(cproblem) if cproblem else None,
        "lower_bound": met.lower_bound,
        "critical_path": met.critical_path_bound,
        "resource_bound": met.resource_bound,
        "binding": met.binding,
        "baseline": base.schedule.makespan,
        "tiny": fast.schedule.makespan,
        "oracle": orc.schedule.makespan,
        "oracle_optimal": bool(orc.optimal),
        "legal": {"baseline": _legal(base), "tiny": _legal(fast), "oracle": _legal(orc)},
        "ms": {"baseline": round(t_base, 3), "tiny": round(t_fast, 3),
               "oracle": round(t_orc, 1)},
        "problems": [{"line": p.line, "kind": p.kind, "severity": p.severity,
                      "text": p.text, "hint": p.hint} for p in problems],
        "errors": len(errors),
        "warns": len(warns),
    }


def _fmt_gain(baseline: int, best: int) -> str:
    if best >= baseline:
        return "-"
    return f"-{baseline - best} ({100 * (baseline - best) / baseline:.0f}%)"


def print_table(rows: list[dict]) -> None:
    head = (f"{'файл':<28} {'N':>3} {'автор':>5} {'база':>5} {'TINY':>5} "
            f"{'oracle':>6} {'опт.':>5} {'UNK':>4} {'ошиб':>5}")
    print(head)
    print("-" * len(head))
    for r in rows:
        opt = "да" if r["oracle_optimal"] else "нет"
        print(f"{r['file']:<28} {r['ops']:>3} {r['compiler_cycles']:>5} "
              f"{r['baseline']:>5} {r['tiny']:>5} {r['oracle']:>6} {opt:>5} "
              f"{r['unknown']:>4} {r['errors']:>5}")


def print_details(rows: list[dict]) -> None:
    for r in rows:
        print()
        print(f"{r['file']}  ({r['path']})")
        print(f"  {r['ops']} операций, {r['bundles']} широких команд, "
              f"nop-тактов {r['nop_cycles']}; нижняя граница {r['lower_bound']} "
              f"({r['binding']})")
        if r["compiler_schedule"]:
            print(f"  расписание компилятора: {r['compiler_cycles']} тактов (принято)")
        else:
            print("  расписание компилятора: не восстановлено — "
                  + (r["compiler_problem"][1] if r["compiler_problem"] else "?"))
        print(f"  baseline {r['baseline']} | TINY Flash {r['tiny']} "
              f"({r['ms']['tiny']} мс) | oracle {r['oracle']} "
              f"({'оптимум доказан' if r['oracle_optimal'] else 'не доказан'}, "
              f"{r['ms']['oracle']} мс)")
        print(f"  выигрыш TINY Flash: {_fmt_gain(r['baseline'], r['tiny'])}; "
              f"UNKNOWN {r['unknown']} ({100 * r['unknown_share']:.0f}%)")
        status = ", ".join(f"{k}: {'законно' if v else 'НЕЗАКОННО'}"
                           for k, v in r["legal"].items())
        print(f"  проверка расписаний: {status}")
        for p in r["problems"][:4]:
            print(f"  ! строка {p['line']}: {p['text']}")
        if len(r["problems"]) > 4:
            print(f"  ... ещё {len(r['problems']) - 4} замечаний")


def write_markdown(rows: list[dict], path: Path, model, budget: float) -> None:
    lines = [
        "# Бейчмарк фрагментов e2k",
        "",
        f"Профиль машины: `{model.name}` ({model.width} портов). "
        f"Точный поиск: бюджет {budget:g} с на файл.",
        "",
        "| файл | N | автор | baseline | TINY Flash | oracle | оптимум | UNKNOWN | ошибки |",
        "|---|---:|---:|---:|---:|---:|---|---:|---:|",
    ]
    for r in rows:
        lines.append(
            f"| `{r['file']}` | {r['ops']} | {r['compiler_cycles']} | "
            f"{r['baseline']} | {r['tiny']} | {r['oracle']} | "
            f"{'да' if r['oracle_optimal'] else 'нет'} | {r['unknown']} | "
            f"{r['errors']} |")
    lines += [
        "",
        "`автор` — длина расписания, как оно написано в файле. Оно может быть",
        "короче законного минимума: линтер показывает места, где результат прочитан",
        "раньше, чем операция его выдаст. `baseline`, `TINY Flash` и `oracle` строят",
        "расписание заново по графу зависимостей и модели машины.",
        "",
        "## Подробности",
        "",
    ]
    for r in rows:
        lines.append(f"### `{r['file']}`")
        lines.append("")
        lines.append(f"- Нижняя граница: {r['lower_bound']} ({r['binding']}); "
                     f"критический путь {r['critical_path']}, "
                     f"ресурсы {r['resource_bound']}.")
        lines.append(f"- Время: baseline {r['ms']['baseline']} мс, "
                     f"TINY Flash {r['ms']['tiny']} мс, "
                     f"oracle {r['ms']['oracle']} мс.")
        if r["compiler_schedule"]:
            lines.append(f"- Расписание компилятора: {r['compiler_cycles']} тактов.")
        else:
            lines.append("- Расписание компилятора не восстановлено: "
                         + (r["compiler_problem"][1] if r["compiler_problem"] else "?"))
        if r["unknown"]:
            names = ", ".join(f"`{k}`" for k in r["unknown_mnemonics"])
            lines.append(f"- UNKNOWN: {r['unknown']} операций ({names}) — "
                         "латентность 1 и любой канал, это заглушка, а не замер.")
        if r["problems"]:
            lines.append("- Замечания линтера:")
            for p in r["problems"][:6]:
                lines.append(f"  - строка {p['line']}: {p['text']}")
        lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="Бейчмарк NEX CLI на фрагментах .s")
    ap.add_argument("paths", nargs="*", help="файлы .s или папки (по умолчанию benchmarks/snippets)")
    ap.add_argument("--profile", default="e2k-v6-measured")
    ap.add_argument("--budget", type=float, default=1.5, help="бюджет oracle, с")
    ap.add_argument("--portfolio", type=float, default=0.4, help="бюджет портфеля oracle, с")
    ap.add_argument("--json", default="benchmarks/results.json")
    ap.add_argument("--md", default="benchmarks/RESULTS.md")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    targets = []
    for raw in (args.paths or ["benchmarks/snippets"]):
        p = Path(raw)
        if not p.is_absolute():
            p = ROOT / p
        if p.is_dir():
            targets.extend(sorted(p.glob("*.s")))
        else:
            targets.append(p)
    if not targets:
        print("нет файлов .s", file=sys.stderr)
        return 2

    model = get_profile(args.profile)
    tiny = TinyFlashScheduler(mode="exact")
    rows = []
    for path in targets:
        if not args.quiet:
            print(f"· {path.name}", file=sys.stderr, flush=True)
        rows.append(run_one(path, model, args.budget, args.portfolio, tiny))

    if not args.quiet:
        print()
        print_table(rows)
        print_details(rows)

    json_path = ROOT / args.json
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps({
        "profile": model.name,
        "budget_s": args.budget,
        "results": rows,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    md_path = ROOT / args.md
    md_path.parent.mkdir(parents=True, exist_ok=True)
    write_markdown(rows, md_path, model, args.budget)

    total = sum(r["ops"] for r in rows)
    wall = sum(r["ms"]["tiny"] + r["ms"]["oracle"] for r in rows)
    print()
    print(f"итого: {len(rows)} файлов, {total} операций, "
          f"TINY Flash + oracle ~ {wall:.0f} мс")
    print(f"сохранено: {args.json}, {args.md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
