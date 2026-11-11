# TINY AI: устройство и обучение

Маленький MLP (~21 тыс. параметров), который даёт планировщику вектор приоритетов и отсрочки.
Текст модель не генерирует, поэтому галлюцинаций нет как класса. Расписание строит обычный
детерминированный код, и оно законно по построению.

Пользовательские цифры и границы — [`docs/TINY.md`](../../docs/TINY.md).

## Файлы

| файл | роль |
|---|---|
| `features.py` | 18 признаков узла: операция, height/asap, латентность, занятость, каналы, степени |
| `model.py` | MLP 18→128→64→1, инференс на стандартной библиотеке |
| `train.py` | обучение клонированием порядка CP-SAT-оракула |
| `es.py` | Evolution Strategies по награде makespan |
| `scheduler.py` | `TinyScheduler`: портфель и выбор лучшего makespan |
| `fast.py` | `TinyFlashScheduler`: тот же результат, но быстрее |
| `eval.py`, `verify.py` | замеры и проверка законности |
| `weights.json`, `weights_defer.json`, `weights_hold.json` | обученные головы |

## Портфель

```text
greedy → prio → prio_defer → prio_hold → rule_hold → rule_hold_far
       → beam_t* → beam_h* → beam_d*
```

Побеждает лучший makespan; ничьи отдаются жадному. Поэтому **хуже жадного не бывает**.
Без `weights.json` остаётся честный фолбэк: веер вокруг height и жадный.

- **prio** — порядок из MLP.
- **defer** — запрет «не раньше» с клипом по жадному makespan.
- **hold** — держка после asap, отдельная голова.
- **rule_hold** — ручные держки монопольного порта без ML.
- **beam** — детерминированный джиттер порядка, K=16 вокруг двух нормализованных центров.

## Команды

```bash
python -m vliw.tiny.train --train train_merged.jsonl \
    --out vliw/tiny/weights.json --max-graphs 8000 --epochs 25 --seed 0
python -m vliw.tiny.train --train train_merged.jsonl \
    --out vliw/tiny/weights_defer.json --target cycle
python -m vliw.tiny.es --train train_hard.jsonl \
    --init vliw/tiny/weights.json --out vliw/tiny/weights.json --iters 20 --pop 16
python -m vliw.tiny.eval --eval eval_hard.jsonl --weights vliw/tiny/weights.json
python -m vliw.tiny.verify --weights vliw/tiny/weights.json --train-sample 500 --fuzz 200
python -m unittest tests.test_tiny tests.test_tiny_fast tests.test_tiny_verify
```

`numpy` нужен только для обучения. Инференс работает на голой стандартной библиотеке.

## Наборы

| набор | роль | правило |
|---|---|---|
| `train_merged.jsonl` | обучение | можно использовать целиком |
| `eval_hard_dev.jsonl` | отбор конфигурации | решать только по нему |
| `eval_hard.jsonl` | финальный тест | смотреть один раз |
| `eval_wide.jsonl` | регресс на лёгких | вровень с жадным |
| случайные графы | never-worse | 0 ухудшений |

## Результаты

- `eval_hard`: 284/300 в оптимуме, разрыв 0,053, законность 100%.
- Настоящий код: 927/947 оптимальных блоков против 890 у жадного.
- Ни одного ухудшения на 1 547 проверенных графах.
- `TinyFlashScheduler`: тот же makespan, 0 расхождений на 3 061 графе; на `eval_real` 0,95 мс/граф.

## Откуда идеи

- `google/ml-compiler-opt` — behavioral cloning как warmstart и ES по makespan.
- `llvm/llvm-project` — AOT-инференс модели без рантайма.
- `google-research-datasets/tpu_graphs` — дисциплина «граф + конфиг + время».
