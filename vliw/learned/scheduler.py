"""Обученный планировщик: тот же протокол Scheduler, что у baseline и oracle.

Раньше здесь была заглушка с `NotImplementedError`, а веса умели работать
только на Kaggle — инференс жил в самодостаточном `training/validate_kaggle.py`
и умел ровно одно: прогнать эвал по файлу. Из инструмента адаптер было не
запустить вообще.

Теперь запускается: `/learned` в CLI. Загрузка и генерация — в `runtime.py`,
здесь только склейка «граф → промпт → ответ → расписание → проверка».

ЧЕМ ЭТОТ ПЛАНИРОВЩИК ОТЛИЧАЕТСЯ ОТ ОСТАЛЬНЫХ ДВУХ
--------------------------------------------------
baseline и oracle по построению выдают ЗАКОННОЕ расписание: если бы они его
нарушили, это была бы ошибка в коде, и `Session.results()` справедливо падает
с «ВНУТРЕННЯЯ ОШИБКА». Обученная модель — не такая: она может поставить
операцию на канал, который её не исполняет, забыть инструкцию или не
остановиться. На широком эвале прогона 1 законных расписаний было 33%.

Поэтому `SchedulingResult` отсюда МОЖЕТ содержать незаконное расписание, и это
не сбой инструмента, а измеряемый результат. Ошибки не проглатываются: они
складываются в `notes` и в `search_stats`, а CLI их печатает. Совать такой
результат в общий кэш `Session.results()` нельзя — там контракт другой.

Формат промпта берётся из `training/encode.py` — того самого модуля, которым
собирался обучающий датасет. Это намеренно: продублировать формат здесь
значило бы завести вторую копию, которая однажды молча разъедется с обучением.
Ровно так и получился EOS-баг (docs/EOS_INCIDENT.md).
"""

from __future__ import annotations

import time

from ..core import (
    DAG,
    Done,
    Failed,
    MachineModel,
    Note,
    Placed,
    Repaired,
    SchedulingResult,
    Started,
    Token,
)
from ..core.schedule import Placement, Schedule

# Сколько токенов максимум ждём от модели. Самый длинный эталон в данных —
# граф на 24 инструкции, это ~400 токенов; берём с запасом, но не бесконечно:
# модель без EOS (адаптер qwen-vliw-lora) не остановится сама никогда.
DEFAULT_MAX_NEW_TOKENS = 768


