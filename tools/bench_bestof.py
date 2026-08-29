"""Замер best-of-N на подвыборке eval_wide.jsonl — источник таблицы в docs/LEARNED.md.

Зачем отдельный скрипт, а не `/learned --bench`: замер идёт часами, и ему
нужны две вещи, которых у CLI-команды не должно быть — подвыборка файла
(каждый 4-й граф: полный файл — это сутки на температуру) и дамп прогресса
в JSON после КАЖДОЙ строки, чтобы сбой на двенадцатом часу не терял
полученное.

Считает четыре прогона на одних и тех же графах:
  * baseline — t=0, один жадный ответ, repair включён (точка сравнения из
    docs/LEARNED.md: 27% на первых 15; здесь — на тех же 75, что и best-of);
  * best-of-8 при t=0.4 / 0.7 / 1.0 — сэмплы k=0..7, каждому repair,
    выбор по минимуму нарушений, потом makespan.

Прогон с N=8 отвечает сразу на все k<=8 (первые k сэмплов) — отдельные
забеги для best-of-2 и best-of-4 не нужны, таблица строится из одного дампа.

Запуск (часы; в фоне — nohup):
    .venv/bin/python tools/bench_bestof.py [out.json]
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

STRIDE = 4
"""Каждый 4-й граф из 300: 75 примеров, репрезентативно по всему файлу."""

N = 8
TEMPERATURES = (0.4, 0.7, 1.0)
SEED = 1


def make_subset(src: Path, out: Path, stride: int) -> int:
    """Каждый stride-й пример в отдельный файл. Возвращает число строк."""
    lines = [l for l in src.read_text(encoding="utf-8").splitlines()
             if l.strip()]
    picked = lines[::stride]
    out.write_text("\n".join(picked) + "\n", encoding="utf-8")
    return len(picked)


def dump_bench(res, path: Path) -> None:
    """BenchResult → JSON. Сэмплы каждой строки — тоже: по ним строится
    таблица k=1,2,4,8 без повторных прогонов."""
    data = {
        "seconds": res.seconds,
        "best_of": ({"n": res.best_of.n, "temperature": res.best_of.temperature,
                     "seed": res.best_of.seed} if res.best_of else None),
        "rows": [{
            "n": r.n, "kind": r.kind, "has_store": r.has_store,
            "gap": r.gap, "first_error": r.first_error,
            "samples": None if r.samples is None else [{
                "valid": s.valid, "errors": s.errors, "missing": s.missing,
                "makespan": s.makespan, "gap": s.gap,
            } for s in r.samples],
        } for r in res.rows],
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                    encoding="utf-8")


def load_rows(path: Path) -> list:
    """Готовые строки из дампа обратно в BenchRow — для возобновления.

    Читается ровно то, что писал `dump_bench`; при любой порче дампа
    возвращается пустой список, и прогон считается с нуля — это безопаснее,
    чем досчитывать поверх испорченного.
    """
    from vliw.learned.bench import BenchRow, SampleOutcome

    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        out = []
        for r in data["rows"]:
            samples = None if r.get("samples") is None else [
                SampleOutcome(valid=s["valid"], errors=s["errors"],
                              missing=s["missing"], makespan=s["makespan"],
                              gap=s["gap"]) for s in r["samples"]]
            out.append(BenchRow(n=r["n"], kind=r["kind"],
                                has_store=r["has_store"], gap=r["gap"],
                                first_error=r["first_error"], samples=samples))
        return out
    except (ValueError, KeyError, TypeError):
        return []


def _fmt_row(k: int, row) -> str:
    mark = "ok " if row.kind == "валидно" else "…  "
    extra = f"сэмплы {row.valid_samples}/{len(row.samples)}" if row.samples else ""
    return (f"  [{k:>3}] {mark} n={row.n:<3} {row.kind:<9} {extra} "
            + (row.first_error or "")[:60])


def summary(out_dir: Path) -> int:
    """Таблица по готовым дампам: доля валидных по k против baseline.

    Вынесено в отдельный режим, потому что таблица нужна ПОСЛЕ многочасового
    прогона, а сам прогон трогать уже нельзя (и не надо — все сэмплы уже
    лежат в дампах).
    """
    tags = ["baseline"] + [f"t{t:g}" for t in TEMPERATURES]
    dumps = {}
    for tag in tags:
        p = out_dir / f"bestof_{tag}.json"
        if p.exists():
            dumps[tag] = json.loads(p.read_text(encoding="utf-8"))
    if not dumps:
        print(f"в {out_dir} нет дампов — прогон ещё не начат", file=sys.stderr)
        return 1

    rows_n = {len(d["rows"]) for d in dumps.values()}
    print(f"# best-of на подвыборке eval_wide.jsonl (каждый {STRIDE}-й)")
    if len(rows_n) > 1:
        print(f"ВНИМАНИЕ: прогон завершён не везде, строк: {sorted(rows_n)}")
    n = min(rows_n)

    def valid_at(tag: str, k: int) -> int:
        return sum(1 for r in dumps[tag]["rows"][:n]
                   if any(s["valid"] for s in (r["samples"] or [])[:k]))

    def gap_mean(tag: str, k: int) -> float | None:
        """Средний разрыв выбранных валидных расписаний среди первых k."""
        gaps = []
        for r in dumps[tag]["rows"][:n]:
            ok = [s for s in (r["samples"] or [])[:k] if s["valid"]]
            if ok:
                gaps.append(min(s["gap"] for s in ok if s["gap"] is not None))
        return sum(gaps) / len(gaps) if gaps else None

    ks = sorted({1, 2, 4, N})
    print(f"\nграфов в сравнении: {n}\n")
    header = "| прогон | " + " | ".join(f"best-of-{k}" for k in ks) + " |"
    print(header)
    print("|---|" + "---|" * len(ks))
    for tag in tags:
        if tag not in dumps:
            continue
        if tag == "baseline":
            v = dumps[tag]["rows"][:n]
            ok = sum(1 for r in v if r["kind"] == "валидно")
            print(f"| baseline (t=0, жадный) | {ok}/{n} " + "| " * (len(ks) - 1) + "|")
            continue
        cells = []
        for k in ks:
            ok = valid_at(tag, k)
            cells.append(f"{ok}/{n} ({100 * ok / n:.0f}%)")
        print(f"| t={dumps[tag]['best_of']['temperature']:g} | "
              + " | ".join(cells) + " |")

    print("\nсредний разрыв до оптимума среди валидных (такты):")
    for tag in tags:
        if tag == "baseline" or tag not in dumps:
            continue
        cells = []
        for k in ks:
            g = gap_mean(tag, k)
            cells.append("—" if g is None else f"{g:.2f}")
        print(f"  t={dumps[tag]['best_of']['temperature']:g}: "
              + "  ".join(f"k={k}: {c}" for k, c in zip(ks, cells)))

    # Качество одного сэмпла — база для честного «даёт ли best-of что-то
    # сверх первого сэмпла».
    print("\nдоля валидных сэмплов (качество ОДНОГО сэмпла):")
    for tag in tags:
        if tag == "baseline" or tag not in dumps:
            continue
        total = ok = 0
        for r in dumps[tag]["rows"][:n]:
            for s in r["samples"] or ():
                total += 1
                ok += s["valid"]
        if total:
            print(f"  t={dumps[tag]['best_of']['temperature']:g}: "
                  f"{ok}/{total} ({100 * ok / total:.0f}%)")
    return 0


def main() -> int:
    from vliw.learned.bench import BestOf, BenchResult, run_bench
    from vliw.core import get_profile
    from vliw.learned import runtime
    from vliw.learned.scheduler import LearnedScheduler

    src = ROOT / "eval_wide.jsonl"
    if not src.exists():
        print(f"нет {src}", file=sys.stderr)
        return 1
    out_dir = ROOT / "build" / "bestof"
    out_dir.mkdir(parents=True, exist_ok=True)
    dataset = out_dir / f"eval_wide_s{STRIDE}.jsonl"
    total = make_subset(src, dataset, STRIDE)
    print(f"подвыборка: каждый {STRIDE}-й из {src.name} -> {total} примеров",
          flush=True)

    machine = get_profile("e2k-v6-measured")
    adapter = runtime.resolve_adapter("lora-eos")
    if adapter is None:
        print("адаптер lora-eos не найден", file=sys.stderr)
        return 1

    # Один и тот же планировщик на все прогоны: бэкенд (llama-server с
    # весами) поднимается один раз, между прогонами меняются только
    # temperature/seed.
    sch = LearnedScheduler(adapter=adapter, repair=True)

    jobs = [("baseline", None)]
    jobs += [(f"t{t:g}", BestOf(n=N, temperature=t, seed=SEED))
             for t in TEMPERATURES]

    for tag, bo in jobs:
        print(f"\n=== {tag} ===", flush=True)
        dump = out_dir / f"bestof_{tag}.json"

        # Возобновление. Замер идёт часами и уже один раз оборвался на
        # середине (перезапуск WSL). Дамп построчный, значит досчитывать
        # можно ровно с той строки, на которой оборвалось: готовые строки
        # читаются обратно, датасет режется с этого места, результаты
        # склеиваются. Порядок строк сохраняется — иначе таблица k=1,2,4,8
        # поехала бы относительно baseline.
        done_rows = load_rows(dump)
        if len(done_rows) >= total:
            print(f"  уже посчитано {len(done_rows)}/{total} — пропускаю",
                  flush=True)
            continue
        run_from = dataset
        if done_rows:
            print(f"  в дампе {len(done_rows)}/{total} — досчитываю остаток",
                  flush=True)
            rest = out_dir / f"rest_{tag}.jsonl"
            lines = [l for l in dataset.read_text(encoding="utf-8").splitlines()
                     if l.strip()]
            rest.write_text("\n".join(lines[len(done_rows):]) + "\n",
                            encoding="utf-8")
            run_from = rest

        t0 = time.time()

        # Явный сброс на baseline: bench меняет атрибуты планировщика под
        # best-of, и без сбоя порядок прогонов когда-нибудь сделает «жадный»
        # baseline сэмплированным — молча.
        if bo is None:
            sch.temperature, sch.seed = 0.0, None

        # Дамп после КАЖДОЙ строки: двенадцатый час прогона нельзя терять
        # из-за одного сбоя. Частичный результат — те же строки, что у
        # финального, просто ещё не все.
        partial = BenchResult(best_of=bo)
        partial.rows.extend(done_rows)

        def on_row(k, row):
            partial.rows.append(row)
            partial.seconds = time.time() - t0
            print(_fmt_row(len(partial.rows), row), flush=True)
            dump_bench(partial, dump)

        res = run_bench(run_from, total - len(done_rows), sch, machine,
                        on_row, best_of=bo)
        res.rows = done_rows + res.rows
        res.seconds = time.time() - t0
        dump_bench(res, dump)
        print(f"--- {tag}: {res.valid}/{len(res.rows)} валидно, "
              f"{res.seconds / 60:.0f} мин", flush=True)

    print("\nвсе прогоны закончены:", flush=True)
    for tag, _ in jobs:
        print(f"  {out_dir / ('bestof_' + tag + '.json')}", flush=True)
    return 0


if __name__ == "__main__":
    out_dir = ROOT / "build" / "bestof"
    if len(sys.argv) > 1 and sys.argv[1] == "summary":
        raise SystemExit(summary(out_dir))
    raise SystemExit(main())
