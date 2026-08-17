"""Сведение дампов validate_kaggle.py в таблицу сравнения прогонов.

Зачем скрипт, а не глазами
--------------------------
Дампы приходят с Kaggle по одному на прогон и эвал — шесть файлов на схему
из RUNBOOK_EOS.md. Свести их руками можно, но именно там и появляется ошибка,
которую потом никто не заметит: категорий шесть, прогонов три, эвала два.

И главное: **ярлыки в дампе нельзя брать на веру**. Категория `kind`
записана тем классификатором, что работал в момент прогона. Дамп от 15.08
22:40 сделан версией, которая не отделяла «хвост» от «галлюцинации» — она
записала 24 законных префикса в безнадёжные (60% «галлюцинаций», хотя
настоящих дыр в id не было ни одной). Сравнение такого дампа со свежим дало
бы «прирост», наполовину состоящий из смены ярлыков.

Поэтому скрипт по умолчанию **пересчитывает kind заново** из `errs`
логикой текущего `classify()` и сообщает, где ярлык разошёлся с записанным.

    python tools/report_runs.py                     # ищет файлы по именам из runbook
    python tools/report_runs.py --run "0. без EOS" base_eval.jsonl base_eval_wide.jsonl \
                                --run "1. +EOS"    eos_eval.jsonl  eos_eval_wide.jsonl

Печатает три вещи: состав ошибок по каждому дампу, сводную таблицу
прогон × эвал, и разбивку широкого эвала по размеру графа — последняя
отвечает на вопрос, ради которого он и заводился: что происходит на графах
18..24, которых в старом эвале нет.
"""

from __future__ import annotations

import argparse
import collections
import json
import re
from pathlib import Path

KINDS = ("валидно", "хвост", "сдвиг", "ресурс", "галлюцинация", "мусор")

# Ярлыки, при которых префикс 0..n-1 законен: расписание настоящих инструкций
# верное, вопрос только в том, остановилась модель или нет.
PREFIX_OK = ("валидно", "хвост")

_STRAY = "несуществующие id"


def classify(errs: list[str], n_keep: int, n_extra: int) -> str:
    """Копия classify() из validate_kaggle.py — ярлык по ПРЕФИКСУ.

    Держится копией намеренно: validate_kaggle.py самодостаточен ради Kaggle
    и импортировать из него нечего, а тащить сюда его целиком незачем.
    """
    if n_keep == 0:
        return "мусор"
    if any(e.startswith("не размещены") for e in errs):
        return "галлюцинация"
    if not errs:
        return "хвост" if n_extra else "валидно"
    if any("выдана в" in e for e in errs):
        return "сдвиг"
    return "ресурс"


class Run:
    """Один дамп: состав ошибок, разрывы, разбивка по размеру графа."""

    def __init__(self, path: Path, reclassify: bool = True):
        self.path = path
        self.total = 0
        self.counts: collections.Counter = collections.Counter()
        self.gaps: list[int] = []
        self.by_n: dict[int, list[bool]] = collections.defaultdict(list)
        self.relabelled: collections.Counter = collections.Counter()
        self.unreliable = 0

        for line in path.open(encoding="utf-8"):
            if not line.strip():
                continue
            rec = json.loads(line)
            self.total += 1
            n_graph = rec["n_graph"]
            errs = rec.get("errs", [])

            # Сколько строк ответа пришлось на id вне графа. В свежих дампах
            # это поле есть; в старых восстанавливаем по разнице.
            if "extra" in rec:
                n_extra = len(rec["extra"])
            else:
                n_extra = max(0, rec["n_decoded"] - n_graph)
            n_keep = max(0, rec["n_decoded"] - n_extra)

            if reclassify:
                # Ошибки про лишние id к префиксу отношения не имеют.
                pref_errs = [e for e in errs if _STRAY not in e]
                # Страховка: в старых дампах errs считались по ВСЕМУ ответу,
                # и нарушение теоретически могло быть завязано на выдуманный
                # id — тогда пересчёт префикса неверен. Ловим и считаем.
                for e in pref_errs:
                    head = re.match(r"\D*(\d+)", e)
                    if head and int(head.group(1)) >= n_graph:
                        self.unreliable += 1
                        break
                kind = classify(pref_errs, n_keep, n_extra)
                if kind != rec.get("kind"):
                    self.relabelled[f"{rec.get('kind')} -> {kind}"] += 1
            else:
                kind = rec["kind"]

            self.counts[kind] += 1
            self.by_n[n_graph].append(kind == "валидно")
            if kind in PREFIX_OK and rec.get("gap") is not None:
                self.gaps.append(rec["gap"])

    # --- производные метрики ---------------------------------------------

    @property
    def valid(self) -> int:
        return self.counts["валидно"]

    @property
    def prefix_ok(self) -> int:
        return sum(self.counts[k] for k in PREFIX_OK)

    def pct(self, n: int) -> float:
        return 100.0 * n / self.total if self.total else 0.0

    @property
    def exact(self) -> int:
        return sum(1 for g in self.gaps if g == 0)


