"""Переснять матрицу портов у ассемблера и сверить с vliw/core/model.py.

Это тот же приём, которым матрица снималась изначально (см. шапку
`vliw/core/model.py`), но выполненный целиком автоматически и за секунды:
для каждой пары (операция, канал) собирается минимальная широкая команда с
этой операцией ровно в этом канале и отдаётся ассемблеру. Если аппаратно так
нельзя, `as` отвечает прямым отказом:

    Error: `muls' cannot be encoded in ALC2

Это ответ про САМО ЖЕЛЕЗО — про кодировку широкой команды, — а не про то, что
решил сделать планировщик компилятора. Тем и ценен: вывод `lcc -O3` показывает
лишь то, что компилятор ЗАХОТЕЛ, и именно на этом первая версия модели
ошиблась, приписав умножителю монополию.

Зачем гонять повторно, если матрица уже снята: она — источник истины для
генератора датасета, валидатора и профиля e2k-v6-measured. Проверка стоит
секунд, а расхождение обесценивает всё, что на ней построено.

ВТОРАЯ ПРОБА — СОЧЕТАНИЯ. Матрица портов отвечает на вопрос «исполнима ли
операция в этом канале», по одной операции за раз. Но у машины есть и второй,
независимый класс ограничений: две операции, каждая из которых по отдельности
законна, вместе в одну широкую команду не кодируются. Тем же приёмом (собрать
и посмотреть, примет ли ассемблер) перебираются все пары — и находятся ровно
два запрета, оба на «швах» между кластерами каналов. Подробности и вывод из
этого — у EXPECTED_COMBO_BANS ниже.

    python tools/probe_matrix.py            # снять и сверить (матрица + сочетания)
    python tools/probe_matrix.py --show     # плюс таблица целиком

То же самое одной командой инструмента: `python -m vliw verify`.

Компилятор ставится не в проект: путь ищется по обычным местам, переопределяется
переменной окружения `E2K_AS`. Если ассемблера нет — скрипт не падает, а
сообщает, что проверить нечем (код возврата 0: на машине без тулчейна это не
провал сборки, а отсутствие возможности).
"""

from __future__ import annotations

import argparse
import itertools
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from vliw.core.model import E2K_V6_MEASURED as MODEL  # noqa: E402

# Класс операции модели → мнемоника lcc и форма операндов. Мнемоники ровно те,
# что стоят в шапке model.py: разночтения между «моделью» и «железом» не должно
# возникать из-за того, что проверили не ту инструкцию.
#
# `{c}` — номер канала, `{d}` — регистр-приёмник. Приёмник параметризован ради
# попарной пробы ниже: две операции в одной широкой команде должны писать в
# РАЗНЫЕ регистры, иначе ассемблер откажет по конфликту приёмника, и это
# неотличимо от запрета на само сочетание.
OPS = {
    "ADD":   "adds,{c}\t%r3, %r4, %r{d}",
    "SUB":   "subs,{c}\t%r3, %r4, %r{d}",
    "AND":   "ands,{c}\t%r3, %r4, %r{d}",
    "SHL":   "shls,{c}\t%r3, %r4, %r{d}",
    "MUL":   "muls,{c}\t%r3, %r4, %r{d}",
    "DIV":   "sdivs,{c}\t%r3, %r4, %r{d}",
    "LOAD":  "ldw,{c}\t0x0, [ _f64,_lts0 a ], %r{d}",
    # У записи форма операндов другая: база, смещение, значение — и значение
    # обязано быть регистром. С литеральным адресом, как у загрузки, ассемблер
    # отвечает «Register should be specified for SRC3», то есть отказывает по
    # синтаксису, а не по каналу. Проверка на такой отказ ниже не зря: иначе
    # опечатка в мнемонике выглядела бы как «порт не поддерживает операцию».
    "STORE": "stw,{c}\t%dr2, 0x0, %r{d}",
}

# Операции, которыми представлен каждый класс при попарной пробе. ADD берётся
# за всю простую арифметику (SUB/AND/SHL кодируются так же и дали бы те же
# ответы) — иначе перебор раздувается вчетверо без новой информации.
PAIR_REPS = ("ADD", "MUL", "DIV", "LOAD", "STORE")

