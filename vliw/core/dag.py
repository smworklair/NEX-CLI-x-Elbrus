"""Граф зависимостей инструкций (DAG) и набор тестовых сценариев.

Один DAG = один участок прямолинейного кода, который планировщик должен
разложить по широким командам. Узлы — инструкции, рёбра — зависимости
«результат → операнд» (RAW).
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from functools import cached_property

from .model import MachineModel

_SYMBOL = {
    "ADD": "+",
    "SUB": "-",
    "MUL": "*",
    "DIV": "/",
    "AND": "&",
    "SHL": "<<",
    # Классы, измеренные 30.08.2026. Плавающая точка помечена точкой в знаке
    # (`+.`, `*.`) — так её видно в тексте участка, не заводя второй алфавит.
    # У остальных знака в привычном смысле нет, поэтому берётся короткое имя:
    # выдумывать для предиката символ значило бы делать вид, что он читается
    # как арифметика.
    "FADD": "+.",
    "FMUL": "*.",
    "FDIV": "/.",
    "PACK": "+|",
    "PACKLOG": "&|",
    "PRED": "?",
    "MERGE": "><",
    "INSF": ">>|",
    "COMBO": "<<+",
    "AAU": "@",
    "RW": "=>",
    "UNKNOWN": "??",
}


@dataclass(frozen=True)
class Instr:
    id: int
    name: str
    op: str
    preds: tuple[int, ...]
    text: str

    def __str__(self) -> str:
        return f"{self.name}: {self.text}"


@dataclass
class DAG:
    key: str
    title: str
    note: str
    instrs: list[Instr]
    profile: str | None = None
    """Профиль модели, для которого сценарий задумывался (None = любой)."""

    family: str = ""
    """Группа сценариев: какой приём оптимизации разбирается (для /scenarios)."""

    lesson: str = ""
    """Одна строка: что именно этот участок показывает и что с ним делать."""

    def __post_init__(self) -> None:
        for i, ins in enumerate(self.instrs):
            assert ins.id == i, "инструкции должны быть пронумерованы подряд"
            for p in ins.preds:
                assert p < i, "предшественник должен идти раньше (граф ацикличен)"

    def __len__(self) -> int:
        return len(self.instrs)

    def __iter__(self):
        return iter(self.instrs)

    def __getitem__(self, i: int) -> Instr:
        return self.instrs[i]

    @cached_property
    def succs(self) -> list[tuple[int, ...]]:
        out: list[list[int]] = [[] for _ in self.instrs]
        for ins in self.instrs:
            for p in ins.preds:
                out[p].append(ins.id)
        return [tuple(s) for s in out]

    def op_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for ins in self.instrs:
            counts[ins.op] = counts.get(ins.op, 0) + 1
        return counts


# --------------------------------------------------------------------------
# Метрики графа относительно конкретной машины
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class DagMetrics:
    """Всё, что можно посчитать про граф ДО планирования.

    Две нижние границы makespan — главный инструмент объяснения в этом демо:
    они сразу показывают, чем связан данный участок кода — длиной цепочки
    зависимостей или количеством каналов.
    """

    asap: tuple[int, ...]
    """Самый ранний такт выдачи без учёта ресурсов (только зависимости)."""

    height: tuple[int, ...]
    """Длина оставшегося критического пути от инструкции до конца (с её латентностью)."""

    critical_path_bound: int
    """Нижняя граница makespan по длине цепочек зависимостей."""

    resource_bound: int
    """Нижняя граница makespan по пропускной способности каналов.

    С 02.09.2026 считается ИНТЕРВАЛЬНО (см. `_interval_bound`), а не делением
    суммарной занятости на число каналов. Прежний способ не выигрывал у
    критического пути НИ НА ОДНОМ из 300 графов трудного эвала — то есть был
    мёртвым кодом с точки зрения границы.
    """

    @property
    def lower_bound(self) -> int:
        return max(self.critical_path_bound, self.resource_bound)

    @property
    def binding(self) -> str:
        if self.resource_bound > self.critical_path_bound:
            return "ресурсы"
        if self.critical_path_bound > self.resource_bound:
            return "критический путь"
        return "и то, и другое"


def _interval_bound(dag: DAG, model: MachineModel,
                    asap: list[int], height: list[int]) -> int:
    """Интервальная (энергетическая) нижняя граница makespan.

    ЗАЧЕМ. Прежняя ресурсная граница делила суммарную занятость каналов на их
    количество — и проигрывала критическому пути на всех 300 графах трудного
    эвала. Она не видела главного: операции не размазаны по расписанию
    равномерно, их прижимают к своим местам зависимости.

    ИДЕЯ. Если операция выдана в такте t, то makespan >= t + height. Канал она
    держит occ тактов, значит освобождает его к t + occ, и от этого момента до
    конца расписания остаётся q = height - occ.

    Возьмём группу каналов C и все операции, которым нужны ТОЛЬКО каналы из C
    (другие могут уйти в сторону, на них рассчитывать нельзя). Отберём те, что
    не могут начаться раньше r и не могут освободить канал позже makespan - q.
    Вся их работа обязана уместиться в это окно:

        sum(occ) <= |C| * (makespan - q - r)

        =>  makespan >= r + q + ceil(sum(occ) / |C|)

    Перебираем все пары порогов (r, q). Стоимость O(n^2) на группу: для
    фиксированного r идём по операциям в порядке убывания q и накапливаем
    работу — так каждый префикс сразу даёт кандидата в границу.

    ЧЕГО ЗДЕСЬ НЕТ. Объединений групп каналов: перебираются только те наборы,
    что реально встречаются у операций графа. Более сильные варианты (все
    подмножества, дизъюнктивные рассуждения на монопольном порту) остаются
    возможным продолжением — эта версия уже сняла 89% узлов перебора.
    """
    n = len(dag)
    if not n:
        return 0
    occ = [model.occupancy(i.op) for i in dag]
    chans = [frozenset(model.channels_for(i.op)) for i in dag]
    tail = [height[i] - occ[i] for i in range(n)]

    best = 0
    for group in set(chans):
        width = len(group)
        if not width:
            continue
        # Только операции, которым БОЛЬШЕ некуда: их каналы вложены в группу.
        idx = [i for i in range(n) if chans[i] <= group]
        if not idx:
            continue
        by_tail = sorted(idx, key=lambda i: -tail[i])
        for r in sorted({asap[i] for i in idx}):
            work = 0
            for i in by_tail:
                if asap[i] < r:
                    continue
                work += occ[i]
                cand = r + tail[i] + -(-work // width)
                if cand > best:
                    best = cand
    return best


def compute_metrics(dag: DAG, model: MachineModel) -> DagMetrics:
    n = len(dag)
    lat = [model.latency(ins.op) for ins in dag]

    asap = [0] * n
    for ins in dag:  # инструкции топологически отсортированы по построению
        for p in ins.preds:
            asap[ins.id] = max(asap[ins.id], asap[p] + lat[p])

    height = [0] * n
    for ins in reversed(dag.instrs):
        h = 0
        for s in dag.succs[ins.id]:
            h = max(h, height[s])
        height[ins.id] = lat[ins.id] + h

    cp_bound = max((asap[i] + height[i] for i in range(n)), default=0)

    # Ресурсная граница — интервальная, см. `_interval_bound`.
    res_bound = _interval_bound(dag, model, asap, height)

    return DagMetrics(
        asap=tuple(asap),
        height=tuple(height),
        critical_path_bound=cp_bound,
        resource_bound=max(0, res_bound),
    )


# --------------------------------------------------------------------------
# Конструктор графов
# --------------------------------------------------------------------------


class DagBuilder:
    def __init__(self, key: str, title: str, note: str = "", profile: str | None = None,
                 family: str = "", lesson: str = ""):
        self.key = key
        self.title = title
        self.note = note
        self.profile = profile
        self.family = family
        self.lesson = lesson
        self._instrs: list[Instr] = []

    def op(self, op: str, name: str, *preds: int, args: str | None = None) -> int:
        i = len(self._instrs)
        if args is not None:
            text = f"{name} = {args}"
        elif op in ("LOAD",):
            src = f"[{self._nm(preds[0])}]" if preds else f"[p{i}]"
            text = f"{name} = ld {src}"
        elif op == "STORE":
            text = f"st {self._nm(preds[0])}" if preds else f"st {name}"
        elif len(preds) == 2:
            text = f"{name} = {self._nm(preds[0])} {_SYMBOL[op]} {self._nm(preds[1])}"
        elif len(preds) == 1:
            text = f"{name} = {self._nm(preds[0])} {_SYMBOL[op]} c{i}"
        else:
            text = f"{name} = x{i} {_SYMBOL[op]} y{i}"
        self._instrs.append(Instr(i, name, op, tuple(preds), text))
        return i

    def _nm(self, i: int) -> str:
        return self._instrs[i].name

    def build(self) -> DAG:
        return DAG(self.key, self.title, self.note, self._instrs, self.profile,
                   self.family, self.lesson)


# --------------------------------------------------------------------------
# Сценарии
# --------------------------------------------------------------------------


def _simple4() -> DAG:
    b = DagBuilder(
        "simple4",
        "Четыре независимые операции и свёртка",
        "Четыре операции разной латентности без зависимостей между собой, потом "
        "попарная свёртка в один результат.\n"
        "Сложение, вычитание, умножение и деление уходят в одну широкую команду, "
        "дальше участок ждёт готовности самого длинного из них.",
        family="основа",
        lesson="С чего начинать: независимые операции расходятся по портам сразу.",
    )
    a = b.op("ADD", "t0")
    m = b.op("MUL", "t1")
    s = b.op("SUB", "t2")
    d = b.op("DIV", "t3")
    s0 = b.op("ADD", "s0", a, m)
    s1 = b.op("ADD", "s1", s, d)
    b.op("ADD", "r", s0, s1)
    return b.build()


def _loadchain() -> DAG:
    b = DagBuilder(
        "loadchain",
        "Восемь загрузок: прячем 5 тактов до готовности данных",
        "Восемь загрузок и арифметика над ними. На e2k загрузка исполнима только "
        "в `,0 ,2 ,3 ,5`, результат готов через 5 тактов.\n"
        "Планировщик должен растащить загрузку и её потребителя и заполнить "
        "дырку полезной работой. Иначе участок стоит, пока данные не придут.",
        family="память",
        lesson="Между загрузкой и её потребителем нужно 5 тактов полезной работы.",
    )
    loads = [b.op("LOAD", f"v{i}") for i in range(8)]
    m0 = b.op("MUL", "p0", loads[0], loads[1])
    m1 = b.op("MUL", "p1", loads[2], loads[3])
    a0 = b.op("ADD", "q0", loads[4], loads[5])
    a1 = b.op("ADD", "q1", loads[6], loads[7])
    s0 = b.op("ADD", "s0", m0, m1)
    s1 = b.op("ADD", "s1", a0, a1)
    r = b.op("ADD", "r", s0, s1)
    b.op("STORE", "out", r)
    return b.build()


def _mixed18() -> DAG:
    b = DagBuilder(
        "mixed18",
        "18 инструкций: смесь латентностей и нерегулярных связей",
        "Два деления, четыре умножения, загрузки и мелкая арифметика, связанные "
        "неравномерно.\n"
        "Цепочки зависимостей тянут длину участка, делитель ставит очередь. "
        "Оба ограничения видны на одном графе.",
        family="основа",
        lesson="Смешанный участок: зависимости и монопольный порт сразу.",
    )
    l0 = b.op("LOAD", "v0")
    l1 = b.op("LOAD", "v1")
    l2 = b.op("LOAD", "v2")
    l3 = b.op("LOAD", "v3")
    d0 = b.op("DIV", "d0", l0, l1)
    m0 = b.op("MUL", "m0", l2, l3)
    a0 = b.op("ADD", "a0", l0, l2)
    a1 = b.op("SUB", "a1", l1, l3)
    m1 = b.op("MUL", "m1", a0, a1)
    a2 = b.op("ADD", "a2", a0, l3)
    d1 = b.op("DIV", "d1", m0, a2)
    a3 = b.op("SHL", "a3", a1)
    m2 = b.op("MUL", "m2", a2, a3)
    a4 = b.op("AND", "a4", a3, l0)
    m3 = b.op("MUL", "m3", m1, a4)
    s0 = b.op("ADD", "s0", d0, m2)
    s1 = b.op("ADD", "s1", d1, m3)
    r = b.op("ADD", "r", s0, s1)
    b.op("STORE", "out", r)
    return b.build()


def _divpressure() -> DAG:
    b = DagBuilder(
        "divpressure",
        "Четыре деления на единственном делителе",
        "Четыре деления и один порт `,5`. Очередь: новое деление раз в два "
        "такта, результат каждого — через 11.\n"
        "Выбирать планировщику не из чего, baseline и oracle совпадают. Предел "
        "машины, а не промах эвристики.",
        family="цена операции",
        lesson="Планировать нечего — лечится только убиранием делений: см. divstrength.",
    )
    divs = [b.op("DIV", f"d{i}") for i in range(4)]
    adds = [b.op("ADD", f"a{i}") for i in range(8)]
    s0 = b.op("ADD", "s0", divs[0], divs[1])
    s1 = b.op("ADD", "s1", divs[2], divs[3])
    s2 = b.op("ADD", "s2", adds[0], adds[1])
    s3 = b.op("ADD", "s3", adds[2], adds[3])
    t0 = b.op("ADD", "t0", s0, s1)
    t1 = b.op("ADD", "t1", s2, s3)
    b.op("ADD", "r", t0, t1)
    return b.build()


def _reduce_tree(b: DagBuilder, ids: list[int], prefix: str) -> int:
    """Попарная свёртка списка значений в одно — как хвост развёрнутого цикла."""
    level = list(ids)
    k = 0
    while len(level) > 1:
        nxt = []
        for i in range(0, len(level) - 1, 2):
            nxt.append(b.op("ADD", f"{prefix}{k}", level[i], level[i + 1]))
            k += 1
        if len(level) % 2:
            nxt.append(level[-1])
        level = nxt
    return level[0]


def _slotclash() -> DAG:
    b = DagBuilder(
        "slotclash",
        "Монополия делителя: тупиковое деление против критического",
        "Два деления на один делитель (порт `,5`, единственный). `z0` готово в "
        "такте 0, но его результата никто не ждёт. `dc` стоит на критическом "
        "пути, операнд готов к такту 1.\n"
        "Эвристика выдаёт то, что готово раньше, и занимает порт. Оптимум "
        "придерживает его для `dc`. Цена ошибки — 1 такт.",
        profile="e2k-v6-measured",
        family="монопольный порт",
        lesson="Монопольный порт нельзя занимать работой, которой никто не ждёт.",
    )
    a0 = b.op("ADD", "a0")            # операнд критического деления, готов к т.1
    dz = b.op("DIV", "z0")           # тупиковое деление, готово в т.0 — ловушка
    dc = b.op("DIV", "dc", a0)       # критическое деление, готово к т.1
    m0 = b.op("MUL", "m0", dc)       # критический путь продолжается умножением
    e0 = b.op("ADD", "e0", m0)
    e1 = b.op("ADD", "e1", e0)
    e2 = b.op("ADD", "e2", e1)
    z = b.op("ADD", "z", dz)         # потребитель тупикового деления (низкий приоритет)
    g0 = b.op("ADD", "g0")           # независимая мелочь — занять свободные порты
    g1 = b.op("ADD", "g1", g0)
    r = b.op("ADD", "r", e2, z)
    r2 = b.op("ADD", "r2", r, g1)
    b.op("STORE", "out", r2)
    return b.build()


def _mulclash() -> DAG:
    b = DagBuilder(
        "mulclash",
        "Умножение на четырёх каналах: зеркало slotclash не сработало",
        "Строился как зеркало slotclash — считалось, что умножитель один "
        "(порт `,0`) и держит его 8 тактов. Ассемблер это опроверг: `muls` "
        "кодируется в `,0 ,1 ,3 ,4`, четыре умножения собираются в одну "
        "широкую команду.\n"
        "Монополии нет, разрыва между эвристикой и оптимумом тоже. Граф "
        "оставлен, чтобы сравнить с профилем `e2k-v6-firstprobe`: там "
        "«разрыв» появляется из ошибки в описании машины.",
        profile="e2k-v6-measured",
        family="проверка модели",
        lesson="Умножитель на четырёх каналах. Сравните с профилем e2k-v6-firstprobe.",
    )
    a0 = b.op("ADD", "a0")
    mz = b.op("MUL", "z0")           # тупиковое умножение, готово в т.0
    mc = b.op("MUL", "mc", a0)       # критическое умножение, готово к т.1
    d0 = b.op("DIV", "d0", mc)       # критический путь уходит в делитель
    e0 = b.op("ADD", "e0", d0)
    e1 = b.op("ADD", "e1", e0)
    z = b.op("ADD", "z", mz)
    g0 = b.op("ADD", "g0")
    g1 = b.op("ADD", "g1", g0)
    r = b.op("ADD", "r", e1, z)
    r2 = b.op("ADD", "r2", r, g1)
    b.op("STORE", "out", r2)
    return b.build()


# --------------------------------------------------------------------------
# Сценарии приёмов оптимизации
#
# Всё, что выше, показывает работу ПЛАНИРОВЩИКА: один и тот же граф, две
# раскладки, разрыв между ними. Дальше — участки, на которых видно другое:
# планировщик уже выжал всё, а такты всё равно теряются, потому что дело в
# самом коде. Такие пары («как написано» → «как надо») и есть повседневная
# работа по оптимизации под e2k из руководства по эффективному
# программированию: реассоциация свёрток, снижение силы операции, развёртка
# цикла, сокращение обращений к памяти, спекулятивное исполнение обеих ветвей.
#
# Пары сравниваются командой /all (или /run <ключ> для каждого): числа в
# таблице считает сам инструмент, здесь они намеренно не зашиты.
# --------------------------------------------------------------------------


def _seqreduce() -> DAG:
    b = DagBuilder(
        "seqreduce",
        "Свёртка в один аккумулятор: параллелизма нет",
        "Как пишут обычно: `for (i…) acc += v[i];`. Восемь загрузок независимы и "
        "уходят сразу, дальше цепочка сложений: каждое ждёт предыдущее.\n"
        "Расписание единственное. Эвристика и точный поиск совпадают. Смотрите "
        "treereduce — та же работа, то же число инструкций, другая форма графа.",
        profile="e2k-v6-measured",
        family="форма графа",
        lesson="Цепочка `acc += x` не параллелится. Разбивайте свёртку в исходнике: treereduce.",
    )
    loads = [b.op("LOAD", f"v{i}") for i in range(8)]
    acc = b.op("ADD", "acc0", loads[0], loads[1])
    for i in range(2, 8):
        acc = b.op("ADD", f"acc{i - 1}", acc, loads[i])
    b.op("STORE", "out", acc)
    return b.build()


def _treereduce() -> DAG:
    b = DagBuilder(
        "treereduce",
        "Та же свёртка деревом: реассоциация",
        "Тот же участок, что seqreduce, и столько же инструкций. Сложения "
        "свёрнуты попарно: четыре частичных суммы, потом две, потом одна. "
        "Критический путь по сложениям — три шага вместо семи.\n"
        "Компилятор сам так не сделает для чисел с плавающей точкой: меняется "
        "порядок округления. Нужно переписать код или явно разрешить "
        "реассоциацию. Сравните: /run seqreduce, затем /run treereduce.",
        profile="e2k-v6-measured",
        family="форма графа",
        lesson="То же число инструкций, участок короче. Выигрыш даёт форма графа.",
    )
    loads = [b.op("LOAD", f"v{i}") for i in range(8)]
    r = _reduce_tree(b, loads, "s")
    b.op("STORE", "out", r)
    return b.build()


def _divstrength() -> DAG:
    b = DagBuilder(
        "divstrength",
        "Снижение силы: те же четыре деления, но сдвигом",
        "Тот же граф, что divpressure. Делитель — константа 2^k, деление стало "
        "сдвигом. Сдвиг исполним на любом из шести портов, занимает один такт, "
        "результат через один — вместо порта `,5` (приём раз в два такта, "
        "латентность 11).\n"
        "Четыре операции уходят в одну широкую команду. Если делитель — "
        "переменная, тот же приём: вынести обратное значение из цикла, одно "
        "деление вместо N.",
        profile="e2k-v6-measured",
        family="цена операции",
        lesson="Убрать деление дешевле, чем планировать его. /run divpressure, затем сюда.",
    )
    fast = [b.op("SHL", f"q{i}") for i in range(4)]
    adds = [b.op("ADD", f"a{i}") for i in range(8)]
    s0 = b.op("ADD", "s0", fast[0], fast[1])
    s1 = b.op("ADD", "s1", fast[2], fast[3])
    s2 = b.op("ADD", "s2", adds[0], adds[1])
    s3 = b.op("ADD", "s3", adds[2], adds[3])
    t0 = b.op("ADD", "t0", s0, s1)
    t1 = b.op("ADD", "t1", s2, s3)
    b.op("ADD", "r", t0, t1)
    return b.build()


def _ptrchase() -> DAG:
    b = DagBuilder(
        "ptrchase",
        "Обход по указателям: цепочка зависимых загрузок",
        "`p = p->next` шесть раз. Адрес следующей загрузки известен только после "
        "предыдущей, переставить их нельзя. При латентности 5 это три десятка "
        "тактов на одном критическом пути.\n"
        "Рядом лежит независимая арифметика: планировщик обязан затолкать её "
        "в те такты, пока идёт обход. /doctor покажет: длину задаёт память.",
        profile="e2k-v6-measured",
        family="память",
        lesson="Зависимые загрузки не переставить. Латентность прячут независимой работой.",
    )
    p = b.op("LOAD", "p0")
    for i in range(1, 6):
        p = b.op("LOAD", f"p{i}", p)
    work = [b.op("ADD", f"w{i}") for i in range(8)]
    w = _reduce_tree(b, work, "u")
    r = b.op("ADD", "r", p, w)
    b.op("STORE", "out", r)
    return b.build()


def _memstream() -> DAG:
    b = DagBuilder(
        "memstream",
        "Поток «загрузить — посчитать — записать»: узкое место — запись",
        "Восемь независимых троек `x = a[i]; x += c; b[i] = x;`. Зависимости "
        "короткие. Запись кодируется только в `,2` и `,5`, загрузка — в четырёх. "
        "Восемь записей не быстрее двух за такт, и `,5` ещё нужен делителю.\n"
        "Эвристика занимает канал записи не в том порядке, точный поиск "
        "обыгрывает. Сокращать надо число обращений: шире тип, векторизация, "
        "слияние циклов.",
        profile="e2k-v6-measured",
        family="память",
        lesson="Запись живёт только в двух каналах.",
    )
    for i in range(8):
        v = b.op("LOAD", f"v{i}")
        t = b.op("ADD", f"t{i}", v)
        b.op("STORE", f"st{i}", t)
    return b.build()


def _unroll4() -> DAG:
    b = DagBuilder(
        "unroll4",
        "Развёртка ×4 с умножением: мешает латентность загрузки",
        "Тело `s += v[i] * k`, четыре итерации. Загрузки и умножения независимы, "
        "накопление свёрнуто деревом. Умножения уходят разом: четыре канала, "
        "латентность 4.\n"
        "Длину участка задаёт загрузка — 5 тактов до готовности данных, потом "
        "свёртка. Разворачивать имеет смысл, данные лучше поднимать повыше "
        "или префетчить заранее.",
        profile="e2k-v6-measured",
        family="циклы",
        lesson="Развёртка работает. Узкое место — латентность загрузки.",
    )
    muls = []
    for i in range(4):
        v = b.op("LOAD", f"v{i}")
        muls.append(b.op("MUL", f"m{i}", v))
    s0 = b.op("ADD", "s0", muls[0], muls[1])
    s1 = b.op("ADD", "s1", muls[2], muls[3])
    r = b.op("ADD", "r", s0, s1)
    b.op("STORE", "out", r)
    return b.build()


def _ifconv() -> DAG:
    b = DagBuilder(
        "ifconv",
        "Обе ветви условия посчитаны заранее",
        "На e2k переход дорогой, свободных портов обычно много. Здесь длинная "
        "ветвь (шесть зависимых сложений) и короткая (три) считаются одновременно, "
        "результат выбирается по условию.\n"
        "Инструкций вдвое больше, участок почти не удлинился: короткая ветвь "
        "уместилась в такты длинной. Если в ветвь попадёт деление, спекуляция "
        "займёт монопольный порт впустую — как в slotclash.",
        profile="e2k-v6-measured",
        family="ветвления",
        lesson="Считать обе ветви выгодно, пока в них универсальные операции.",
    )
    c = b.op("SUB", "cond")
    long_br = b.op("ADD", "L0")
    for i in range(1, 6):
        long_br = b.op("ADD", f"L{i}", long_br)
    short_br = b.op("ADD", "S0")
    for i in range(1, 3):
        short_br = b.op("ADD", f"S{i}", short_br)
    sel = b.op("ADD", "sel", long_br, short_br)
    r = b.op("AND", "r", sel, c)
    b.op("STORE", "out", r)
    return b.build()


def random_dag(
    seed: int,
    n: int = 24,
    key: str | None = None,
    title: str | None = None,
    note: str = "",
    profile: str | None = None,
    weights: dict[str, float] | None = None,
    max_preds: int = 2,
    reach: int = 6,
) -> DAG:
    """Воспроизводимый случайный граф — для поиска показательных примеров."""
    rnd = random.Random(seed)
    w = weights or {"ADD": 4, "SUB": 2, "MUL": 3, "DIV": 1, "SHL": 1, "AND": 1, "LOAD": 2}
    ops = list(w)
    probs = [w[o] for o in ops]

    b = DagBuilder(
        key or f"rand{seed}",
        title or f"Случайный граф (seed={seed}, {n} инструкций)",
        note,
        profile,
    )
    for i in range(n):
        op = rnd.choices(ops, probs)[0]
        cands = list(range(max(0, i - reach), i))
        k = 0 if not cands else rnd.randint(0, min(max_preds, len(cands)))
        if op in ("MUL", "DIV", "ADD", "SUB") and cands and k == 0 and rnd.random() < 0.6:
            k = 1
        preds = tuple(sorted(rnd.sample(cands, k))) if k else ()
        b.op(op, f"n{i}", *preds)
    return b.build()


def _wide_ilp() -> DAG:
    """Крупный участок с высоким ILP — здесь связывают уже ресурсы, а не путь."""
    b = DagBuilder(
        "wide_ilp",
        "Развёрнутый цикл: упор в пропускную способность",
        "14 независимых умножений и много сложений готовы сразу. Умножения "
        "расходятся по `,0 ,1 ,3 ,4` и идут по одному в такт на каждом.\n"
        "Участок связан числом операций на шесть портов: нижняя граница по "
        "ресурсам обгоняет границу по критическому пути. Граф большой — "
        "точный поиск переключается на запасной портфельный движок.",
        profile="e2k-v6-measured",
        family="циклы",
        lesson="Здесь связывают ресурсы, не зависимости. Единственный такой сценарий.",
    )
    muls = [b.op("MUL", f"m{i}") for i in range(14)]
    adds = [b.op("ADD", f"a{i}") for i in range(18)]
    mid = []
    for i in range(0, 14, 2):
        mid.append(b.op("ADD", f"p{i//2}", muls[i], muls[i + 1]))
    for i in range(0, 18, 2):
        mid.append(b.op("ADD", f"q{i//2}", adds[i], adds[i + 1]))
    lvl = mid
    idx = 0
    while len(lvl) > 1:
        nxt = []
        for i in range(0, len(lvl) - 1, 2):
            nxt.append(b.op("ADD", f"r{idx}", lvl[i], lvl[i + 1]))
            idx += 1
        if len(lvl) % 2:
            nxt.append(lvl[-1])
        lvl = nxt
    return b.build()


def _twodividers() -> DAG:
    """Два РАЗНЫХ делителя на одном порту — конфликт, которого раньше не было."""
    b = DagBuilder(
        "twodividers",
        "Один порт, два делителя: целочисленный против плавающего",
        "Измерение 30.08.2026 показало, что деление с плавающей точкой "
        "исполняется ровно там же, где целочисленное, — на единственном порту "
        "`,5`. До этого модель знала один делитель, и такой конфликт было "
        "НЕЧЕМ выразить.\n"
        "Граф построен как `slotclash`: тупиковое деление `fz` готово в такте "
        "0 и занимает порт, критическое `dc` ждёт операнда до такта 1. Там "
        "такая ловушка стоила эвристике такт — ЗДЕСЬ НЕ СТОИТ НИЧЕГО, и это "
        "результат, а не недоделка. Причина в самих измеренных числах: "
        "латентность FDIV — 14 тактов против 11 у DIV, и высоты обеих "
        "операций сравниваются (21 против 21). Потерянный на порту такт "
        "прячется внутри и так длинного хвоста деления ПТ, поэтому точный "
        "поиск не находит расстановки лучше.",
        profile="e2k-v6-measured",
        family="монопольный порт",
        lesson="Тот же конфликт, что в slotclash, но с другим классом — и "
               "цена у него нулевая: длинная латентность прячет потерю "
               "порта. Ловушка опасна не сама по себе, а по соотношению "
               "чисел.",
    )
    # Устройство ловушки — как в slotclash, но ловушка ДРУГОГО класса: порт
    # `,5` держат два разных делителя, и раньше выразить это было нечем.
    a0 = b.op("ADD", "a0")            # операнд критического деления, готов к т.1
    fz = b.op("FDIV", "fz")           # тупиковое деление ПТ, готово в т.0
    dc = b.op("DIV", "dc", a0)        # критическое деление, операнд к т.1
    m0 = b.op("MUL", "m0", dc)        # за ним тянется длинный хвост
    e0 = b.op("ADD", "e0", m0)
    e1 = b.op("ADD", "e1", e0)
    e2 = b.op("ADD", "e2", e1)
    zm = b.op("FMUL", "zm", fz)       # хвост тупикового: умножение ПТ…
    z = b.op("FADD", "z", zm)         # …и сложение — оба на всех шести каналах
    g0 = b.op("ADD", "g0")
    g1 = b.op("AND", "g1", g0)
    r = b.op("ADD", "r", e2, z)
    r2 = b.op("ADD", "r2", r, g1)
    b.op("STORE", "out", r2)
    return b.build()


def _packnarrow() -> DAG:
    """Упакованная арифметика: всего две дорожки на всю ширину машины."""
    b = DagBuilder(
        "packnarrow",
        "SIMD в двух каналах: ширина машины не помогает",
        "Упакованные сложения (`PACK`) ассемблер принимает только в `,0` и "
        "`,3` — проверено перебором. Шесть каналов есть, а разложить можно "
        "по два в такт.\n"
        "Восемь независимых упакованных операций: казалось бы, машина "
        "шириной шесть проглотит их за пару тактов. На деле они выстраиваются "
        "в очередь из двух дорожек, и скалярная мелочь вокруг — единственное, "
        "чем можно занять остальные четыре канала.",
        profile="e2k-v6-measured",
        family="узкий класс",
        lesson="Ширина машины считается не портами, а портами ДЛЯ ЭТОЙ "
               "операции. Эвристика справляется с этим сама: когда мест мало, "
               "выбирать особо не из чего — ошибиться негде.",
    )
    src = b.op("LOAD", "v")
    packs = [b.op("PACK", f"p{i}", src) for i in range(8)]
    fill = [b.op("ADD", f"s{i}", src) for i in range(4)]
    acc = b.op("PACKLOG", "acc", *packs[:4])
    acc2 = b.op("PACKLOG", "acc2", acc, *packs[4:])
    tail = b.op("ADD", "t", acc2, *fill)
    b.op("STORE", "out", tail)
    return b.build()


def _predchain() -> DAG:
    """Предикаты: if-conversion упирается в четыре канала из шести."""
    b = DagBuilder(
        "predchain",
        "Предикаты: цена превращения ветвлений в поток",
        "Сравнения, кладущие результат в предикат (`PRED`), исполняются в "
        "`,0 ,1 ,3 ,4`, но НЕ в `,2` и `,5` — измерено ассемблером. Именно "
        "ими компилятор заменяет ветвления, и в настоящем коде их много: на "
        "выводе `lcc -O3` это второй по частоте класс после арифметики.\n"
        "Здесь шесть сравнений готовят маски, а `MERGE` выбирает по ним "
        "значения. Загрузки при этом хотят `,2` и `,5` — то есть ровно те "
        "каналы, которые предикатам недоступны. Расписание получается "
        "плотным не потому, что операций много, а потому что они не "
        "перемешиваются.",
        profile="e2k-v6-measured",
        family="узкий класс",
        lesson="Два класса, каждый со своими каналами, мешают друг другу "
               "меньше, чем кажется: они заполняют разные половины команды, "
               "и эвристика попадает в оптимум без подсказок.",
    )
    a = b.op("LOAD", "a")
    c = b.op("LOAD", "c")
    preds = [b.op("PRED", f"pd{i}", a, c) for i in range(6)]
    m1 = b.op("MERGE", "m1", *preds[:3])
    m2 = b.op("MERGE", "m2", *preds[3:])
    ins = b.op("INSF", "ins", m1, m2)
    cb = b.op("COMBO", "cb", ins)
    b.op("STORE", "out", cb)
    return b.build()


SCENARIOS: dict[str, DAG] = {}


def _register(dag: DAG) -> None:
    SCENARIOS[dag.key] = dag


for _d in (
    # работа планировщика: один граф — две раскладки
    _simple4(),
    _loadchain(),
    _mixed18(),
    _slotclash(),
    _mulclash(),
    _divpressure(),
    _wide_ilp(),
    # классы, измеренные 30.08.2026: до них модель не знала ни плавающей
    # точки, ни предикатов, ни упакованных — и показать их было нечем
    _twodividers(),
    _packnarrow(),
    _predchain(),
    # приёмы оптимизации: парами «как написано» → «как надо»
    _seqreduce(),
    _treereduce(),
    _divstrength(),
    _unroll4(),
    _ptrchase(),
    _memstream(),
    _ifconv(),
):
    _register(_d)


def get_scenario(key: str) -> DAG:
    if key in SCENARIOS:
        return SCENARIOS[key]
    if key.startswith("rand"):
        try:
            return random_dag(int(key[4:]))
        except ValueError:
            pass
    raise SystemExit(
        f"неизвестный сценарий {key!r}; доступны: {', '.join(SCENARIOS)} "
        f"(или randN, где N — seed)"
    )