def print_composition(name: str, run: Run) -> None:
    print(f"\n{name}  —  {run.path.name}  ({run.total} примеров)")
    for k in KINDS:
        n = run.counts[k]
        if n:
            print(f"    {k:<14} {n:>4}  ({run.pct(n):>5.1f}%)")
    print(f"    {'-'*36}")
    print(f"    {'валидно':<14} {run.valid:>4}  ({run.pct(run.valid):>5.1f}%)"
          f"   префикс законен: {run.prefix_ok} ({run.pct(run.prefix_ok):.1f}%)")
    if run.gaps:
        avg = sum(run.gaps) / len(run.gaps)
        print(f"    разрыв до оптимума среди законных префиксов: "
              f"{avg:.2f} такта, точно оптимальных {run.exact}/{len(run.gaps)}")
    if run.relabelled:
        print("    ПЕРЕКЛАССИФИЦИРОВАНО (ярлык в дампе устарел):")
        for change, n in run.relabelled.most_common():
            print(f"        {n:>4}  {change}")
    if run.unreliable:
        print(f"    !! {run.unreliable} записей, где нарушение завязано на id вне "
              f"графа — пересчёт префикса для них ненадёжен")


def print_matrix(rows: list[tuple[str, Run | None, Run | None]]) -> None:
    print("\n" + "=" * 78)
    print("СВОДНАЯ ТАБЛИЦА: валидно % (префикс законен %)")
    print("=" * 78)
    print(f"{'прогон':<34} {'eval.jsonl 6..14':>20} {'eval_wide 4..24':>20}")
    print("-" * 78)

    def cell(r: Run | None) -> str:
        if r is None:
            return f"{'—':>20}"
        return f"{r.pct(r.valid):>11.1f}% ({r.pct(r.prefix_ok):.0f}%)"

    for name, narrow, wide in rows:
        print(f"{name:<34} {cell(narrow):>20} {cell(wide):>20}")

    # Дельты между соседними прогонами — то, ради чего прогонов три, а не один.
    print("-" * 78)
    labels = ["стоимость EOS-бага (0 -> 1)", "вклад новых данных (1 -> 2)"]
    for i in range(len(rows) - 1):
        (_, n0, w0), (_, n1, w1) = rows[i], rows[i + 1]
        lab = labels[i] if i < len(labels) else f"{i} -> {i+1}"

        def delta(a: Run | None, b: Run | None) -> str:
            if a is None or b is None:
                return f"{'—':>20}"
            d = b.pct(b.valid) - a.pct(a.valid)
            return f"{d:>+19.1f}п"

        print(f"{lab:<34} {delta(n0, n1):>20} {delta(w0, w1):>20}")


