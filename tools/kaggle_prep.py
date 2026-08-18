"""Подготовка всего, что нужно залить в Kaggle, — без ключа и без сети.

Собирает в `build/kaggle/` один датасет (данные + адаптер + два скрипта) и два
ядра-скрипта: шаг 0 (baseline, только инференс) и прогон 1 (изолированный EOS).
После этого залив сводится к одной команде `tools/kaggle_push.sh`.

Почему всё в ОДИН датасет, а не в три
-------------------------------------
Адаптер `qwen-vliw-lora` нигде не опубликован — он лежит только на диске
(120 МБ safetensors). Значит грузить его всё равно придётся. А раз так, то и
данные, и `validate_kaggle.py` с `train_qlora.py` кладутся туда же: у ядра
получается один `dataset_sources`, и в путях `/kaggle/input/...` нечего
перепутать.

Прогон 2 (с нуля на train_merged) намеренно НЕ готовится: он дорогой по квоте
и запускается отдельным решением. См. docs/RUNBOOK_EOS.md.

    python tools/kaggle_prep.py

ВНИМАНИЕ: эта команда сама по себе НЕ заливает ничего на Kaggle и не знает
твоего логина — id в dataset-metadata.json / kernel-metadata.json остаются
заглушкой `"USERNAME/..."`. Реальный логин подставляет и заливает
`tools/kaggle_push.sh` (он же вызывает этот скрипт сам, первым шагом). Раньше
здесь было сказано «подставлять руками не надо» без уточнения, что это верно
только при запуске через kaggle_push.sh — прямой `kaggle datasets create -p
build/kaggle/dataset` после голого `python tools/kaggle_prep.py` упал бы на
несуществующем пользователе "USERNAME".
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build" / "kaggle"
DATA = BUILD / "dataset"

# Что уезжает в датасет: (источник, имя внутри датасета)
PAYLOAD = [
    ("train_merged.jsonl", "train_merged.jsonl"),
    ("dataset.jsonl", "dataset.jsonl"),
    ("training/checkpoints/eval.jsonl", "eval.jsonl"),
    ("eval_wide.jsonl", "eval_wide.jsonl"),
    ("training/validate_kaggle.py", "validate_kaggle.py"),
    ("training/train_qlora.py", "train_qlora.py"),
]
ADAPTER_SRC = "training/checkpoints/qwen-vliw-lora"
ADAPTER_DST = "qwen-vliw-lora"

DATASET_SLUG = "vliw-eos-run"

# Файлы адаптера, нужные для инференса и продолжения обучения. Чекпоинты
# промежуточных шагов (checkpoint-1200/1250) не берём: это ещё ~240 МБ, а
# нужен только сам адаптер.
ADAPTER_FILES = ("adapter_config.json", "adapter_model.safetensors",
                 "tokenizer.json", "tokenizer_config.json",
                 "chat_template.jinja")

# Общий пролог для обоих ядер: находит датасет в /kaggle/input с ретраями.
# Понадобился не для перестраховки — два реальных прогона подряд упали именно
# здесь, по двум РАЗНЫМ причинам:
#   v1: `kaggle datasets status` отчитался "ready", а контейнер ядра, запущенный
#       сразу за этим, стартовал с пустым /kaggle/input — маунт ещё не успел
#       прикрепиться. Лечится ретраями с паузой.
#   v2: с ретраями дождались непустого /kaggle/input, но `glob("*/marker")`
#       (один уровень) всё равно не находил ничего. Диагностика показала
#       почему: верхний уровень — не сам датасет, а папка `datasets`. Kaggle
#       сменил структуру монтирования, `/kaggle/input/<slug>/...` (плоско)
#       больше не гарантия. Лечится рекурсивным glob вместо одноуровневого.
# Если структура сменится в третий раз — упадёт с полным деревом на 3 уровня
# в сообщении, а не с "не нашёл и всё".
FIND_DATASET = '''\
def _find_dataset(marker_file, tries=6, pause=10):
    import glob, os, time
    for i in range(tries):
        hits = glob.glob(f"/kaggle/input/**/{marker_file}", recursive=True)
        if hits:
            return os.path.dirname(hits[0])
        if i < tries - 1:
            print(f"  датасет ещё не примонтирован (попытка {i+1}/{tries}), "
                  f"жду {pause}с...", flush=True)
            time.sleep(pause)
    tree = []
    for root, dirs, files in os.walk("/kaggle/input"):
        depth = root.count(os.sep) - "/kaggle/input".count(os.sep)
        tree.append(root + (" [" + ", ".join(files) + "]" if files else ""))
        if depth >= 4:   # печатаем и этот уровень, вглубь просто не идём дальше
            dirs[:] = []
    raise AssertionError(
        f"датасет не подключён: {marker_file!r} не найден в /kaggle/input "
        f"(рекурсивно, {tries} попыток). Дерево:\\n  " + "\\n  ".join(tree))
'''

# Самопроверка GPU: ловит несовместимость железа/сборки torch ДО того, как
# потрачены минуты на pip install и скачивание базовой модели (~6 ГБ).
# `machine_shape: NvidiaTeslaT4` в kernel-metadata.json чинит СИМПТОМ уже
# случившегося инцидента (Kaggle выдал P100/sm_60, стандартный образ ставит
# torch без ядер под эту архитектуру — крах был на PeftModel.from_pretrained,
# через много минут после старта). Пин не проверяет, что Kaggle реально
# выдал совместимую карту, и не ловит следующую несовместимость той же
# природы (например, если Kaggle обновит сборку torch в самом T4-образе).
# Эта проверка — не про конкретную карту, а про реальную CUDA-операцию:
# ловит именно то падение, что уже было, и любое похожее, дёшево и рано.
CHECK_GPU = '''\
def _check_gpu():
    import torch
    if not torch.cuda.is_available():
        raise SystemExit("нет GPU: torch.cuda.is_available() == False")
    name = torch.cuda.get_device_name(0)
    cap = torch.cuda.get_device_capability(0)
    print(f"GPU: {name}, compute capability {cap[0]}.{cap[1]}", flush=True)
    try:
        (torch.zeros(8, 8, device="cuda") @ torch.zeros(8, 8, device="cuda")).sum().item()
    except RuntimeError as e:
        raise SystemExit(
            f"GPU {name} (capability {cap[0]}.{cap[1]}) не подходит для этой "
            f"сборки torch: {e}\\n"
            f"Так падал P100 (sm_60) под стандартным образом Kaggle — "
            f"kernel-metadata.json просит NvidiaTeslaT4, но если Kaggle всё "
            f"равно выдал несовместимую карту, лучше узнать это сейчас, за "
            f"секунды, а не после pip install и скачивания базовой модели."
        ) from e
    print("GPU: базовая CUDA-операция прошла — совместимость подтверждена", flush=True)
'''

STEP0 = '''\
"""Шаг 0: baseline текущего адаптера. Обучения нет, только инференс.

