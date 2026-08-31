"""CAB: один ответ модели — несколько законных расписаний, выбор точным критерием.

ЗАЧЕМ
-----
До сих пор модель обязана была быть бухгалтером: помнить матрицу каналов,
следить, кто уже занял канал в этом такте, считать готовность операндов.
В этом она плоха — `docs/DIAG3.md` считает поштучно: 315 незаконных каналов,
208 конфликтов, 26 неготовых операндов. Хороша она в другом: из 98 законных
ответов прогона 1 девяносто семь были ТОЧНЫМ оптимумом CP-SAT.

Отсюда смена разделения труда. У модели забирается вся бухгалтерия и
остаётся ровно то, что она умеет, — ПОРЯДОК: кого рассматривать раньше.
Бухгалтерию ведёт `list_schedule` из `core/baseline.py`, который по
построению не выдаст инструкцию раньше предков и не посадит две на один
канал. Любое расписание отсюда законно, доказывать это нечем — оно законно
механизмом, а не удачей.

ЧТО ИМЕННО БЕРЁТСЯ У МОДЕЛИ

* `order_from_model` — порядок. Операции сортируются по её же `(такт, канал)`;
  выбор канала при этом ВЫБРАСЫВАЕТСЯ целиком. Это не потеря, а смысл: канал
  — самая частая её ошибка, а порядок — самое ценное, что она даёт.
* `floor_from_model` — такты, но только как «не раньше». Планировщик вправе
  операцию отодвинуть и не вправе подтянуть. Это преемник доктрины
  `repair.py` («такты модели не трогаем»), без её тупика: repair честно
  сдаётся, когда законного канала нет вовсе, а здесь законное расписание
  получается всегда.

ЧЕГО ЗДЕСЬ НЕТ
--------------
Оптимальности. `list_schedule` — жадный проход, он не доказывает ничего и
может проиграть оракулу. Здесь считается только законность и makespan.

И честности задаром тоже нет. Такты в вариантах «порядок» и «порядок+такты»
ставит планировщик, а не модель, поэтому makespan там — ГИБРИД, и подписан
он гибридом. По той же причине рост доли законных расписаний до 100% ничего
не говорит об улучшении модели: законность здесь определительная, свойство
механизма. Сравнивать после CAB надо не «сколько законных», а «на сколько
тактов хуже оракула».
"""

from __future__ import annotations

from dataclasses import dataclass

from ..core.baseline import list_schedule
from ..core.dag import DAG, compute_metrics
from ..core.model import MachineModel
from ..core.schedule import Schedule


@dataclass(frozen=True)
class Variant:
    """Один кандидат портфеля.

    `name` — короткая подпись для колонки, `how` — фраза человеку о том, чья
    именно это работа. Разделены, потому что в отчёте нужно и то и другое:
    в таблице тесно, а под таблицей нужно понимать, что откуда взялось.
    """

    name: str
    how: str
    schedule: Schedule
    errors: tuple[str, ...] = ()

    @property
    def legal(self) -> bool:
        return not self.errors and self.schedule.complete

    @property
    def makespan(self) -> int:
        return self.schedule.makespan


def order_from_model(placements: dict[int, tuple[int, int]], n: int,
                     height) -> list[float]:
    """Ответ модели → вектор приоритетов для `list_schedule`.

    Чем больше число, тем раньше инструкцию рассмотрят. Размещённые моделью
    идут в её собственном порядке `(такт, канал)`; неразмещённые — следом, по
    убыванию критического пути, то есть по правилу baseline.

    Почему неразмещённые именно в хвост, а не вперемешку. Модель о них не
    высказалась вовсе (оборвалась, потеряла формат), и придумывать за неё
    место нечестно. Хвост по height — это плавный откат к жадной эвристике
    ровно на той части графа, где мнения модели нет: чем меньше она успела
    сказать, тем ближе результат к baseline, а не к случайности.
    """
    def key(i: int):
        place = placements.get(i)
        if place is None:
            return (1, -int(height[i]), i)
        cycle, channel = place
        return (0, cycle, channel, i)

    order = sorted(range(n), key=key)
    prio = [0.0] * n
    for rank, i in enumerate(order):
        prio[i] = float(n - rank)
    return prio


def floor_from_model(placements: dict[int, tuple[int, int]],
                     limit: int) -> dict[int, int]:
    """Такты модели как запрет «не раньше» (`defer_until`).

    `limit` отсекает галлюцинации: такт больше потолка (длины жадного
    расписания) — это не мнение о планировании, а сбой формата, и уважать
    его нельзя. Иначе одно число вроде «такт 900» растянуло бы расписание на
    900 тактов, причём совершенно законно, — и замер стал бы бессмысленным.
    """
    return {i: c for i, (c, _ch) in placements.items() if 0 < c <= limit}


def variants(dag: DAG, model: MachineModel,
             placements: dict[int, tuple[int, int]],
             *, extra: tuple[Variant, ...] = ()) -> list[Variant]:
    """Портфель кандидатов на один граф. Генерация модели не вызывается.

    `extra` — то, что посчитано выше по течению на том же ответе (сырое
    расписание модели и починенное `repair.py`). Они идут в портфель
    наравне, чтобы отбор мог предпочесть ответ самой модели, когда он не
    хуже, — и чтобы в отчёте было видно, что алгоритм ничего не «улучшил»
    там, где улучшать было нечего.
    """
    metrics = compute_metrics(dag, model)
    n = len(dag)

    greedy, _ = list_schedule(dag, model, priority=[float(h) for h in metrics.height],
                              height=metrics.height)
    out = [
        *extra,
        Variant("жадный", "baseline, модель не участвовала", greedy,
                tuple(greedy.validate())),
    ]

    prio = order_from_model(placements, n, metrics.height)
    by_order, _ = list_schedule(dag, model, priority=prio, height=metrics.height)
    out.append(Variant(
        "порядок",
        "порядок от модели, такты и каналы — планировщик",
        by_order, tuple(by_order.validate())))

    defer = floor_from_model(placements, greedy.makespan)
    if defer:
        by_both, _ = list_schedule(dag, model, priority=prio,
                                   defer_until=defer, height=metrics.height)
        out.append(Variant(
            "порядок+такты",
            "порядок от модели, её такты как «не раньше», каналы — планировщик",
            by_both, tuple(by_both.validate())))

    return out


def choose(cands: list[Variant]) -> Variant:
    """Лучший законный кандидат: меньше тактов — лучше.

    При равенстве побеждает тот, кто раньше в списке, а первым идёт ответ
    самой модели. Это не косметика: иначе портфель приписывал бы алгоритму
    победы там, где модель справилась сама и её просто пересчитали в то же
    число тактов.

    Если законных нет вообще (пустой граф или вырожденный вход) — вернём
    первого, чтобы вызывающий печатал диагноз, а не ловил исключение.
    """
    legal = [(i, c) for i, c in enumerate(cands) if c.legal]
    if not legal:
        return cands[0]
    return min(legal, key=lambda p: (p[1].makespan, p[0]))[1]
