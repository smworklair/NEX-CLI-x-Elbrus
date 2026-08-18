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

from ..core import DAG, MachineModel, SchedulingResult
from ..core.schedule import Schedule

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
                 device: str | None = None):
        """`backend` можно передать готовым — это точка подмены для тестов."""
        self._adapter = adapter
        self._backend = backend
        self._device = device
        self.max_new_tokens = max_new_tokens

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

    def schedule(self, dag: DAG, model: MachineModel) -> SchedulingResult:
        from training.encode import clip_placements, decode_completion, encode_prompt

        prompt = encode_prompt(dag, model)
        t0 = time.monotonic()
        raw = self.backend().generate(prompt, self.max_new_tokens)
        elapsed = time.monotonic() - t0

        decoded = decode_completion(raw)
        keep, extra = clip_placements(decoded, len(dag))

        # Собираем расписание вручную, а не через build_schedule(): нам нужно
        # поимённо знать, какие строки модель выдала за пределами графа и
        # какие инструкции пропустила, — иначе диагноз выродится в «невалидно».
        sched = Schedule(dag, model)
        for i, (cycle, channel) in sorted(keep.items()):
            sched.place(i, cycle, channel)

        missing = sorted(set(range(len(dag))) - set(keep))
        errs = sched.validate()

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
            },
        )
