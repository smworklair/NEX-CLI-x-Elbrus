"""Подготовка всего, что нужно залить в Kaggle, — без ключа и без сети.

Собирает в `build/kaggle/` один датасет (данные + адаптер + два скрипта) и три
ядра-скрипта: шаг 0 (baseline, только инференс), прогон 1 (изолированный EOS)
и прогон 2 (полное обучение с нуля на слитых данных). После этого залив
сводится к одной команде `tools/kaggle_push.sh`.

Почему всё в ОДИН датасет, а не в три
-------------------------------------
Адаптер `qwen-vliw-lora` нигде не опубликован — он лежит только на диске
(120 МБ safetensors). Значит грузить его всё равно придётся. А раз так, то и
данные, и `validate_kaggle.py` с `train_qlora.py` кладутся туда же: у ядра
получается один `dataset_sources`, и в путях `/kaggle/input/...` нечего
перепутать.

Прогон 2 здесь ГОТОВИТСЯ, но заливается только явным `kaggle_push.sh run2` —
в режимы step0/run1/all он не входит: дорогой по квоте (≈2 эпохи по 39 700
примеров), решение о запуске принимается отдельно. См. docs/RUNBOOK_EOS.md.

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

# Адаптер прогона 1 — тот, что дал 97.7%/32.7%. Едет в датасет вторым, чтобы
# сравнивать режимы генерации на ОБОИХ адаптерах в одном ядре: иначе адаптер
# прогона 1 доступен только как вывод ядра vliw-run1-eos, и сравнение
# оказывается «между ядрами», где легко перепутать причину и следствие.
EOS_ADAPTER_SRC = "training/checkpoints/lora-eos"
EOS_ADAPTER_DST = "lora-eos"

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

RUN2 = '''\
"""Прогон 2: полное обучение с нуля на слитых данных (train_merged).

Отличия от прогона 1 — ДВЕ, и обе осознанные (docs/RUNBOOK_EOS.md, шаг 2):
  * без --adapter: в старом адаптере запечена привычка не останавливаться,
    переучиваться ей дороже, чем учиться с чистого листа;
  * train_merged.jsonl вместо dataset.jsonl: вдвое больше примеров, включая
    размеры графов, которых модель раньше не видела (eval_wide 16..24).
Прогон 1 уже доказал ценность EOS (26.7% -> 97.7%); здесь EOS есть по
умолчанию, поэтому стоп-условие на самопроверку оставлено как страховка.

Память: слитые данные длиннее старых (графы до 24 операций), и первый запуск
упал CUDA OOM на шаге 303 при batch 4. Теперь batch 2 × accum 8 — тот же
эффективный батч 16 и те же ~4964 шагов, вдвое меньше пиковой активации,
плюс expandable_segments против фрагментации за часы обучения.

≈4960 шагов; чекпоинты каждые 100 шагов — сессия Kaggle уже обрывалась
на 93% эпохи.
"""
import os, subprocess, sys

''' + FIND_DATASET + CHECK_GPU + '''
BASE = _find_dataset("train_qlora.py")
OUT = "/kaggle/working/lora-merged"
_check_gpu()

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-U",
                "transformers", "peft", "bitsandbytes", "accelerate", "datasets"],
               check=True)

# --- обучение с живой проверкой EOS в логе ------------------------------
# expandable_segments: совет самого сообщения об OOM — аллокатор перестаёт
# терять гигабайты в дыры от фрагментации на многочасовом прогоне.
env = dict(os.environ,
           PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True")
proc = subprocess.Popen(
    [sys.executable, "-u", f"{BASE}/train_qlora.py",
     "--base", "Qwen/Qwen2.5-3B-Instruct",
     "--data", f"{BASE}/train_merged.jsonl",
     "--out", OUT, "--epochs", "2",
     "--batch-size", "2", "--accum", "8"],
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
    env=env)

eos_ok = None
for line in proc.stdout:
    print(line, end="", flush=True)
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
if proc.returncode != 0:
    raise SystemExit(f"обучение упало: код {proc.returncode}")
if eos_ok is None:
    # Маркера нет, а обучение ЗАВЕРШИЛОСЬ успешно. Раньше это был SystemExit —
    # и однажды так погиб бы целый прогон из-за одной строчки, потерянной по
    # дороге от процесса в лог Kaggle (случилось с его соседкой через строку:
    # «EOS попадает в loss» дошла, «EOS_SELFCHECK: OK» сразу за ней — нет).
    # Глушить обучение имеет смысл только при ЯВНОМ FAIL: он ловится выше,
    # в потоке, пока процесс ещё жив. Здесь же всё уже посчитано — честно
    # предупредить и продолжить замеры.
    print("\\n!! маркер EOS_SELFCHECK не увиден при успешном обучении — "
          "потерялся в пайпе лога; проверьте строки самопроверки выше "
          "вручную", flush=True)

# --- замеры по обоим эвалам ---------------------------------------------
for data, dump in (("eval.jsonl", "merged_eval.jsonl"),
                   ("eval_wide.jsonl", "merged_eval_wide.jsonl")):
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
RESUME2 = '''\
"""Доводка прогона 2: продолжить после обрыва и/или доделать замеры.