Смысл шага — снять точку отсчёта ТЕМ ЖЕ классификатором, которым будут
меряться следующие прогоны. Прошлая цифра «36% валидно» снята дампом от
15.08 22:40, а validate_kaggle.py переписан в 22:51: прежняя версия не
отделяла «хвост» (законный префикс, модель не остановилась) от
«галлюцинации» (дыры в настоящих id) и записала 24 законных префикса в брак.
Сравнение свежего замера с той цифрой дало бы прирост, наполовину состоящий
из смены ярлыков.
"""
import subprocess, sys, os

''' + FIND_DATASET + CHECK_GPU + '''
BASE = _find_dataset("validate_kaggle.py")
print("датасет:", BASE, flush=True)
_check_gpu()

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-U",
                "transformers", "peft", "bitsandbytes", "accelerate"], check=True)

for data, dump in (("eval.jsonl", "base_eval.jsonl"),
                   ("eval_wide.jsonl", "base_eval_wide.jsonl")):
    print("\\n" + "=" * 70, flush=True)
    print("ЗАМЕР:", data, flush=True)
    print("=" * 70, flush=True)
    subprocess.run([sys.executable, f"{BASE}/validate_kaggle.py",
                    "--model", f"{BASE}/qwen-vliw-lora",
                    "--dump", f"/kaggle/working/{dump}",
                    f"{BASE}/{data}"], check=True)
'''

RUN1 = '''\
"""Прогон 1: изолированный EOS. Данные ТЕ ЖЕ, меняется одна переменная.

