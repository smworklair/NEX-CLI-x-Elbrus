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

    python tools/probe_matrix.py            # снять и сверить
    python tools/probe_matrix.py --show     # плюс таблица целиком

Компилятор ставится не в проект: путь ищется по обычным местам, переопределяется
переменной окружения `E2K_AS`. Если ассемблера нет — скрипт не падает, а
сообщает, что проверить нечем (код возврата 0: на машине без тулчейна это не
провал сборки, а отсутствие возможности).
"""

from __future__ import annotations

import argparse
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
OPS = {
    "ADD":   "adds,{c}\t%r3, %r4, %r5",
    "SUB":   "subs,{c}\t%r3, %r4, %r5",
    "AND":   "ands,{c}\t%r3, %r4, %r5",
    "SHL":   "shls,{c}\t%r3, %r4, %r5",
    "MUL":   "muls,{c}\t%r3, %r4, %r5",
    "DIV":   "sdivs,{c}\t%r3, %r4, %r5",
    "LOAD":  "ldw,{c}\t0x0, [ _f64,_lts0 a ], %r5",
    # У записи форма операндов другая: база, смещение, значение — и значение
    # обязано быть регистром. С литеральным адресом, как у загрузки, ассемблер
    # отвечает «Register should be specified for SRC3», то есть отказывает по
    # синтаксису, а не по каналу. Проверка на такой отказ ниже не зря: иначе
    # опечатка в мнемонике выглядела бы как «порт не поддерживает операцию».
    "STORE": "stw,{c}\t%dr2, 0x0, %r5",
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
\t  {instr}
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


def probe(as_bin: str, op: str, channel: int, tmp: Path) -> tuple[bool, str]:
    """Принимает ли канал эту операцию. Возвращает (принимает, текст отказа)."""
    src = tmp / f"{op}_{channel}.s"
    src.write_text(SKELETON.format(instr=OPS[op].format(c=channel)), encoding="utf-8")
    r = subprocess.run([as_bin, "-mcpu=elbrus-v6", str(src), "-o", str(src.with_suffix(".o"))],
                       capture_output=True, text=True)
    if r.returncode == 0:
        return True, ""
    msg = " ".join(line.strip() for line in r.stderr.splitlines()
                   if "Error" in line)[:120]
    # Отказ именно по кодировке канала, а не по синтаксису — иначе мы бы
    # «доказали» отсутствие порта опечаткой в мнемонике.
    if "cannot be encoded in ALC" not in msg:
        return False, f"НЕ ПРО КАНАЛ: {msg}"
    return False, msg


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
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--show", action="store_true", help="напечатать матрицу целиком")
    args = ap.parse_args(argv)
    return 0 if run(show=args.show) else 1


if __name__ == "__main__":
    sys.exit(main())
