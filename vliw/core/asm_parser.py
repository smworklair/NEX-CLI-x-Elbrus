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
    # `sxt` — расширение знака, встречается в настоящем выводе lcc. Здесь
    # раньше стоял `adds_`: такой мнемоники нет, ни в одной пробе и ни в
    # одном скомпилированном файле она не встречается — опечатка с первого
    # коммита, занимавшая место настоящей операции.
    "movts": "ADD", "movtd": "ADD", "sxt": "ADD",

    # --- Плавающая точка, предикаты, упакованные (30.08.2026) ----------------
    # Каналы и латентности этих классов сняты у ассемблера и компилятора, а не
    # предположены — см. model.py. До этого все они попадали в UNKNOWN, и на
    # выводе `lcc -O3` таких операций было 37%.
    "fadds": "FADD", "faddd": "FADD", "fsubs": "FADD", "fsubd": "FADD",
    "fmuls": "FMUL", "fmuld": "FMUL",
    "fdivs": "FDIV", "fdivd": "FDIV",

    # Сравнения, кладущие результат в предикат. Их много и они разные по
    # ширине операнда (`b` — байтовая форма записи, `d` — двойное слово);
    # для планирования это один класс: канал и латентность у них общие.
    "cmpesb": "PRED", "cmpedb": "PRED", "cmplsb": "PRED", "cmpldb": "PRED",
    "cmplesb": "PRED", "cmpledb": "PRED", "cmpbsb": "PRED", "cmpbdb": "PRED",
    "cmpandesb": "PRED", "cmpandedb": "PRED",
    "cmpandsb": "PRED", "cmpanddb": "PRED",

    # Упакованные: `p*` — 64-битные, `qp*` — 128-битные. Оба класса живут в
    # тех же двух каналах, поэтому различать их для планирования нечем.
    "paddw": "PACK", "paddb": "PACK", "paddh": "PACK", "paddd": "PACK",
    "psubw": "PACK", "psubb": "PACK", "psubh": "PACK", "psubd": "PACK",
    "pcmpgtw": "PACK", "pcmpeqw": "PACK", "pminsw": "PACK", "pmaxsw": "PACK",
    "qpaddw": "PACK", "qpaddb": "PACK", "qpaddh": "PACK", "qpaddd": "PACK",
    "qpsubw": "PACK", "qpsllw": "PACK", "qpsrlw": "PACK",
    "qpminsw": "PACK", "qpmaxsw": "PACK", "qpcmpgtw": "PACK",
    "qppackdl": "PACK", "qpswitchd": "PACK",

    # Упакованная ЛОГИКА и сдвиги — шире арифметики по каналам (,0 ,1 ,3 ,4
    # против ,0 ,3), проверено ассемблером.
    "qpor": "PACKLOG", "qpand": "PACKLOG", "qpxor": "PACKLOG",
    "qpsllw": "PACKLOG", "qpsrlw": "PACKLOG", "qpsraw": "PACKLOG",
    "por": "PACKLOG", "pand": "PACKLOG", "pxor": "PACKLOG",
    "psllw": "PACKLOG", "psrlw": "PACKLOG",

    # Упакованная плавающая точка — те же каналы и та же цена, что у
    # скалярной: отдельного класса не заводим.
    "pfadds": "FADD", "pfaddd": "FADD", "pfsubs": "FADD",
    "pfmuls": "FMUL", "pfmuld": "FMUL",

    # Устройство доступа к массивам: обмен с его регистрами и запись через
    # него. Каналы ,2 и ,5 — те же, что у обычной записи в память.
    "aaurw": "AAU", "aaurwd": "AAU", "aaurr": "AAU", "aaurrd": "AAU",
    "staaw": "AAU", "staad": "AAU", "staah": "AAU", "staab": "AAU",
    "staaq": "AAU", "mmurw": "AAU", "mmurr": "AAU",

    # Сращённые операции: сдвиг со сложением за такт. Только ,1 и ,4.
    "shl_adds": "COMBO", "shl_addd": "COMBO",
    "shr_adds": "COMBO", "shr_addd": "COMBO",
    "getf_adds": "COMBO", "getf_addd": "COMBO",

    # Битовые поля: вставка уже, чтение и выбор шире.
    "insfs": "INSF", "insfd": "INSF",
    "getfs": "MERGE", "getfd": "MERGE",
    "merges": "MERGE", "merged": "MERGE",

    # Широкая загрузка/запись — те же порты, что у обычных.
    "ldqp": "LOAD", "ldapq": "LOAD", "stqp": "STORE", "stapq": "STORE",

    # Запись в регистры состояния (счётчик цикла %lsr и подобные) — ,0.
    "rwd": "RW", "rws": "RW",
}

