"""Разбор настоящего `.s`-вывода lcc для Эльбруса.

Это мост между прототипом и реальным кодом. Раньше инструмент умел только
синтетические сценарии; здесь он принимает файл, который выдал компилятор, и
строит по нему граф зависимостей — после чего к нему применимы все те же
инструменты: точный поиск, диагностика, сравнение.

Что понимаем в файле:

  * широкие команды в фигурных скобках `{ … }` — одна пачка = один такт выдачи;
  * операции с указанием канала: `adds,0 %r1, %r2, %r3`;
  * `nop N` — компилятор так кодирует вынужденную задержку;
  * метки, директивы (`.text`, `.global`, …) и комментарии — пропускаем.

Чего НЕ делаем и почему. Мы не эмулируем семантику: нас интересуют только
зависимости по регистрам (кто пишет — кто читает) и класс операции. Этого
достаточно, чтобы построить граф и переспланировать участок. Предикаты,
спекуляция, обращения к памяти сложнее «загрузить/сохранить» игнорируются —
ровно так же, как их игнорирует модель машины в `model.py`.

Допущение о порядке операндов: последний операнд — приёмник
(`adds,0 %r1, %r2, %r3` → `r3 = r1 + r2`). Так устроено большинство операций
в выводе lcc; для нашей задачи (граф зависимостей) важен именно приёмник.
Строки, которые не удалось разобрать, считаются и показываются в отчёте —
инструмент не делает вид, что понял файл целиком.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

from .dag import DAG, Instr
from .model import MachineModel
from .schedule import Schedule

# Мнемоника e2k -> класс операции нашей модели. Список покрывает то, что
# реально встречалось в экспериментах (probe.c / test.c); всё незнакомое
# считается простой арифметикой и помечается как нераспознанное.
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

# `adds,0 %r1, %r2, %r3` — мнемоника, необязательный канал, операнды.
_OP = re.compile(
    r"^\s*(?P<mn>[a-z][a-z0-9_]*)"      # мнемоника
    r"(?:,(?P<chan>\d+))?"              # канал: ,0 … ,5
    r"(?:\s+(?P<args>.*?))?\s*$"
)
_NOP = re.compile(r"^\s*nop\s+(?P<n>\d+)\s*$", re.I)
_REG = re.compile(r"%?\b([a-z]+\d+|[a-z]+\[\d+\])\b")
_COMMENT = re.compile(r"(//|!|;).*$")


@dataclass
class AsmOp:
    """Одна операция из `.s`."""

    index: int
    mnemonic: str
    op: str                 # класс нашей модели: ADD/MUL/DIV/LOAD/…
    channel: int | None     # номер канала из `,N`, если был указан
    dst: str | None
    srcs: tuple[str, ...]
    bundle: int             # номер широкой команды, в которой стояла
    cycle: int              # такт выдачи по расписанию компилятора
    text: str
    known: bool = True
    line: int = 0
    """Номер строки в исходнике, 1-based.

    Нужен редактору КОДА: он ставит расписание НА текст (такт и канал в
    гуттере той самой строки) и водит курсор от находки к строке. Без этого
    операция и её строка связаны только порядком, а порядок ломает первый
    же пропуск нераспознанной строки.
    """


@dataclass
class AsmProblem:
    """Замечание к строке исходника.

    Разбор и раньше считал, сколько строк не понял и сколько мнемоник не
    знает, — но только ЧИСЛОМ в отчёте («пропущено строк: 3»). Найти эти
    строки человек мог лишь глазами. Замечание держит номер строки, поэтому
    редактор ставит метку прямо на неё, а клик по списку ведёт курсор.
    """

    line: int
    kind: str              # parse | mnemonic | channel | busy | free
    severity: str          # error | warn | info
    text: str
    hint: str = ""
    op: int = -1           # индекс операции, если замечание про операцию


@dataclass
class ParsedAsm:
    """Результат разбора файла."""

    ops: list[AsmOp] = field(default_factory=list)
    bundles: int = 0
    nop_cycles: int = 0
    skipped_lines: int = 0
    unknown_mnemonics: dict[str, int] = field(default_factory=dict)
    source: str = ""
    problems: list[AsmProblem] = field(default_factory=list)
    """Что разбор не понял — с номерами строк, а не только счётчиком."""

    @property
    def compiler_cycles(self) -> int:
        """Длина расписания, которое построил сам компилятор."""
        if not self.ops:
            return 0
        return max(o.cycle for o in self.ops) + 1

    def op_counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for o in self.ops:
            out[o.op] = out.get(o.op, 0) + 1
        return out


def parse_asm(text: str, source: str = "") -> ParsedAsm:
    """Разобрать текст `.s` в набор операций с их исходным расписанием."""
    res = ParsedAsm(source=source)
    bundle = -1
    cycle = 0
    in_bundle = False
    pending_nop = 0

    for lineno, raw in enumerate(text.splitlines(), 1):
        line = _COMMENT.sub("", raw).strip()
        if not line:
            continue

        if line.startswith("{"):
            in_bundle = True
            bundle += 1
            cycle += pending_nop
            pending_nop = 0
            line = line[1:].strip()
            if not line:
                continue
        if line.startswith("}"):
            in_bundle = False
            cycle += 1
            continue

        # Директивы и метки к расписанию отношения не имеют.
        if line.startswith(".") or line.endswith(":"):
            continue

        m_nop = _NOP.match(line)
        if m_nop:
            # `nop N` — задержка перед следующей широкой командой.
            pending_nop += int(m_nop.group("n"))
            res.nop_cycles += int(m_nop.group("n"))
            continue

        m = _OP.match(line)
        if not m:
            res.skipped_lines += 1
            res.problems.append(AsmProblem(
                line=lineno, kind="parse", severity="warn",
                text="строку не разобрать — в граф она не попала",
                hint="ждём операцию вида `adds,0 %r1, %r2, %r3`"))
            continue

        mn = m.group("mn").lower()
        if mn in ("nop", "return", "ct", "ibranch", "call", "disp"):
            continue

        op_class = MNEMONICS.get(mn)
        known = op_class is not None
        if not known:
            op_class = "ADD"      # считаем простой арифметикой, но помечаем
            res.unknown_mnemonics[mn] = res.unknown_mnemonics.get(mn, 0) + 1
            near = difflib.get_close_matches(mn, MNEMONICS, n=3, cutoff=0.72)
            res.problems.append(AsmProblem(
                line=lineno, kind="mnemonic", severity="warn", op=len(res.ops),
                text=f"мнемоника `{mn}` незнакомая — считаю как арифметику "
                     f"(латентность 1, любой канал)",
                hint=("может быть: " + "  ".join(near)) if near else
                     "список известных — в MNEMONICS (core/asm_parser.py)"))

        args = (m.group("args") or "").strip()
        regs = _REG.findall(args)
        dst = regs[-1] if regs else None
        srcs = tuple(regs[:-1]) if len(regs) > 1 else ()

        chan = m.group("chan")
        res.ops.append(AsmOp(
            index=len(res.ops), mnemonic=mn, op=op_class,
            channel=int(chan) if chan is not None else None,
            dst=dst, srcs=srcs,
            bundle=max(0, bundle), cycle=cycle,
            text=line, known=known, line=lineno,
        ))

    res.bundles = bundle + 1
    if not in_bundle and res.ops and all(o.cycle == 0 for o in res.ops):
        # Файл без фигурных скобок: считаем, что каждая операция — свой такт.
        for i, o in enumerate(res.ops):
            o.cycle = i
            o.bundle = i
        res.bundles = len(res.ops)
    return res


def build_dag(parsed: ParsedAsm, key: str = "asm", title: str = "") -> DAG:
    """Построить граф зависимостей по чтению/записи регистров (RAW)."""
    last_writer: dict[str, int] = {}
    instrs: list[Instr] = []

    for o in parsed.ops:
        preds = []
        for s in o.srcs:
            w = last_writer.get(s)
            if w is not None and w not in preds:
                preds.append(w)
        instrs.append(Instr(
            id=o.index,
            name=(o.dst or f"i{o.index}"),
            op=o.op,
            preds=tuple(sorted(preds)),
            text=o.text,
        ))
        if o.dst:
            last_writer[o.dst] = o.index

    return DAG(
        key=key,
        title=title or f"Разобранный .s: {parsed.source or 'без имени'}",
        note=(f"{len(parsed.ops)} операций из {parsed.bundles} широких команд. "
              f"Граф построен по зависимостям «запись → чтение» регистров; "
              f"расписание компилятора — {parsed.compiler_cycles} тактов."),
        instrs=instrs,
    )


def compiler_schedule(parsed: ParsedAsm, dag: DAG, model: MachineModel) -> Schedule | None:
    """Восстановить расписание, которое построил САМ компилятор.

    Нужно, чтобы честно сравнить: сколько тактов получилось у lcc и сколько
    даёт точный поиск на том же графе. Если в файле не было явных каналов или
    раскладка противоречит модели машины, возвращаем None — врать не будем.
    """
    sched = Schedule(dag, model)
    used: dict[tuple[int, int], int] = {}
    for o in parsed.ops:
        ports = model.channels_for(o.op)
        if not ports:
            return None
        port = o.channel if o.channel in ports else None
        if port is None:
            port = next((p for p in ports if (o.cycle, p) not in used), None)
            if port is None:
                return None
        if (o.cycle, port) in used:
            return None
        occ = model.occupancy(o.op)
        for k in range(occ):
            used[(o.cycle + k, port)] = o.index
        sched.place(o.index, o.cycle, port)
    return sched


def lint(parsed: ParsedAsm, model: MachineModel) -> list[AsmProblem]:
    """Проверить разобранный исходник по модели машины.

    Разбор отвечает на вопрос «что здесь написано», линтер — на вопрос
    «может ли машина это исполнить так, как написано». Три вещи, на которых
    рукописный e2k-ассемблер ломается чаще всего, и все три проверяются
    ИЗМЕРЕННЫМИ числами из `model.py`, а не догадкой:

      1. канал не тот — `muls,2` ассемблер отвергает («cannot be encoded in
         ALC2»), потому что умножение живёт на `,0 ,1 ,3 ,4`;
      2. порт уже занят — деление держит `,5` два такта, и второе деление
         в следующем такте физически не примут;
      3. результат ещё не готов — латентность деления 11 тактов, и чтение
         его приёмника через такт читает старое значение.

    Третья ошибка самая злая: она не мешает ни ассемблеру, ни нашему
    разбору — код собирается и «работает», просто считает не то. Поэтому
    замечание несёт номер такта, в котором значение будет готово.

    Возвращает список замечаний, отсортированный по строке; замечания
    разбора (`parsed.problems`) сюда НЕ входят — они уже есть у разбора.
    """
    out: list[AsmProblem] = []
    if not parsed.ops:
        return out

    # 1. Канал против матрицы портов.
    for o in parsed.ops:
        if o.channel is None:
            continue
        allowed = model.channels_for(o.op)
        if allowed and o.channel not in allowed:
            names = " ".join(model.port_label(p) for p in allowed)
            out.append(AsmProblem(
                line=o.line, kind="channel", severity="error", op=o.index,
                text=f"{o.mnemonic} в канале ,{o.channel} — этого канала у "
                     f"операции нет",
                hint=f"{o.op} исполним на: {names}"))

    # 2. Порт занят. Считаем ровно так же, как compiler_schedule: операция с
    #    occupancy > 1 держит клетку и в следующих тактах.
    held: dict[tuple[int, int], AsmOp] = {}
    for o in parsed.ops:
        ports = model.channels_for(o.op)
        port = o.channel if (o.channel is not None and o.channel in ports) else None
        if port is None:
            port = next((p for p in ports if (o.cycle, p) not in held), None)
        if port is None:
            continue
        occ = model.occupancy(o.op)
        prev = held.get((o.cycle, port))
        if prev is not None:
            same = prev.cycle == o.cycle
            free_at = prev.cycle + model.occupancy(prev.op)
            out.append(AsmProblem(
                line=o.line, kind="busy", severity="error", op=o.index,
                text=(f"канал ,{port} в такте {o.cycle} уже занят: "
                      + (f"{prev.mnemonic} из строки {prev.line}" if same else
                         f"{prev.mnemonic} из строки {prev.line} держит порт "
                         f"{model.occupancy(prev.op)} т.")),
                hint=f"порт освободится в такте {free_at}"))
        for k in range(occ):
            held.setdefault((o.cycle + k, port), o)

    # 3. Результат ещё не готов: чтение раньше латентности.
    last_writer: dict[str, AsmOp] = {}
    for o in parsed.ops:
        for src in o.srcs:
            w = last_writer.get(src)
            if w is None:
                continue
            ready = w.cycle + model.latency(w.op)
            if o.cycle < ready:
                out.append(AsmProblem(
                    line=o.line, kind="ready", severity="error", op=o.index,
                    text=f"%{src} читается в такте {o.cycle}, а {w.mnemonic} "
                         f"из строки {w.line} отдаст его только в такте {ready}",
                    hint=f"латентность {w.op} — {model.latency(w.op)} т.; "
                         f"нужен разрыв в {ready - w.cycle} т."))
        if o.dst:
            last_writer[o.dst] = o

    # 4. Каналы вообще не проставлены: расписание компилятора мы тогда не
    #    восстанавливаем, а раскладываем сами — и это надо сказать вслух,
    #    иначе «18 тактов у lcc» выглядит как замер, хотя это наша догадка.
    free = [o for o in parsed.ops if o.channel is None]
    if free:
        out.append(AsmProblem(
            line=free[0].line, kind="free", severity="info", op=free[0].index,
            text=f"{len(free)} из {len(parsed.ops)} операций без канала — "
                 f"раскладку по портам домысливаем",
            hint="в выводе lcc канал есть всегда: `adds,0 …`"))

    out.sort(key=lambda p: (p.line, p.kind))
    return out


def parse_file(path: str) -> ParsedAsm:
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return parse_asm(fh.read(), source=path)
