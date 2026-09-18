# Крошки: tiny-приоритеты вместо LLM

Крошка = MLP на ~10-40К параметров, дает только вектор приоритетов для
`list_schedule`. Законность — по построению (детерминированный планировщик),
галлюцинаций нет как класс: текста модель не генерирует.

## Крошка-1: priority (готова)

- `features.py` — 18 фич узла (op one-hot + height/asap/latency/occupancy/
  каналы/степени/is_div/is_store). Незнакомые опкоды → нули в one-hot.
- `model.py` — MLP 18→128→64→1, 10625 параметров, инференс чистый stdlib.
- `train.py` — клонирование порядка CP-SAT-оракула, апсемплинг DIV/STORE.
  Флаг `--train-extra/--extra-repeat` подмешивает второй набор повторами
  до шаффла (сделан под `train_hard.jsonl`, но на замерах 18.09 подмес
  проигрывает чистому merged — см. docs/TINY.md, включать только с цифрой).
- `scheduler.py` — `TinyScheduler`: портфель {tiny, baseline}, выбор по
  makespan. Хуже baseline не бывает. Без `weights.json` — не хуже baseline
  (веер вокруг height работает и без весов; при K=16 на `slotclash`
  выигрывает 24→23).
  Веса от другого числа фич не валят планировщик, а дают честный fallback
  (`load_error`, см. код) — было нужно при откате эксперимента с 20 фичами.
- `weights.json` — supervised на 8000 графах `train_merged` (сид 0) +
  ES-доводка по `train_hard.jsonl` (см. команды ниже). Без ES — 87/120
  на DEV, с ES — 91/120.
- `weights_hold.json` — вторая defer-голова (цель hold: держка после asap,
  а не абсолютный такт). Отдельный член портфеля `prio_hold`: min по
  супермножеству не бывает хуже, по факту +3 на DEV (91→94) и +13 на
  финале (219→232). Маркер цели — в файле весов (`target`), отсутствие —
  legacy `cycle`; трактовка — в `scheduler._holds_of`, а не по имени файла.

## Команды (все — голый Python + numpy только для train)

```bash
python -m vliw.tiny.train --train train_merged.jsonl --out vliw/tiny/weights.json --max-graphs 8000 --epochs 25 --seed 0
python -m vliw.tiny.train --train train_merged.jsonl --out vliw/tiny/weights_defer.json --max-graphs 8000 --epochs 25 --seed 0 --target cycle
python -m vliw.tiny.es --train train_hard.jsonl --init vliw/tiny/weights.json --out vliw/tiny/weights.json --iters 20 --pop 16 --batch 96 --seed 0
python -m vliw.tiny.eval --eval eval_hard.jsonl --weights vliw/tiny/weights.json
python -m vliw.tiny.verify --weights vliw/tiny/weights.json --train-sample 500 --fuzz 200
python tools/harvest_dev.py --n 120 --jobs 4 --out eval_hard_dev.jsonl
python tools/tiny_losses.py
python -m unittest tests.test_tiny -v
```

## Наборы и их роль (не путать!)

| набор | роль | правило |
|---|---|---|
| `train_merged.jsonl` | обучение | можно есть целиком |
| `eval_hard_dev.jsonl` (120, сиды 20300xxx) | DEV-отбор: сид/эпохи/ансамбль | решать только по нему |
| `eval_hard.jsonl` (300) | финальный тест | смотреть один раз в конце |
| `eval_wide.jsonl` | регресс на легких | должен быть вровень с baseline |
| fuzz `random_dag` | never-worse | 0 проигрышей |

## Крошка-2: defer_until (готова)

- Тот же MLP (10625 параметров), цель — такт оракула (`--target cycle`).
- На инференсе такты идут как `defer_until` («не раньше») с клипом по
  жадному makespan (прием из `floor_from_model` в CAB).
- `weights_defer.json`. Дает +13 побед на DEV поверх порядка.

## Крошка-3: веер beam (готова, весов нет — это поиск)

- Детерминированный гауссов джиттер порядка (фикс. сиды), K=16 вокруг двух
  центров: скоры крошки-1 и нормированный height. Точный выбор по makespan.
- Контроль честности: beam вокруг ненормированного height дает 0 побед
  (джиттер убивает масштаб) — поэтому центры нормализуем; это задокументировано
  в `scheduler.py`. Beam вокруг height без крошек: 76/120 — поиск силен сам
  по себе; крошки добавляют сверху (86→88 на DEV).
- Портфель: greedy → prio → prio_defer → prio_hold → beam_t* → beam_h* →
  beam_d* (веер по держкам). Ничьи — greedy. Текущий финал: 234/300,
  гэп 0.220 (см. docs/TINY.md).

## Замер крошек 1+2+3+ES (13.09.2026, конфиг заморожен по DEV, тест — один прогон)

`eval_hard 300`: gap **0.270** vs 0.970 baseline, **219/300** в оптимуме,
**203/300** строго лучше, valid 100%, ~63мс/граф CPU.
DEV 120: 91 победа. `eval_wide`: вровень (0 побед, 0 поражений).
Сценарии: `slotclash 24→23 (beam_t2)`, остальные вровень.
Qwen+CAB для масштаба: 0.82 / ~60 в оптимуме при 2-6ГБ и 30с/граф.
Итого крошек: ~21К параметров + поиск, миллисекунды, 0 галлюцинаций.

## Откуда алгоритмы (те самые три ссылки — использованы, не для галочки)

- `google/ml-compiler-opt` (MLGO-статья, arxiv 2101.04808): их два алгоритма —
  Policy Gradient и Evolution Strategies. Behavioral cloning как warmstart
  (наши prio/defer) и ES fine-tune по makespan-награде (`vliw/tiny/es.py`,
  `train_hard.jsonl` 400 трудных) — прямо оттуда. ES: 34.17 → 30.55 standalone,
  +22 победы в полном портфеле на тесте.
- `llvm/llvm-project`: `MLModelRunner` release-mode (AOT: модель вшивается в
  бинарь без рантайма) — наш `weights.json` + stdlib-инференс это та же идея
  в миниатюре; development-mode логирование — наши `trace/search_stats`.
- `google-research-datasets/tpu_graphs` (архив): дисциплина троек
  «граф + конфиг + время» — наш формат `prompt/completion/meta`; их GNN
  cost-модель — план на этап больших графов, где оракул бессилен.