# `adds,0 %r1, %r2, %r3` — мнемоника, необязательный канал, операнды.
CONTROL = {
    "nop", "return", "ct", "ibranch", "call", "disp", "rbranch",
    "setwd", "setbn", "setsft", "settr", "setmas", "setei",
    "getsp", "getpl", "bap", "eap", "flushr", "flushc", "wait",
    "ipd", "abn", "abp", "abg", "alc", "loop_mode", "pref", "landing",
}
"""Управляющие и настроечные операции — в графе ВЫЧИСЛЕНИЙ им не место.

`setwd` объявляет окно регистров, `disp` готовит переход, `getsp` берёт
указатель стека — они не считают и зависимостей по данным не создают.
Раньше список был из шести имён, а всё остальное попадало в граф как
арифметика: на настоящем `-O3` такие фантомы занимали чужие порты и
восстановление расписания компилятора падало на первом же `setwd` в такте 0.
Считаются отдельно (`ParsedAsm.control_ops`): спрятать их молча было бы
враньём, посчитать сложением — тоже.
"""

_OP = re.compile(
    r"^\s*(?P<mn>[a-z][a-z0-9_]*)"      # мнемоника
    r"(?:,(?P<chan>\d+))?"              # канал: ,0 … ,5
    r"(?P<flags>(?:,[a-z][a-z0-9]*)*)"  # модификаторы после канала: ,sm и др.
    r"(?:\s+(?P<args>.*?))?\s*$"
)
"""Команда широкой команды.

МОДИФИКАТОРЫ. После канала компилятор ставит признаки исполнения — прежде
всего `,sm` (speculative mode, спекулятивное исполнение). Раньше их не было
в шаблоне, и такая строка не подходила под него ЦЕЛИКОМ: операция молча
пропадала. На пробах это не проявлялось (в `examples/probes/*.s` ни одного
`,sm`), а на настоящем `-O3` так теряется больше половины кода — 90 строк
из 182 на обычном цикле. Модификаторы разбираются и сохраняются в
`AsmOp.flags`: спекулятивная операция всё равно занимает канал и такт,
поэтому в графе ей место, а признак может понадобиться позже.
"""
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
    flags: tuple[str, ...] = ()
    """Модификаторы после канала: `("sm",)` у спекулятивной операции."""
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
    control_ops: int = 0
    """Сколько управляющих операций пропущено (см. CONTROL)."""
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
    saw_bundle = False
    pending_nop = 0

    for lineno, raw in enumerate(text.splitlines(), 1):
        line = _COMMENT.sub("", raw).strip()
        if not line:
            continue

        if line.startswith("{"):
            in_bundle = True
            saw_bundle = True
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
        if mn in CONTROL:
            res.control_ops += 1
            continue

        chan = m.group("chan")

        op_class = MNEMONICS.get(mn)
        known = op_class is not None
        if not known:
            # Незнакомая мнемоника БЕЗ канала — не операция ALC. В e2k всё,
            # что исполняется на шести арифметических каналах, несёт `,N`;
            # без него это предикатная логика (`landp`, `pass`), подготовка
            # перехода (`ldisp`) или иной блок. Раньше такие попадали в граф
            # сложением и занимали чужие порты — восстановление расписания
            # компилятора падало на первом же из них. Считаем их вместе с
            # управляющими и в граф вычислений не берём.
            if chan is None:
                res.control_ops += 1
                res.unknown_mnemonics[mn] = res.unknown_mnemonics.get(mn, 0) + 1
                continue
            # С каналом — настоящая операция ALC, просто класс нам неизвестен.
            # Раньше здесь стояло op_class = "ADD": чужая операция уезжала в
            # отчёт сложением с латентностью 1, и `fdivd` считался как ADD.
            op_class = "UNKNOWN"
            res.unknown_mnemonics[mn] = res.unknown_mnemonics.get(mn, 0) + 1
            near = difflib.get_close_matches(mn, MNEMONICS, n=3, cutoff=0.72)
            res.problems.append(AsmProblem(
                line=lineno, kind="mnemonic", severity="warn", op=len(res.ops),
                text=f"мнемоника `{mn}` незнакомая — класс UNKNOWN "
                     f"(латентность 1, любой канал: заглушка, не измерение)",
                hint=("может быть: " + "  ".join(near)) if near else
                     "список известных — в MNEMONICS (core/asm_parser.py)"))

        args = (m.group("args") or "").strip()
        regs = _REG.findall(args)
        dst = regs[-1] if regs else None
        srcs = tuple(regs[:-1]) if len(regs) > 1 else ()

        res.ops.append(AsmOp(
            index=len(res.ops), mnemonic=mn, op=op_class,
            channel=int(chan) if chan is not None else None,
            dst=dst, srcs=srcs,
            bundle=max(0, bundle), cycle=cycle,
            text=line, known=known, line=lineno,
            flags=tuple(f for f in (m.group("flags") or "").split(",") if f),
        ))

    res.bundles = bundle + 1
    if not saw_bundle and res.ops:
        # Файл без фигурных скобок: считаем, что каждая операция — свой такт.
        #
        # Условие смотрит на то, ВСТРЕЧАЛАСЬ ли хоть одна `{`, а не на
        # `in_bundle`. Прежняя проверка (`not in_bundle` и все такты нулевые)
        # ошибалась на файле из ОДНОЙ широкой команды: после закрывающей `}`
        # флаг снят, такты у всех операций нулевые — и разбор растаскивал
        # соседей по такту на разные такты, ровно теряя то, ради чего файл и
        # читается. На многотактных файлах не проявлялось: там такты разные.
        for i, o in enumerate(res.ops):
            o.cycle = i
            o.bundle = i
        res.bundles = len(res.ops)
    return res


