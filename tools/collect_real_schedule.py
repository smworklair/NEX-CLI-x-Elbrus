#!/usr/bin/env python3
"""Строит граф зависимостей и расписание компилятора по настоящему .s (lcc).

    python3 collect_real_schedule.py путь/к/файлу.s

Единственная зависимость — стандартная библиотека Python 3; остальной
проект не нужен (см. сопроводительное письмо).

Разбирает широкие команды в фигурных скобках (`adds,0 %r1, %r2, %r3` и
т.п.), строит по ним граф зависимостей между операциями и, если в файле
явно проставлены каналы, восстанавливает расписание, которое построил сам
компилятор. Печатает разбор на экран и одну JSON-строку под ним — больше
никуда ничего не пишет и не отправляет; сохранить строку в файл, приложить
к письму или не делать этого вовсе — решает тот, кто запустил скрипт,
глядя на распечатанное.

В результат попадает только структура: класс операции, зависимости между
ними, такт и канал по решению компилятора. Не попадают текст строк, имена
регистров (заменены на локальные порядковые номера) и путь к файлу — только
его короткое имя.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

# --------------------------------------------------------------------------
# Копия разбора из vliw/core/asm_parser.py. Самодостаточная копия, а не
# импорт, — намеренно: этот файл рассылается людям, у которых основного
# репозитория нет и не будет. Логика (мнемоники, регексы, разбор bundle)
# держится идентичной оригиналу, чтобы результат был совместим.
# --------------------------------------------------------------------------

MNEMONICS: dict[str, str] = {
    "adds": "ADD", "addd": "ADD", "addw": "ADD", "incs": "ADD", "incd": "ADD",
    "subs": "SUB", "subd": "SUB", "subw": "SUB", "decs": "SUB",
    "muls": "MUL", "muld": "MUL", "mulw": "MUL", "umuls": "MUL", "umuld": "MUL",
    "sdivs": "DIV", "sdivd": "DIV", "udivs": "DIV", "udivd": "DIV",
    "divs": "DIV", "divd": "DIV",
    "ldw": "LOAD", "ldd": "LOAD", "ldb": "LOAD", "ldh": "LOAD",
    "ldgdw": "LOAD", "ldgdd": "LOAD",
    "stw": "STORE", "std": "STORE", "stb": "STORE", "sth": "STORE",
    "shls": "SHL", "shld": "SHL", "shrs": "SHL", "shrd": "SHL",
    "sars": "SHL", "sard": "SHL", "scls": "SHL", "scrs": "SHL",
    "ands": "AND", "andd": "AND", "ors": "AND", "ord": "AND",
    "xors": "AND", "xord": "AND", "andns": "AND",
    "movts": "ADD", "movtd": "ADD", "adds_": "ADD",
}

_OP = re.compile(
    r"^\s*(?P<mn>[a-z][a-z0-9_]*)"
    r"(?:,(?P<chan>\d+))?"
    r"(?:\s+(?P<args>.*?))?\s*$"
)
_NOP = re.compile(r"^\s*nop\s+(?P<n>\d+)\s*$", re.I)
_REG = re.compile(r"%?\b([a-z]+\d+|[a-z]+\[\d+\])\b")
_COMMENT = re.compile(r"(//|!|;).*$")

# Матрица портов и occupancy — копия из vliw/core/model.py, нужна, чтобы
# ТОЧНО так же, как настоящий asm_parser.compiler_schedule(), проверять
# конфликты занятости порта и честно возвращать None, если расписание в
# файле противоречиво (например, канал не проставлен и свободного порта не
# нашлось). Без этой проверки можно было бы молча приписать компилятору
# расписание, которого он не строил.
_CHANNELS = {
    "ADD": (0, 1, 2, 3, 4, 5), "SUB": (0, 1, 2, 3, 4, 5),
    "AND": (0, 1, 2, 3, 4, 5), "SHL": (0, 1, 2, 3, 4, 5),
    "MUL": (0, 1, 3, 4), "DIV": (5,),
    "LOAD": (0, 2, 3, 5), "STORE": (2, 5),
}
_OCCUPANCY = {"DIV": 2}  # остальные по умолчанию 1


class Op:
    __slots__ = ("index", "mnemonic", "op", "channel", "dst", "srcs",
                "cycle", "known")

    def __init__(self, index, mnemonic, op, channel, dst, srcs, cycle, known):
        self.index = index
        self.mnemonic = mnemonic
        self.op = op
        self.channel = channel
        self.dst = dst
        self.srcs = srcs
        self.cycle = cycle
        self.known = known


def parse_asm(text: str) -> tuple[list[Op], int, dict[str, int], int]:
    """(операции, тактов у компилятора, незнакомые мнемоники, пропущено строк)."""
    ops: list[Op] = []
    unknown: dict[str, int] = {}
    skipped = 0
    cycle = 0
    pending_nop = 0

    for raw in text.splitlines():
        line = _COMMENT.sub("", raw).strip()
        if not line:
            continue
        if line.startswith("{"):
            cycle += pending_nop
            pending_nop = 0
            line = line[1:].strip()
            if not line:
                continue
        if line.startswith("}"):
            cycle += 1
            continue
        if line.startswith(".") or line.endswith(":"):
            continue

        m_nop = _NOP.match(line)
        if m_nop:
            pending_nop += int(m_nop.group("n"))
            continue

        m = _OP.match(line)
        if not m:
            skipped += 1
            continue

        mn = m.group("mn").lower()
        if mn in ("nop", "return", "ct", "ibranch", "call", "disp"):
            continue

        op_class = MNEMONICS.get(mn)
        known = op_class is not None
        if not known:
            op_class = "ADD"
            unknown[mn] = unknown.get(mn, 0) + 1

        args = (m.group("args") or "").strip()
        regs = _REG.findall(args)
        dst = regs[-1] if regs else None
        srcs = tuple(regs[:-1]) if len(regs) > 1 else ()

        chan = m.group("chan")
        ops.append(Op(
            index=len(ops), mnemonic=mn, op=op_class,
            channel=int(chan) if chan is not None else None,
            dst=dst, srcs=srcs, cycle=cycle, known=known,
        ))

    compiler_cycles = (max(o.cycle for o in ops) + 1) if ops else 0
    if ops and all(o.cycle == 0 for o in ops):
        # Файл без фигурных скобок (например, руками вставленный листинг
        # без bundle-разметки) — считаем, что такт неизвестен, а не что все
        # операции реально стоят в одном такте: это было бы неправдой.
        compiler_cycles = 0
        for o in ops:
            o.cycle = -1

    return ops, compiler_cycles, unknown, skipped


def anonymize(ops: list[Op]) -> tuple[list[dict], list[dict] | None]:
    """Граф зависимостей + расписание компилятора. Регистры — локальные id.

    Граф не зависит от того, удалось ли восстановить расписание — если
    в файле не было явных каналов, зависимости всё равно ценны сами по
    себе (реальная форма графа, а не только тайминг).
    """
    reg_id: dict[str, int] = {}

    def rid(name: str) -> int:
        return reg_id.setdefault(name, len(reg_id))

    last_writer: dict[str, int] = {}
    graph: list[dict] = []
    for o in ops:
        preds = sorted({last_writer[s] for s in o.srcs if s in last_writer})
        graph.append({"id": o.index, "op": o.op, "preds": preds})
        if o.dst:
            last_writer[o.dst] = o.index
        # регистры анонимизируем даже если не используются в графе — не
        # оставляем реальные имена нигде в промежуточных структурах
        for r in (*o.srcs, o.dst):
            if r:
                rid(r)

    schedule = _compiler_schedule(ops)
    return graph, schedule


def _compiler_schedule(ops: list[Op]) -> list[dict] | None:
    """Точная копия vliw/core/asm_parser.compiler_schedule().

    Не «есть ли канал у операций», а честная попытка разложить каждую
    операцию по занятости порта — с occupancy деления (держит порт 2
    такта). Если такт не проставлен (файл без фигурных скобок), портфель
    портов пуст для этого класса операций или клетка уже занята —
    возвращаем None, а не приблизительный результат: врать не будем, что
    компилятор построил то, чего он не строил.
    """
    if not ops or any(o.cycle < 0 for o in ops):
        return None
    used: dict[tuple[int, int], int] = {}
    out: list[dict] = []
    for o in ops:
        ports = _CHANNELS.get(o.op, ())
        if not ports:
            return None
        port = o.channel if o.channel in ports else None
        if port is None:
            port = next((p for p in ports if (o.cycle, p) not in used), None)
            if port is None:
                return None
        if (o.cycle, port) in used:
            return None
        occ = _OCCUPANCY.get(o.op, 1)
        for k in range(occ):
            used[(o.cycle + k, port)] = o.index
        out.append({"id": o.index, "cycle": o.cycle, "channel": port})
    return out


def render_preview(graph: list[dict], schedule: list[dict] | None) -> str:
    lines = ["граф зависимостей (это и есть то, что уйдёт наружу):"]
    for n in graph:
        pred_s = f" <- {' '.join(map(str, n['preds']))}" if n["preds"] else ""
        lines.append(f"  {n['id']} {n['op']}{pred_s}")
    if schedule:
        lines.append("расписание компилятора (такт=канал):")
        for s in schedule:
            lines.append(f"  {s['id']}: такт={s['cycle']} канал={s['channel']}")
    else:
        lines.append("(явных каналов в файле нет — расписание компилятора "
                     "не восстановлено, только граф)")
    return "\n".join(lines)


def process(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    ops, compiler_cycles, unknown, skipped = parse_asm(text)
    graph, schedule = anonymize(ops)

    op_counts: dict[str, int] = {}
    for n in graph:
        op_counts[n["op"]] = op_counts.get(n["op"], 0) + 1

    return {
        "source": path.name,          # только имя файла, без пути целиком
        "n_ops": len(graph),
        "op_counts": op_counts,
        "graph": graph,
        "compiler_schedule": schedule,
        "compiler_cycles": compiler_cycles or None,
        "unknown_mnemonics": unknown,
        "skipped_lines": skipped,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", type=Path, help="один или несколько .s-файлов")
    ap.add_argument("--out", type=Path, default=None,
                    help="дописать JSON-строки в файл вместо/вместе с печатью "
                         "в терминал (по умолчанию только печать — ничего "
                         "не сохраняется без явного указания)")
    ap.add_argument("--quiet", action="store_true",
                    help="не печатать человекочитаемый разбор, только JSON-строки")
    args = ap.parse_args(argv)

    out_fh = args.out.open("a", encoding="utf-8") if args.out else None
    try:
        for path in args.files:
            if not path.exists():
                print(f"!! файл не найден: {path}", file=sys.stderr)
                continue
            rec = process(path)

            if not args.quiet:
                print(f"\n=== {path.name} ===")
                if rec["n_ops"] == 0:
                    print("ни одной операции не разобрано — это не тот файл "
                         "или формат сильно отличается от ожидаемого")
                else:
                    print(f"операций: {rec['n_ops']}   "
                         f"по типам: {rec['op_counts']}")
                    if rec["skipped_lines"]:
                        print(f"строк не разобрано: {rec['skipped_lines']}")
                    if rec["unknown_mnemonics"]:
                        print(f"незнакомые мнемоники: {rec['unknown_mnemonics']} "
                             f"— посчитаны как обычная арифметика")
                    print(render_preview(rec["graph"], rec["compiler_schedule"]))
                print("--- JSON-строка ниже: то, что стоит прислать целиком ---")

            line = json.dumps(rec, ensure_ascii=False)
            print(line)
            if out_fh:
                out_fh.write(line + "\n")
    finally:
        if out_fh:
            out_fh.close()

    if not args.quiet:
        print(f"\nНичего никуда не отправлено само — файл{'ы' if len(args.files)>1 else ''} "
             f"выше только распечатан{'ы' if len(args.files)>1 else ''} в терминал"
             + (f" и дописан{'ы' if len(args.files)>1 else ''} в {args.out}" if args.out else "")
             + ". Отправлять или нет — решать вам.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
