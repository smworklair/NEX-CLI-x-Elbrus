"""Типизированная кодировка граф+модель ⇄ текст для дообучения LLM.

Одна и та же функция кодирования используется и генератором датасета
(`generate_dataset.py`, гоняет только `vliw.core`, CPU), и валидатором
(`validate.py`, разбирает ответ модели обратно в `Schedule` и проверяет
`Schedule.validate()`). Формат нарочно жёсткий и однообразный — модели проще
выучить одну структуру, а парсеру проще её разобрать без гадания.

Ничего из этого файла не тянет torch/transformers — чистый Python, можно
гонять где угодно, в том числе на бесплатном Deepnote (только CPU).
"""

from __future__ import annotations

import re

from vliw.core import DAG, MachineModel, Schedule

_LINE_RE = re.compile(r"(\d+):\s*такт=(\d+)\s*канал=(\d+)")


def encode_prompt(dag: DAG, model: MachineModel) -> str:
    """Граф зависимостей + профиль машины → текст-запрос."""
    lines = [f"профиль: {model.name}", "граф:"]
    for ins in dag:
        preds = " ".join(str(p) for p in ins.preds)
        lines.append(f"{ins.id} {ins.op}" + (f" <- {preds}" if preds else ""))
    lines.append("расписание:")
    return "\n".join(lines)


def encode_completion(schedule: Schedule) -> str:
    """Готовое расписание → текст-ответ (эталон для обучения)."""
    lines = []
    for i in sorted(schedule.placements):
        p = schedule.placements[i]
        lines.append(f"{i}: такт={p.cycle} канал={p.channel}")
    return "\n".join(lines)


def decode_completion(text: str) -> dict[int, tuple[int, int]]:
    """Текст-ответ модели → {id инструкции: (такт, канал)}.

    Намеренно терпимый парсер: строки, не совпавшие с шаблоном (модель
    что-то дописала от себя, галлюцинировала пояснение и т.п.), просто
    пропускаются — а не роняют разбор целиком. Неполнота обнаружится сама:
    `Schedule.validate()` увидит невыданные инструкции.
    """
    out: dict[int, tuple[int, int]] = {}
    for m in _LINE_RE.finditer(text):
        i, cycle, channel = (int(x) for x in m.groups())
        out[i] = (cycle, channel)
    return out


def clip_placements(decoded: dict[int, tuple[int, int]], n: int
                    ) -> tuple[dict[int, tuple[int, int]], list[int]]:
    """Оставить только id из графа. Хвост (id ≥ n) — отдельно.

    Это не подгон метрики: в графе нет инструкции 8, если их всего 8 (0..7).
    Собрать из хвоста расписание нельзя. Префикс 0..n-1 при этом можно
    проверить как обычное расписание — и отдельно посчитать, остановилась
    ли модель.
    """
    keep = {i: p for i, p in decoded.items() if 0 <= i < n}
    extra = sorted(i for i in decoded if not (0 <= i < n))
    return keep, extra


def build_schedule(dag: DAG, model: MachineModel,
                    decoded: dict[int, tuple[int, int]]) -> Schedule:
    """Собрать `Schedule` из разобранного ответа — для прогона через validate()."""
    keep, _ = clip_placements(decoded, len(dag))
    sched = Schedule(dag, model)
    for i, (cycle, channel) in keep.items():
        sched.place(i, cycle, channel)
    return sched
