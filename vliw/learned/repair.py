"""Починка каналов в ответе модели: такты её, каналы — законные.

Зачем
-----
Замер показал ровное разделение: когда модель не путает канал, она попадает
ТОЧНО в оптимум (разрыв 0.00 такта на всех законных расписаниях). А когда
путает — почти всегда это STORE, поставленный на канал, который его не
исполняет. В обучающих данных прогона 1 не было ни одной операции STORE,
и модель просто не знает, что её исполняют только `,2` и `,5`.

То есть модель ошибается не в ПЛАНИРОВАНИИ, а в знании матрицы машины. План
— распределение инструкций по тактам — у неё хороший. Матрица же известна
точно и лежит в `vliw/core/model.py`.

Отсюда решение: оставить такты модели нетронутыми и переназначить только
каналы, законным образом. Это не подгонка метрики: makespan определяется
ТАКТАМИ, а такты мы не трогаем вообще. Меняется лишь то, на какой порт внутри
своего такта попадёт операция.

ЧЕСТНОСТЬ. Результат после починки — уже не «что выдала модель», а гибрид, и
называть его надо гибридом. Поэтому `repair()` возвращает подробный отчёт:
сколько каналов переставлено и каких именно. Интерфейс это печатает, а не
прячет: видно, где модель справилась сама, а где её починили.

ЧЕГО ЗДЕСЬ НЕТ. Такты не двигаются никогда. Если модель нарушила зависимость
(потребитель раньше производителя) или занятость порта во времени — почининть
это, не меняя тактов, нельзя, и мы честно не пытаемся: такие нарушения
остаются, и `Schedule.validate()` их покажет.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..core.model import MachineModel
from ..core.schedule import Schedule


@dataclass
class RepairReport:
    """Что именно пришлось переставить."""

    moved: list[tuple[int, int, int]] = field(default_factory=list)
    """(инструкция, канал модели, канал после починки)."""
    impossible: list[int] = field(default_factory=list)
    """Инструкции, которым законного канала в их такте не нашлось вовсе."""

    @property
    def touched(self) -> int:
        return len(self.moved)

    @property
    def ok(self) -> bool:
        return not self.impossible


def _assign_cycle(ops: list[tuple[int, tuple[int, ...], int]],
                  width: int) -> dict[int, int] | None:
    """Раздать каналы инструкциям одного такта. None — раздать нельзя.

    Двудольное паросочетание Куна, тот же приём, что в точном поиске
    (`vliw/core/oracle.py`). Жадно «первый свободный подходящий» здесь не
    годится: операция с широкой матрицей может занять единственный канал,
    нужный операции с узкой (например ADD сядет на `,2`, и STORE, которому
    доступны только `,2` и `,5`, останется без места, хотя решение было).

    `ops` — (инструкция, допустимые каналы, канал по мнению модели). Порядок
    предпочтения внутри инструкции: сначала канал модели, потом остальные, —
    чтобы не переставлять то, что и так законно.
    """
    owner: dict[int, int] = {}          # канал -> инструкция

    def augment(op: int, allowed: tuple[int, ...], seen: set[int],
                prefer: int) -> bool:
        order = ([prefer] if prefer in allowed else []) + \
                [c for c in allowed if c != prefer]
        for ch in order:
            if ch in seen or ch >= width:
                continue
            seen.add(ch)
            holder = owner.get(ch)
            if holder is None:
                owner[ch] = op
                return True
            h_allowed, h_prefer = holders[holder]
            if augment(holder, h_allowed, seen, h_prefer):
                owner[ch] = op
                return True
        return False

    holders: dict[int, tuple[tuple[int, ...], int]] = {
        i: (allowed, prefer) for i, allowed, prefer in ops
    }
    # Сначала те, кому выбирать не из чего: у них меньше всего вариантов, и
    # если начать с «широких», узкие останутся без места.
    for i, allowed, prefer in sorted(ops, key=lambda t: len(t[1])):
        if not augment(i, allowed, set(), prefer):
            return None
    return {op: ch for ch, op in owner.items()}


def repair(sched: Schedule, model: MachineModel) -> tuple[Schedule, RepairReport]:
    """Новое расписание с теми же тактами и законными каналами.

    Исходное расписание не меняется — возвращается копия.
    """
    dag = sched.dag
    report = RepairReport()

    by_cycle: dict[int, list[int]] = {}
    for i, p in sched.placements.items():
        by_cycle.setdefault(p.cycle, []).append(i)

    fixed = Schedule(dag, model)
    for cycle in sorted(by_cycle):
        ops = []
        for i in sorted(by_cycle[cycle]):
            allowed = model.channels_for(dag[i].op)
            ops.append((i, allowed, sched.placements[i].channel))

        got = _assign_cycle(ops, model.width)
        if got is None:
            # Раздать законно нельзя — в этом такте больше операций, чем
            # подходящих портов. Такты мы не двигаем, значит оставляем как
            # было: пусть validate() покажет настоящую проблему.
            for i, _, prefer in ops:
                fixed.place(i, cycle, prefer)
                report.impossible.append(i)
            continue

        for i, _, prefer in ops:
            ch = got[i]
            fixed.place(i, cycle, ch)
            if ch != prefer:
                report.moved.append((i, prefer, ch))

    return fixed, report
