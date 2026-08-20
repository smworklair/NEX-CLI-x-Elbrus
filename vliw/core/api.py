"""Общий контракт планировщика.

ЭТО ТОЧКА ПОДСТАНОВКИ ОБУЧЕННОЙ МОДЕЛИ.

Baseline-эвристика и «оракул» (доказанный оптимум) реализуют один и тот же
интерфейс `Scheduler`. Когда на Hexagon появится реально обученная модель,
её достаточно завернуть в класс с тем же `schedule()` — весь остальной код
(валидация, метрики, объяснения, CLI, визуализация) не меняется.

Минимальная реализация нового планировщика:

    class LearnedScheduler:
        name = "ИИ-планировщик (обученная модель)"
        kind = "learned"
        short = "learned"

        def schedule(self, dag, model):
            ...
            return SchedulingResult(schedule=sched, trace=steps, notes=[])

Формат `trace` не обязателен для работы — он нужен только для объяснений.
Планировщик, который его не заполняет, останется рабочим, но потеряет
пошаговый разбор в выводе.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from .dag import DAG
from .model import MachineModel
from .schedule import Placement, Schedule


@dataclass
class Candidate:
    """Одна инструкция-кандидат в решении конкретного такта."""

    instr: int
    ready_at: int
    """С какого такта операнды готовы."""
    height: int
    """Длина оставшегося критического пути (приоритет baseline-эвристики)."""
    chosen: bool = False
    channel: int | None = None
    reason: str = ""
    """Почему выбрана / почему нет — то, что печатается человеку."""


@dataclass
class DecisionStep:
    """Снимок решения планировщика в одном такте."""

    cycle: int
    free_channels: tuple[int, ...]
    candidates: list[Candidate] = field(default_factory=list)
    blocked: list[tuple[int, int]] = field(default_factory=list)
    """(инструкция, до какого такта она держит канал) — занятые монопольно."""
    rule: str = ""
    """Формулировка правила, по которому принято решение."""
    comment: str = ""
    """Свободный комментарий к такту."""

    @property
    def issued(self) -> list[int]:
        return [c.instr for c in self.candidates if c.chosen]


@dataclass
class SchedulingResult:
    schedule: Schedule
    trace: list[DecisionStep] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    """Заметки для отчёта: чем занимался планировщик, что доказал, где сдался."""
    optimal: bool | None = None
    """True — оптимальность доказана, False — точно нет, None — неизвестно."""
    search_stats: dict[str, object] = field(default_factory=dict)


@runtime_checkable
class Scheduler(Protocol):
    name: str
    kind: str
    short: str

    def schedule(self, dag: DAG, model: MachineModel) -> SchedulingResult: ...


# --------------------------------------------------------------------------
# Поток событий планировщика
# --------------------------------------------------------------------------
#
# ЗАЧЕМ ЭТО ПОЯВИЛОСЬ. Контракт выше описывает планировщик, который считает и
# возвращает результат целиком. Для baseline и «оракула» этого хватало: они
# считают миллисекунды, и разницы между «идёт» и «готово» человек не замечает.
#
# Обученная модель считает 30..60 секунд и выдаёт ответ ПО ЧАСТЯМ. В прежнем
# контракте показать это было нечем, поэтому появился сторонний kwarg
# `on_text=` у `LearnedScheduler.schedule()` — его нет в протоколе, и знает о
# нём только `cli.py`, который печатает поток прямо в stdout. А полноэкранный
# интерфейс собирает stdout команды целиком (`vliw/tui/bridge.py`) и показывает
# в конце — то есть стриминг там невидим ПО ПОСТРОЕНИЮ: экран замирает на
# полминуты, потом вываливается стена текста.
#
# Поток событий убирает причину, а не следствие: планировщик рассказывает о
# себе по ходу дела, а интерфейс решает, как это показать — построчной
# печатью, заливкой решётки или полосой прогресса.
#
# ЧТО ЭТО НЕ ЛОМАЕТ. Протокол `Scheduler` остаётся прежним. Планировщик,
# написанный по старому контракту (одна функция `schedule()`, как обещано в
# докстринге этого файла и в README), продолжает работать: `stream()` сам
# обернёт его в переигровку. Baseline и «оракул» не меняются ни строкой.


@dataclass(frozen=True)
class Started:
    """Планировщик представился. Всегда первое событие потока."""

    who: str
    note: str = ""


@dataclass(frozen=True)
class Note:
    """Строка для человека: то, что раньше печаталось как `Style.dim(...)`.

    `level` — роль для раскраски (`dim`, `warning`, `error`, `success`), а не
    готовый цвет: красить умеет только `vliw.ui`, ядро про цвета не знает.
    """

    text: str
    level: str = "dim"


@dataclass(frozen=True)
class Token:
    """Кусок сырого ответа модели, как он пришёл.

    Только для планировщиков, которые ГЕНЕРИРУЮТ текст. Baseline и «оракул»
    таких событий не производят: им нечего показывать посимвольно.
    """

    text: str


@dataclass(frozen=True)
class Step:
    """Одно решение планировщика (такт, кандидаты, правило).

    `live=False` означает ПЕРЕИГРОВКУ уже готового разбора, а не наблюдение за
    работой. Флаг едет внутри события намеренно: иначе интерфейс однажды
    подпишет мгновенную переигровку baseline как «смотрим, как оно думает», и
    поймать это будет нечем.
    """

    step: DecisionStep
    live: bool = True


@dataclass(frozen=True)
class Placed:
    """Операция встала в (такт, канал).

    Отдельно от `Step` потому, что модель `DecisionStep` не производит вовсе —
    у неё нет рассуждения по тактам, — но размещения производит. Решётке нужно
    ровно это событие, и оно одно работает для всех планировщиков.
    """

    placement: Placement
    live: bool = True


@dataclass(frozen=True)
class Repaired:
    """Канал переназначен починкой: такт не тронут, канал стал законным.

    Своё событие, а не строчка в заметках: иначе починенная ячейка молча
    выглядит как работа модели. Ровно то приписывание модели чужого
    результата, против которого написан докстринг `vliw/learned/scheduler.py`.
    """

    instr: int
    frm: int
    to: int


@dataclass(frozen=True)
class Progress:
    """Сделано `done` из `total`. Для замеров и всего, что идёт минутами.

    `total=0` — когда общее число заранее неизвестно.
    """

    done: int
    total: int = 0
    note: str = ""


@dataclass(frozen=True)
class Done:
    """Терминальное событие: всё получилось."""

    result: SchedulingResult


@dataclass(frozen=True)
class Failed:
    """Терминальное событие: не получилось, и это ОЖИДАЕМЫЙ исход.

    Сюда идут отказы, которые являются измеряемым результатом или обычным
    состоянием чужой машины: веса не найдены, модель не уложилась в срок,
    llama.cpp не собран. Ошибка В КОДЕ планировщика сюда НЕ идёт — она летит
    исключением и валит команду громко, как и раньше (см. проверку расписаний
    baseline/«оракула» в `cli.py`: незаконное расписание оттуда — это
    внутренняя ошибка, а не событие).
    """

    error: str


SchedulerEvent = (Started | Note | Token | Step | Placed | Repaired
                  | Progress | Done | Failed)

TERMINAL = (Done, Failed)
"""Поток всегда заканчивается ровно одним событием из этих — оно последнее."""


def _replay(res: SchedulingResult) -> Iterator[SchedulerEvent]:
    """Готовый результат — как поток событий, по тактам.

    Порядок «решение такта, затем что в этом такте встало» выбран не для
    красоты: он позволяет показывать переигровку в той же решётке и тем же
    кодом, что и живую работу модели.
    """
    seen: set[int] = set()
    for st in res.trace:
        yield Step(st, live=False)
        for i in st.issued:
            p = res.schedule.placements.get(i)
            if p is not None and i not in seen:
                seen.add(i)
                yield Placed(p, live=False)
    # `trace` не обязателен (см. докстринг файла): планировщик без него
    # остаётся рабочим. Размещения всё равно обязаны доехать до решётки.
    for i, p in sorted(res.schedule.placements.items()):
        if i not in seen:
            yield Placed(p, live=False)


def stream(scheduler, dag: DAG, model: MachineModel) -> Iterator[SchedulerEvent]:
    """Единый вход для интерфейсов: работа планировщика как поток событий.

    Планировщик, у которого есть `schedule_events()`, рассказывает о себе сам.
    Планировщику по старому контракту хватает `schedule()` — его результат
    переигрывается событиями, и снаружи разницы в обращении нет.

    ОТМЕНА. Поток — генератор, поэтому отмена не требует ни флагов, ни
    отдельного протокола: `gen.close()` бросает `GeneratorExit` в текущей
    точке `yield`, и планировщик доводит свой `finally` (у обученной модели там
    убийство подпроцесса llama.cpp). Потребителю достаточно перестать читать.

    ОТСЮДА ПРАВИЛО ДЛЯ АВТОРА `schedule_events()`: `try` обязан начинаться ДО
    первого `yield`, а не после. `GeneratorExit` прилетает в ту точку, где
    генератор стоит сейчас; если он стоит на `yield` вне `try`, `finally` не
    отработает. Отмена сразу после «планировщик представился» — самый частый
    случай в жизни (человек запустил и передумал), и для обученной модели она
    оставила бы осиротевший процесс llama.cpp с гигабайтами весов. Правило
    приколочено тестом `test_try_after_first_yield_leaks_...`.
    """
    fn = getattr(scheduler, "schedule_events", None)
    if fn is not None:
        yield from fn(dag, model)
        return

    yield Started(getattr(scheduler, "short", "?"),
                  getattr(scheduler, "name", ""))
    res = scheduler.schedule(dag, model)
    yield from _replay(res)
    yield Done(res)
