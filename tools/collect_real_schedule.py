#!/usr/bin/env python3
"""Снимает граф зависимостей и расписание компилятора с настоящего .s (lcc).

    python3 collect_real_schedule.py путь/к/файлу.s          # разобрать
    python3 collect_real_schedule.py report присланное.jsonl # свести присланное
    python3 collect_real_schedule.py to-dataset in.jsonl -o train.jsonl
    python3 collect_real_schedule.py selftest                # проверить сам себя

Единственная зависимость — стандартная библиотека Python 3; остальной проект
не нужен (см. сопроводительное письмо).

Разбирает широкие команды в фигурных скобках (`adds,0 %r1, %r2, %r3` и т.п.),
строит по ним граф зависимостей между операциями и, если в файле проставлены
каналы, восстанавливает расписание, которое построил сам компилятор. Печатает
разбор на экран и одну JSON-строку под ним — больше никуда ничего не пишет и не
отправляет; сохранить строку в файл, приложить к письму или не делать этого
вовсе — решает тот, кто запустил скрипт, глядя на распечатанное.

В результат попадает только структура: класс операции, зависимости между ними,
такт и канал по решению компилятора. Не попадают текст строк, имена регистров
(заменены на локальные порядковые номера) и путь к файлу — только его короткое
имя.

ЧТО ЭТО ДАЁТ ТОМУ, КТО ПОЛУЧИТ ОТВЕТ. Три вещи, и ни одна не требует исходников:

  1. РАСПИСАНИЕ ПРОТИВ НИЖНЕЙ ГРАНИЦЫ. По графу считается длина критического
     пути и ресурсная граница; `slack` — расстояние от расписания lcc до этой
     границы. Осторожно с чтением: граница НЕ обязана быть достижимой, поэтому
     slack=9 не значит «девять тактов потеряно» — значит «сюда стоит
     посмотреть». А вот slack=0 доказателен: ниже границы не бывает, значит
     расписание оптимально. Настоящий оптимум считает точный поиск в основном
     репозитории — здесь его намеренно нет, скрипт обходится stdlib.

  2. ЛАТЕНТНОСТИ, ИЗМЕРЕННЫЕ ПО ЧУЖОМУ КОДУ. Компилятор обязан разводить
     зависимые операции не ближе латентности. Поэтому МИНИМАЛЬНЫЙ зазор между
     производителем и потребителем по всему файлу — верхняя оценка латентности,
     и с ростом числа файлов она сходится к настоящей. `observed_min_gap`
     собирает эти зазоры; `report` сводит их по всем присланным файлам и прямо
     говорит, где наша модель машины врёт. Это тот же способ, которым мерили
     руками (цепочка `x = x * b`), но по реальному коду и на масштабе.

  3. ОБУЧАЮЩИЕ ПРИМЕРЫ. `to-dataset` превращает присланное в тот же формат
     prompt/completion, что и synthetic-выборка. Настоящие расписания настоящего
     компилятора — ровно то, чего в выборке нет.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path

SCHEMA = 2
TOOL_VERSION = "2.0"

# --------------------------------------------------------------------------
# Копия модели из vliw/core/asm_parser.py и vliw/core/model.py. Самодостаточная
# копия, а не импорт, — намеренно: этот файл рассылается людям, у которых
# основного репозитория нет и не будет. Логика держится идентичной оригиналу,
# чтобы результат был совместим.
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
    "movts": "ADD", "movtd": "ADD", "sxt": "ADD",
}

# Управляющие и настроечные операции. В графе ВЫЧИСЛЕНИЙ им не место: `setwd`
# объявляет окно регистров, `disp` готовит переход, `getsp` берёт указатель
# стека. Раньше всё незнакомое считалось арифметикой — и в probe.s из 36
# «операций» пять были такими фантомами (14%), они завышали n_ops и портили
# op_counts. Теперь они считаются отдельно (`control_ops`) и в граф не идут:
# спрятать их молча было бы враньём, посчитать сложением — тоже.
CONTROL = {
    "nop", "return", "ct", "ibranch", "call", "disp", "rbranch",
    "setwd", "setbn", "setsft", "settr", "setmas", "setei",
    "getsp", "getpl", "bap", "eap", "flushr", "flushc", "wait",
    "ipd", "abn", "abp", "abg", "alc", "loop_mode", "pref", "landing",
}

# У записи в память НЕТ регистра-приёмника: `std,2 %dr2, 0x0, %db[0]` кладёт
# %db[0] по адресу %dr2, то есть последний операнд — ИСТОЧНИК. Считая его
# приёмником (как делала первая версия), мы и теряли настоящую зависимость по
# сохраняемому значению, и выдумывали несуществующую запись в регистр.
NO_DST = {"STORE"}

# Латентности и занятие порта — из vliw/core/model.py, там же указано, как
# каждое число получено. Уезжают в JSON целиком (`model`), чтобы получатель
# видел, ПРОТИВ ЧЕГО считались нижние границы, и мог поправить.
_LATENCY = {"ADD": 1, "SUB": 1, "AND": 1, "SHL": 1,
            "MUL": 4, "DIV": 11, "LOAD": 5, "STORE": 1}
_OCCUPANCY = {"DIV": 2}                       # остальные по умолчанию 1
_LAT_SOURCE = {"ADD": "измерено", "SUB": "измерено",
               "AND": "допущение", "SHL": "допущение",
               "MUL": "измерено", "DIV": "измерено",
               "LOAD": "измерено", "STORE": "допущение"}
_CHANNELS = {
    "ADD": (0, 1, 2, 3, 4, 5), "SUB": (0, 1, 2, 3, 4, 5),
    "AND": (0, 1, 2, 3, 4, 5), "SHL": (0, 1, 2, 3, 4, 5),
    "MUL": (0, 1, 3, 4), "DIV": (5,),
    "LOAD": (0, 2, 3, 5), "STORE": (2, 5),
}
WIDTH = 6

_OP = re.compile(
    r"^\s*(?P<mn>[a-z][a-z0-9_]*)"
    r"(?:,(?P<chan>\d+))?"
    r"(?P<flags>(?:,[a-z][a-z0-9]*)*)"  # модификаторы после канала: ,sm и др.
    r"(?:\s+(?P<args>.*?))?\s*$"
)
"""Одна операция широкой команды.

