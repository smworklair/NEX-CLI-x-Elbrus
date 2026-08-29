#!/usr/bin/env python3
"""Похожа ли синтетика на настоящий вывод lcc — проверка в один запуск.

Компилирует локальным кросс-lcc набор обычных C-программ на -O0/-O2/-O3,
разбирает результат тем же парсером, что и весь проект
(`vliw.core.asm_parser`), и кладёт рядом две картины:

  * словарь операций, на котором обучалась модель (dataset.jsonl и др.);
  * словарь операций, который реально печатает компилятор.

Ничего не скачивает и не отправляет. Все временные файлы — в /tmp.

    python3 tools/check_real_vs_synth.py
"""

from __future__ import annotations

import collections
import itertools
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vliw.core.asm_parser import (                          # noqa: E402
    MNEMONICS, build_dag, compiler_schedule, parse_asm)
from vliw.core.model import get_profile                     # noqa: E402

# ВАЖНО ПРО ЗАМЕР. Незнакомая операция С каналом получает класс UNKNOWN,
# незнакомая БЕЗ канала уходит в управляющие и в граф не попадает (см.
# asm_parser.CONTROL). Поэтому доля чужого считается по `unknown_mnemonics`,
# а не по одному лишь классу: часть незнакомых до графа не доходит вовсе.

# Обычный код, а не подобранный под ответ: цикл с накоплением, плавающая
# точка, ветвление, копирование памяти, хеш строки.
PROGRAMS = {
    "loop":   "int f(int *a,int n){int s=0;for(int i=0;i<n;i++)s+=a[i]*3+1;return s;}",
    "math":   "double g(double x,double y){return (x*y + x/y)*(x - y);}",
    "branch": "int h(int a,int b,int c){if(a>b)return a*c;else if(b>c)return b+c;return a-b-c;}",
    "mem":    "void cp(char *d,const char *s,int n){for(int i=0;i<n;i++)d[i]=s[i];}",
    "str":    "unsigned hs(const char*s){unsigned h=5381;while(*s)h=h*33+(unsigned char)*s++;return h;}",
}
LEVELS = ("0", "2", "3")


def find_lcc() -> Path | None:
    """Кросс-lcc из комплекта МЦСТ. Тот же, которым сняты examples/probes/."""
    for p in sorted(Path.home().glob("e2k-toolchain/opt/mcst/lcc-*/bin/lcc")):
        return p
    return None


def synthetic_mix(name: str, limit: int = 20000):
    """Классы операций в обучающем файле. None — файла нет."""
    path = ROOT / name
    if not path.exists():
        return None
    ops: collections.Counter = collections.Counter()
    sizes = []
    with path.open(encoding="utf-8") as f:
        for line in itertools.islice(f, limit):
            row = json.loads(line)
            k = 0
            for raw in row["prompt"].split("\n")[2:]:
                raw = raw.strip()
                if raw == "расписание:":
                    break
                if not raw:
                    continue
                k += 1
                ops[raw.split(" <- ")[0].split(" ", 1)[1]] += 1
            sizes.append(k)
    return ops, sizes


def main() -> int:
    lcc = find_lcc()
    if lcc is None:
        print("кросс-lcc не найден в ~/e2k-toolchain — компилировать нечем",
              file=sys.stderr)
        return 1
    ver = subprocess.run([str(lcc), "--version"], capture_output=True,
                         text=True).stdout.splitlines()[0]
    print(f"компилятор: {ver}\n")

    machine = get_profile("e2k-v6-measured")
    tmp = Path(tempfile.mkdtemp(prefix="real_vs_synth_"))
    rows = []
    real_ops: collections.Counter = collections.Counter()
    unknown_mn: collections.Counter = collections.Counter()

    for name, src in PROGRAMS.items():
        c = tmp / f"{name}.c"
        c.write_text(src + "\n", encoding="utf-8")
        for lvl in LEVELS:
            s = tmp / f"{name}_O{lvl}.s"
            r = subprocess.run([str(lcc), "-S", f"-O{lvl}", str(c), "-o", str(s)],
                               capture_output=True, text=True)
            if r.returncode != 0 or not s.exists():
                print(f"  {name} -O{lvl}: компилятор отказал", file=sys.stderr)
                continue
            parsed = parse_asm(s.read_text(encoding="utf-8"))
            ops = parsed.ops
            counts = collections.Counter(o.op for o in ops)
            real_ops += counts
            for mn, k in parsed.unknown_mnemonics.items():
                unknown_mn[mn] += k
            n = len(ops) or 1
            unk = sum(1 for o in ops if o.op == "UNKNOWN")
            sched = compiler_schedule(parsed, build_dag(parsed, name), machine)
            rows.append((f"{name}_O{lvl}", len(ops), 100.0 * unk / n,
                         parsed.skipped_lines,
                         "да" if sched is not None else "нет"))

    print("НАСТОЯЩИЙ ВЫВОД lcc")
    print(f"  {'файл':<12}{'операций':>9}{'UNKNOWN':>10}"
          f"{'не разобрано':>14}{'расписание lcc':>16}")
    for name, n, unk, skipped, sched in rows:
        print(f"  {name:<12}{n:>9}{unk:>9.0f}%{skipped:>14}{sched:>16}")

    total = sum(real_ops.values()) or 1
    unk_total = sum(unknown_mn.values())
    print("\n  классы операций у компилятора (как их видит парсер):")
    for op, k in real_ops.most_common():
        print(f"    {op:<10}{k:>6}{100.0 * k / total:>7.1f}%")
    known = total - real_ops.get("UNKNOWN", 0)
    print(f"\n  опознано: {known} из {total} операций "
          f"({100.0 * known / total:.0f}%)")

    print(f"\n  мнемоник в словаре проекта: {len(MNEMONICS)}"
          f"  →  классов: {len(set(MNEMONICS.values()))}")
    if unknown_mn:
        print(f"  незнакомых мнемоник: {len(unknown_mn)} штук, "
              f"{sum(unknown_mn.values())} вхождений")
        print("    " + ", ".join(sorted(unknown_mn)[:24]))

    print("\nСИНТЕТИКА, НА КОТОРОЙ УЧИЛИ")
    for name in ("dataset.jsonl", "train_merged.jsonl", "eval_wide.jsonl"):
        mix = synthetic_mix(name)
        if mix is None:
            print(f"  {name}: нет файла")
            continue
        ops, sizes = mix
        tot = sum(ops.values()) or 1
        print(f"  {name}: графы {min(sizes)}..{max(sizes)} операций, "
              f"классов {len(ops)}")
        print("    " + "  ".join(f"{op} {100.0 * k / tot:.0f}%"
                                 for op, k in ops.most_common()))

    unk_share = 100.0 * real_ops.get("UNKNOWN", 0) / total
    print(f"\nИТОГ: {unk_share:.0f}% операций в графе — UNKNOWN: класс машине "
          f"неизвестен,\nсчитаются с латентностью 1 и любым каналом "
          f"(заглушка, не измерение).")
    print(f"файлы остались в {tmp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