def build_dag(parsed: ParsedAsm, key: str = "asm", title: str = "") -> DAG:
    """Построить граф зависимостей по чтению/записи регистров (RAW).

    СЕМАНТИКА ШИРОКОЙ КОМАНДЫ. Все операции одного такта читают операнды
    ОДНОВРЕМЕННО, прежде чем ляжет хоть одна запись этого же такта. Поэтому
    текстовый порядок внутри `{ … }` ничего не значит, и вот эта пара из
    probe.s — НЕ зависимость по данным:

        {  ldw,0    0x0, [ a+16 ], %r5      ← пишет %r5
           sdivs,5  %r5, %r6, %r4           ← читает СТАРЫЙ %r5
        }

    Деление берёт значение, загруженное раньше, а загрузка готовит %r5 для
    следующего потребителя: обычное переиспользование регистра при
    программной конвейеризации.

    Прежняя версия шла по операциям подряд и такие пары читала как «запись →
    чтение» по номеру строки. Последствия не косметические: выдуманные рёбра
    завышали критический путь, а расписание самого компилятора переставало
    проходить `Schedule.validate()` — инструмент объявлял вывод lcc
    незаконным на ровном месте. Здесь такт обрабатывается целиком: сначала
    все читают состояние ПРЕДЫДУЩИХ тактов, потом все пишут.
    """
    last_writer: dict[str, int] = {}
    instrs: list[Instr] = []

    def group_key(o: AsmOp) -> int:
        # Такт неизвестен (файл без фигурных скобок) — операция сама по себе,
        # иначе весь файл слипся бы в один «такт» и зависимости исчезли бы.
        return o.cycle if o.cycle >= 0 else -(o.index + 1)

    i = 0
    ops = parsed.ops
    while i < len(ops):
        j = i
        while j < len(ops) and group_key(ops[j]) == group_key(ops[i]):
            j += 1

        # Такт целиком: сперва ЧИТАЮТ все операции такта — по состоянию,
        # сложившемуся к его началу, — и только потом применяются записи.
        for o in ops[i:j]:
            preds = []
            for src in o.srcs:
                w = last_writer.get(src)
                if w is not None and w not in preds:
                    preds.append(w)
            instrs.append(Instr(
                id=o.index,
                name=(o.dst or f"i{o.index}"),
                op=o.op,
                preds=tuple(sorted(preds)),
                text=o.text,
            ))
        for o in ops[i:j]:
            if o.dst:
                last_writer[o.dst] = o.index
        i = j

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


