"""Трудность графа: есть ли на нём что выигрывать у жадной эвристики.

ЗАЧЕМ ЭТОТ ФАЙЛ ПОЯВИЛСЯ
------------------------
Замер 30.08.2026 (`docs/CAB.md`) показал вещь, которая обесценивает разом все
прежние сравнения обученной модели: **на `eval_wide.jsonl` жадная эвристика
стоит в ДОКАЗАННОМ оптимуме на 298 графах из 300**, а на `eval.jsonl` — на всех
300. То есть метрика «модель выдала законное расписание» сравнивалась не с
конкурентом, а с пустотой: baseline там законен всегда и оптимален почти
всегда, причём за миллисекунды против сотен секунд у модели.

`vliw/core/oracle.py` сформулировал это в своей шапке ещё до появления модели:

    Разрыв между baseline и этим потолком и есть бюджет, за который имеет
    смысл бороться обученной моделью. Если разрыва нет — эвристика уже
    оптимальна, и учить на этом графе нечему.

Здесь этот бюджет считается явно, одним числом, и на нём можно фильтровать.

ЧЕГО ЗДЕСЬ НЕТ
--------------
Утверждений о трудности графа, на котором оптимум не доказан. Оракул работает
в бюджете и на больших графах сдаётся; тогда `Hardness.proven` — False, и
такой граф нельзя ни назвать лёгким, ни назвать трудным. Молча считать его
одним из двух — ровно тот способ соврать, из-за которого и понадобился этот
файл.
"""

from __future__ import annotations

from dataclasses import dataclass

from .baseline import GreedyListScheduler
from .dag import DAG
from .model import MachineModel
from .oracle import OracleScheduler
from .schedule import Schedule


@dataclass(frozen=True)
class Hardness:
    """Сколько тактов на этом графе можно отыграть у эвристики."""

    baseline: int
    """Длина жадного расписания."""
    optimum: int
    """Длина оптимального — если он доказан, иначе лучшее найденное."""
    proven: bool
    """Доказана ли оптимальность. Без этого `gap` — нижняя оценка, не факт."""
    schedule: Schedule
    """Оптимальное расписание. Готовый эталон для обучающего примера."""

    @property
    def gap(self) -> int:
        return self.baseline - self.optimum

    @property
    def hard(self) -> bool:
        """Есть ли что выигрывать. Недоказанный оптимум трудным не считается.

        Осторожность намеренно однобокая: пропустить трудный граф — потерять
        пример, а назвать трудным граф с недоказанным оптимумом — отравить
        выборку эталоном, который сам может быть хуже оптимального.
        """
        return self.proven and self.gap > 0


def measure(dag: DAG, model: MachineModel, *, budget_s: float = 10.0) -> Hardness:
    """Жадный против точного поиска на одном графе."""
    base = GreedyListScheduler().schedule(dag, model)
    orc = OracleScheduler(budget_s=budget_s, portfolio_s=0.5).schedule(dag, model)
    return Hardness(
        baseline=base.schedule.makespan,
        optimum=orc.schedule.makespan,
        proven=bool(orc.optimal),
        schedule=orc.schedule,
    )


def harvest_one(task: tuple[int, int, int, str]) -> dict | None:
    """Один кандидат: породить граф, померить, вернуть пример или None.

    Функция верхнего уровня и принимает только простые значения — иначе её
    нельзя раздать процессам. Профиль передаётся ИМЕНЕМ, а не объектом:
    `MachineModel` через pickle гонять незачем, а имя однозначно.

    Импорты внутри намеренно: `vliw.core` не должен на уровне модуля зависеть
    ни от `tools/`, ни от `training/` — это слои выше. Тот же приём уже
    применён в `vliw/learned/scheduler.py`.
    """
    import random

    from training.encode import encode_completion, encode_prompt

    from .dag import Instr
    from .model import get_profile

    seed, n_lo, n_hi, profile = task
    from tools.vliw_gen import PRESSURE_WEIGHTS, SHAPES, gen_graph

    model = get_profile(profile)
    rnd = random.Random(seed)
    n = rnd.randint(n_lo, n_hi)
    shape = rnd.choice(SHAPES)
    raw = gen_graph(rnd, n, shape, PRESSURE_WEIGHTS)
    dag = DAG("hard", "", "",
              [Instr(x.id, f"n{x.id}", x.op, x.preds, f"n{x.id}") for x in raw])

    h = measure(dag, model, budget_s=6.0)
    if not h.hard:
        return None
    return {
        "prompt": encode_prompt(dag, model),
        "completion": encode_completion(h.schedule),
        "meta": {"makespan": h.optimum, "n": n, "shape": shape,
                 "gap": h.gap, "baseline": h.baseline, "seed": seed},
    }
