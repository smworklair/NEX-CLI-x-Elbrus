"""Оракул прототипа: точный поиск оптимума вместо эвристики.

ВАЖНО про терминологию. Это НЕ «ИИ» и не обученная модель — это точный
математический поиск (branch-and-bound с итеративным углублением). Он считает
недостижимый на практике ТЕОРЕТИЧЕСКИЙ ПОТОЛОК: сколько тактов в принципе
достижимо на данном графе и данной машине. Обученной модели в проекте пока
физически нет (см. vliw/learned/) — когда она появится, она должна
ПРИБЛИЖАТЬСЯ к этому потолку, но гарантированного оптимума давать не будет.

Разрыв между baseline и этим потолком и есть бюджет, за который имеет смысл
бороться обученной моделью. Если разрыва нет — эвристика уже оптимальна,
и учить на этом графе нечему. Это такой же честный результат, и демо его
не прячет.

Два движка, в порядке применения:

  1. ТОЧНЫЙ (branch-and-bound с итеративным углублением). Считаем нижнюю
     границу LB и верхнюю UB (расписание baseline). Для T = LB, LB+1, ...
     спрашиваем «существует ли расписание длиной ровно T?» поиском в глубину.
     Первое T с ответом «да» оптимально по построению.

     Отсечения:
       * дедлайны: инструкцию с остаточным критическим путём height нельзя
         выдать позже, чем T - height;
       * прогноз самого раннего старта с учётом и зависимостей, и занятости
         каналов;
       * доминирование: неблокирующую операцию нет смысла откладывать, если
         для неё есть свободный подходящий канал;
       * симметрия: взаимозаменяемые инструкции и равноправные каналы
         не порождают разных ветвей;
       * мемоизация провальных состояний.

  2. ПОРТФЕЛЬНЫЙ (если точный не уложился в бюджет). Прогоняем тот же жадный
     движок с сотнями разных векторов приоритетов и вариантов придержать
     деление, берём лучшее найденное. Оптимальность при этом НЕ доказана,
     и в отчёте это написано прямо. По смыслу это ровно то, чем будет
     заниматься обученная модель: сэмплировать хорошие порядки вместо
     единственного жёсткого правила.
"""

from __future__ import annotations

import itertools
import random
import time
from dataclasses import dataclass

from .api import Candidate, DecisionStep, SchedulingResult
from .baseline import GreedyListScheduler, list_schedule
from .dag import DAG, compute_metrics
from .model import MachineModel
from .schedule import Schedule


class _Timeout(Exception):
    pass


@dataclass
class _Ctx:
    dag: DAG
    model: MachineModel
    lat: list[int]
    occ: list[int]
    capable: list[tuple[int, ...]]
    height: tuple[int, ...]
    chan_class: tuple[int, ...]
    deadline_wall: float
    nodes: int = 0

    def tick(self) -> None:
        self.nodes += 1
        if self.nodes % 512 == 0 and time.monotonic() > self.deadline_wall:
            raise _Timeout


def _channel_classes(model: MachineModel) -> tuple[int, ...]:
    """Каналы с одинаковым набором умений взаимозаменяемы — метим их классом."""
    sig: dict[tuple[bool, ...], int] = {}
    out = []
    for ch in range(model.width):
        key = tuple(ch in model.channels_for(op) for op in sorted(model.ops))
        out.append(sig.setdefault(key, len(sig)))
    return tuple(out)


# --------------------------------------------------------------------------
# Раскладка выбранных операций по каналам (двудольное паросочетание Куна)
# --------------------------------------------------------------------------


class _Matcher:
    """Инкрементальное паросочетание «операция → канал»."""

    def __init__(self, free: set[int]):
        self.free = free
        self.owner: dict[int, int] = {}  # канал -> операция
        self.allowed: dict[int, tuple[int, ...]] = {}

    def copy(self) -> "_Matcher":
        m = _Matcher(self.free)
        m.owner = dict(self.owner)
        m.allowed = dict(self.allowed)
        return m

    def add(self, op: int, allowed: tuple[int, ...]) -> bool:
        self.allowed[op] = allowed
        if self._augment(op, set()):
            return True
        del self.allowed[op]
        return False

    def _augment(self, op: int, seen: set[int]) -> bool:
        for ch in self.allowed[op]:
            if ch not in self.free or ch in seen:
                continue
            seen.add(ch)
            holder = self.owner.get(ch)
            if holder is None or self._augment(holder, seen):
                self.owner[ch] = op
                return True
        return False

    def assignment(self) -> dict[int, int]:
        return {op: ch for ch, op in self.owner.items()}


# --------------------------------------------------------------------------
# Точный поиск
# --------------------------------------------------------------------------


