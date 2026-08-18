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
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Импортируем classify()/_KIND из validate_kaggle.py, а не держим вторую
# ручную копию. Раньше здесь была именно копия — оправдана она была тем, что
# validate_kaggle.py самодостаточен РАДИ KAGGLE (там нет пакета training).
# Но report_runs.py работает только локально, этого ограничения у него нет,
# а validate_kaggle.py на верхнем уровне и так тянет только stdlib (torch и
# соседи — ленивый импорт внутри main()), так что импорт almost free. Копия
# уже расходилась однажды: см. докстринг ниже про дамп от 15.08 22:40 —
# именно тогда classify() в validate_kaggle.py чинили, а старая копия
# осталась бы с прежним (неверным) поведением, если бы она тут была.
from training.validate_kaggle import _KIND, classify              # noqa: E402

KINDS = tuple(_KIND)

# Ярлыки, при которых префикс 0..n-1 законен: расписание настоящих инструкций
# верное, вопрос только в том, остановилась модель или нет. Эта группировка
# не выводится из _KIND автоматически (там корзины "валидно"/"хвост"/"почти"/
# "мимо", а не булев "легален ли префикс") — validate_kaggle.py сам её
# держит явным списком в _print_composition(), здесь то же самое явно.
PREFIX_OK = ("валидно", "хвост")

# Подстрока из текста ошибки "несуществующие id инструкций в ответе модели:
# ...", который печатает Schedule.validate() (через validate_kaggle.py). Не
# импортируется — это не именованная константа там, а текст внутри f-строки;
# трогать структуру validate_kaggle.py ради этого не стоит (самодостаточность
# ради Kaggle). Если формулировка ошибки там изменится, поправить и здесь.
_STRAY = "несуществующие id"


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
            # это поле есть (список настоящих значений); в старых (без
            # "extra") приходится восстанавливать по одним лишь счётчикам —
            # а по счётчикам это ОДНОЗНАЧНО восстановимо только когда модель
            # выдала НЕ МЕНЬШЕ строк, чем в графе (n_decoded >= n_graph):
            # тогда "лишнее сверху" и есть хвост. Если n_decoded < n_graph,
            # формула max(0, n_decoded-n_graph) даёт n_extra=0 независимо от
            # того, СКОЛЬКО из decoded id реально вне графа — 0 или все — и
            # правильный n_keep этим не восстановить (проверено на примере:
            # n_graph=10, decoded={50,51} — реально n_keep=0/"мусор", формула
            # даёт n_keep=2 и классификатор уходит в "галлюцинация"). Честнее
            # не гадать: в этом случае ярлык берём из дампа как есть, не
            # пересчитываем, и помечаем ненадёжным.
            if "extra" in rec:
                n_extra = len(rec["extra"])
                n_keep = max(0, rec["n_decoded"] - n_extra)
                reclassify_this = reclassify
            elif rec["n_decoded"] >= n_graph:
                n_extra = rec["n_decoded"] - n_graph
                n_keep = n_graph
                reclassify_this = reclassify
            else:
                n_extra = n_keep = 0   # не используются — reclassify_this=False
                reclassify_this = False
                self.unreliable += 1

            if reclassify_this:
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


def build_rows(specs: list[tuple[str, Path | None, Path | None]], reclassify: bool
              ) -> tuple[list[tuple[str, Run | None, Run | None]], list[str]]:
    """Загрузить дампы из specs, попутно печатая состав ошибок каждого."""
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
    return rows, missing


def report(specs: list[tuple[str, Path | None, Path | None]], reclassify: bool = True) -> bool:
    """Свести дампы в таблицу с дельтами. True — нашлось хоть что-то.

    Вынесено из main() отдельно, чтобы `vliw/cli.py` (команда `/report`) могло
    вызвать ровно ту же сводку в процессе, без второго питона subprocess'ом.
    """
    rows, missing = build_rows(specs, reclassify)
    if not rows:
        return False

    print_matrix(rows)
    print_by_size(rows)

    if missing:
        print(f"\nещё не прогнано: {', '.join(missing)}")
    if reclassify:
        print("\nЯрлыки пересчитаны текущим classify() — с ярлыками из дампа "
              "сравнение было бы нечестным (см. докстринг).")
    return True


def default_specs(checkpoints_dir: Path) -> list[tuple[str, Path | None, Path | None]]:
    """specs для «обычного цикла» — по именам из RUNBOOK_EOS.md."""
    specs = []
    for name, narrow, wide in DEFAULT_RUNS:
        p, w = checkpoints_dir / narrow, checkpoints_dir / wide
        specs.append((name, p if p.exists() else None, w if w.exists() else None))
    return specs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", action="append", nargs="+", metavar=("ИМЯ ДАМП"),
                    help="ИМЯ дамп_eval [дамп_eval_wide]; можно несколько раз")
    ap.add_argument("--dir", type=Path, default=Path("training/checkpoints"),
                    help="где искать дампы, если --run не задан")
    ap.add_argument("--as-dumped", action="store_true",
                    help="взять ярлыки из дампа как есть, без пересчёта "
                         "(осторожно: старые дампы путают хвост с галлюцинацией)")
    args = ap.parse_args(argv)

    reclassify = not args.as_dumped
    specs: list[tuple[str, Path | None, Path | None]] = []

    if args.run:
        for item in args.run:
            if len(item) < 2:
                print(f"--run нужен хотя бы ИМЯ и один дамп: {item}", file=sys.stderr)
                return 1
            name, narrow, *rest = item
            specs.append((name, Path(narrow), Path(rest[0]) if rest else None))
    else:
        specs = default_specs(args.dir)

    if not report(specs, reclassify):
        print(f"дампов не найдено в {args.dir}. Забери их с Kaggle "
              f"(--dump в validate_kaggle.py) или укажи пути через --run.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