# ОЖИДАЕМЫЕ запреты на СОЧЕТАНИЯ операций в одной широкой команде.
#
# Матрица портов отвечает на вопрос «исполнима ли операция в этом канале».
# Но у e2k есть и ВТОРОЙ, независимый класс ограничений: две операции, каждая
# из которых по отдельности законна в своём канале, вместе в одну широкую
# команду не кодируются. Ассемблер знает ровно два таких запрета:
#
#     the combination of STORE in ALC2 with LOAD in ALC3 is prohibited
#     the combination of STORE in ALC5 with LOAD in ALC0 is prohibited
#
# Оба лежат на «швах» между кластерами каналов (ALC0-2 и ALC3-5): запись в
# последнем канале одного кластера не сочетается с загрузкой в первом канале
# соседнего. Это и есть кластерность машины — но проявленная как СТРУКТУРНЫЙ
# ЗАПРЕТ в широкой команде, а не как межкластерная задержка.
#
# ВНИМАНИЕ: в vliw/core/model.py этого ограничения СЕЙЧАС НЕТ — модель знает
# только матрицу «порт → операции». Расхождение известное и намеренно
# зафиксировано здесь, а не замолчано: см. раздел в examples/probes/README.md.
EXPECTED_COMBO_BANS: set[tuple[tuple[str, int], tuple[str, int]]] = {
    (("STORE", 2), ("LOAD", 3)),
    (("STORE", 5), ("LOAD", 0)),
}

# Минимальная законная программа: пролог (setwd), одна проверяемая широкая
# команда, эпилог. Меньше — ассемблер ругается уже на структуру, и отказ
# нельзя будет отличить от отказа по каналу.
SKELETON = """\
\t.text
\t.global\tmain
\t.type\tmain, #function
\t.align\t8
main:
\t{{
\t  setwd\twsz = 0xc, nfx = 0x1, dbl = 0x0
\t}}
\t{{
{body}
\t}}
\t{{
\t  return\t%ctpr3
\t}}
\t{{
\t  ct\t%ctpr3
\t}}
\t.data
\t.global\ta
\t.type\ta, #object
\t.align\t16
a:
\t.uadword\t0x0
"""

CANDIDATES = [
    "~/e2k-toolchain/opt/mcst/lcc-1.29.16.e2k-v6.linux-6.1/bin.toolchain/e2k-linux-as",
    "~/e2k-toolchain/opt/mcst/*/bin.toolchain/e2k-linux-as",
]


def find_as() -> str | None:
    env = os.environ.get("E2K_AS")
    if env and Path(env).exists():
        return env
    for pat in CANDIDATES:
        for p in sorted(Path(os.path.expanduser("/")).glob(pat.lstrip("~/").lstrip("/"))
                        if "*" in pat else []):
            if p.exists():
                return str(p)
        p = Path(os.path.expanduser(pat))
        if "*" not in pat and p.exists():
            return str(p)
    return shutil.which("e2k-linux-as")


def _assemble(as_bin: str, body: str, tmp: Path, tag: str) -> tuple[bool, str]:
    """Собрать одну широкую команду. Возвращает (принято, текст отказа)."""
    src = tmp / f"{tag}.s"
    src.write_text(SKELETON.format(body=body), encoding="utf-8")
    r = subprocess.run([as_bin, "-mcpu=elbrus-v6", str(src), "-o", str(src.with_suffix(".o"))],
                       capture_output=True, text=True)
    if r.returncode == 0:
        return True, ""
    msg = " ".join(line.strip() for line in r.stderr.splitlines()
                   if "Error" in line)[:160]
    return False, msg


def probe(as_bin: str, op: str, channel: int, tmp: Path) -> tuple[bool, str]:
    """Принимает ли канал эту операцию. Возвращает (принимает, текст отказа)."""
    body = "\t  " + OPS[op].format(c=channel, d=5)
    ok, msg = _assemble(as_bin, body, tmp, f"{op}_{channel}")
    if ok:
        return True, ""
    # Отказ именно по кодировке канала, а не по синтаксису — иначе мы бы
    # «доказали» отсутствие порта опечаткой в мнемонике.
    if "cannot be encoded in ALC" not in msg:
        return False, f"НЕ ПРО КАНАЛ: {msg}"
    return False, msg


def probe_pair(as_bin: str, a: tuple[str, int], b: tuple[str, int],
               tmp: Path) -> tuple[bool, str]:
    """Собираются ли две операции в ОДНУ широкую команду.

    Обе по отдельности законны в своих каналах (это проверено выше), каналы
    разные, приёмники разные — поэтому отказ может быть только про само
    сочетание.
    """
    (opA, cA), (opB, cB) = a, b
    body = ("\t  " + OPS[opA].format(c=cA, d=5) + "\n"
            "\t  " + OPS[opB].format(c=cB, d=6))
    return _assemble(as_bin, body, tmp, f"pair_{opA}{cA}_{opB}{cB}")