Продолжаем существующий адаптер на старом dataset.jsonl одну эпоху. Отличие
от прошлого обучения ровно одно — к каждому примеру приклеен EOS и он попадает
в loss. Если «хвост» после этого схлопнется, диагноз подтверждён: 36% были не
нехваткой данных, а тем, что модель ни разу не видела, как заканчивать ответ.

Стоп-условие встроено: если самопроверка EOS не прошла, обучение не
запускается и ядро падает, не сжигая квоту.
"""
import subprocess, sys, os

''' + FIND_DATASET + CHECK_GPU + '''
BASE = _find_dataset("train_qlora.py")
OUT = "/kaggle/working/lora-eos"
_check_gpu()

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-U",
                "transformers", "peft", "bitsandbytes", "accelerate", "datasets"],
               check=True)

# --- обучение с живой проверкой EOS в логе ------------------------------
proc = subprocess.Popen(
    [sys.executable, "-u", f"{BASE}/train_qlora.py",
     "--base", "Qwen/Qwen2.5-3B-Instruct",
     "--adapter", f"{BASE}/qwen-vliw-lora",
     "--data", f"{BASE}/dataset.jsonl",
     "--out", OUT, "--epochs", "1"],
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

eos_ok = None
for line in proc.stdout:
    print(line, end="", flush=True)
    # Матчим на однозначный маркер train_qlora.py::check_eos(), а не на
    # совпадение подстрок "ВНИМАНИЕ"+"EOS" — та пара могла совпасть с
    # ЛЮБОЙ чужой строкой лога (например, из transformers/peft), убив
    # здоровое обучение ложным срабатыванием.
    if "EOS_SELFCHECK: OK" in line:
        eos_ok = True
    elif "EOS_SELFCHECK: FAIL" in line:
        eos_ok = False
        print("\\n!! Самопроверка EOS не прошла — глушу обучение, квоту не жжём.",
              flush=True)
        proc.kill()
        break
proc.wait()

if eos_ok is False:
    raise SystemExit("EOS не доходит до loss — см. лог выше")
if eos_ok is None:
    raise SystemExit("самопроверка EOS не напечаталась: не та версия train_qlora.py?")
if proc.returncode != 0:
    raise SystemExit(f"обучение упало: код {proc.returncode}")

# --- замеры по обоим эвалам ---------------------------------------------
for data, dump in (("eval.jsonl", "eos_eval.jsonl"),
                   ("eval_wide.jsonl", "eos_eval_wide.jsonl")):
    print("\\n" + "=" * 70, flush=True)
    print("ЗАМЕР:", data, flush=True)
    print("=" * 70, flush=True)
    subprocess.run([sys.executable, f"{BASE}/validate_kaggle.py",
                    "--model", OUT, "--dump", f"/kaggle/working/{dump}",
                    f"{BASE}/{data}"], check=True)
'''

# Заголовок ядра ОБЯЗАН слагифицироваться ровно в тот же slug, что и id, иначе
# Kaggle молча создаёт ядро по адресу, вычисленному из заголовка, а не по
# заданному id — ровно так и вышло на первом заливе: заголовок был кириллицей
# ("Шаг 0: baseline адаптера без обучения"), Kaggle срезал всё нелатинское и
# получил slug `0-baseline` вместо `vliw-step0-baseline`. CLI об этом
# предупреждает («title does not resolve to id»), но не отказывается —
# создаёт по-своему. Поэтому заголовок здесь = слова из slug через пробел,
# без пунктуации: человекочитаемое описание — в докстринге самого скрипта
# ядра и в RUNBOOK_EOS.md, а не в title.
KERNELS = [
    ("vliw-step0-baseline", "step0.py", STEP0, "vliw step0 baseline"),
    ("vliw-run1-eos", "run1_eos.py", RUN1, "vliw run1 eos"),
]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true",
                    help="пересобрать build/kaggle с нуля")
    args = ap.parse_args()

    if args.force and BUILD.exists():
        shutil.rmtree(BUILD)
    DATA.mkdir(parents=True, exist_ok=True)

    missing = [src for src, _ in PAYLOAD if not (ROOT / src).exists()]
    missing += [f"{ADAPTER_SRC}/{name}" for name in ADAPTER_FILES
               if not (ROOT / ADAPTER_SRC / name).exists()]
    if missing:
        raise SystemExit("нет файлов: " + ", ".join(missing))

    # Копируем БЕЗУСЛОВНО, не по mtime. Раньше было "копировать, только если
    # source новее" — но strict-greater по mtime на WSL/смонтированных дисках
    # (грубая гранулярность, git checkout, переизвлечение из архива) может не
    # продвинуться после перетренировки, и тогда на Kaggle тихо уезжает
    # СТАРЫЙ адаптер без единой ошибки — а обнаруживается это только после
    # целого дорогого GPU-прогона на не тех весах. Payload здесь весь целиком
    # меньше 200 МБ, лишняя копия — секунды; это дешевле, чем ещё раз
    # разбираться, почему прогон 2 продолжил не тот адаптер.
    total = 0
    for src, dst in PAYLOAD:
        s, d = ROOT / src, DATA / dst
        shutil.copy2(s, d)
        total += d.stat().st_size

    adir = DATA / ADAPTER_DST
    adir.mkdir(exist_ok=True)
    for name in ADAPTER_FILES:
        s, d = ROOT / ADAPTER_SRC / name, adir / name
        shutil.copy2(s, d)
        total += d.stat().st_size

    # Слаг дописывается при заливке: username берётся из kaggle.json, чтобы
    # здесь не было заглушки, которую легко забыть заменить.
    (DATA / "dataset-metadata.json").write_text(json.dumps({
        "title": "VLIW e2k scheduler — data, adapter, scripts",
        "id": f"USERNAME/{DATASET_SLUG}",
        "licenses": [{"name": "CC0-1.0"}],
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    for slug, code_file, code, title in KERNELS:
        kdir = BUILD / slug
        kdir.mkdir(parents=True, exist_ok=True)
        (kdir / code_file).write_text(code, encoding="utf-8")
        (kdir / "kernel-metadata.json").write_text(json.dumps({
            "id": f"USERNAME/{slug}",
            "title": title,
            "code_file": code_file,
            "language": "python",
            "kernel_type": "script",
            "is_private": True,
            "enable_gpu": True,
            # Явно T4, а не «любой enable_gpu=True». Без этого Kaggle иногда
            # выдаёт P100 (Pascal, sm_60) — стандартный образ ставит torch без
            # ядер под sm_60, PeftModel.from_pretrained падает с
            # `CUDA error: no kernel image is available for execution on the
            # device`. Это не гипотеза: ровно так упал первый реальный прогон
            # шага 0. Собственная документация Kaggle (kernels_metadata.md)
            # прямо предупреждает: NvidiaTeslaP100 несовместима со стандартным
            # образом, рекомендация — NvidiaTeslaT4.
            "machine_shape": "NvidiaTeslaT4",
            "enable_internet": True,
            "dataset_sources": [f"USERNAME/{DATASET_SLUG}"],
            "competition_sources": [],
            "kernel_sources": [],
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"собрано в {BUILD.relative_to(ROOT)}")
    print(f"  датасет: {len(PAYLOAD)} файлов + адаптер, {total / 2**20:.0f} МБ")
    for slug, code_file, _, _ in KERNELS:
        print(f"  ядро:    {slug}/{code_file}")
    print("\nдальше: tools/kaggle_push.sh (подставит username и зальёт)")


if __name__ == "__main__":
    main()