def _earliest_starts(
    ctx: _Ctx,
    unscheduled: frozenset[int],
    ready_time: tuple[int, ...],
    free_at: tuple[int, ...],
    t: int,
) -> list[int] | None:
    """Самый ранний реально достижимый старт каждой ещё не выданной инструкции."""
    est = [0] * len(ctx.dag)
    for i in sorted(unscheduled):
        e = max(t, ready_time[i])
        for p in ctx.dag[i].preds:
            if p in unscheduled:
                e = max(e, est[p] + ctx.lat[p])
        chans = ctx.capable[i]
        if not chans:
            return None
        e = max(e, min(free_at[c] for c in chans))
        est[i] = e
    return est


def _group_interchangeable(
    ctx: _Ctx, ids: list[int], ready_time: tuple[int, ...]
) -> list[list[int]]:
    """Сгруппировать инструкции, между которыми в этом такте нет разницы."""
    buckets: dict[tuple, list[int]] = {}
    for i in ids:
        key = (
            ctx.dag[i].op,
            ctx.capable[i],
            ctx.height[i],
            ready_time[i],
            ctx.dag.succs[i],
        )
        buckets.setdefault(key, []).append(i)
    return [sorted(v) for v in buckets.values()]


def _count_vectors(sizes: list[int], total: int):
    """Все раскладки `total` штук по группам с ограничением сверху."""
    def rec(k: int, left: int, acc: list[int]):
        if k == len(sizes):
            if left == 0:
                yield tuple(acc)
            return
        rest = sum(sizes[k + 1 :])
        lo = max(0, left - rest)
        for c in range(min(sizes[k], left), lo - 1, -1):
            acc.append(c)
            yield from rec(k + 1, left - c, acc)
            acc.pop()

    yield from rec(0, total, [])


def _candidate_subsets(
    ctx: _Ctx,
    ready: list[int],
    free: set[int],
    ready_time: tuple[int, ...],
) -> list[tuple[int, ...]]:
    """Какие наборы инструкций имеет смысл выдать в этом такте.

    Рассматриваем только наборы, к которым нельзя добавить ещё одну
    неблокирующую готовую инструкцию (оставлять подходящий канал пустым
    без причины никогда не выгодно), и все варианты по блокирующим
    операциям — их как раз бывает выгодно придержать.
    """
    blocking = [i for i in ready if ctx.occ[i] > 1]
    nonblk = [i for i in ready if ctx.occ[i] == 1]
    groups = _group_interchangeable(ctx, nonblk, ready_time)
    sizes = [len(g) for g in groups]

    out: list[tuple[int, ...]] = []
    seen: set[tuple[int, ...]] = set()

    for r in range(len(blocking), -1, -1):
        for bs in itertools.combinations(blocking, r):
            ctx.tick()
            base = _Matcher(free)
            if not all(base.add(i, ctx.capable[i]) for i in bs):
                continue
            probe = base.copy()
            extra = sum(1 for i in nonblk if probe.add(i, ctx.capable[i]))
            for counts in _count_vectors(sizes, extra):
                sub = list(bs)
                for g, c in zip(groups, counts):
                    sub.extend(g[:c])
                m = base.copy()
                if all(m.add(i, ctx.capable[i]) for i in sub[len(bs) :]):
                    key = tuple(sorted(sub))
                    if key not in seen:
                        seen.add(key)
                        out.append(key)

    out.sort(key=lambda s: -sum(ctx.height[i] for i in s))
    return out


def _search(
    ctx: _Ctx,
    target: int,
    t: int,
    unscheduled: frozenset[int],
    ready_time: tuple[int, ...],
    free_at: tuple[int, ...],
    placed: list[tuple[int, int, int]],
    failed: set,
) -> list[tuple[int, int, int]] | None:
    if not unscheduled:
        return list(placed)

    ctx.tick()

    est = _earliest_starts(ctx, unscheduled, ready_time, free_at, t)
    if est is None:
        return None
    for i in unscheduled:
        if est[i] + ctx.height[i] > target:
            return None

    by_class: dict[int, list[int]] = {}
    for ch, cls in enumerate(ctx.chan_class):
        by_class.setdefault(cls, []).append(max(0, free_at[ch] - t))
    key = (
        unscheduled,
        tuple(sorted((cls, tuple(sorted(v))) for cls, v in by_class.items())),
        tuple(max(0, ready_time[i] - t) for i in sorted(unscheduled)),
    )
    if key in failed:
        return None

    free = {c for c in range(ctx.model.width) if free_at[c] <= t}
    ready = [
        i
        for i in unscheduled
        if ready_time[i] <= t and all(p not in unscheduled for p in ctx.dag[i].preds)
    ]

    for sub in _candidate_subsets(ctx, ready, free, ready_time):
        m = _Matcher(free)
        for i in sub:
            m.add(i, ctx.capable[i])
        assign = m.assignment()
        new_free = list(free_at)
        new_ready = list(ready_time)
        for i in sub:
            ch = assign[i]
            new_free[ch] = t + ctx.occ[i]
            avail = t + ctx.lat[i]
            for s in ctx.dag.succs[i]:
                new_ready[s] = max(new_ready[s], avail)
        for i in sub:
            placed.append((i, t, assign[i]))

        res = _search(
            ctx,
            target,
            t + 1,
            unscheduled - frozenset(sub),
            tuple(new_ready),
            tuple(new_free),
            placed,
            failed,
        )
        if sub:
            del placed[len(placed) - len(sub) :]
        if res is not None:
            return res

    failed.add(key)
    return None