def probe_combinations(as_bin: str, measured: dict[str, tuple[int, ...]],
                       tmp: Path) -> tuple[set, list[str]]:
    """Полный попарный перебор: какие сочетания ассемблер не кодирует.

    Возвращает (найденные запреты, отказы не про сочетание).
    """
    cells = [(op, c) for op in PAIR_REPS for c in measured.get(op, ())]
    bans: set[tuple[tuple[str, int], tuple[str, int]]] = set()
    odd: list[str] = []
    for a, b in itertools.combinations(cells, 2):
        if a[1] == b[1]:
            continue        # один канал двумя операциями — тривиально нельзя
        ok, msg = probe_pair(as_bin, a, b, tmp)
        if ok:
            continue
        if "prohibited" in msg or "combination" in msg:
            # Порядок в паре нормализуем: запрет симметричен, а ассемблер
            # называет стороны в своём порядке (STORE раньше LOAD).
            bans.add(tuple(sorted((a, b))))
        else:
            odd.append(f"{a[0]},{a[1]} + {b[0]},{b[1]}: {msg}")
    return bans, odd


def run(show: bool = False) -> bool:
    """Переснять и сверить матрицу. True — совпадает (или ассемблера нет).

    Вынесено из main() отдельно, чтобы `vliw/cli.py` (команда `/verify`) могло
    вызвать ровно ту же проверку в процессе, без второго питона subprocess'ом.
    """
    as_bin = find_as()
    if not as_bin:
        print("ассемблера e2k нет (ни E2K_AS, ни ~/e2k-toolchain, ни в PATH) — "
              "проверить матрицу нечем")
        print("это не провал: на машине без тулчейна модель просто не "
              "перепроверяется, источником истины остаётся vliw/core/model.py")
        return True
    print(f"ассемблер: {as_bin}\nпрофиль:   {MODEL.name}, портов {MODEL.width}\n")

    width = MODEL.width
    measured: dict[str, tuple[int, ...]] = {}
    broken: list[str] = []

    with tempfile.TemporaryDirectory(prefix="e2kprobe-") as td:
        tmp = Path(td)
        for op in OPS:
            ok: list[int] = []
            for ch in range(width):
                accepted, msg = probe(as_bin, op, ch, tmp)
                if accepted:
                    ok.append(ch)
                elif msg.startswith("НЕ ПРО КАНАЛ"):
                    broken.append(f"{op},{ch}: {msg}")
            measured[op] = tuple(ok)

    if broken:
        print("!! ассемблер отказал не по кодировке канала — проверка "
              "недостоверна для этих пар:")
        for b in broken[:8]:
            print("   ", b)
        print()

    if show:
        print("    " + " " * 7 + "".join(f"{f',{c}':>4}" for c in range(width)))
        for op in OPS:
            row = "".join(f"{'•' if c in measured[op] else '·':>4}"
                          for c in range(width))
            print(f"    {op:<7}{row}")
        print()

    diffs = []
    for op in OPS:
        model_ch = MODEL.channels_for(op)
        if measured[op] != model_ch:
            diffs.append(f"{op}: ассемблер {measured[op]}, model.py {model_ch}")

    if diffs:
        print("РАСХОЖДЕНИЯ (истина — ассемблер, править model.py):")
        for d in diffs:
            print("   ", d)
        return False

    print(f"матрица портов совпадает с vliw/core/model.py по всем "
          f"{len(OPS)}×{width} парам")
    print("(латентности и occupancy этим способом не проверяются: они меряются "
          "цепочками зависимых и потоками независимых операций, см. "
          "examples/probes/README.md)")

    return _report_combinations(as_bin, measured)


def _report_combinations(as_bin: str, measured: dict[str, tuple[int, ...]]) -> bool:
    """Второй класс ограничений: запреты на СОЧЕТАНИЯ в широкой команде."""
    with tempfile.TemporaryDirectory(prefix="e2kpairs-") as td:
        bans, odd = probe_combinations(as_bin, measured, Path(td))

    want = {tuple(sorted(p)) for p in EXPECTED_COMBO_BANS}
    print(f"\nсочетания в широкой команде: найдено запретов {len(bans)}")
    for a, b in sorted(bans):
        print(f"    {a[0]},{a[1]} + {b[0]},{b[1]} — вместе не кодируются")

    if odd:
        print("!! отказ не про сочетание — проверка недостоверна для этих пар:")
        for o in odd[:8]:
            print("   ", o)

    if bans != want:
        print("\nРАСХОЖДЕНИЕ с ожидаемым набором запретов "
              "(EXPECTED_COMBO_BANS в этом файле):")
        for p in sorted(want - bans):
            print(f"    ожидали, но ассемблер разрешает: {p}")
        for p in sorted(bans - want):
            print(f"    НОВЫЙ запрет, которого мы не знали: {p}")
        return False

    print("    совпадает с ожидаемым набором")
    print("    ВАЖНО: в vliw/core/model.py этих запретов НЕТ — модель знает "
          "только матрицу «порт → операции».")
    print("    Расхождение известное, не забытое: см. examples/probes/README.md, "
          "раздел про сочетания.")
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--show", action="store_true", help="напечатать матрицу целиком")
    args = ap.parse_args(argv)
    return 0 if run(show=args.show) else 1


if __name__ == "__main__":
    sys.exit(main())