МОДИФИКАТОРЫ. После канала компилятор ставит признаки исполнения, прежде
всего `,sm` — спекулятивное исполнение. Без них в шаблоне строка не
подходила под него ЦЕЛИКОМ и операция молча пропадала: на выводе `lcc -O3`
обычного цикла так терялось 90 строк из 182, больше половины кода. На
простых пробах это не проявляется — там `,sm` нет вовсе, поэтому и жило
незамеченным.
"""
_NOP = re.compile(r"^\s*nop\s+(?P<n>\d+)\s*$", re.I)
_REG = re.compile(r"%?\b([a-z]+\d+|[a-z]+\[\d+\])\b")
_COMMENT = re.compile(r"(//|!|;).*$")
# lcc подписывает каждую широкую команду комментарием `! <0007>`, и это НОМЕР
# ТАКТА, а не порядковый номер команды: пропуски в нумерации ровно совпадают с
# его же `nop N` (в probe.s 8 → 10 при `nop 1`, 34 → 40 при `nop 5`). То есть
# такт выдачи не надо реконструировать — компилятор его назвал. Читаем ДО
# срезания комментариев, свой счёт оставляем как сверку.
_BUNDLE_MARK = re.compile(r"!\s*<(\d+)>")


class Op:
    __slots__ = ("index", "mnemonic", "op", "channel", "dst", "srcs",
                 "cycle", "bundle", "known", "line")

    def __init__(self, index, mnemonic, op, channel, dst, srcs,
                 cycle, bundle, known, line):
        self.index = index
        self.mnemonic = mnemonic
        self.op = op
        self.channel = channel
        self.dst = dst
        self.srcs = srcs
        self.cycle = cycle
        self.bundle = bundle
        self.known = known
        self.line = line


class Parsed:
    __slots__ = ("ops", "bundles", "nop_cycles", "control_ops", "unknown",
                 "skipped", "marker_cycles", "marker_seen", "marker_mismatch")

    def __init__(self):
        self.ops: list[Op] = []
        self.bundles = 0
        self.nop_cycles = 0
        self.marker_cycles = 0      # последний такт по разметке lcc, +1
        self.marker_seen = 0        # сколько широких команд он подписал
        self.marker_mismatch = 0    # где наш счёт разошёлся с его разметкой
        self.control_ops = 0
        self.unknown: dict[str, int] = {}
        self.skipped = 0

    @property
    def compiler_cycles(self) -> int:
        return (max(o.cycle for o in self.ops) + 1) if self.ops else 0


def parse_asm(text: str) -> Parsed:
    """Разобрать текст .s в операции с их исходным расписанием."""
    res = Parsed()
    bundle = -1
    cycle = 0
    pending_nop = 0
    pending_mark: int | None = None

    def take(body: str, lineno: int) -> None:
        nonlocal pending_nop
        if body.startswith(".") or body.endswith(":"):
            return                                  # директива или метка

        m_nop = _NOP.match(body)
        if m_nop:
            # `nop N` стоит ВНУТРИ широкой команды и означает задержку ПЕРЕД
            # следующей: применяем её на открытии следующей скобки.
            pending_nop += int(m_nop.group("n"))
            res.nop_cycles += int(m_nop.group("n"))
            return

        m = _OP.match(body)
        if not m:
            res.skipped += 1
            return

        mn = m.group("mn").lower()
        if mn in CONTROL:
            res.control_ops += 1
            return

        op_class = MNEMONICS.get(mn)
        known = op_class is not None
        if not known:
            # Незнакомую мнемонику НЕ выдаём за сложение молча: класс остаётся
            # UNKNOWN, каналы у неё считаются любыми, латентность 1, и она
            # видна в отчёте отдельной строкой вместе с похожими знакомыми.
            res.unknown[mn] = res.unknown.get(mn, 0) + 1
            # Но БЕЗ канала это и не операция ALC. В e2k всё, что исполняется
            # на шести арифметических каналах, несёт `,N`; без него перед нами
            # предикатная логика (`landp`, `pass`) или подготовка перехода
            # (`ldisp`) — другой блок машины. Считая их арифметикой, мы сажали
            # их на чужие порты, и расписание компилятора переставало
            # восстанавливаться на первом же из них.
            if m.group("chan") is None:
                res.control_ops += 1
                return
            op_class = "UNKNOWN"

        args = (m.group("args") or "").strip()
        regs = _REG.findall(args)
        if op_class in NO_DST:
            dst, srcs = None, tuple(regs)
        else:
            dst = regs[-1] if regs else None
            srcs = tuple(regs[:-1]) if len(regs) > 1 else ()

        chan = m.group("chan")
        res.ops.append(Op(
            index=len(res.ops), mnemonic=mn, op=op_class,
            channel=int(chan) if chan is not None else None,
            dst=dst, srcs=srcs, cycle=cycle, bundle=max(0, bundle),
            known=known, line=lineno,
        ))

    for lineno, raw in enumerate(text.splitlines(), 1):
        mk = _BUNDLE_MARK.search(raw)
        if mk:
            pending_mark = int(mk.group(1))
            res.marker_cycles = max(res.marker_cycles, pending_mark + 1)

        line = _COMMENT.sub("", raw).strip()
        # Одна строка может нести и открытие, и содержимое, и закрытие:
        # `{ nop 1 }` в выводе lcc встречается, а первая версия на такой
        # строке теряла ТАКТ целиком — закрывающую скобку никто не считал.
        while line:
            if line.startswith("{"):
                bundle += 1
                cycle += pending_nop
                pending_nop = 0
                if pending_mark is not None:
                    # Такт берём у самого компилятора, а не у своего счётчика.
                    # Расхождение не проглатываем: оно значит, что мы чего-то не
                    # понимаем в формате, и знать об этом важнее, чем получить
                    # гладкое число.
                    res.marker_seen += 1
                    if pending_mark != cycle:
                        res.marker_mismatch += 1
                    cycle = pending_mark
                    pending_mark = None
                line = line[1:].strip()
                continue
            if line.startswith("}"):
                cycle += 1
                line = line[1:].strip()
                continue
            close = line.find("}")
            if close >= 0:
                body, line = line[:close].strip(), line[close:]
            else:
                body, line = line, ""
            if body:
                take(body, lineno)

    res.bundles = bundle + 1
    if res.ops and all(o.cycle == 0 for o in res.ops):
        # Файл без фигурных скобок (руками вставленный листинг без
        # bundle-разметки) — такт неизвестен. Сказать «все операции стоят в
        # такте 0» было бы неправдой.
        for o in res.ops:
            o.cycle = -1
    return res


# --------------------------------------------------------------------------
# Граф зависимостей
# --------------------------------------------------------------------------

def build_graph(ops: list[Op]) -> list[dict]:
    """Граф зависимостей. Регистры — локальные порядковые номера.

    Главное правило — СЕМАНТИКА ШИРОКОЙ КОМАНДЫ: все операции одного такта
    читают операнды ОДНОВРЕМЕННО, до того как ляжет хоть одна запись этого же
    такта. Поэтому текстовый порядок внутри `{ … }` ничего не значит, и вот эта
    пара из probe.s — НЕ зависимость по данным:

        {  ldw,0    0x0, [ a+16 ], %r5      ← пишет %r5
           sdivs,5  %r5, %r6, %r4           ← читает СТАРЫЙ %r5
        }

    Деление берёт значение, загруженное раньше, а загрузка готовит %r5 для
    следующего потребителя: это переиспользование регистра (WAR), обычное дело
    при программной конвейеризации. Первая версия читала такие пары как «запись
    → чтение» по номеру строки — выдумывала рёбра, завышала критический путь и
    портила обучающие примеры. Здесь такт обрабатывается целиком: сначала все
    читают состояние ПРЕДЫДУЩИХ тактов, потом все пишут.

    Три вида рёбер, и разделены они не для красоты:

      preds (RAW, «запись → чтение») — настоящая зависимость по данным. Только
        она ограничивает оптимум, поэтому критический путь считается по ней.
      war  («чтение → запись») и waw («запись → запись») — ложные зависимости.
        Они снимаются переименованием регистров, оптимум не ограничивают, но
        БЕЗ НИХ переставлять операции нельзя: получится код, который считает
        не то. Первая версия их не записывала, и присланный граф не годился
        для перепланирования — только для просмотра.
    """
    reg_id: dict[str, int] = {}

    def rid(name: str) -> int:
        return reg_id.setdefault(name, len(reg_id))

    last_writer: dict[str, int] = {}
    readers: dict[str, list[int]] = defaultdict(list)
    graph: list[dict] = [None] * len(ops)          # type: ignore[list-item]

    def group_key(o: Op) -> int:
        # Такт неизвестен (файл без фигурных скобок) — каждая операция сама по
        # себе, иначе весь файл слипся бы в один «такт» и все зависимости
        # исчезли бы разом.
        return o.cycle if o.cycle >= 0 else -(o.index + 1)

    i = 0
    while i < len(ops):
        j = i
        while j < len(ops) and group_key(ops[j]) == group_key(ops[i]):
            j += 1
        group = ops[i:j]

        # 1. Читают все — по состоянию на начало такта.
        for o in group:
            graph[o.index] = {
                "id": o.index,
                "op": o.op,
                "preds": sorted({last_writer[s] for s in o.srcs
                                 if s in last_writer}),
                "war": [],
                "waw": [],
                "dst": rid(o.dst) if o.dst else None,
                "srcs": [rid(s) for s in o.srcs],
            }
        # 2. Отмечаем читателей — включая читателей ЭТОГО такта: именно они
        #    дают WAR-ребро к записи, стоящей с ними в одной команде.
        for o in group:
            for s in o.srcs:
                readers[s].append(o.index)
        # 3. Теперь пишут.
        for o in group:
            if not o.dst:
                continue
            w = last_writer.get(o.dst)
            if w is not None:
                graph[o.index]["waw"] = [w]
            graph[o.index]["war"] = sorted(set(readers.get(o.dst, ()))
                                           - {o.index})
            last_writer[o.dst] = o.index
            readers[o.dst] = []
        i = j
    return graph


def _lat(op: str) -> int:
    return _LATENCY.get(op, 1)


def _occ(op: str) -> int:
    return _OCCUPANCY.get(op, 1)


def _ports(op: str) -> tuple[int, ...]:
    return _CHANNELS.get(op, tuple(range(WIDTH)))    # UNKNOWN — любой канал


# --------------------------------------------------------------------------
# Нижние границы: против чего сравнивать расписание компилятора
# --------------------------------------------------------------------------

def critical_path(graph: list[dict]) -> int:
    """Длина критического пути по RAW-рёбрам, в тактах.

    Нижняя граница ЛЮБОГО корректного расписания: сколько бы портов ни было,
    цепочку зависимых операций короче не сделать. Считается по программному
    порядку — предшественник всегда левее, поэтому одного прохода хватает.
    """
    est = [0] * len(graph)
    end = 0
    for n in graph:
        i = n["id"]
        for p in n["preds"]:
            est[i] = max(est[i], est[p] + _lat(graph[p]["op"]))
        end = max(end, est[i] + _lat(n["op"]))
    return end


def resource_bound(counts: dict[str, int]) -> int:
    """Нижняя граница по портам, в тактах.

    Две оценки, обе честные и обе не тугие:
      * операций класса больше, чем портов под них: ceil(n·occ / портов);
      * порт — единственный дом для своих операций (делитель на `,5`): они
        встают в очередь, и очередь не короче суммы их occupancy.
    """
    best = 0
    sole: dict[int, int] = defaultdict(int)
    for op, n in counts.items():
        ports = _ports(op)
        if not ports:
            continue
        best = max(best, math.ceil(n * _occ(op) / len(ports)))
        if len(ports) == 1:
            sole[ports[0]] += n * _occ(op)
    if sole:
        best = max(best, max(sole.values()))
    return max(best, math.ceil(sum(counts.values()) / WIDTH) if counts else 0)


def observed_gaps(graph: list[dict], ops: list[Op]) -> dict[str, int]:
    """Минимальный зазор «производитель → потребитель» по классам операций.

    Компилятор ОБЯЗАН развести зависимые операции не ближе латентности, значит
    для каждого класса min(зазор) ≥ латентность нигде не нарушится, а сверху
    сходится к ней по мере накопления файлов. Это и есть замер латентности по
    чужому коду — без доступа к самому коду.
    """
    gaps: dict[str, int] = {}
    for n in graph:
        c = ops[n["id"]]
        if c.cycle < 0:
            continue
        for p in n["preds"]:
            pr = ops[p]
            if pr.cycle < 0:
                continue
            g = c.cycle - pr.cycle
            if g <= 0:
                # RAW внутри одного такта невозможен по построению графа;
                # если такое всё же всплыло — молчать нельзя, это баг разбора.
                raise AssertionError(
                    f"RAW-ребро {p}->{n['id']} с зазором {g}: разбор сломан")
            if pr.op not in gaps or g < gaps[pr.op]:
                gaps[pr.op] = g
    return gaps


def latency_violations(gaps: dict[str, int]) -> list[dict]:
    """Где настоящий код разошёлся с нашей моделью латентностей.

    Не ошибка скрипта, а НАХОДКА: если lcc ставит потребителя ближе, чем мы
    считали возможным, значит либо латентность у их машины меньше, либо мы
    неверно определили приёмник операции. И то и другое надо знать.
    """
    out = []
    for op, g in sorted(gaps.items()):
        if g < _lat(op):
            out.append({"op": op, "assumed": _lat(op), "observed": g,
                        "source": _LAT_SOURCE.get(op, "допущение")})
    return out


def reg_pressure(ops: list[Op]) -> int:
    """Сколько значений живо одновременно в пике.

    Планировщик может растащить операции и упереться в регистры, а не в порты.
    Без этого числа «оптимальное» расписание может оказаться нереализуемым.
    """
    last_use: dict[str, int] = {}
    for o in ops:
        for s in o.srcs:
            last_use[s] = o.index
    live: set[str] = set()
    peak = 0
    for o in ops:
        if o.dst:
            live.add(o.dst)
        peak = max(peak, len(live))
        for s in o.srcs:
            if last_use.get(s) == o.index:
                live.discard(s)
    return peak


def compiler_schedule(ops: list[Op]) -> list[dict] | None:
    """Расписание, которое построил САМ компилятор.

    Не «есть ли канал у операций», а честная попытка разложить каждую операцию
    по занятости порта — с occupancy деления (держит порт 2 такта). Если такт
    не проставлен (файл без фигурных скобок), портфель портов пуст для этого
    класса или клетка уже занята — возвращаем None, а не приблизительный
    результат: врать не будем, что компилятор построил то, чего он не строил.
    """
    if not ops or any(o.cycle < 0 for o in ops):
        return None
    used: dict[tuple[int, int], int] = {}
    out: list[dict] = []
    for o in ops:
        ports = _ports(o.op)
        if not ports:
            return None
        port = o.channel if o.channel in ports else None
        if port is None:
            port = next((p for p in ports if (o.cycle, p) not in used), None)
            if port is None:
                return None
        if (o.cycle, port) in used:
            return None
        for k in range(_occ(o.op)):
            used[(o.cycle + k, port)] = o.index
        out.append({"id": o.index, "cycle": o.cycle, "channel": port})
    return out


def fingerprint(graph: list[dict]) -> str:
    """Отпечаток структуры графа: одинаковые графы схлопываются при сводке.

    Считается по форме (id, класс, предшественники), а не по тексту, поэтому
    ничего лишнего не несёт и не зависит от имени файла: два человека,
    приславшие один и тот же код, будут видны как один файл, а не как два.
    """
    canon = json.dumps([[n["id"], n["op"], n["preds"]] for n in graph],
                       separators=(",", ":"))
    return hashlib.sha256(canon.encode()).hexdigest()[:16]


# --------------------------------------------------------------------------
# Сборка записи
# --------------------------------------------------------------------------

def process(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    res = parse_asm(text)
    graph = build_graph(res.ops)

    counts: dict[str, int] = {}
    for n in graph:
        counts[n["op"]] = counts.get(n["op"], 0) + 1

    sched = compiler_schedule(res.ops)
    cycles = res.compiler_cycles if sched else 0
    cp = critical_path(graph)
    rb = resource_bound(counts)
    lower = max(cp, rb)
    gaps = observed_gaps(graph, res.ops)

    widths: dict[str, int] = defaultdict(int)
    ports: dict[str, int] = defaultdict(int)
    if sched:
        per_cycle: dict[int, int] = defaultdict(int)
        for s in sched:
            per_cycle[s["cycle"]] += 1
            ports[str(s["channel"])] += 1
        for w in per_cycle.values():
            widths[str(w)] += 1

    return {
        "schema": SCHEMA,
        "tool": TOOL_VERSION,
        "source": path.name,            # только имя файла, без пути целиком
        "fingerprint": fingerprint(graph),
        "n_ops": len(graph),
        "op_counts": counts,
        "graph": graph,
        "compiler_schedule": sched,
        "compiler_cycles": cycles or None,
        "bundles": res.bundles,
        "lcc_cycles": res.marker_cycles or None,
        "marker_checked": res.marker_seen,
        "marker_mismatch": res.marker_mismatch,
        "nop_cycles": res.nop_cycles,
        "bundle_widths": dict(widths) or None,
        "port_usage": dict(ports) or None,
        "critical_path": cp,
        "resource_bound": rb,
        "lower_bound": lower,
        "slack": (cycles - lower) if cycles else None,
        "ipc": round(len(graph) / cycles, 2) if cycles else None,
        "reg_pressure": reg_pressure(res.ops),
        "observed_min_gap": gaps,
        "latency_violations": latency_violations(gaps),
        "control_ops": res.control_ops,
        "unknown_mnemonics": res.unknown,
        "skipped_lines": res.skipped,
        "model": {
            "width": WIDTH,
            "latency": _LATENCY,
            "occupancy": _OCCUPANCY,
            "channels": {k: list(v) for k, v in _CHANNELS.items()},
            "note": "латентности сняты с lcc-1.29.16 / e2k-v6; если у вас "
                    "другая машина — цифры поправьте, границы пересчитаются",
        },
    }


# --------------------------------------------------------------------------
# Печать
# --------------------------------------------------------------------------

def render_preview(rec: dict) -> str:
    graph = rec["graph"]
    lines = ["граф зависимостей (это и есть то, что уйдёт наружу):"]
    for n in graph:
        bits = ""
        if n["preds"]:
            bits += f" <- {' '.join(map(str, n['preds']))}"
        false_dep = n["war"] + n["waw"]
        if false_dep:
            bits += f"   (ложные: {' '.join(map(str, sorted(set(false_dep))))})"
        lines.append(f"  {n['id']} {n['op']}{bits}")

    sched = rec["compiler_schedule"]
    if sched:
        lines.append("расписание компилятора (такт=канал):")
        for s in sched:
            lines.append(f"  {s['id']}: такт={s['cycle']} канал={s['channel']}")
    else:
        lines.append("(явных каналов в файле нет — расписание компилятора "
                     "не восстановлено, только граф)")
    return "\n".join(lines)


def render_summary(rec: dict) -> str:
    out = [f"операций: {rec['n_ops']}   по типам: {rec['op_counts']}"]
    if rec["control_ops"]:
        out.append(f"управляющих операций пропущено: {rec['control_ops']} "
                   f"(setwd/disp/ct и подобные — они не считают)")
    if rec["skipped_lines"]:
        out.append(f"строк не разобрано: {rec['skipped_lines']}")
    if rec["unknown_mnemonics"]:
        for mn, k in sorted(rec["unknown_mnemonics"].items()):
            near = difflib.get_close_matches(mn, MNEMONICS, n=3, cutoff=0.72)
            hint = ("похоже на: " + ", ".join(near)) if near else "класс UNKNOWN"
            out.append(f"незнакомая мнемоника `{mn}` ×{k} — {hint}")

    if rec["compiler_cycles"]:
        out.append(
            f"тактов у компилятора: {rec['compiler_cycles']}   "
            f"нижняя граница: {rec['lower_bound']} "
            f"(критический путь {rec['critical_path']}, "
            f"порты {rec['resource_bound']})")
        slack = rec["slack"]
        if slack == 0:
            out.append("  запас 0 — расписание упёрлось в нижнюю границу: "
                       "это оптимум, и он доказан")
        else:
            out.append(f"  запас до границы: {slack} т. — НЕ доказанная "
                       f"потеря (граница не обязана быть достижимой), "
                       f"а метка «этот файл стоит посмотреть»")
        out.append(f"  IPC {rec['ipc']}   пик живых значений: "
                   f"{rec['reg_pressure']}   ширина команд: "
                   f"{rec['bundle_widths']}")
    if rec.get("marker_checked"):
        if rec["marker_mismatch"]:
            out.append(f"  СВЕРКА: из {rec['marker_checked']} широких команд, "
                       f"подписанных lcc, наш счёт разошёлся на "
                       f"{rec['marker_mismatch']} — такты взяты по его "
                       f"разметке, но разбор формата неточен")
        else:
            out.append(f"  сверка: все {rec['marker_checked']} широких команд "
                       f"совпали с разметкой lcc — такт не реконструкция, "
                       f"а его собственный ответ")
        tail = (rec.get("lcc_cycles") or 0) - (rec.get("compiler_cycles") or 0)
        if rec.get("compiler_cycles") and tail > 0:
            out.append(f"  (всего у lcc {rec['lcc_cycles']} т.; последние "
                       f"{tail} заняты возвратом и переходом — операций графа "
                       f"там нет, в сравнение они не идут)")
    for v in rec["latency_violations"]:
        out.append(f"  НАХОДКА: {v['op']} — мы считали латентность "
                   f"{v['assumed']} ({v['source']}), а в файле зазор "
                   f"{v['observed']}; значит модель надо править")
    return "\n".join(out)


# --------------------------------------------------------------------------
# Режимы
# --------------------------------------------------------------------------

def read_records(paths: list[Path]) -> list[dict]:
    recs: list[dict] = []
    for p in paths:
        if not p.exists():
            print(f"!! файл не найден: {p}", file=sys.stderr)
            continue
        for ln, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"!! {p.name}:{ln} не JSON — пропущено ({e})",
                      file=sys.stderr)
                continue
            if "graph" not in rec:
                print(f"!! {p.name}:{ln} нет поля graph — это не наша запись",
                      file=sys.stderr)
                continue
            recs.append(rec)
    return recs


def cmd_collect(args) -> int:
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
                    print(render_summary(rec))
                    print(render_preview(rec))
                print("--- JSON-строка ниже: то, что стоит прислать целиком ---")
            line = json.dumps(rec, ensure_ascii=False)
            print(line)
            if out_fh:
                out_fh.write(line + "\n")
    finally:
        if out_fh:
            out_fh.close()

    if not args.quiet:
        many = len(args.files) > 1
        print(f"\nНичего никуда не отправлено само — файл{'ы' if many else ''} "
              f"выше только распечатан{'ы' if many else ''} в терминал"
              + (f" и дописан{'ы' if many else ''} в {args.out}"
                 if args.out else "")
              + ". Отправлять или нет — решать вам.")
    return 0


def cmd_report(args) -> int:
    """Свести присланное: что пришло, где компилятор оставил такты, где мы врём."""
    recs = read_records(args.files)
    if not recs:
        print("нечего сводить: ни одной записи не прочитано", file=sys.stderr)
        return 1

    seen: dict[str, dict] = {}
    dups = 0
    for r in recs:
        fp = r.get("fingerprint") or fingerprint(r["graph"])
        if fp in seen:
            dups += 1
            continue
        seen[fp] = r
    uniq = list(seen.values())

    old = [r for r in uniq if r.get("schema", 1) < SCHEMA]
    print(f"записей прочитано: {len(recs)}   уникальных графов: {len(uniq)}"
          + (f"   повторов схлопнуто: {dups}" if dups else ""))
    if old:
        print(f"ВНИМАНИЕ: {len(old)} записей от старой версии скрипта "
              f"(schema<{SCHEMA}) — у них нет нижних границ и ложных рёбер; "
              f"их стоит пересобрать новой версией")

    print("\nфайл                     оп.  такты  граница  запас   IPC")
    print("-" * 62)
    with_sched = 0
    total_ops = 0
    total_slack = 0
    for r in sorted(uniq, key=lambda x: -(x.get("slack") or 0)):
        total_ops += r.get("n_ops", 0)
        cyc = r.get("compiler_cycles")
        lb = r.get("lower_bound")
        sl = r.get("slack")
        if cyc:
            with_sched += 1
            total_slack += sl or 0
        name = (r.get("source") or "?")[:22]
        print(f"{name:<22} {r.get('n_ops', 0):>5} "
              f"{(cyc if cyc else '—'):>6} {(lb if lb is not None else '—'):>8} "
              f"{(sl if sl is not None else '—'):>6} "
              f"{(r.get('ipc') if r.get('ipc') else '—'):>6}")
    print("-" * 62)
    print(f"итого: {total_ops} операций, у {with_sched} из {len(uniq)} файлов "
          f"восстановлено расписание, суммарный запас {total_slack} т.")
    print("«запас» — расстояние до НИЖНЕЙ ГРАНИЦЫ, а не до достижимого "
          "оптимума: 0 доказывает оптимальность, большое число лишь "
          "показывает, с какого файла начинать смотреть.")

    # Латентности по чужому коду — главный улов сводки.
    agg: dict[str, int] = {}
    for r in uniq:
        for op, g in (r.get("observed_min_gap") or {}).items():
            if op not in agg or g < agg[op]:
                agg[op] = g
    if agg:
        print("\nлатентности, измеренные по присланному коду:")
        print("  класс   наша модель        минимальный зазор   вывод")
        for op in sorted(agg):
            g, mine = agg[op], _lat(op)
            if g < mine:
                verdict = f"МОДЕЛЬ ЗАВЫШЕНА: не больше {g}"
            elif g == mine:
                verdict = "сходится"
            else:
                verdict = f"не противоречит (сверху не прижато: ≤{g})"
            print(f"  {op:<7} {mine:>3} ({_LAT_SOURCE.get(op, 'допущение')})"
                  f"{'':<4}{g:>6}{'':<14}{verdict}")
        print("  напоминание: зазор — ВЕРХНЯЯ оценка латентности "
              "(компилятор не мог поставить ближе), и она тем точнее, "
              "чем больше файлов пришло.")

    ops_total: dict[str, int] = defaultdict(int)
    for r in uniq:
        for op, n in (r.get("op_counts") or {}).items():
            ops_total[op] += n
    if ops_total:
        print(f"\nсостав операций по всем файлам: {dict(sorted(ops_total.items()))}")

    unknown: dict[str, int] = defaultdict(int)
    for r in uniq:
        for mn, n in (r.get("unknown_mnemonics") or {}).items():
            unknown[mn] += n
    if unknown:
        print("\nмнемоники, которых мы не знаем "
              "(их стоит добавить в MNEMONICS — сейчас они класса UNKNOWN):")
        for mn, n in sorted(unknown.items(), key=lambda kv: -kv[1]):
            near = difflib.get_close_matches(mn, MNEMONICS, n=3, cutoff=0.72)
            print(f"  {mn:<16} ×{n}"
                  + (f"   похоже на: {', '.join(near)}" if near else ""))
    return 0


def cmd_to_dataset(args) -> int:
    """Присланное → обучающие примеры в формате dataset.jsonl."""
    recs = read_records(args.files)
    seen: set[str] = set()
    written = 0
    skipped = 0
    fh = args.out.open("w", encoding="utf-8") if args.out else sys.stdout
    try:
        for r in recs:
            sched = r.get("compiler_schedule")
            if not sched:
                skipped += 1
                continue        # без расписания нет ответа — учить нечему
            ids = {n["id"] for n in r["graph"]}
            if {s["id"] for s in sched} != ids:
                # Расписание не про этот граф (обрезанная или склеенная
                # запись). В обучение такое пускать нельзя.
                print(f"!! {r.get('source')}: расписание не совпадает с графом "
                      f"по составу операций — пропущено", file=sys.stderr)
                skipped += 1
                continue
            fp = r.get("fingerprint") or fingerprint(r["graph"])
            if fp in seen:
                skipped += 1
                continue
            seen.add(fp)

            graph_lines = []
            for n in r["graph"]:
                pred = (" <- " + " ".join(map(str, n["preds"]))) if n["preds"] else ""
                graph_lines.append(f"{n['id']} {n['op']}{pred}")
            prompt = ("профиль: e2k-v6-measured\nграф:\n"
                      + "\n".join(graph_lines) + "\nрасписание:")
            completion = "\n".join(
                f"{s['id']}: такт={s['cycle']} канал={s['channel']}"
                for s in sched)
            fh.write(json.dumps({
                "prompt": prompt,
                "completion": completion,
                "meta": {
                    "source": "real",          # отличать от synthetic-выборки
                    "file": r.get("source"),
                    "fingerprint": fp,
                    "n": r.get("n_ops"),
                    "width": WIDTH,
                    "makespan": r.get("compiler_cycles"),
                    "lower_bound": r.get("lower_bound"),
                    "slack": r.get("slack"),
                },
            }, ensure_ascii=False) + "\n")
            written += 1
    finally:
        if fh is not sys.stdout:
            fh.close()
    print(f"обучающих примеров записано: {written}"
          + (f", пропущено (без расписания или повтор): {skipped}" if skipped else "")
          + (f" → {args.out}" if args.out else ""), file=sys.stderr)
    if written:
        print("meta.source=\"real\" — этим они отличаются от synthetic-выборки; "
              "мешать в обучение можно, но долю реальных держите на виду.",
              file=sys.stderr)
    return 0


_SAMPLE = """\
	.text
