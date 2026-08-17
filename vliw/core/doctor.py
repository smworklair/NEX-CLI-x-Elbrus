"""Диагностика расписания: где именно теряются такты и почему.

Это «агент» прототипа в честном смысле слова: он сам проходит по готовому
расписанию набором правил-детекторов, находит проблемы, считает ЦЕНУ каждой в
тактах и объясняет причину. Никакой языковой модели и никакой сети — только
детерминированный анализ. Поэтому вывод воспроизводим: на одном и том же
расписании всегда одни и те же находки, их можно проверить руками по решётке.

Модуль ничего не печатает — возвращает данные (`Diagnosis`), а рисует их
`vliw.ui`. Это позволяет показывать одни и те же находки и в отчёте команды
`/doctor`, и в боковой панели.

Главный вопрос, на который отвечают правила: «этот такт потерян — из-за
занятого порта, из-за неготовых операндов или из-за неудачного выбора?»
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .dag import DAG, DagMetrics, compute_metrics
from .model import MachineModel
from .schedule import Schedule

# Порог, начиная с которого находка считается серьёзной (доля от makespan).
HIGH_SHARE = 0.15
MED_SHARE = 0.05


@dataclass
class Finding:
    """Одна находка: либо ошибка планировщика, либо предел машины.

    Различать эти два случая — самое важное в диагностике. Задержка операции
    сама по себе ещё не ошибка: если порт занят более срочной работой, ждать
    правильно. Ошибка — когда монопольный порт занят МЕНЕЕ срочной операцией,
    а более срочная из-за этого стоит. Признак: сравнение остаточного
    критического пути (height) у задержанной операции и у той, что заняла порт.
    """

    code: str            # машинный код правила: monopoly-block, idle-stall, …
    title: str
    cycles_lost: int     # наблюдаемая цена в тактах
    where: str
    why: str
    fix: str
    kind: str = "loss"   # loss — можно отыграть; limit — предел машины
    severity: str = "low"
    instrs: tuple[int, ...] = ()

    @property
    def recoverable(self) -> bool:
        return self.kind == "loss"

    def mark(self) -> str:
        if self.kind == "limit":
            return "="
        return {"high": "!!", "medium": "!", "low": "·"}.get(self.severity, "·")


@dataclass
class PortStat:
    index: int
    label: str
    busy: int            # тактов занят
    issued: int          # сколько операций выдано
    sole_ops: tuple[str, ...] = ()   # операции, для которых порт единственный

    def load(self, span: int) -> float:
        return (self.busy / span) if span else 0.0


@dataclass
class Diagnosis:
    """Результат разбора расписания — чистые данные для отрисовки."""

    findings: list[Finding] = field(default_factory=list)
    makespan: int = 0
    lower_bound: int = 0
    span: int = 0
    idle_cycles: int = 0
    ports: list[PortStat] = field(default_factory=list)
    slot_utilization: float = 0.0

    @property
    def total_lost(self) -> int:
        """Разрыв до теоретического предела — сколько тактов в принципе лишние."""
        return max(0, self.makespan - self.lower_bound)

    @property
    def top(self) -> list[Finding]:
        return self.findings[:5]

    @property
    def clean(self) -> bool:
        return not self.findings


def _severity(cost: int, makespan: int) -> str:
    if not makespan:
        return "low"
    share = cost / makespan
    if share >= HIGH_SHARE:
        return "high"
    if share >= MED_SHARE:
        return "medium"
    return "low"


def _ready_times(dag: DAG, sched: Schedule) -> list[int]:
    """С какого такта операнды каждой инструкции готовы (по этому расписанию)."""
    rt = [0] * len(dag)
    for ins in dag:
        for p in ins.preds:
            rt[ins.id] = max(rt[ins.id], sched.ready_at(p))
    return rt


def diagnose(dag: DAG, model: MachineModel, sched: Schedule,
             metrics: DagMetrics | None = None) -> Diagnosis:
    """Разобрать расписание и вернуть отсортированный список проблем."""
    met = metrics or compute_metrics(dag, model)
    d = Diagnosis(
        makespan=sched.makespan,
        lower_bound=met.lower_bound,
        span=sched.span_cycles,
        slot_utilization=sched.slot_utilization,
    )
    d.ports = _port_stats(dag, model, sched)
    d.idle_cycles = _idle_cycles(dag, sched)

    findings: list[Finding] = []
    findings += _rule_delayed_instructions(dag, model, sched, met)
    findings += _rule_idle_stretches(dag, model, sched)
    findings += _rule_port_bottleneck(dag, model, sched, d)
    findings += _rule_gap_to_bound(dag, model, sched, met)

    for f in findings:
        f.severity = _severity(f.cycles_lost, d.makespan) if f.recoverable else "low"
    # Сначала то, что можно отыграть, потом факты о пределах машины.
    findings.sort(key=lambda f: (f.kind != "loss", -f.cycles_lost))
    d.findings = findings
    return d


# --------------------------------------------------------------------------
# Статистика по портам
# --------------------------------------------------------------------------


def _port_stats(dag: DAG, model: MachineModel, sched: Schedule) -> list[PortStat]:
    busy = sched.busy_map()
    sole = model.sole_host_ops()
    stats = []
    for p in model.ports:
        cells = [c for (c, port) in busy if port == p.index]
        issued = sum(
            1 for (c, port), (_, head) in busy.items() if port == p.index and head
        )
        stats.append(PortStat(
            index=p.index, label=model.port_label(p.index),
            busy=len(cells), issued=issued,
            sole_ops=tuple(sole.get(p.index, ())),
        ))
    return stats


def _idle_cycles(dag: DAG, sched: Schedule) -> int:
    """Такты внутри участка, в которых не выдано ни одной операции."""
    issued = {p.cycle for p in sched.placements.values()}
    last = max(issued, default=0)
    return sum(1 for t in range(last + 1) if t not in issued)


# --------------------------------------------------------------------------
# Правило 1: инструкция готова, но выдана позже — кто ей помешал
# --------------------------------------------------------------------------


def _rule_delayed_instructions(dag: DAG, model: MachineModel, sched: Schedule,
                               met: DagMetrics) -> list[Finding]:
    """Ищет операции, простоявшие «в очереди», и виновника задержки.

    Ядро диагностики. Если инструкция была готова в такте rt, а выдана в
    ac > rt, значит её что-то держало. Смотрим, кто в это время занимал порты,
    на которых она вообще исполнима.

    Ключевое различение: ждать — не обязательно плохо. Если порт занимала
    БОЛЕЕ срочная операция (её остаточный критический путь длиннее), то
    планировщик поступил верно, и это предел машины, а не ошибка. Ошибка —
    когда монопольный порт отдали МЕНЕЕ срочной операции: тогда такты
    действительно потеряны зря и их можно отыграть перестановкой.
    """
    rt = _ready_times(dag, sched)
    busy = sched.busy_map()
    height = met.height
    out: list[Finding] = []

    for ins in dag:
        i = ins.id
        ac = sched.cycle_of(i)
        delay = ac - rt[i]
        if delay <= 0:
            continue

        ports = model.channels_for(ins.op)
        monopoly = len(ports) == 1

        blockers: dict[int, int] = {}
        for t in range(rt[i], ac):
            for port in ports:
                hit = busy.get((t, port))
                if hit and hit[0] != i:
                    blockers[hit[0]] = blockers.get(hit[0], 0) + 1
        if not blockers:
            continue

        worst = max(blockers, key=lambda k: blockers[k])
        held = blockers[worst]
        wname, wop = dag[worst].name, dag[worst].op
        pname = (model.port_label(ports[0]) if monopoly
                 else ",".join(model.port_label(p) for p in ports))

        # Виновник менее срочен, чем тот, кого он задержал → это просчёт.
        wasted = height[worst] < height[i]

        if monopoly and wasted:
            out.append(Finding(
                code="monopoly-block",
                title=f"монопольный порт {pname} занят менее срочной {wname}",
                cycles_lost=delay,
                where=f"{ins.name} готова в т.{rt[i]}, выдана только в т.{ac}",
                why=(f"порт {pname} — единственный исполнитель {ins.op}; его "
                     f"{held} т. занимала {wname} ({wop}, остаток пути "
                     f"{height[worst]}), пока ждала {ins.name} (остаток "
                     f"{height[i]}) — более срочная"),
                fix=(f"выдать {ins.name} раньше {wname}: {wname} никто не ждёт, "
                     f"её можно посчитать позже, в тени длинной операции"),
                kind="loss",
                instrs=(i, worst),
            ))
        elif monopoly:
            out.append(Finding(
                code="monopoly-queue",
                title=f"очередь на монопольный порт {pname}",
                cycles_lost=delay,
                where=f"{ins.name} ждёт с т.{rt[i]} до т.{ac}",
                why=(f"{wname} ({wop}) на том же единственном порту {pname} была "
                     f"не менее срочной (остаток {height[worst]} против "
                     f"{height[i]}) — ждать здесь правильно"),
                fix=("это предел машины: две операции физически не помещаются "
                     "на один порт одновременно"),
                kind="limit",
                instrs=(i, worst),
            ))
        elif wasted:
            out.append(Finding(
                code="port-contention",
                title=f"{ins.name} ({ins.op}) ждала занятые порты",
                cycles_lost=delay,
                where=f"готова в т.{rt[i]}, выдана в т.{ac}",
                why=(f"порты {pname} были заняты, дольше всех — {wname}, "
                     f"менее срочная"),
                fix="развести операции по портам или по тактам",
                kind="loss",
                instrs=(i, worst),
            ))
    return out


# --------------------------------------------------------------------------
# Правило 2: сплошные простои
# --------------------------------------------------------------------------


def _rule_idle_stretches(dag: DAG, model: MachineModel,
                         sched: Schedule) -> list[Finding]:
    """Отрезки тактов без единой выдачи, с разбором причины.

    Простой считается ПОТЕРЕЙ только если в эти такты что-то реально можно
    было выдать: нашлась готовая операция и свободный подходящий порт. Иначе
    это физика участка (нечего считать или всё занято), а не просчёт.
    """
    issued_at: dict[int, list[int]] = {}
    for p in sched.placements.values():
        issued_at.setdefault(p.cycle, []).append(p.instr)
    last = max(issued_at, default=0)
    busy = sched.busy_map()
    rt = _ready_times(dag, sched)

    def could_issue(t: int) -> bool:
        """Была ли в такте t готовая операция и свободный для неё порт."""
        for ins in dag:
            if rt[ins.id] > t or sched.cycle_of(ins.id) <= t:
                continue
            for port in model.channels_for(ins.op):
                if (t, port) not in busy:
                    return True
        return False

    out: list[Finding] = []
    t = 0
    while t <= last:
        if t in issued_at:
            t += 1
            continue
        start = t
        while t <= last and t not in issued_at:
            t += 1
        span = t - start
        if span < 3:
            continue

        holders = {
            busy[(c, p.index)][0]
            for c in range(start, t) for p in model.ports
            if (c, p.index) in busy
        }
        # Можно ли было хоть что-то выдать в эти такты?
        wasted = any(could_issue(c) for c in range(start, t))

        if wasted:
            why = "были готовые операции и свободные порты, но выдачи не было"
            fix = "заполнить простой независимой работой — такты теряются зря"
        elif holders:
            names = ", ".join(sorted(dag[i].name for i in holders)[:3])
            why = (f"все подходящие порты заняты длинными операциями ({names}), "
                   f"а готовой работы для свободных портов нет")
            fix = ("предел участка: занять машину нечем, пока считаются длинные "
                   "операции")
        else:
            why = "ни одна операция не готова: ждём результатов предыдущих"
            fix = ("длина цепочки зависимостей — простой неизбежен при любом "
                   "порядке выдачи")
        out.append(Finding(
            code="idle-stall",
            title=f"простой {span} т. подряд (т.{start}–{t - 1})",
            cycles_lost=span,
            where=f"такты {start}–{t - 1}",
            why=why,
            fix=fix,
            kind="loss" if wasted else "limit",
        ))
    return out


# --------------------------------------------------------------------------
# Правило 3: узкое место по портам
# --------------------------------------------------------------------------


def _rule_port_bottleneck(dag: DAG, model: MachineModel, sched: Schedule,
                          d: Diagnosis) -> list[Finding]:
    out: list[Finding] = []
    span = sched.span_cycles
    if not span:
        return out
    for st in d.ports:
        load = st.load(span)
        if load < 0.6 or not st.sole_ops:
            continue
        ops = "/".join(st.sole_ops)
        out.append(Finding(
            code="port-saturated",
            title=f"порт {st.label} загружен на {load:.0%} — узкое место",
            cycles_lost=0,   # это не потеря, а факт: предел машины
            where=f"порт {st.label} ({ops})",
            why=(f"{st.issued} операций {ops} обязаны пройти через единственный "
                 f"порт {st.label}, он занят {st.busy} из {span} тактов"),
            fix=("это предел машины, а не ошибка планировщика: ускорить можно "
                 "только уменьшив число таких операций в участке"),
            kind="limit",
        ))
    return out


# --------------------------------------------------------------------------
# Правило 4: разрыв до теоретического предела
# --------------------------------------------------------------------------


def _rule_gap_to_bound(dag: DAG, model: MachineModel, sched: Schedule,
                       met: DagMetrics) -> list[Finding]:
    gap = sched.makespan - met.lower_bound
    if gap <= 0:
        return []
    return [Finding(
        code="above-lower-bound",
        title=f"расписание на {gap} т. длиннее теоретического предела",
        cycles_lost=gap,
        where=f"{sched.makespan} т. против нижней границы {met.lower_bound} т.",
        why=(f"предел задаёт {met.binding} — критический путь "
             f"{met.critical_path_bound} т., ресурсы {met.resource_bound} т."),
        fix=("часть разрыва отыгрывается порядком выдачи — сравните с точным "
             "поиском командой /compare"),
    )]
