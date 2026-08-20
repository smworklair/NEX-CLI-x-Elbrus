"""Запуск обученного адаптера локально: поиск весов, зависимости, генерация.

Зачем этот слой отдельно от `scheduler.py`
------------------------------------------
Веса до сих пор работали только на Kaggle: инференс жил в
`training/validate_kaggle.py`, который самодостаточен РАДИ Kaggle (там нет
пакета `vliw`) и умеет ровно одно — прогнать эвал по файлу и напечатать
сводку. Из инструмента адаптер было не запустить вообще.

Здесь ровно та же схема загрузки, что и в `validate_kaggle.py` (включая обход
двух багов окружения — они разобраны на месте), но пригодная к вызову из CLI:
модель поднимается один раз и отвечает на произвольный граф.

Тяжёлые импорты (torch/transformers/peft) — ТОЛЬКО внутри функций. У проекта
нет обязательных зависимостей, и `import vliw` не должен их требовать: без
установленного torch инструмент обязан работать как раньше, просто без
команды `/learned`.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
CHECKPOINTS = _ROOT / "training" / "checkpoints"
VENDOR = _ROOT / "vendor"

# Пакеты, без которых локальный запуск невозможен. Проверяются по отдельности,
# чтобы сообщение называло недостающее поимённо, а не «что-то не так».
REQUIRED = ("torch", "transformers", "peft")


# --------------------------------------------------------------------------
# Что вообще есть на диске
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Adapter:
    """Найденный LoRA-адаптер."""

    path: Path
    base: str
    """Базовая модель из adapter_config.json — LoRA привязан к ней по форме."""
    size_mb: float
    has_tokenizer: bool
    """Лежит ли рядом токенизатор.

    У `lora-eos` его нет (обучение сохранило только адаптер), поэтому
    токенизатор приходится брать у базовой модели или у соседнего адаптера —
    иначе загрузка падает на ровном месте.
    """

    @property
    def name(self) -> str:
        return self.path.name


def find_adapters(root: Path | None = None) -> list[Adapter]:
    """Все адаптеры в training/checkpoints — по наличию adapter_config.json."""
    root = root or CHECKPOINTS
    out: list[Adapter] = []
    if not root.exists():
        return out
    for cfg in sorted(root.glob("*/adapter_config.json")):
        try:
            data = json.loads(cfg.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        weights = cfg.parent / "adapter_model.safetensors"
        out.append(Adapter(
            path=cfg.parent,
            base=data.get("base_model_name_or_path", "?"),
            size_mb=weights.stat().st_size / 1e6 if weights.exists() else 0.0,
            has_tokenizer=(cfg.parent / "tokenizer_config.json").exists(),
        ))
    return out


def resolve_adapter(name: str | None = None) -> Adapter | None:
    """Адаптер по имени/пути; без имени — последний по времени изменения."""
    found = find_adapters()
    if name:
        p = Path(name)
        if (p / "adapter_config.json").exists():
            got = find_adapters(p.parent)
            return next((a for a in got if a.path == p), None)
        return next((a for a in found if a.name == name), None)
    if not found:
        return None
    return max(found, key=lambda a: a.path.stat().st_mtime)


def missing_deps() -> list[str]:
    """Каких пакетов не хватает для локального запуска."""
    import importlib.util

    return [m for m in REQUIRED if importlib.util.find_spec(m) is None]


def _mem_total_gb() -> float | None:
    """Сколько всего ОЗУ. Нужно для честного предупреждения про размер модели."""
    try:
        with open("/proc/meminfo", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) / 1e6
    except OSError:
        pass
    return None


def status(name: str | None = None) -> tuple[bool, list[str]]:
    """(готово ли к запуску, строки отчёта). Не требует torch."""
    lines: list[str] = []
    adapters = find_adapters()
    if adapters:
        lines.append("найденные адаптеры:")
        for a in adapters:
            tok = "" if a.has_tokenizer else "  (без токенизатора — возьмём у базовой)"
            lines.append(f"  {a.name}  {a.size_mb:.0f} МБ  база: {a.base}{tok}")
    else:
        lines.append(f"адаптеров не найдено в {CHECKPOINTS}")

    miss = missing_deps()
    if miss:
        lines.append("")
        lines.append("не хватает пакетов: " + ", ".join(miss))
        lines.append("  поставить:  .venv/bin/pip install " + " ".join(miss))
    else:
        lines.append("")
        lines.append("зависимости на месте: " + ", ".join(REQUIRED))

    mem = _mem_total_gb()
    if mem is not None:
        lines.append("")
        lines.append(f"ОЗУ на машине: {mem:.1f} ГБ")
        if mem < 12:
            lines.append(
                "  ВНИМАНИЕ: Qwen2.5-3B даже в bfloat16 занимает ~6.2 ГБ плюс "
                "активации. На этой машине запуск будет уходить в своп и "
                "считаться минутами на граф, а то и не поднимется вовсе.")
            lines.append(
                "  Разумный путь для CPU — 4-битный GGUF через llama.cpp "
                "(~2 ГБ): см. docs/LEARNED.md.")

    # llama.cpp — основной путь на CPU, проверяем его первым.
    lines.append("")
    if adapters:
        best = resolve_adapter(name)
        if best is not None:
            ok, problems = llama_cpp_ready(best)
            if ok:
                b = find_gguf_base()
                srv_ok, _ = llama_server_ready(best)
                if srv_ok:
                    lines.append(f"llama-server: готов  (адаптер {best.name})")
                    lines.append(f"  база {b.name}, "
                                 f"{b.stat().st_size / 1e9:.1f} ГБ, 4 бита")
                    lines.append(f"  веса грузятся один раз за сессию, "
                                 f"{default_threads()} потоков")
                    lines.append("  замерено: 12 с на граф против 32 с у "
                                 "процесса на команду")
                else:
                    lines.append(f"llama.cpp: готов  (адаптер {best.name})")
                    lines.append(f"  база {b.name}, "
                                 f"{b.stat().st_size / 1e9:.1f} ГБ, 4 бита")
                    lines.append("  процесс на каждую команду: веса читаются "
                                 "заново, около 32 с на граф")
                return True, lines
            lines.append("llama.cpp: не готов")
            for pr in problems:
                lines.append("  " + pr)

    ready = bool(adapters) and not miss
    return ready, lines


# --------------------------------------------------------------------------
# Бэкенды генерации
# --------------------------------------------------------------------------


class Backend:
    """Что угодно, что умеет продолжить текст.

    ОСНОВНОЙ метод — `generate_events()`: генератор кусков ответа. Так, а не
    через callback `on_text=`, потому что генератор даёт отмену бесплатно и
    правильно. Раньше здесь был callback, и отменить генерацию было нечем:
    Textual снимал свой воркер, а блокирующий `subprocess` внутри про отмену
    не знал и продолжал считать (см. комментарий к `_GENERATE_LOCK` ниже —
    из-за этого пришлось заводить блокировку). У генератора `close()` бросает
    `GeneratorExit` в точке `yield`, отрабатывает `finally`, и подпроцесс
    llama.cpp умирает вместе с отменой.

    `generate()` оставлен как удобная обёртка: он собирает поток целиком.
    Реализовывать в наследнике нужно только `generate_events()`.
    """

    name = "?"

    slow_start = False
    """Грузит ли бэкенд веса при первом обращении.

    Нужно интерфейсу, чтобы не обещать долгое ожидание там, где его нет:
    подставной бэкенд отвечает мгновенно, и подпись «веса грузятся с диска»
    была бы про него неправдой.
    """

    def generate_events(self, prompt: str, max_new_tokens: int):
        """Куски ответа по мере генерации. Сырые: маркеры конца не срезаны."""
        raise NotImplementedError

    def generate(self, prompt: str, max_new_tokens: int,
                 on_text=None) -> str:
        """Весь ответ целиком. `on_text(chunk)` — по мере поступления."""
        parts: list[str] = []
        for chunk in self.generate_events(prompt, max_new_tokens):
            parts.append(chunk)
            if on_text:
                on_text(chunk)
        return "".join(parts).split(END_MARKER)[0]


END_MARKER = "[end of text]"
"""Чем llama.cpp помечает конец. Может прийти разорванным между кусками,
поэтому срезается по СОБРАННОМУ тексту, а не по каждому куску отдельно."""


class ScriptedBackend(Backend):
    """Заранее заданные ответы. Для тестов и разбора уже снятых прогонов.

    Позволяет прогнать весь путь «граф → промпт → ответ → расписание →
    проверка» без torch и без весов — то есть проверять склейку, а не модель.
    """

    name = "scripted"

    def __init__(self, replies: list[str] | str):
        self._replies = [replies] if isinstance(replies, str) else list(replies)
        self._i = 0

    def generate_events(self, prompt: str, max_new_tokens: int):
        if not self._replies:
            return
        r = self._replies[min(self._i, len(self._replies) - 1)]
        self._i += 1
        yield r


class TransformersBackend(Backend):
    """Локальный запуск через transformers + peft — как на Kaggle, но в CLI.

    Модель поднимается ОДИН раз на объект: загрузка 3B весов занимает
    десятки секунд, и делать её на каждый граф бессмысленно.
    """

    name = "transformers"
    slow_start = True

    def __init__(self, adapter: Adapter, dtype: str = "auto", device: str = "auto"):
        self.adapter = adapter
        self.dtype = dtype
        self.device = device
        self._tok = None
        self._model = None

    def _resolve(self):
        """Устройство и тип весов — конкретные, а не строка «auto».

        Тип выбирается по устройству, и это не вкусовщина:
          * float32 на CPU — 12.4 ГБ на 3B, не влезает почти никуда;
          * float16 на CPU в torch местами не имеет ядер и падает в
            медленные ветки, зато на GPU это норма (так и гоняли на Kaggle);
          * bfloat16 — половина памяти (~6.2 ГБ) и нормальная поддержка на
            современных x86, поэтому он и стоит умолчанием для CPU.
        """
        import torch

        device = self.device
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        if self.dtype != "auto":
            return device, getattr(torch, self.dtype)
        return device, (torch.float16 if device == "cuda" else torch.bfloat16)

    def _load(self):
        if self._model is not None:
            return
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer

        # Тот же точечный обход, что и в training/validate_kaggle.py: peft
        # этой версии кодирует несовместимую torchao прямым ImportError, хотя
        # torchao-квантование мы не используем вовсе (обычный LoRA).
        try:
            import peft.tuners.lora.torchao as _torchao_mod

            _torchao_mod.is_torchao_available = lambda: False
        except Exception:
            pass

        # Токенизатор: рядом с адаптером его может не быть (у lora-eos нет),
        # тогда берём у базовой модели. Раньше это был бы отказ на пустом месте.
        tok_src = str(self.adapter.path) if self.adapter.has_tokenizer else self.adapter.base
        self._tok = AutoTokenizer.from_pretrained(tok_src, trust_remote_code=True)

        device, torch_dtype = self._resolve()

        # `torch_dtype=`, а не новое `dtype=`: именно это имя проверенно
        # работает на Kaggle (training/validate_kaggle.py), и в transformers 5.x
        # оно всё ещё принимается — устарело, но не удалено. Определять имя
        # через inspect.signature() бессмысленно: параметр идёт в **kwargs, и
        # в сигнатуре его нет ни под одним из имён.
        #
        # Имя базы берём из adapter_config.json явно — если подсунуть путь
        # адаптера, новые transformers пытаются подтянуть LoRA внутри
        # from_pretrained и падают. Адаптер применяем отдельно, ниже.
        base = AutoModelForCausalLM.from_pretrained(
            self.adapter.base,
            torch_dtype=torch_dtype,
            device_map="auto" if device == "cuda" else None,
            low_cpu_mem_usage=True,
            trust_remote_code=True,
        )
        model = PeftModel.from_pretrained(base, str(self.adapter.path))
        model.eval()
        if device == "cpu":
            model.to("cpu")
        self._model = model

    def generate_events(self, prompt: str, max_new_tokens: int):
        """Одним куском: transformers здесь считает без стриминга.

        Честно отдаём один `yield` вместо имитации потока. Интерфейс увидит
        отсутствие промежуточных событий и покажет ожидание, а не ложную
        побуквенную анимацию.
        """
        import torch

        self._load()
        inputs = self._tok(prompt, return_tensors="pt").to(self._model.device)
        with torch.no_grad():
            out = self._model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,           # детерминированно — как на замерах
                pad_token_id=self._tok.pad_token_id or self._tok.eos_token_id,
            )
        # Возвращаем ТОЛЬКО продолжение: промпт модель повторяет на входе, и
        # если его не срезать, разбор увидит строки графа как «расписание».
        gen = out[0][inputs["input_ids"].shape[1]:]
        yield self._tok.decode(gen, skip_special_tokens=True)


def make_backend(adapter: Adapter, device: str | None = None,
                 dtype: str = "auto", prefer: str = "auto") -> Backend:
    """Бэкенд для запуска. По умолчанию — постоянный llama-server.

    Порядок не случайный.

    1. `llama-server` — тот же llama.cpp, но процесс живёт между командами:
       веса читаются один раз за сессию. Замерено на `slotclash`/`lora-eos`:
       14 с против 32 с, первый токен 0.11 с против ~20 с. Ответ совпадает
       до строки — это те же веса и `temperature=0`.
    2. `llama-completion` — процесс на каждый запрос. Остаётся запасным: он
       не требует сокета и проверен дольше.
    3. `transformers` — эталонный путь, им гонялись замеры на Kaggle, и на
       машине с GPU он предпочтительнее. База в bfloat16 занимает 6.2 ГБ
       против 2.1 ГБ у 4-битного GGUF, поэтому на CPU он последний.
    """
    if prefer in ("auto", "llama-server"):
        ok, problems = llama_server_ready(adapter)
        if ok:
            return LlamaServerBackend(adapter)
        if prefer == "llama-server":
            raise RuntimeError("путь llama-server не готов:\n  "
                               + "\n  ".join(problems))

    if prefer in ("auto", "llama.cpp"):
        ok, problems = llama_cpp_ready(adapter)
        if ok:
            return LlamaCppBackend(adapter)
        if prefer == "llama.cpp":
            raise RuntimeError("путь llama.cpp не готов:\n  " + "\n  ".join(problems))

    miss = missing_deps()
    if miss:
        raise RuntimeError(
            "для локального запуска не хватает пакетов: " + ", ".join(miss)
            + ".\nПоставить:  .venv/bin/pip install " + " ".join(miss)
            + "\nБез них инструмент работает как раньше — просто без /learned.")
    device = device or os.environ.get("NEX_LEARNED_DEVICE", "auto")
    return TransformersBackend(adapter, dtype=dtype, device=device)


# Один процесс llama-completion за раз, на весь инструмент. Найдено по факту:
# два процесса по 3.6 ГБ одновременно, 1 ГБ свободной памяти, секунды до OOM.
#
# ИСХОДНАЯ ПРИЧИНА УСТРАНЕНА, блокировка осталась подстраховкой. Раньше отмена
# до подпроцесса не доходила: Textual снимал свой воркер, а блокирующий вызов
# внутри про это не знал и считал дальше — отсюда и второй процесс рядом с
# первым. Теперь генерация — генератор, и `close()` доводит `finally` с
# `proc.kill()`. Замерено: процессов llama-completion 0 → 1 → 0, где 0 —
# через четыре секунды после прерывания.
#
# Почему блокировку всё-таки не убрали: она стережёт случай, до которого
# отмена не дотягивается по определению — два ОДНОВРЕМЕННЫХ запуска (`/learned`
# и `/learned --bench` из разных мест). Там отменять нечего, там надо не дать
# запуститься второму.
_GENERATE_LOCK = threading.Lock()


class LlamaCppBackend(Backend):
    """Локальный запуск через llama.cpp — 4-битная база, CPU, без GPU.

    Почему именно этот путь, а не transformers
    ------------------------------------------
    Адаптер обучался на Kaggle поверх 4-битной базы (`load_in_4bit=True` в
    training/train_qlora.py), то есть точная база ему и не нужна была никогда.
    Здесь та же идея, но квантование llama.cpp: база занимает 2.1 ГБ вместо
    6.2 ГБ в bfloat16 — разница между «влезает на ноутбук» и «уходит в своп».

    Запускается внешний бинарник, а не питоновская обёртка: у llama-cpp-python
    нет готовых колёс, он собирается из исходников, а компилятора на машине
    может не быть. Готовый бинарник ggml-org работает как есть.
    """

    name = "llama.cpp"
    slow_start = True

    def __init__(self, adapter: Adapter, threads: int = 0):
        self.adapter = adapter
        self.threads = threads or default_threads()
        self.binary = find_llama_binary()
        self.base_gguf = find_gguf_base()
        self.lora_gguf = gguf_adapter_for(adapter)

    def generate_events(self, prompt: str, max_new_tokens: int):
        """Куски ответа по мере генерации.

        Блокировка берётся ДО первого `yield` (см. правило в
        `vliw/core/api.py::stream`): иначе отмена ровно на первом событии
        прошла бы мимо `finally`, и блокировка осталась бы взятой навсегда —
        модель больше не запустилась бы до перезапуска инструмента.
        """
        if not _GENERATE_LOCK.acquire(blocking=False):
            raise RuntimeError(
                "модель уже считает предыдущий запрос — дождитесь его "
                "завершения, повторный запуск запустил бы второй процесс "
                "рядом с первым и вдвое больше памяти")
        try:
            yield from self._generate_events_locked(prompt, max_new_tokens)
        finally:
            _GENERATE_LOCK.release()

    def _generate_events_locked(self, prompt: str, max_new_tokens: int):
        import subprocess
        import tempfile

        # Промпт передаём файлом, а не -p: в нём переводы строк и кириллица,
        # и через аргументы командной строки это ломается на ровном месте.
        with tempfile.NamedTemporaryFile("w", suffix=".txt", encoding="utf-8",
                                         delete=False) as f:
            f.write(prompt)
            prompt_file = f.name

        # -c ограничивает контекст, а с ним и KV-cache. Без этого флага
        # llama.cpp резервирует под контекст столько, сколько заявляет модель
        # (у Qwen2.5 это 32768) — 1.1 ГБ памяти впустую при промпте в
        # ~200 токенов и ответе до max_new_tokens. Разница измерена:
        # 4.66 ГБ пиковой RSS с дефолтным контекстом против 3.55 ГБ с -c 2048.
        # Обнаружено по факту: OOM-killer убил подпроцесс внутри полноэкранного
        # режима, где памяти и так меньше запаса (кэш расписаний, отрисовка).
        ctx = max(1024, (max_new_tokens + 400) * 2)
        cmd = [
            str(self.binary),
            "-m", str(self.base_gguf),
            "-f", prompt_file,
            "-n", str(max_new_tokens),
            "-c", str(ctx),
            "--temp", "0",              # детерминированно — как на замерах
            "-t", str(self.threads),
            "-no-cnv",                  # БЕЗ chat-шаблона: обучение шло на сыром промпте
            "--no-warmup",
        ]
        if self.lora_gguf is not None:
            cmd += ["--lora", str(self.lora_gguf)]

        env = _llama_env(self.binary)

        # Popen, а не subprocess.run: run() отдаёт вывод только целиком и в
        # конце, а генерация идёт ~30 секунд. Читаем посимвольно и отдаём
        # наружу по мере поступления — чтобы было видно, как модель пишет
        # расписание, а не тишина на полминуты.
        timeout_s = max(120, max_new_tokens * 3)
        deadline = time.monotonic() + timeout_s
        tail = prompt[-40:]          # по нему отличаем эхо промпта от ответа
        buf: list[str] = []
        answer: list[str] = []
        echo_done = False
        proc = None
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, env=env, bufsize=1)
            while True:
                if time.monotonic() > deadline:
                    proc.kill()
                    raise TimeoutError(
                        f"модель не уложилась в {timeout_s} с — вероятно, "
                        "процессор занят другим процессом модели")
                chunk = proc.stdout.read(1)
                if not chunk:
                    break
                buf.append(chunk)
                if echo_done:
                    answer.append(chunk)
                    yield chunk
                    continue
                # llama.cpp сперва повторяет промпт, и только потом пишет своё.
                # Пока не увидели хвост промпта — всё это эхо, наружу не отдаём.
                if "".join(buf[-len(tail):]) == tail:
                    echo_done = True
            proc.wait(timeout=10)
        finally:
            if proc is not None and proc.poll() is None:
                proc.kill()
            try:
                os.unlink(prompt_file)
            except OSError:
                pass

        if echo_done:
            return

        # Потоковый детектор эха не сработал: хвост промпта проскочил мимо
        # него (например, llama.cpp переформатировал пробелы). Тогда наружу
        # не ушло НИ ОДНОГО куска — спасаем текст по готовому буферу и отдаём
        # одним событием. Раньше здесь расходились две правды: `generate()`
        # возвращал спасённый текст, а поток `on_text` в этом случае молчал.
        out = "".join(buf)
        if tail in out:
            out = out.split(tail, 1)[1]
        if out:
            yield out


_SERVER = None
"""Один сервер на процесс инструмента. См. `vliw/learned/server.py`."""

def default_threads() -> int:
    """Сколько потоков давать llama.cpp. Половина логических ядер.

    Не `os.cpu_count()`, хотя раньше было именно так. Замерено на этой машине
    (12 логических ядер, `slotclash`, `lora-eos`, тёплый кэш промпта):

        -t  4     14.2 с
        -t  6     12.5 с
        -t  8     12.8 с
        -t 12     20.0 с      ← столько брал прежний код

    Все логические ядра — худший вариант из проверенных, и с заметным
    отрывом: гипертрединг не даёт вторых АЛУ, а потоки начинают драться за
    кэш и память. Половина логических ядер попадает примерно в число
    физических, и это же значение остаётся разумным на машине без
    гипертрединга. Предел в 8 — чтобы на 32-ядерном сервере не заводить
    шестнадцать потоков под задачу, которая от них уже не ускоряется.
    """
    return max(2, min(8, (os.cpu_count() or 4) // 2))


SERVER_CTX = 4096
"""Окно контекста сервера: хватает и планировщику, и разговору агента."""

SERVER_MAX_TOKENS = 768
"""Под какой длиной ответа рассчитан контекст сервера.