main:
	! <0000>
	{
	  setwd	wsz = 0xc, nfx = 0x1
	  ldw,3	0x0, [ _f64,_lts0 a ], %r3
	}
	! <0001>
	{
	  ldw,2	0x0, [ _f64,_lts0 b ], %r4
	}
	! <0002>
	{ nop 1 }
	! <0004>
	{
	  ldw,0	0x0, [ _f64,_lts0 c ], %r3
	  muls,1	%r3, %r4, %r5
	  nop 4
	}
	! <0009>
	{
	  adds,1	%r5, %r3, %r6
	  std,2	%r3, 0x0, %r4
	}
"""


def cmd_selftest(args) -> int:
    """Проверить, что скрипт делает то, что обещает, — до запуска на своём коде."""
    res = parse_asm(_SAMPLE)
    graph = build_graph(res.ops)
    checks: list[tuple[str, bool, str]] = []

    ops_by_class = [n["op"] for n in graph]
    checks.append(("управляющие операции не попали в граф",
                   "UNKNOWN" not in ops_by_class and len(graph) == 6,
                   f"классы: {ops_by_class}"))
    checks.append(("`{ nop 1 }` одной строкой не потерял такт",
                   res.bundles == 5,
                   f"широких команд насчитано: {res.bundles}, ждали 5"))
    checks.append(("такты сошлись с разметкой lcc (nop-ы съели такты)",
                   res.marker_seen == 5 and res.marker_mismatch == 0
                   and [o.cycle for o in res.ops] == [0, 1, 4, 4, 9, 9],
                   f"сверено {res.marker_seen}, расхождений "
                   f"{res.marker_mismatch}, такты "
                   f"{[o.cycle for o in res.ops]}"))
    store = graph[-1]
    checks.append(("у записи нет приёмника, оба регистра — источники",
                   store["op"] == "STORE" and store["dst"] is None
                   and len(store["srcs"]) == 2,
                   f"STORE: dst={store['dst']} srcs={store['srcs']}"))
    mul = graph[3]
    checks.append(("в одной команде чтение идёт ДО записи: умножение взяло "
                   "%r3 из такта 0, а не у соседней загрузки",
                   mul["op"] == "MUL" and mul["preds"] == [0, 1],
                   f"MUL preds={mul['preds']}, ждали [0, 1]"))
    checks.append(("соседняя загрузка получила WAR-ребро от умножения",
                   graph[2]["war"] == [3] and graph[2]["waw"] == [0],
                   f"LOAD war={graph[2]['war']} waw={graph[2]['waw']}"))
    cp = critical_path(graph)
    checks.append(("критический путь считается по латентностям",
                   cp == 5 + 4 + 1,
                   f"критический путь {cp}, ждали 10 (LOAD 5 + MUL 4 + ADD 1)"))
    sched = compiler_schedule(res.ops)
    checks.append(("расписание компилятора восстановлено целиком",
                   sched is not None and len(sched) == len(graph),
                   f"расписание: {sched}"))
    fp1 = fingerprint(graph)
    fp2 = fingerprint(build_graph(parse_asm(_SAMPLE).ops))
    checks.append(("отпечаток устойчив", fp1 == fp2, f"{fp1} / {fp2}"))

    ok = True
    for name, passed, detail in checks:
        print(f"  [{'ок' if passed else 'НЕ ТАК'}] {name}")
        if not passed:
            ok = False
            print(f"         {detail}")
    print("\nсамопроверка пройдена — скрипт разбирает формат как ожидается."
          if ok else
          "\nСАМОПРОВЕРКА НЕ ПРОШЛА: разбор ведёт себя не так, как задумано. "
          "Присылать результаты этой сборки не стоит.")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    modes = {"collect", "report", "to-dataset", "selftest"}
    # Совместимость со старым вызовом: `скрипт файл.s` без имени режима.
    if not argv or (argv[0] not in modes and not argv[0].startswith("-")):
        argv.insert(0, "collect")
    elif argv and argv[0].startswith("-") and argv[0] not in ("-h", "--help"):
        argv.insert(0, "collect")

    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="mode", required=True)

    p = sub.add_parser("collect", help="разобрать .s и напечатать JSON-строки")
    p.add_argument("files", nargs="+", type=Path, help="один или несколько .s")
    p.add_argument("--out", type=Path, default=None,
                   help="дописать JSON-строки в файл вместо/вместе с печатью "
                        "в терминал (по умолчанию только печать — ничего "
                        "не сохраняется без явного указания)")
    p.add_argument("--quiet", action="store_true",
                   help="не печатать человекочитаемый разбор, только JSON")
    p.set_defaults(fn=cmd_collect)

    p = sub.add_parser("report", help="свести присланные JSONL в одну картину")
    p.add_argument("files", nargs="+", type=Path)
    p.set_defaults(fn=cmd_report)

    p = sub.add_parser("to-dataset",
                       help="присланное → обучающие примеры prompt/completion")
    p.add_argument("files", nargs="+", type=Path)
    p.add_argument("--out", type=Path, default=None)
    p.set_defaults(fn=cmd_to_dataset)

    p = sub.add_parser("selftest", help="проверить разбор на встроенном образце")
    p.set_defaults(fn=cmd_selftest)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
