"""Обученная модель планирования: запуск локально, тем же протоколом.

`LearnedScheduler` реализует протокол `Scheduler` из `vliw.core.api` — тот же
`schedule(dag, model) -> SchedulingResult`, что у baseline и oracle, поэтому
CLI и визуализация про него ничего особенного не знают.

Одно отличие принципиально: baseline и oracle по построению выдают ЗАКОННОЕ
расписание, а обученная модель — не обязательно. Её ошибки не прячутся, а
складываются в `notes`/`search_stats` и печатаются. Подробности — в
`scheduler.py`.

Тяжёлые зависимости (torch/transformers/peft) грузятся лениво, внутри
`runtime.py`: `import vliw` их не требует, и без них инструмент работает как
раньше — просто без команды `/learned`.
"""

from .scheduler import LearnedScheduler

__all__ = ["LearnedScheduler"]