UNKNOWN_SHARE_LIMIT = 0.05
"""С какой доли UNKNOWN сравнение с компилятором перестаёт что-либо значить."""


def unknown_share(parsed: ParsedAsm) -> float:
    """Доля операций, класс которых машине неизвестен."""
    if not parsed.ops:
        return 0.0
    return sum(1 for o in parsed.ops if o.op == "UNKNOWN") / len(parsed.ops)


def compiler_schedule_checked(parsed: ParsedAsm, dag: DAG, model: MachineModel):
    """Расписание компилятора + причина, если его нельзя показывать.

    Одна функция на оба интерфейса намеренно. До 0.9 построчный режим и
    полноэкранный КОД решали это порознь и разошлись: `/load` проверял
    расписание через `Schedule.validate()` и отбрасывал непрошедшее, а КОД
    показывал makespan любого восстановленного; про долю UNKNOWN не думал
    ни один. Разъехаться двум копиям тут нечему — копия одна.

    Возвращает `(schedule|None, problem|None)`, где problem — пара
    (заголовок, подробность) для показа человеку.
    """
    sched = compiler_schedule(parsed, dag, model)
    if sched is None:
        return None, ("расписание компилятора не восстановлено",
                      "раскладка по каналам не сходится с моделью")
    errs = sched.validate()
    if errs:
        detail = (errs[0] if len(errs) == 1
                  else f"{len(errs)} замечаний, первое: {errs[0]}")
        return None, (
            "расписание компилятора не принято проверкой",
            detail + ". Частая причина на настоящем -O3 — конвейеризованный "
                     "цикл: значение берётся из предыдущей итерации, а разбор "
                     "читает файл линейно")
    return sched, None


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
    #
    # ТАКТ ЦЕЛИКОМ, а не построчно. Все операции широкой команды читают
    # операнды одновременно, до того как ляжет хоть одна запись этого же
    # такта, — поэтому сосед по такту производителем быть не может. Проверка
    # шла по порядку строк и объявляла НЕЗАКОННЫМ вывод самого lcc: в
    # probe.s соседние `ldw` и `sdivs` внутри одной `{ … }` давали три
    # «ошибки» на ровном месте. То же самое чинилось в build_dag — здесь
    # отдельная копия логики, и она отстала.
    last_writer: dict[str, AsmOp] = {}
    ops = parsed.ops
    i = 0
    while i < len(ops):
        j = i
        while j < len(ops) and ops[j].cycle == ops[i].cycle:
            j += 1
        for o in ops[i:j]:
            for src in o.srcs:
                w = last_writer.get(src)
                if w is None:
                    continue
                ready = w.cycle + model.latency(w.op)
                if o.cycle < ready:
                    out.append(AsmProblem(
                        line=o.line, kind="ready", severity="error", op=o.index,
                        text=f"%{src} читается в такте {o.cycle}, а "
                             f"{w.mnemonic} из строки {w.line} отдаст его "
                             f"только в такте {ready}",
                        hint=f"латентность {w.op} — {model.latency(w.op)} т.; "
                             f"нужен разрыв в {ready - w.cycle} т."))
        for o in ops[i:j]:
            if o.dst:
                last_writer[o.dst] = o
        i = j

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
