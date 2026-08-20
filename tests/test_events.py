"""Поток событий планировщика: `vliw.core.api.stream()`.

Главное, что здесь проверяется, — обещание совместимости. Докстринг
`vliw/core/api.py` и README говорят стороннему автору: заверни свой
планировщик в класс с одним методом `schedule()` — и весь остальной код
(валидация, метрики, объяснения, CLI, отрисовка) заработает без правок.
Поток событий появился ПОСЛЕ этого обещания, поэтому первым делом проверяется,
что планировщик по старому контракту через него проходит целиком.

Второе — отмена. Она не отдельный протокол, а свойство генератора: `close()`
бросает `GeneratorExit` в точке `yield`, и планировщик доводит свой `finally`.
У обученной модели в этом `finally` убивается подпроцесс llama.cpp, поэтому
тест на «finally отработал» — не формальность.
"""

from __future__ import annotations

import unittest

from vliw.core import (
    DAG,
    Done,
    Failed,
    GreedyListScheduler,
    OracleScheduler,
    Placed,
    SchedulingResult,
    Started,
    Step,
    Token,
    get_profile,
    get_scenario,
    stream,
)
from vliw.core.api import TERMINAL
from vliw.core.schedule import Schedule

M = get_profile("e2k-v6-measured")


class OldContractScheduler:
    """Планировщик ровно по старому контракту: ни событий, ни трассы."""

    name = "старый контракт"
    kind = "heuristic"
    short = "old"

    def schedule(self, dag: DAG, model) -> SchedulingResult:
        sched = Schedule(dag, model)
        for i, instr in enumerate(dag):
            sched.place(i, i, model.channels_for(instr.op)[0])
        return SchedulingResult(schedule=sched)


class StreamAdapterTest(unittest.TestCase):
    """Планировщик без `schedule_events()` — через переигровку результата."""

    def setUp(self) -> None:
        self.dag = get_scenario("slotclash")

    def _events(self, scheduler):
        return list(stream(scheduler, self.dag, M))

    def test_old_contract_scheduler_works_untouched(self) -> None:
        """Класс с одним `schedule()` даёт полноценный поток — обещание в силе."""
        evs = self._events(OldContractScheduler())
        self.assertIsInstance(evs[0], Started)
        self.assertIsInstance(evs[-1], Done)
        placed = [e for e in evs if isinstance(e, Placed)]
        self.assertEqual(len(placed), len(self.dag))

    def test_no_trace_still_places_everything(self) -> None:
        """Трасса не обязательна — но решётка обязана получить все размещения.

        `OldContractScheduler` не заполняет `trace` вовсе. Если бы события
        `Placed` брались только из трассы, решётка осталась бы пустой.
        """
        evs = self._events(OldContractScheduler())
        got = {e.placement.instr for e in evs if isinstance(e, Placed)}
        self.assertEqual(got, set(range(len(self.dag))))

    def test_every_instruction_placed_exactly_once(self) -> None:
        """Ни одна инструкция не заливается в решётку дважды.

        В переигровке размещения берутся сперва из трассы, потом из остатка
        расписания. Пересечение этих двух источников — самая правдоподобная
        ошибка здесь, и она даёт мигающую ячейку в интерфейсе.
        """
        for scheduler in (GreedyListScheduler(),
                          OracleScheduler(budget_s=5.0, portfolio_s=1.0)):
            with self.subTest(scheduler=scheduler.short):
                evs = self._events(scheduler)
                placed = [e.placement.instr for e in evs if isinstance(e, Placed)]
                self.assertEqual(len(placed), len(set(placed)))
                self.assertEqual(set(placed), set(range(len(self.dag))))

    def test_exactly_one_terminal_event_and_it_is_last(self) -> None:
        """Потребителю нужно знать, что поток кончился, ровно один раз."""
        evs = self._events(GreedyListScheduler())
        terminals = [e for e in evs if isinstance(e, TERMINAL)]
        self.assertEqual(len(terminals), 1)
        self.assertIs(terminals[0], evs[-1])

    def test_replay_is_marked_not_live(self) -> None:
        """Переигровка обязана быть подписана как переигровка.

        Иначе интерфейс однажды покажет мгновенный baseline как «смотрим, как
        оно думает». Флаг едет в событии именно чтобы это было невозможно.
        """
        evs = self._events(GreedyListScheduler())
        marks = {e.live for e in evs if isinstance(e, (Step, Placed))}
        self.assertEqual(marks, {False})

    def test_terminal_result_is_the_schedulers_own(self) -> None:
        """`Done.result` — тот же объект, что вернул планировщик, без копий."""
        scheduler = GreedyListScheduler()
        direct = scheduler.schedule(self.dag, M)
        evs = self._events(scheduler)
        self.assertEqual(evs[-1].result.schedule.makespan,
                         direct.schedule.makespan)