ЗАЧЕМ ОТДЕЛЬНОЕ ЯДРО. Полное обучение занимает ~8ч45м и почти исчерпывает
окно GPU-сессии Kaggle, а оба замера поверх обучения в ту же сессию уже
не помещаются (прогон 2 дошёл до wide-замера и был убит лимитом на 220/300).
Здесь вывод прошлого ядра подключён источником — датасетом vliw-run2-lora,
потому что kernel_sources от упавшего/отменённого ядра Kaggle не принимает, —
и ядро делает ровно то, что осталось:

  * train_meta.json в его выводе ЕСТЬ — обучение успело завершиться,
    не успели только замеры; тренировку не повторяем;
  * иначе берём СТАРШИЙ checkpoint-N (save_total_limit=2 хранит два)
    и зовём train_qlora.py c --resume: Trainer продолжает с сохранённого
    шага — шаги, планировщик и оптимизатор восстанавливаются из
    trainer_state.json, а не с нуля.

Параметры (--batch-size 2 --accum 8 --epochs 2) обязаны совпадать с
прошлым запуском: resume разворачивает сохранённое расписание шагов.
"""
import glob, os, shutil, subprocess, sys

''' + FIND_DATASET + CHECK_GPU + '''
BASE = _find_dataset("train_qlora.py")
OUT = "/kaggle/working/lora-merged"
_check_gpu()

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-U",
                "transformers", "peft", "bitsandbytes", "accelerate", "datasets"],
               check=True)

# --- вывод прошлого ядра ---------------------------------------------------
# Структура монтирования у Kaggle уже менялась дважды (см. FIND_DATASET),
# а zip-датасет при распаковке может потерять верхнюю папку архива. Поэтому
# корень вывода ищем по содержимому, ДВУМЯ путями: завершённое обучение
# опознаётся по train_meta.json, оборванное — по checkpoint-N/trainer_state.json
# (в vliw-eos-run лежит лишь старый qwen-vliw-lora без того и другого).
meta_hits = glob.glob("/kaggle/input/**/train_meta.json", recursive=True)
ckpt_hits = glob.glob("/kaggle/input/**/checkpoint-*/trainer_state.json",
                      recursive=True)

def _tree_hint():
    tree = []
    for root, dirs, files in os.walk("/kaggle/input"):
        depth = root.count(os.sep) - "/kaggle/input".count(os.sep)
        tree.append(root + (" [" + ", ".join(files) + "]" if files else ""))
        if depth >= 3:
            dirs[:] = []
    return "\\n  ".join(tree)

if meta_hits:
    parents = sorted({os.path.dirname(p) for p in meta_hits})
    if len(parents) != 1:
        raise SystemExit("найдено несколько завершённых адаптеров:"
                         "\\n  " + "\\n  ".join(parents))
    PREV = parents[0]
elif ckpt_hits:
    roots = sorted({os.path.dirname(os.path.dirname(p)) for p in ckpt_hits})
    if len(roots) != 1:
        raise SystemExit("найдены чекпоинты в нескольких выводах:"
                         "\\n  " + "\\n  ".join(roots))
    PREV = roots[0]
else:
    raise SystemExit("в подключённых источниках нет ни train_meta.json, "
                     "ни checkpoint-*/trainer_state.json. Дерево:\\n  "
                     + _tree_hint())

if os.path.exists(f"{PREV}/train_meta.json"):
    # Обучение ДОШЛО до конца: адаптер сохранён, не успели только замеры.
    print("адаптер из прошлого прогона полный (train_meta.json) — "
          "обучение пропускаю, сразу замеры", flush=True)
    MODEL = PREV          # вход смонтирован read-only — инференсу хватит
else:
    cks = glob.glob(f"{PREV}/checkpoint-*")
    if not cks:
        raise SystemExit("в прошлом прогоне нет ни чекпоинтов, ни "
                         "train_meta.json — продолжать не с чего")
    latest = max(cks, key=lambda p: int(p.rsplit("-", 1)[1]))
    n = os.path.basename(latest).rsplit("-", 1)[1]
    dst = f"{OUT}/checkpoint-{n}"
    print(f"продолжаю с {os.path.basename(latest)}", flush=True)
    # Старый dst сносим целиком: dirs_exist_ok=True смешал бы файлы двух
    # неидентичных попыток, если ядро перезапускали поверх другого обрыва.
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(latest, dst)

    env = dict(os.environ,
               PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True")
    proc = subprocess.Popen(
        [sys.executable, "-u", f"{BASE}/train_qlora.py",
         "--base", "Qwen/Qwen2.5-3B-Instruct",
         "--data", f"{BASE}/train_merged.jsonl",
         "--out", OUT, "--epochs", "2",
         "--batch-size", "2", "--accum", "8",
         "--resume", dst],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        bufsize=1, env=env)
    eos_ok = None
    for line in proc.stdout:
        print(line, end="", flush=True)
        if "EOS_SELFCHECK: OK" in line:
            eos_ok = True
        elif "EOS_SELFCHECK: FAIL" in line:
            eos_ok = False
            print("\\n!! Самопроверка EOS не прошла — глушу дообучение.",
                  flush=True)
            proc.kill()
            break
    proc.wait()
    if eos_ok is False:
        raise SystemExit("EOS не доходит до loss — см. лог выше")
    if proc.returncode != 0:
        raise SystemExit(f"дообучение упало: код {proc.returncode}")
    if eos_ok is None:
        print("\\n!! маркер EOS_SELFCHECK не увиден при успешном дообучении "
              "— потерялся в пайпе лога (уже бывало)", flush=True)
    MODEL = OUT

# --- замеры по обоим эвалам ---------------------------------------------
for data, dump in (("eval.jsonl", "merged_eval.jsonl"),
                   ("eval_wide.jsonl", "merged_eval_wide.jsonl")):
    print("\\n" + "=" * 70, flush=True)
    print("ЗАМЕР:", data, flush=True)
    print("=" * 70, flush=True)
    subprocess.run([sys.executable, f"{BASE}/validate_kaggle.py",
                    "--model", MODEL, "--dump", f"/kaggle/working/{dump}",
                    f"{BASE}/{data}"], check=True)
'''


# Диагностика прогона 2: посмотреть, ЧТО модель реально выдаёт.
#
# Дампы говорят «строк не разобралось» (26% «мусор», 41% обрыв), но не
# показывают сам ответ — validate_kaggle.py разбирал text и выбрасывал.
# Теперь он кладёт сырой ответ в поле "text", и 20 примеров хватает,
# чтобы развести три диагноза, которые снаружи выглядят одинаково:
#   пусто            -> модель переучилась на EOS (лечится схемой обучения)
#   проза не в формате -> адаптер не применился (лечится плумбингом)
#   верный формат, обрыв -> недоучена / упёрлась в max_new_tokens
# Обучения здесь нет: инференс на 20 примерах, минуты GPU, не часы.
DIAG2 = '''\
"""Диагностика адаптера прогона 2: 20 примеров с сырым текстом ответа."""
import glob, os, subprocess, sys

''' + FIND_DATASET + CHECK_GPU + '''
BASE = _find_dataset("validate_kaggle.py")
_check_gpu()

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-U",
                "transformers", "peft", "bitsandbytes", "accelerate"], check=True)

# Адаптер прогона 2 — по train_meta.json, как в run2_resume: имя папки
# после распаковки zip негарантированно, содержимое — гарантировано.
hits = glob.glob("/kaggle/input/**/train_meta.json", recursive=True)
if not hits:
    raise SystemExit("адаптер прогона 2 не найден (искал train_meta.json)")
MODEL = os.path.dirname(hits[0])
print("адаптер:", MODEL, flush=True)

# Два замера на ОДНОМ адаптере и одних примерах: разница между ними и есть
# вклад ограничения, без примеси «другой чекпоинт / другие данные».
for extra, dump in (([], "diag2_free.jsonl"),
                    (["--constrained"], "diag2_constrained.jsonl")):
    print("\\n" + "=" * 70, flush=True)
    print("ЗАМЕР:", "ограниченная" if extra else "обычная", "генерация", flush=True)
    print("=" * 70, flush=True)
    subprocess.run([sys.executable, f"{BASE}/validate_kaggle.py",
                    "--model", MODEL, "--limit", "20",
                    "--dump", f"/kaggle/working/{dump}",
                    f"{BASE}/eval.jsonl"] + extra, check=True)
'''

# Квадрат 2x2 на широком эвале: два адаптера x два режима генерации.
#
# Зачем после diag2. Тот показал главное — под ограниченной генерацией
# адаптер прогона 2 даёт 20/20 валидных и все двадцать точно оптимальны
# (docs/DIAG2.md). Но мерено на eval.jsonl, где графы 6..14 и НОЛЬ операций
# STORE, а именно STORE — доминирующий класс ошибок на широком эвале: 85%
# всех «ресурсов» (docs/ROADMAP.md). То есть решающий класс ошибок diag2 не
# видел в принципе.
#
# Проверяемое предсказание. Ограниченная генерация выбирает канал ТОЛЬКО из
# исполнимых, значит STORE на канале ,0 невозможен по построению — эти
# ошибки обязаны обнулиться, а не уменьшиться. Если не обнулятся, диагноз
# неверен, и это тоже ответ.
#
# Почему оба адаптера и оба режима, а не только недостающая клетка. Прежние
# числа (32.7% и 14.7%) сняты в разное время разными запусками; сравнивать с
# ними новое измерение — значит смешивать «эффект ограничения» с «эффектом
# другого запуска». Квадрат считается одним ядром на одних примерах, поэтому
# разность строк означает ровно то, что написано на строках.
#
# Весь eval_wide (300 примеров), а не подвыборка: квота позволяет, а на 20
# примерах разница между 70% и 80% статистически неразличима.
DIAG3 = '''\
"""Ограниченная генерация против обычной на широком эвале, два адаптера."""
import glob, os, subprocess, sys

''' + FIND_DATASET + CHECK_GPU + '''
BASE = _find_dataset("validate_kaggle.py")
_check_gpu()

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-U",
                "transformers", "peft", "bitsandbytes", "accelerate"], check=True)

# Адаптер прогона 2 приезжает отдельным датасетом (vliw-run2-lora) и лежит
# рядом с train_meta.json; адаптер прогона 1 — внутри основного датасета
# папкой lora-eos. Ищем оба по содержимому, а не по имени папки: имя после
# распаковки zip негарантированно, содержимое — гарантировано.
hits = glob.glob("/kaggle/input/**/train_meta.json", recursive=True)
if not hits:
    raise SystemExit("адаптер прогона 2 не найден (искал train_meta.json)")
RUN2 = os.path.dirname(hits[0])

eos = [d for d in glob.glob("/kaggle/input/**/lora-eos", recursive=True)
       if os.path.isdir(d)]
if not eos:
    raise SystemExit("адаптер прогона 1 не найден (искал папку lora-eos)")
RUN1 = eos[0]

print("прогон 1:", RUN1, flush=True)
print("прогон 2:", RUN2, flush=True)

for tag, model in (("run1", RUN1), ("run2", RUN2)):
    for extra, mode in ((["--constrained"], "ограниченная"), ([], "обычная")):
        print("\\n" + "=" * 70, flush=True)
        print(f"АДАПТЕР {tag} / {mode} генерация", flush=True)
        print("=" * 70, flush=True)
        subprocess.run([sys.executable, f"{BASE}/validate_kaggle.py",
                        "--model", model,
                        "--dump", f"/kaggle/working/diag3_{tag}_"
                                  + ("con" if extra else "free") + ".jsonl",
                        f"{BASE}/eval_wide.jsonl"] + extra, check=True)
'''

KERNELS = [
    ("vliw-step0-baseline", "step0.py", STEP0, "vliw step0 baseline"),
    ("vliw-run1-eos", "run1_eos.py", RUN1, "vliw run1 eos"),
    ("vliw-run2-merged", "run2_merged.py", RUN2, "vliw run2 merged"),
    # Доводка прогона 2. Подключить вывод vliw-run2-merged как kernel_sources
    # НЕЛЬЗЯ: Kaggle отказывает в источниках от ядра, чья версия упала или
    # отменена (проверено 23.08: "not valid kernel sources"). Поэтому финальный
    # адаптер вынесен отдельным датасетом vliw-run2-lora — собирается вручную
    # из вывода прогона (lora-merged без checkpoint-*). Заливается ТОЛЬКО
    # явным `kaggle_push.sh resume`, в `all` не входит.
    ("vliw-run2-resume", "run2_resume.py", RESUME2, "vliw run2 resume",
     {"dataset_sources": [f"USERNAME/{DATASET_SLUG}",
                          f"USERNAME/vliw-run2-lora"]}),
    # Диагностика: только инференс на 20 примерах. Как и resume, берёт
    # адаптер из отдельного датасета vliw-run2-lora и в `all` не входит —
    # запускается явным `kaggle_push.sh diag`.
    ("vliw-diag2", "diag2.py", DIAG2, "vliw diag2",
     {"dataset_sources": [f"USERNAME/{DATASET_SLUG}",
                          f"USERNAME/vliw-run2-lora"]}),
    # Квадрат 2x2 на широком эвале. Как и diag2, в `all` не входит и берёт
    # адаптер прогона 2 отдельным датасетом; адаптер прогона 1 едет в
    # основном датасете папкой lora-eos.
    # ВНИМАНИЕ НА ИМЯ. Kaggle делает слаг ядра из ЗАГОЛОВКА, а не из id:
    # заголовок «vliw diag3 wide» создал ядро vliw-diag3-wide, а не
    # vliw-diag3, и `pull` (он ходит по именам папок в build/kaggle) искал бы
    # результат не там. У остальных ядер заголовок и id совпадают случайно —
    # здесь совпадение сломало лишнее слово. Держим их одинаковыми явно.
    ("vliw-diag3-wide", "diag3.py", DIAG3, "vliw diag3 wide",
     {"dataset_sources": [f"USERNAME/{DATASET_SLUG}",
                          f"USERNAME/vliw-run2-lora"]}),
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
    # У lora-eos проверяем только сам адаптер: токенизатора рядом нет и быть
    # не должно (обучение сохранило только веса поправки).
    missing += [f"{EOS_ADAPTER_SRC}/{name}"
                for name in ("adapter_config.json", "adapter_model.safetensors")
                if not (ROOT / EOS_ADAPTER_SRC / name).exists()]
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

    for src_dir, dst_dir in ((ADAPTER_SRC, ADAPTER_DST),
                             (EOS_ADAPTER_SRC, EOS_ADAPTER_DST)):
        adir = DATA / dst_dir
        adir.mkdir(exist_ok=True)
        for name in ADAPTER_FILES:
            src_file = ROOT / src_dir / name
            if not src_file.exists():
                # У lora-eos рядом нет файлов токенизатора: обучение сохранило
                # только адаптер. Это не поломка — загрузчик берёт токенизатор
                # у базовой модели (см. docs/LEARNED.md).
                continue
            d = adir / name
            shutil.copy2(src_file, d)
            total += d.stat().st_size

    # Слаг дописывается при заливке: username берётся из kaggle.json, чтобы
    # здесь не было заглушки, которую легко забыть заменить.
    (DATA / "dataset-metadata.json").write_text(json.dumps({
        "title": "VLIW e2k scheduler — data, adapter, scripts",
        "id": f"USERNAME/{DATASET_SLUG}",
        "licenses": [{"name": "CC0-1.0"}],
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    for entry in KERNELS:
        slug, code_file, code, title = entry[:4]
        extras = entry[4] if len(entry) > 4 else {}
        kdir = BUILD / slug
        kdir.mkdir(parents=True, exist_ok=True)
        (kdir / code_file).write_text(code, encoding="utf-8")
        meta = {
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
        }
        # Ядро-доводка добавляет источник — вывод прошлого прогона.
        meta.update(extras)
        (kdir / "kernel-metadata.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"собрано в {BUILD.relative_to(ROOT)}")
    print(f"  датасет: {len(PAYLOAD)} файлов + адаптер, {total / 2**20:.0f} МБ")
    for entry in KERNELS:
        print(f"  ядро:    {entry[0]}/{entry[1]}")
    print("\nдальше: tools/kaggle_push.sh (подставит username и зальёт)")


if __name__ == "__main__":
    main()
