# Обучение Qwen на планировщик — пошагово

Цель: заполнить `vliw/learned/scheduler.py` — сейчас там `NotImplementedError`
(см. [vliw/learned/README.md](../vliw/learned/README.md)). Модель учится на
парах «граф зависимостей → оптимальное расписание», эталон для которых даёт
оракул точного поиска, уже реализованный в проекте.

Ничего не платим до тех пор, пока бесплатного пути реально не хватит:
данные — на своей машине или бесплатном Deepnote (только CPU), дообучение —
на бесплатном GPU Kaggle (~30 GPU-часов/неделю, без карты).

## Шаг 1. Сгенерировать датасет (CPU, без ИИ-зависимостей)

Работает где угодно — на этой машине, на Deepnote (Basic-машина, 2 vCPU/5 ГБ
хватает с запасом), в обычном терминале:

```bash
cd vliw-ai-scheduler-demo
python3 training/generate_dataset.py \
    --count 20000 \
    --sizes 6,8,10,12,14 \
    --budget 1.5 \
    --out dataset.jsonl
```

- `--count` — сколько примеров набрать. Для первого прогона возьмите 500-1000
  (быстро, минут за 5-15) — это шаг 4 покажет, работает ли вся цепочка вообще,
  прежде чем тратить часы на 20 тысяч.
- `--budget` — сколько секунд оракул ищет оптимум на ОДНОМ графе. Больше
  графы (`--sizes`) — нужен больший бюджет, иначе много примеров отбросится
  как «не доказано» (это ожидаемо и безопасно: генератор берёт только
  доказанные оптимумы, см. комментарии в файле).
- Формат — JSONL, одна строка = один пример:
  `{"prompt": "...", "completion": "...", "meta": {...}}`.

Прежде чем куда-то грузить датасет — самопроверка (тоже CPU, без модели):

```bash
python3 training/validate.py dataset.jsonl
```

Должно быть `N/N валидны, round-trip проверен`. Если нет — проблема в
`training/encode.py`, чинить здесь, до всякого обучения.

## Шаг 2. Завести Kaggle-ноутбук с GPU

1. Зарегистрироваться на kaggle.com (карта не нужна для бесплатного GPU).
2. New Notebook → справа Settings → **Accelerator: GPU T4×2** (или P100).
3. Add Data → загрузить `dataset.jsonl` (Kaggle положит его в
   `/kaggle/input/<имя-датасета>/dataset.jsonl`).
4. Первая ячейка — поставить зависимости (их нет в базовом образе Kaggle):

```bash
!pip install -q -U -r requirements-kaggle.txt
```

(или руками: `!pip install -q transformers peft bitsandbytes accelerate datasets` —
`trl` не нужен, `train_qlora.py` сидит на обычном `transformers.Trainer`.)

5. Загрузить `training/train_qlora.py` и `training/validate_kaggle.py`
   в ноутбук (`%%writefile ...` целиком из локальных файлов).

## Шаг 3. Дообучить (QLoRA, 4 бита)

`--base` подставляется как есть. Формат данных один: сырой prompt+completion.
В конец каждого примера дописывается EOS — без него модель не учится
останавливаться и на коротких графах дописывает хвост (это уже измерено
на Qwen2.5-3B: 24/50 «лишних id» при законном префиксе 0..n-1).

**Та же база, ещё эпохи** (адаптер уже есть в Input):

```bash
!python train_qlora.py \
    --base Qwen/Qwen2.5-3B-Instruct \
    --adapter /kaggle/input/datasets/shokhruhmir/sexrex/qwen-vliw-lora \
    --data /kaggle/input/<имя-датасета>/dataset.jsonl \
    --out /kaggle/working/qwen-vliw-lora \
    --epochs 2
```

**Другая база с нуля** — та же команда без `--adapter`, другой `--base` и `--out`:

```bash
# Coder, тот же размер
!python train_qlora.py \
    --base Qwen/Qwen2.5-Coder-3B-Instruct \
    --data /kaggle/input/<имя-датасета>/dataset.jsonl \
    --out /kaggle/working/coder-vliw-lora \
    --epochs 2

# соседний класс, без thinking-режима
!python train_qlora.py \
    --base Qwen/Qwen3-4B-Instruct-2507 \
    --data /kaggle/input/<имя-датасета>/dataset.jsonl \
    --out /kaggle/working/qwen3-vliw-lora \
    --epochs 2
```

7B на T4: `--batch-size 2`. Не берите `Qwen3-4B` / `Qwen3-4B-Thinking-*` —
у них режим размышления, ответы будут длиннее и ломать парсер.

В логе должно быть `trainable params ... < 2%` и строка `EOS в конце каждого примера`.

Ячейку обучения и ячейку оценки **не гоняйте в одном Save & Run All**, если
не хотите сжечь весь GPU-бюджет на повторное обучение. Одна версия — одна база.

## Шаг 4. Проверить, что модель не врёт

На Kaggle — `validate_kaggle.py` (в образе нет пакета `vliw`). Не больше 50
примеров, пока смотрите состав ошибок:

```bash
!python validate_kaggle.py \
    --model /kaggle/working/qwen-vliw-lora \
    --limit 50 \
    --dump /kaggle/working/eval_kinds.jsonl \
    /kaggle/input/datasets/shokhruhmir/nex-gp/eval.jsonl
```

Две цифры в конце:

- **как есть** — модель сама остановилась, расписание законно;
- **префикс 0..n-1** — то же после отрезания id, которых в графе нет.

Хвост при законном префиксе — это стоп (EOS / эпохи), не «модель не поняла
задачу» и не повод менять базу. Дыры в настоящих id и пустой ответ — повод
смотреть другую `--base`.

Локально, без GPU, кодировку данных проверяет `python3 training/validate.py dataset.jsonl`.

## Шаг 5. Забрать адаптер и подключить к CLI

Скачать папку `/kaggle/working/qwen-vliw-lora` (Kaggle → Output → Download).
Дальше в `vliw/learned/scheduler.py` реализовать `schedule()`: закодировать
`(dag, model)` через `training.encode.encode_prompt`, дать модели
сгенерировать продолжение, разобрать `training.encode.decode_completion`,
собрать `Schedule`, вызвать `.validate()` — и только если чисто, вернуть
`SchedulingResult`. Если невалидно — честно откатываться на `baseline`
(GreedyListScheduler), а не выдавать сломанное расписание как рабочее.

## Если бесплатного не хватит

30 GPU-часов/неделю на Kaggle и 4-битный QLoRA на 3B-модели с датасетом в
несколько тысяч коротких примеров — это заведомо посильно бесплатно; сюда
переходить нет нужды заранее. Если всё же упрётесь: Deepnote Team даёт
$50/мес GPU-кредита (студенческий Education-план сам GPU не включает, только
безлимитный CPU, см. обсуждение) — но сначала стоит исчерпать бесплатный путь.