# --------------------------------------------------------------------------
# Портфельный поиск (запасной движок)
# --------------------------------------------------------------------------


def _portfolio(
    dag: DAG,
    model: MachineModel,
    height: tuple[int, ...],
    best: Schedule,
    budget_s: float,
    seed: int = 20260811,
) -> tuple[Schedule, int]:
    rnd = random.Random(seed)
    blocking = [i.id for i in dag if model.occupancy(i.op) > 1]
    deadline = time.monotonic() + budget_s
    tries = 0
    hmax = max(height) if height else 1
    while time.monotonic() < deadline and tries < 20000:
        tries += 1
        jitter = rnd.choice((0.0, 0.15, 0.4, 1.0)) * hmax
        prio = [h + rnd.uniform(-jitter, jitter) for h in height]
        defer = {
            i: rnd.randint(1, 5) for i in blocking if rnd.random() < 0.25
        }
        cand, _ = list_schedule(
            dag, model, prio, defer_until=defer, height=height
        )
        if cand.makespan < best.makespan and not cand.validate():
            best = cand
    return best, tries


# --------------------------------------------------------------------------


class OracleScheduler:
    name = "Оракул (точный поиск: теоретический потолок оптимизации)"
    kind = "exact"
    short = "oracle"

    def __init__(self, budget_s: float = 20.0, portfolio_s: float = 5.0):
        self.budget_s = budget_s
        self.portfolio_s = portfolio_s

    def schedule(self, dag: DAG, model: MachineModel) -> SchedulingResult:
        metrics = compute_metrics(dag, model)
        base = GreedyListScheduler().schedule(dag, model)
        best = base.schedule
        ub = best.makespan
        lb = metrics.lower_bound

        ctx = _Ctx(
            dag=dag,
            model=model,
            lat=[model.latency(i.op) for i in dag],
            occ=[model.occupancy(i.op) for i in dag],
            capable=[model.channels_for(i.op) for i in dag],
            height=metrics.height,
            chan_class=_channel_classes(model),
            deadline_wall=time.monotonic() + self.budget_s,
        )

        notes = [
            f"Нижняя граница: {lb} тактов (критический путь "
            f"{metrics.critical_path_bound}, ресурсы {metrics.resource_bound}) — "
            f"связывает {metrics.binding}.",
            f"Верхняя граница на старте — расписание baseline: {ub} тактов.",
        ]
        proven: bool | None = None
        timed_out = False
        engine = "exact"
        t0 = time.monotonic()
        proved_impossible = lb  # всё, что строго меньше, доказанно недостижимо

        if lb >= ub:
            proven = True
            notes.append(
                "Расписание baseline уже упирается в нижнюю границу: улучшить "
                "его невозможно, оптимальность доказана без перебора."
            )
        else:
            for target in range(lb, ub):
                try:
                    res = _search(
                        ctx,
                        target,
                        0,
                        frozenset(range(len(dag))),
                        tuple([0] * len(dag)),
                        tuple([0] * model.width),
                        [],
                        set(),
                    )
                except _Timeout:
                    timed_out = True
                    break
                if res is not None:
                    s = Schedule(dag, model)
                    for i, c, ch in res:
                        s.place(i, c, ch)
                    errs = s.validate()
                    if errs:
                        raise AssertionError(
                            "точный поиск выдал некорректное расписание: " + "; ".join(errs)
                        )
                    best = s
                    proven = True
                    if target == lb:
                        notes.append(
                            f"Расписание длиной {target} тактов найдено сразу на "
                            f"нижней границе — короче не бывает по построению."
                        )
                    elif target == lb + 1:
                        notes.append(
                            f"Найдено расписание длиной {target} тактов; цель {lb} "
                            f"перебором доказанно недостижима."
                        )
                    else:
                        notes.append(
                            f"Найдено расписание длиной {target} тактов; все цели "
                            f"от {lb} до {target - 1} доказанно недостижимы."
                        )
                    break
                proved_impossible = target + 1
            else:
                proven = True
                notes.append(
                    f"Все цели от {lb} до {ub - 1} доказанно недостижимы — "
                    f"значит расписание baseline ({ub}) уже оптимально."
                )

        portfolio_tries = 0
        if timed_out:
            engine = "portfolio"
            proven = False
            notes.append(
                f"Точный поиск не уложился в бюджет {self.budget_s:g} с "
                f"(разобрано {ctx.nodes} узлов). Переключаемся на портфельный "
                f"перебор приоритетов."
            )
            best, portfolio_tries = _portfolio(
                dag, model, metrics.height, best, self.portfolio_s
            )
            notes.append(
                f"Портфель: {portfolio_tries} прогонов жадного движка с разными "
                f"приоритетами. Лучшее найденное — {best.makespan} тактов; "
                f"оптимум доказанно лежит в [{proved_impossible}, {best.makespan}]."
            )

        elapsed = time.monotonic() - t0
        return SchedulingResult(
            schedule=best,
            trace=_replay_trace(best, dag, model, metrics.height),
            notes=notes,
            optimal=proven,
            search_stats={
                "engine": engine,
                "nodes": ctx.nodes,
                "portfolio_tries": portfolio_tries,
                "seconds": round(elapsed, 3),
                "lower_bound": lb,
                "proved_impossible_below": proved_impossible,
                "baseline_upper_bound": ub,
                "result": best.makespan,
                "timed_out": timed_out,
            },
        )


