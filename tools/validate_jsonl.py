"""Проверка датасета настоящим валидатором проекта.

Прогоняет каждую строку jsonl (`prompt` + `completion`) через
`Schedule.validate()` из `vliw.core` — не через копию логики в генераторе и не
через самодостаточный `validate_kaggle.py`. Смысл именно в этом: если модель
мира в генераторе разъедется с `vliw/core/model.py`, увидно будет здесь.

Печатается только сводка — файл на 20 000 строк целиком читать незачем:

    python tools/validate_jsonl.py dataset.jsonl vliw_train_extra_fixed.jsonl

Разрыв до оптимума = makespan построенного расписания минус `meta.makespan`.
Для примеров, где расписание считалось CP-SAT'ом, `meta.makespan` — доказанный
минимум, поэтому разрыв обязан быть нулевым.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from training.encode import decode_completion                      # noqa: E402
from vliw.core.dag import DAG, Instr                               # noqa: E402
from vliw.core.model import DEFAULT_PROFILE, get_profile           # noqa: E402
from vliw.core.schedule import Schedule                            # noqa: E402


def parse_prompt(prompt: str) -> list[Instr]:
    """Промпт → инструкции. Шапка (2 строки) и хвост `расписание:` отбрасываются."""
    instrs: list[Instr] = []
    for line in prompt.split("\n")[2:]:
        line = line.strip()
        if line == "расписание:":
            break
        if not line:
            continue
        head, _, preds_s = line.partition(" <- ")
        idx_s, _, op = head.partition(" ")
        preds = tuple(int(p) for p in preds_s.split()) if preds_s else ()
        i = int(idx_s)
        instrs.append(Instr(i, f"n{i}", op, preds, f"n{i}"))
    return instrs


def check_file(path: Path, profile: str, show: int) -> bool:
    model = get_profile(profile)
    n = bad = 0
    gaps: list[int] = []
    shown = 0
    reasons: dict[str, int] = {}
    n_instr_min = n_instr_max = None

    with path.open(encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            if not line.strip():
                continue
            n += 1
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                # Номер строки печатаем СВОЙ, а не exc.lineno: разбираем по
                # строке за раз, и внутри одной строки парсер всегда видит
                # первую — на файле в 20 000 строк «строка 1» бесполезна.
                print(f"\n{path.name}: строка {lineno} не разбирается как "
                      f"JSON ({exc.msg}).")
                print("  здесь ждут по одному JSON-объекту на строку")
                return False
            instrs = parse_prompt(row["prompt"])
            decoded = decode_completion(row["completion"])

            sched = Schedule(DAG(path.name, path.name, "", instrs), model)
            for i, (cycle, ch) in decoded.items():
                if 0 <= i < len(instrs):
                    sched.place(i, cycle, ch)

            errs = sched.validate()
            meta_n = row.get("meta", {}).get("n")
            if meta_n is not None and meta_n != len(instrs):
                errs = errs + [f"граф разобран не целиком: {len(instrs)} из {meta_n}"]
            stray = sorted(i for i in decoded if not (0 <= i < len(instrs)))
            if stray:
                errs = errs + [f"id вне графа в ответе: {stray}"]

            if errs:
                bad += 1
                reasons[errs[0].split(":")[0][:48]] = \
                    reasons.get(errs[0].split(":")[0][:48], 0) + 1
                if shown < show:
                    shown += 1
                    print(f"  [строка {lineno}] {errs[:3]}")
                continue

            k = len(instrs)
            n_instr_min = k if n_instr_min is None else min(n_instr_min, k)
            n_instr_max = k if n_instr_max is None else max(n_instr_max, k)
            if "makespan" in row.get("meta", {}):
                gaps.append(sched.makespan - row["meta"]["makespan"])

    # Пустой файл — это не «всё в порядке». Обрезанный при копировании или
    # недокачанный датасет проходил как «ИТОГ: ОК» с нулём примеров, и
    # проверка молча подтверждала то, чего не проверяла.
    if n == 0:
        print(f"\n{path.name}  (профиль {model.name})")
        print("  примеров:             0")
        print("  ИТОГ: ПУСТО — проверять нечего, ни одного примера в файле")
        return False

    print(f"\n{path.name}  (профиль {model.name})")
    print(f"  примеров:             {n}")
    print(f"  невалидных:           {bad}")
    if reasons:
        for r, k in sorted(reasons.items(), key=lambda kv: -kv[1]):
            print(f"      {k:>6}  {r}")
    if gaps:
        avg = sum(gaps) / len(gaps)
        print(f"  разрыв до оптимума:   min={min(gaps)} max={max(gaps)} "
              f"среднее={avg:.4f}  (посчитан у {len(gaps)})")
        worse = sum(1 for g in gaps if g > 0)
        better = sum(1 for g in gaps if g < 0)
        if worse or better:
            print(f"      хуже meta: {worse}, лучше meta: {better} "
                  f"(<0 значит meta.makespan не оптимум)")
    if n_instr_min is not None:
        print(f"  инструкций в графе:   {n_instr_min}..{n_instr_max}")

    ok = bad == 0 and (not gaps or max(gaps) == 0)
    print(f"  ИТОГ: {'ОК' if ok else 'ЕСТЬ ПРОБЛЕМЫ'}")
    return ok


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--profile", default=DEFAULT_PROFILE)
    ap.add_argument("--show", type=int, default=3,
                    help="сколько первых сбойных примеров распечатать")
    args = ap.parse_args(argv)

    ok = all([check_file(p, args.profile, args.show) for p in args.files])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