class EventfulScheduler:
    """Планировщик, который рассказывает о себе сам, и делает это ПРАВИЛЬНО.

    Правильно — значит `try` начинается ДО первого `yield`, а не после. См.
    `LeakyScheduler` ниже: там показано, что бывает иначе.
    """

    name = "событийный"
    kind = "learned"
    short = "ev"

    def __init__(self) -> None:
        self.cleaned = False
        self.emitted = 0

    def schedule_events(self, dag: DAG, model):
        try:
            yield Started(self.short)
            while True:                     # бесконечный — как генерация модели
                self.emitted += 1
                yield Token("x")
        finally:
            # У обученной модели здесь убивается подпроцесс llama.cpp.
            self.cleaned = True

    def schedule(self, dag: DAG, model) -> SchedulingResult:
        raise AssertionError("при наличии schedule_events() не должен вызываться")


class LeakyScheduler:
    """Тот же планировщик, но `try` начинается ПОСЛЕ первого `yield`.

    Существует только затем, чтобы приколотить правило контракта тестом.
    Отмена ровно на первом событии бросает `GeneratorExit` мимо `try`, и
    `finally` не отрабатывает. Для обученной модели это означало бы
    осиротевший процесс llama.cpp, который держит гигабайты и порт.
    """

    name = "дырявый"
    kind = "learned"
    short = "leak"

    def __init__(self) -> None:
        self.cleaned = False

    def schedule_events(self, dag: DAG, model):
        yield Started(self.short)           # ← вне try: здесь и течёт
        try:
            while True:
                yield Token("x")
        finally:
            self.cleaned = True


class EventfulPathTest(unittest.TestCase):

    def setUp(self) -> None:
        self.dag = get_scenario("simple4")

    def test_schedule_events_wins_over_schedule(self) -> None:
        """Есть `schedule_events()` — переигровка не используется."""
        sch = EventfulScheduler()
        gen = stream(sch, self.dag, M)
        self.assertIsInstance(next(gen), Started)
        self.assertIsInstance(next(gen), Token)
        gen.close()

    def test_close_runs_scheduler_cleanup(self) -> None:
        """Отмена доводит `finally` планировщика — процесс модели не осиротеет."""
        sch = EventfulScheduler()
        gen = stream(sch, self.dag, M)
        for _ in range(4):
            next(gen)
        self.assertFalse(sch.cleaned)
        gen.close()
        self.assertTrue(sch.cleaned)

    def test_cancel_on_the_very_first_event_still_cleans_up(self) -> None:
        """Отмена на первом же событии — тоже отмена, и убирать за собой надо.

        Самый вероятный сценарий в жизни: человек запустил модель, сразу
        передумал и нажал Esc. К этому моменту поток отдал ровно `Started`.
        """
        sch = EventfulScheduler()
        gen = stream(sch, self.dag, M)
        next(gen)
        gen.close()
        self.assertTrue(sch.cleaned)
        self.assertEqual(sch.emitted, 0)

    def test_try_after_first_yield_leaks_and_that_is_why_the_rule_exists(self) -> None:
        """Правило «`try` до первого `yield`» — приколочено, а не на словах.

        Это не проверка `stream()`, а фиксация того, ЧТО ИМЕННО ломается при
        нарушении контракта. Если однажды кто-то напишет планировщик так —
        пусть провалится здесь, а не осиротевшим процессом на чужой машине.
        """
        sch = LeakyScheduler()
        gen = stream(sch, self.dag, M)
        next(gen)                            # отдал Started, стоит вне try
        gen.close()
        self.assertFalse(sch.cleaned, "поведение Python изменилось — перечитать контракт")


class FailingScheduler:
    """Ожидаемый отказ: весов нет. Это результат, а не поломка инструмента."""

    name = "без весов"
    kind = "learned"
    short = "nofail"

    def schedule_events(self, dag: DAG, model):
        yield Started(self.short)
        yield Failed("нет весов: адаптер не сконвертирован в GGUF")


class FailedEventTest(unittest.TestCase):

    def test_failed_is_terminal(self) -> None:
        """`Failed` закрывает поток так же, как `Done` — потребитель один."""
        evs = list(stream(FailingScheduler(), get_scenario("simple4"), M))
        self.assertIsInstance(evs[-1], Failed)
        self.assertEqual(len([e for e in evs if isinstance(e, TERMINAL)]), 1)


if __name__ == "__main__":
    unittest.main()
