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
                lines.append(f"llama.cpp: готов  (адаптер {best.name})")
                b = find_gguf_base()
                lines.append(f"  база {b.name}, {b.stat().st_size / 1e9:.1f} ГБ, 4 бита")
                lines.append("  это основной путь: 4 бита против 6.2 ГБ у transformers")
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
    """Что угодно, что умеет продолжить текст. Один метод — намеренно."""

    name = "?"

    def generate(self, prompt: str, max_new_tokens: int) -> str:
        raise NotImplementedError


class ScriptedBackend(Backend):
    """Заранее заданные ответы. Для тестов и разбора уже снятых прогонов.

    Позволяет прогнать весь путь «граф → промпт → ответ → расписание →
    проверка» без torch и без весов — то есть проверять склейку, а не модель.
    """

    name = "scripted"

    def __init__(self, replies: list[str] | str):
        self._replies = [replies] if isinstance(replies, str) else list(replies)
        self._i = 0

    def generate(self, prompt: str, max_new_tokens: int) -> str:
        if not self._replies:
            return ""
        r = self._replies[min(self._i, len(self._replies) - 1)]
        self._i += 1
        return r


class TransformersBackend(Backend):
    """Локальный запуск через transformers + peft — как на Kaggle, но в CLI.

    Модель поднимается ОДИН раз на объект: загрузка 3B весов занимает
    десятки секунд, и делать её на каждый граф бессмысленно.
    """

    name = "transformers"

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

    def generate(self, prompt: str, max_new_tokens: int) -> str:
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
        return self._tok.decode(gen, skip_special_tokens=True)


def make_backend(adapter: Adapter, device: str | None = None,
                 dtype: str = "auto", prefer: str = "auto") -> Backend:
    """Бэкенд для запуска. По умолчанию — llama.cpp, если он готов.

    Порядок не случайный: llama.cpp держит базу в 4 битах (2.1 ГБ против
    6.2 ГБ у transformers в bfloat16) и на CPU считает быстрее. transformers
    остаётся как эталонный путь — им гонялись замеры на Kaggle, и на машине
    с GPU он предпочтительнее.
    """
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


# Один процесс llama-completion за раз, на весь инструмент. Без этого
# повторный /learned (или /learned --bench, пока первый ещё считает) уходит в
# ВТОРОЙ параллельный subprocess: Textual отменяет СТАРЫЙ воркер только на
# своём уровне, а subprocess.run() внутри него — блокирующий вызов, он эту
# отмену не видит и продолжает работать. Найдено по факту: два процесса по
# 3.6 ГБ каждый одновременно, 1 ГБ свободной памяти, секунды до OOM.
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

    def __init__(self, adapter: Adapter, threads: int = 0):
        self.adapter = adapter
        self.threads = threads or (os.cpu_count() or 4)
        self.binary = find_llama_binary()
        self.base_gguf = find_gguf_base()
        self.lora_gguf = gguf_adapter_for(adapter)

    def generate(self, prompt: str, max_new_tokens: int) -> str:
        import subprocess
        import tempfile

        if not _GENERATE_LOCK.acquire(blocking=False):
            raise RuntimeError(
                "модель уже считает предыдущий запрос — дождитесь его "
                "завершения, повторный запуск запустил бы второй процесс "
                "рядом с первым и вдвое больше памяти")
        try:
            return self._generate_locked(prompt, max_new_tokens)
        finally:
            _GENERATE_LOCK.release()

    def _generate_locked(self, prompt: str, max_new_tokens: int) -> str:
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

        env = dict(os.environ)
        # libgomp лежит внутри torch — своей в системе может не быть, а ставить
        # её через apt нельзя без root. Берём оттуда, раз уж torch установлен.
        libs = [str(self.binary.parent)]
        torch_lib = _torch_lib_dir()
        if torch_lib:
            libs.append(str(torch_lib))
        env["LD_LIBRARY_PATH"] = ":".join(libs + [env.get("LD_LIBRARY_PATH", "")])

        try:
            r = subprocess.run(cmd, capture_output=True, text=True, env=env,
                               timeout=max(120, max_new_tokens * 3))
        finally:
            try:
                os.unlink(prompt_file)
            except OSError:
                pass

        out = r.stdout
        # llama.cpp повторяет промпт на выходе перед продолжением. Срезаем его
        # по хвосту промпта, иначе разбор примет строки графа за расписание.
        tail = prompt[-40:]
        if tail in out:
            out = out.split(tail, 1)[1]
        return out.split("[end of text]")[0]


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