Своя константа, а не импорт `LearnedScheduler.DEFAULT_MAX_NEW_TOKENS`:
`scheduler` уже импортирует `runtime`, и обратный импорт замкнул бы круг.
Значение одно и то же и по одной причине — самый длинный эталон в данных
(граф на 24 инструкции) укладывается примерно в 400 токенов, здесь запас.
"""


class LlamaServerBackend(Backend):
    """Постоянный llama-server: веса живут между командами.

    Отличий от `LlamaCppBackend` два, и оба на стороне процесса, а не модели:
    веса читаются один раз за сессию, а смена адаптера — HTTP-запрос вместо
    перезапуска. Ответ тот же самый: та же сборка llama.cpp, те же веса,
    `temperature=0`. Проверено на `slotclash`/`lora-eos` — совпадение до
    строки, при 14 с против 32 с.
    """

    name = "llama-server"
    slow_start = True

    def __init__(self, adapter: Adapter, threads: int = 0):
        self.adapter = adapter
        self.threads = threads or default_threads()
        self.binary = find_llama_server()
        self.base_gguf = find_gguf_base()

    def generate_events(self, prompt: str, max_new_tokens: int):
        # Адаптер передаём в complete(), а не выбираем заранее: он держит
        # режим сервера занятым на всю генерацию, чтобы разговор с базовой
        # моделью не переключил LoRA у нас под руками.
        yield from shared_server().complete(prompt, max_new_tokens,
                                            adapter=self.adapter.name)


def shared_server():
    """Один llama-server на процесс инструмента: и планировщику, и агенту.

    Второй процесс завести нельзя: база в 4 битах занимает 3.5 ГБ, а на
    машине с 8 ГБ два таких уже не помещаются. Поэтому режимы делят один
    процесс и переключаются шкалами LoRA — планировщику адаптер, разговору
    голая база (см. `LlamaServer.using`).
    """
    global _SERVER

    from . import server as _srv

    if _SERVER is None:
        binary, base = find_llama_server(), find_gguf_base()
        if binary is None or base is None:
            raise _srv.ServerError("llama-server или база GGUF не найдены в vendor/")
        # Пустой список адаптеров — не ошибка: разговор идёт на голой базе,
        # и агенту обученные веса не нужны вовсе. Наличие адаптера для
        # ПЛАНИРОВЩИКА проверяет `llama_server_ready()`, до этого места.
        adapters = [(a.name, gguf_adapter_for(a)) for a in find_adapters()]
        adapters = [(n, p) for n, p in adapters if p is not None]
        # Контекст фиксируется при старте, поэтому его хватать должно ОБОИМ
        # режимам, а не только планировщику. Замерено: системный промпт
        # агента — 1451 токен (факты об участке, матрица портов, находки
        # доктора), плюс история диалога, плюс ответ. Прежние 2336 были
        # посчитаны по планировщику, у которого промпт короткий, — и агент
        # упирался в потолок, отвечая обрывком или пустотой.
        #
        # Не 32768, которые заявляет модель: столько llama.cpp зарезервировал
        # бы под KV-кэш и съел лишний гигабайт (см. LlamaCppBackend).
        ctx = SERVER_CTX
        _SERVER = _srv.LlamaServer(binary=binary, base_gguf=base,
                                   adapters=adapters, threads=default_threads(),
                                   ctx=ctx, env=_llama_env(binary))
    _SERVER.ensure()
    return _SERVER


def llama_server_ready(adapter: Adapter) -> tuple[bool, list[str]]:
    """Готов ли путь llama-server: бинарник, база, сконвертированный адаптер."""
    problems = []
    if find_llama_server() is None:
        problems.append("нет бинарника llama-server в vendor/")
    if find_gguf_base() is None:
        problems.append("нет квантованной базы (*.gguf) в vendor/models/")
    if gguf_adapter_for(adapter) is None:
        problems.append(f"адаптер {adapter.name} не сконвертирован в GGUF")
    return not problems, problems


def _llama_env(binary: Path) -> dict[str, str]:
    """Окружение для запуска llama.cpp.

    libgomp лежит внутри torch — своей в системе может не быть, а ставить её
    через apt нельзя без root. Берём оттуда, раз уж torch установлен.
    """
    env = dict(os.environ)
    libs = [str(binary.parent)]
    torch_lib = _torch_lib_dir()
    if torch_lib:
        libs.append(str(torch_lib))
    env["LD_LIBRARY_PATH"] = ":".join(libs + [env.get("LD_LIBRARY_PATH", "")])
    return env


def _torch_lib_dir():
    """Папка с библиотеками torch — там же лежит libgomp.so.1."""
    try:
        import importlib.util

        spec = importlib.util.find_spec("torch")
        if spec and spec.origin:
            d = Path(spec.origin).parent / "lib"
            if d.exists():
                return d
    except Exception:
        pass
    return None


def find_llama_server() -> Path | None:
    """Бинарник llama-server в vendor/. Постоянный процесс, см. server.py."""
    for p in sorted(VENDOR.glob("llama-*/llama-server")):
        if os.access(p, os.X_OK):
            return p
    return None


def find_llama_binary() -> Path | None:
    """Бинарник llama-completion в vendor/. Неинтерактивный, в отличие от llama-cli."""
    for p in sorted(VENDOR.glob("llama-*/llama-completion")):
        if os.access(p, os.X_OK):
            return p
    return None


def find_gguf_base() -> Path | None:
    """Квантованная база в vendor/models. Адаптеры (…-f16.gguf) исключаем."""
    for p in sorted((VENDOR / "models").glob("*.gguf")):
        if not p.name.endswith("-f16.gguf"):
            return p
    return None


def gguf_adapter_for(adapter: Adapter) -> Path | None:
    """Сконвертированный в GGUF адаптер рядом с базой."""
    p = VENDOR / "models" / f"{adapter.name}-f16.gguf"
    return p if p.exists() else None


def llama_cpp_ready(adapter: Adapter) -> tuple[bool, list[str]]:
    """Готов ли путь llama.cpp: бинарник, база, сконвертированный адаптер."""
    problems = []
    if find_llama_binary() is None:
        problems.append("нет бинарника llama-completion в vendor/")
    if find_gguf_base() is None:
        problems.append("нет квантованной базы (*.gguf) в vendor/models/")
    if gguf_adapter_for(adapter) is None:
        problems.append(f"адаптер {adapter.name} не сконвертирован в GGUF")
    return not problems, problems