def _replay_trace(
    sched: Schedule, dag: DAG, model: MachineModel, height: tuple[int, ...]
) -> list[DecisionStep]:
    """Восстановить пошаговый разбор из готового расписания.

    Планировщик с полным просчётом принимает решение не потактно, а сразу
    целиком, поэтому объяснение строится обратным проходом: в каждом такте
    видно, что он выдал и какие готовые инструкции сознательно отложил.
    """
    n = len(dag)
    if not sched.complete:
        return []
    last = max(p.cycle for p in sched.placements.values())
    by_cycle: dict[int, list[int]] = {}
    for p in sched.placements.values():
        by_cycle.setdefault(p.cycle, []).append(p.instr)

    ready_time = [0] * n
    for ins in dag:
        for p in ins.preds:
            ready_time[ins.id] = max(ready_time[ins.id], sched.ready_at(p))

    trace: list[DecisionStep] = []
    for t in range(last + 1):
        issued = sorted(by_cycle.get(t, []), key=lambda i: sched.placements[i].channel)
        held = [
            p
            for p in sched.placements.values()
            if p.cycle < t < p.cycle + model.occupancy(dag[p.instr].op)
        ]
        busy = {p.channel for p in held}
        used = busy | {sched.placements[i].channel for i in issued}
        step = DecisionStep(
            cycle=t,
            free_channels=tuple(c for c in range(model.width) if c not in busy),
            blocked=[
                (p.instr, p.cycle + model.occupancy(dag[p.instr].op)) for p in held
            ],
            rule="решение принято с учётом всего оставшегося графа "
            "(просчёт до конца участка, а не по текущему такту)",
        )
        for i in range(n):
            if sched.cycle_of(i) < t or ready_time[i] > t:
                continue
            cand = Candidate(instr=i, ready_at=ready_time[i], height=height[i])
            if i in issued:
                cand.chosen = True
                cand.channel = sched.placements[i].channel
                cand.reason = f"в найденном расписании — именно этот такт (h={height[i]})"
                occ = model.occupancy(dag[i].op)
                if occ > 1:
                    cand.reason += f"; займёт канал монопольно до такта {t + occ}"
            elif not (set(model.channels_for(dag[i].op)) - used):
                cand.reason = "все подходящие каналы этого такта уже заняты"
            else:
                cand.reason = (
                    f"канал есть, но выдача отложена до такта "
                    f"{sched.cycle_of(i)} — сознательное решение"
                )
            step.candidates.append(cand)

        # Главное объяснение: где полный просчёт пошёл против жадного правила.
        chosen_h = [height[i] for i in issued]
        deferred = [c for c in step.candidates if not c.chosen]
        outranked = [c for c in deferred if chosen_h and c.height > max(chosen_h)]
        if outranked:
            names = ", ".join(dag[c.instr].name for c in outranked)
            step.comment = (
                f"выдал операции с h={max(chosen_h)}, придержав {names} "
                f"с h={max(c.height for c in outranked)}: жадное правило по "
                f"критическому пути сделало бы наоборот"
            )
        if not step.issued:
            step.rule = "пауза"
            step.comment = (
                "в этом расписании такт пуст — все нужные каналы заняты "
                "ранее выданными операциями"
            )
        trace.append(step)
    return trace