class LearnedScheduler:
    """Обученная модель как планировщик. Реализует протокол Scheduler."""

    name = "ИИ-планировщик (обученная модель)"
    kind = "learned"
    short = "learned"

    def __init__(self, adapter=None, backend=None,
                 max_new_tokens: int = DEFAULT_MAX_NEW_TOKENS,
                 device: str | None = None, repair: bool = False,
                 temperature: float = 0.0, seed: int | None = None):
        """`backend` можно передать готовым — это точка подмены для тестов.

        `repair=True` включает починку каналов (см. repair.py): такты модели
        остаются как есть, незаконный канал переназначается на законный.
        Результат тогда — ГИБРИД, и он подписан как гибрид, а не как чистый
        ответ модели.

        `temperature`/`seed` — сэмплинг для best-of-N (см. bench.py). Это
        атрибуты, а не аргументы `schedule()`, потому что протокол Scheduler
        фиксирован, а bench-у удобно менять их между сэмплами. Умолчание —
        жадный детерминированный ответ, которым сняты все замеры: путь до
        бэкенда остаётся прежним вызовом байт-в-байт.
        """
        self._adapter = adapter
        self._backend = backend
        self._device = device
        self.max_new_tokens = max_new_tokens
        self.repair = repair
        self.temperature = temperature
        self.seed = seed

    # --- ленивая загрузка --------------------------------------------------

    def backend(self):
        if self._backend is None:
            from . import runtime

            adapter = self._adapter
            if adapter is None:
                adapter = runtime.resolve_adapter()
            if adapter is None:
                raise RuntimeError(
                    f"обученных весов не найдено в {runtime.CHECKPOINTS}. "
                    "Адаптер — это папка с adapter_config.json и "
                    "adapter_model.safetensors.")
            self._adapter = adapter
            self._backend = runtime.make_backend(adapter, device=self._device)
        return self._backend

    @property
    def adapter(self):
        return self._adapter

    # --- собственно планирование ------------------------------------------

    def schedule_events(self, dag: DAG, model: MachineModel):
        """Работа модели как поток событий: токены и ЖИВАЯ заливка решётки.

        Решётка заполняется по ходу генерации, а не в конце. Это возможно
        потому, что формат ответа построчный (одна строка — одно размещение),
        а `decode_completion` разбирает текст построчно и терпимо: как только
        строка дописана, размещение уже известно. Полминуты ожидания
        превращаются в полминуты наблюдения за тем, как модель раскладывает
        участок.

        Незаконные размещения отдаются НАРАВНЕ с законными: модель ставит
        STORE на канал, который его не исполняет, и это её настоящий ответ.
        Судит расписание `validate()` в конце, а решётка показывает, ГДЕ
        именно модель ошиблась, — прятать это до вердикта значило бы прятать
        главное.
        """
        from training.encode import decode_completion, encode_prompt

        from . import runtime

        yield Started(self.short, self.name)

        try:
            be = self.backend()
        except (RuntimeError, OSError, ImportError) as e:
            yield Failed(str(e))
            return

        yield Note(f"{getattr(be, 'name', '?')}"
                   + (f" · адаптер {self._adapter.name}" if self._adapter else "")
                   + (" — первый запуск долгий, веса грузятся с диска"
                      if getattr(be, "slow_start", False) else ""))

        prompt = encode_prompt(dag, model)
        n = len(dag)
        t0 = time.monotonic()
        parts: list[str] = []
        line: list[str] = []
        seen: dict[int, tuple[int, int]] = {}

        def _flush_line() -> list[Placed]:
            """Дописанная строка → размещения, которых ещё не было.

            Повтор того же размещения не событие: модель иногда переписывает
            строку, и без этой проверки ячейка мигала бы впустую. А вот
            ИЗМЕНЁННОЕ размещение той же инструкции — событие: ячейка честно
            переедет, как это и произошло у модели.
            """
            text = "".join(line)
            line.clear()
            out: list[Placed] = []
            for i, (cycle, channel) in sorted(decode_completion(text).items()):
                if not (0 <= i < n) or seen.get(i) == (cycle, channel):
                    continue
                seen[i] = (cycle, channel)
                out.append(Placed(Placement(i, cycle, channel), live=True))
            return out

        gen = be.generate_events(
            prompt, self.max_new_tokens,
            **runtime.sampling_kwargs(self.temperature, self.seed))
        try:
            for chunk in gen:
                parts.append(chunk)
                yield Token(chunk)
                for ch in chunk:
                    if ch == "\n":
                        yield from _flush_line()
                    else:
                        line.append(ch)
        except (RuntimeError, OSError, ImportError, TimeoutError) as e:
            yield Failed(f"не удалось запустить модель: {e}")
            return
        finally:
            # Явно, а не полагаясь на сборщик мусора: здесь убивается
            # подпроцесс llama.cpp и отпускается _GENERATE_LOCK. При отмене
            # (`close()` снаружи) в эту точку прилетает GeneratorExit, и
            # закрыть вложенный генератор — единственный способ не оставить
            # процесс с гигабайтами весов жить дальше.
            #
            # getattr, а не прямой вызов: контракт `generate_events()` —
            # ИТЕРАТОР кусков, а не обязательно генератор. Бэкенд вправе
            # вернуть что угодно итерируемое (в тестах так и есть), и у него
            # `close()` может не быть.
            closer = getattr(gen, "close", None)
            if closer is not None:
                closer()

        yield from _flush_line()          # хвост без перевода строки

        raw = "".join(parts).split(runtime.END_MARKER)[0]
        res = self._assemble(dag, model, raw, time.monotonic() - t0)
        for i, was, now in res.search_stats.get("repair_moves", ()):
            yield Repaired(i, was, now)
        yield Done(res)

    def schedule(self, dag: DAG, model: MachineModel,
                 on_text=None) -> SchedulingResult:
        """Весь ответ целиком — старый контракт, поверх потока событий.

        `on_text(chunk)` оставлен ради построчного режима и тестов. Новый код
        должен брать `schedule_events()`: там есть ещё и заливка решётки, и
        отмена.
        """
        res = None
        for ev in self.schedule_events(dag, model):
            if isinstance(ev, Token):
                if on_text:
                    on_text(ev.text)
            elif isinstance(ev, Done):
                res = ev.result
            elif isinstance(ev, Failed):
                # Прежний `schedule()` падал исключением, и `cmd_learned` его
                # ловит. Сохраняем это поведение дословно.
                raise RuntimeError(ev.error)
        assert res is not None, "поток обязан кончиться Done или Failed"
        return res

    def _assemble(self, dag: DAG, model: MachineModel, raw: str,
                  elapsed: float) -> SchedulingResult:
        """Сырой ответ модели → расписание, диагноз, метрики."""
        from training.encode import clip_placements, decode_completion

        decoded = decode_completion(raw)
        keep, extra = clip_placements(decoded, len(dag))

        # Собираем расписание вручную, а не через build_schedule(): нам нужно
        # поимённо знать, какие строки модель выдала за пределами графа и
        # какие инструкции пропустила, — иначе диагноз выродится в «невалидно».
        sched = Schedule(dag, model)
        for i, (cycle, channel) in sorted(keep.items()):
            sched.place(i, cycle, channel)

        missing = sorted(set(range(len(dag))) - set(keep))
        raw_errs = sched.validate()

        # Починка каналов. Только при полном ответе: если модель что-то не
        # разместила, чинить нечего — дыру в расписании каналом не закрыть.
        report = None
        errs = raw_errs
        if self.repair and not missing:
            from .repair import repair as _repair

            fixed, report = _repair(sched, model)
            fixed_errs = fixed.validate()
            # Берём починенное, только если стало не хуже. Строгая проверка, а
            # не вера в свой же алгоритм: расписание после починки обязано
            # пройти тот же validate(), что и любое другое.
            if len(fixed_errs) <= len(raw_errs):
                sched, errs = fixed, fixed_errs
            else:
                report = None

        notes = [
            f"модель: {getattr(self.backend(), 'name', '?')}"
            + (f" · адаптер {self._adapter.name}" if self._adapter else ""),
            f"сгенерировано за {elapsed:.1f} с, разобрано строк: {len(decoded)}",
        ]
        if extra:
            notes.append(
                f"НЕ ОСТАНОВИЛАСЬ: {len(extra)} строк для несуществующих "
                f"инструкций (id {extra[:6]}{'…' if len(extra) > 6 else ''}). "
                "Префикс при этом может быть законным — см. docs/EOS_INCIDENT.md.")
        if missing:
            notes.append(f"НЕ РАЗМЕЩЕНЫ инструкции: {missing}")
        if report is not None and report.touched:
            notes.append(
                f"ПОЧИНЕНО КАНАЛОВ: {report.touched} "
                f"(такты модели не тронуты, makespan её же)")
            for i, was, now in report.moved[:6]:
                notes.append(f"  {dag[i].op} #{i}: канал {was} -> {now}")
            if len(report.moved) > 6:
                notes.append(f"  … ещё {len(report.moved) - 6}")
        if errs:
            notes.append(f"РАСПИСАНИЕ НЕЗАКОННО, нарушений {len(errs)}:")
            notes.extend("  " + e for e in errs[:8])
            if len(errs) > 8:
                notes.append(f"  … ещё {len(errs) - 8}")
        elif not missing:
            notes.append(f"расписание законно, makespan {sched.makespan}")

        return SchedulingResult(
            schedule=sched,
            notes=notes,
            optimal=None,          # модель ничего не доказывает
            search_stats={
                "raw": raw,
                "seconds": elapsed,
                "n_decoded": len(decoded),
                "extra": extra,
                "missing": missing,
                "errors": errs,
                "valid": not errs and not missing,
                "repaired": report.touched if report is not None else 0,
                "repair_moves": report.moved if report is not None else [],
                "errors_before_repair": raw_errs,
            },
        )
