"""Baseline: жадный list scheduler по длине остаточного критического пути.

Это ровно то, что стоит в реальных компиляторах (в LLVM `MachineScheduler`
устроен так же по сути): на каждом такте берём готовые инструкции,
сортируем по убыванию высоты в графе и раздаём по свободным каналам,
пока каналы не кончатся.

Планировщик намеренно сделан не соломенным чучелом:
  * он work-conserving — если инструкция с высоким приоритетом не влезает
    в оставшиеся каналы, он идёт дальше по списку и заполняет слот тем,
    что влезает;
  * он не тратит «дорогие» каналы зря — сложение уходит на канал, который
    умеет меньше всего операций.

Его слабость принципиальна и не лечится подкруткой: приоритет по критическому
пути видит только длину цепочек и ничего не знает о том, сколько ресурсов
потребуют инструкции в следующих тактах.

Функция `list_schedule` вынесена наружу: тот же самый жадный движок с другим
вектором приоритетов используется оракулом (точным поиском) как база для перебора.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from .api import Candidate, DecisionStep, SchedulingResult
from .dag import DAG, compute_metrics
from .model import MachineModel
from .schedule import ChannelState, Schedule


def channel_costs(model: MachineModel) -> list[int]:
    """«Ценность» канала = сколько классов операций он умеет.

    Дешёвые каналы раздаём первыми, чтобы не занять умножитель сложением.
    """
    return [
        sum(1 for op in model.ops if ch in model.channels_for(op))
        for ch in range(model.width)
    ]


def list_schedule(
    dag: DAG,
    model: MachineModel,
    priority: Sequence[float],
    *,
    defer_until: Mapping[int, int] | None = None,
    collect_trace: bool = False,
    height: Sequence[int] | None = None,
) -> tuple[Schedule, list[DecisionStep]]:
    """Один проход жадного потактового планирования.

    `priority` — чем больше, тем раньше инструкция будет рассмотрена.
    `defer_until` — искусственный запрет выдавать инструкцию раньше такта
    (нужен перебору, который проверяет, не выгоднее ли придержать деление).
    """
    n = len(dag)
    if height is None:
        height = compute_metrics(dag, model).height
    costs = channel_costs(model)
    defer = defer_until or {}

    sched = Schedule(dag, model)
    chans = ChannelState(model.width)
    ready_time = [0] * n
    unscheduled = set(range(n))
    trace: list[DecisionStep] = []

    cycle = 0
    guard = 0
    while unscheduled:
        guard += 1
        if guard > 100000:
            raise RuntimeError("планировщик зациклился")

        ready = sorted(
            (
                i
                for i in unscheduled
                if all(p not in unscheduled for p in dag[i].preds)
                and ready_time[i] <= cycle
            ),
            key=lambda i: (-priority[i], i),
        )

        step: DecisionStep | None = None
        if collect_trace:
            step = DecisionStep(
                cycle=cycle,
                free_channels=tuple(
                    c for c in range(model.width) if chans.free_at[c] <= cycle
                ),
                blocked=[
                    (p.instr, chans.free_at[p.channel])
                    for p in sched.placements.values()
                    if model.occupancy(dag[p.instr].op) > 1
                    and chans.free_at[p.channel] > cycle
                ],
                rule="приоритет = убывание остаточного критического пути (height); "
                "при равенстве — меньший номер инструкции",
            )

        issued_any = False
        for i in ready:
            op = dag[i].op
            capable = model.channels_for(op)
            free = chans.free_channels(cycle, capable)
            cand = Candidate(instr=i, ready_at=ready_time[i], height=int(height[i]))

            if defer.get(i, 0) > cycle:
                cand.reason = f"придержана перебором до такта {defer[i]}"
                if step:
                    step.candidates.append(cand)
                continue
            if not free:
                if not chans.free_channels(cycle, tuple(range(model.width))):
                    cand.reason = "все каналы этого такта заняты"
                else:
                    cand.reason = (
                        f"свободные каналы не исполняют {op} "
                        f"(нужен один из {','.join(map(str, capable))})"
                    )
                if step:
                    step.candidates.append(cand)
                continue

            ch = min(free, key=lambda c: (costs[c], c))
            occ = model.occupancy(op)
            sched.place(i, cycle, ch)
            chans.occupy(ch, cycle, occ)
            unscheduled.discard(i)
            issued_any = True
            avail = cycle + model.latency(op)
            for s in dag.succs[i]:
                ready_time[s] = max(ready_time[s], avail)

            cand.chosen = True
            cand.channel = ch
            cand.reason = (
                f"наивысший приоритет из готовых (h={int(height[i])}), "
                f"канал {ch} свободен"
            )
            if occ > 1:
                cand.reason += f"; займёт канал монопольно до такта {cycle + occ}"
            if step:
                step.candidates.append(cand)

        if step is not None:
            if not issued_any:
                step.rule = "простой"
                step.comment = (
                    "выдать нечего: операнды ещё не готовы или все подходящие "
                    "каналы заняты"
                )
            trace.append(step)
        cycle += 1

    return sched, trace


class GreedyListScheduler:
    name = "Baseline: жадный list scheduler (критический путь)"
    kind = "heuristic"
    short = "baseline"

    def schedule(self, dag: DAG, model: MachineModel) -> SchedulingResult:
        metrics = compute_metrics(dag, model)
        sched, trace = list_schedule(
            dag,
            model,
            priority=[float(h) for h in metrics.height],
            collect_trace=True,
            height=metrics.height,
        )
        return SchedulingResult(
            schedule=sched,
            trace=trace,
            optimal=None,
            notes=[
                "Решение принимается только по текущему такту — заглядывания "
                "вперёд нет.",
                "Приоритет height не знает, сколько каналов потребуют "
                "инструкции в следующих тактах.",
            ],
        )
