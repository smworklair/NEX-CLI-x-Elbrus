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

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from .dag import DAG
from .model import MachineModel
from .schedule import Schedule


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