def print_by_size(rows: list[tuple[str, Run | None, Run | None]]) -> None:
    """Широкий эвал по размеру графа — ради этого он и заводился."""
    wides = [(name, w) for name, _, w in rows if w is not None]
    if not wides:
        return
    buckets = [(4, 7), (8, 11), (12, 15), (16, 19), (20, 24)]
    w = 30 + 12 * len(buckets)
    print("\n" + "=" * w)
    print("ШИРОКИЙ ЭВАЛ ПО РАЗМЕРУ ГРАФА: валидно %")
    print("(старый eval.jsonl покрывает только 6..14 — правые корзины он не видит)")
    print("=" * w)
    head = "".join(f"{f'{lo}..{hi}':>12}" for lo, hi in buckets)
    print(f"{'прогон':<30}{head}")
    print("-" * w)
    for name, run in wides:
        cells = ""
        for lo, hi in buckets:
            vals = [v for n, vs in run.by_n.items() if lo <= n <= hi for v in vs]
            cells += f"{'—':>12}" if not vals else \
                f"{100.0 * sum(vals) / len(vals):>11.0f}%"
        print(f"{name:<30}{cells}")
    print(f"{'(примеров в корзине)':<30}" + "".join(
        f"{sum(1 for n, vs in wides[0][1].by_n.items() if lo <= n <= hi for _ in vs):>12}"
        for lo, hi in buckets))


# Имена из RUNBOOK_EOS.md — чтобы обычный случай запускался без аргументов.
DEFAULT_RUNS = [
    ("0. текущий адаптер (без EOS)", "base_eval.jsonl", "base_eval_wide.jsonl"),
    ("1. + EOS, старые данные", "eos_eval.jsonl", "eos_eval_wide.jsonl"),
    ("2. + EOS, слитые данные", "merged_eval.jsonl", "merged_eval_wide.jsonl"),
]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", action="append", nargs="+", metavar=("ИМЯ ДАМП"),
                    help="ИМЯ дамп_eval [дамп_eval_wide]; можно несколько раз")
    ap.add_argument("--dir", type=Path, default=Path("training/checkpoints"),
                    help="где искать дампы, если --run не задан")
    ap.add_argument("--as-dumped", action="store_true",
                    help="взять ярлыки из дампа как есть, без пересчёта "
                         "(осторожно: старые дампы путают хвост с галлюцинацией)")
    args = ap.parse_args()

    reclassify = not args.as_dumped
    specs: list[tuple[str, Path | None, Path | None]] = []

    if args.run:
        for item in args.run:
            if len(item) < 2:
                raise SystemExit(f"--run нужен хотя бы ИМЯ и один дамп: {item}")
            name, narrow, *rest = item
            specs.append((name, Path(narrow), Path(rest[0]) if rest else None))
    else:
        for name, narrow, wide in DEFAULT_RUNS:
            p, w = args.dir / narrow, args.dir / wide
            specs.append((name, p if p.exists() else None, w if w.exists() else None))

    rows: list[tuple[str, Run | None, Run | None]] = []
    missing: list[str] = []
    for name, narrow, wide in specs:
        r_n = Run(narrow, reclassify) if narrow and narrow.exists() else None
        r_w = Run(wide, reclassify) if wide and wide.exists() else None
        if r_n is None and r_w is None:
            missing.append(name)
            continue
        rows.append((name, r_n, r_w))
        if r_n:
            print_composition(name + "  [eval 6..14]", r_n)
        if r_w:
            print_composition(name + "  [eval_wide 4..24]", r_w)

    if not rows:
        raise SystemExit(
            f"дампов не найдено в {args.dir}. Забери их с Kaggle "
            f"(--dump в validate_kaggle.py) или укажи пути через --run.")

    print_matrix(rows)
    print_by_size(rows)

    if missing:
        print(f"\nещё не прогнано: {', '.join(missing)}")
    if reclassify:
        print("\nЯрлыки пересчитаны текущим classify() — с ярлыками из дампа "
              "сравнение было бы нечестным (см. докстринг).")


if __name__ == "__main__":
    main()
