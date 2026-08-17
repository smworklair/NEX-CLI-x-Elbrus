# tools/ — вспомогательные скрипты

Всё здесь запускается локально на CPU и ничего не требует, кроме `.venv`
(единственное исключение отмечено). Порядок — примерно тот, в котором это
нужно по ходу работы.

| скрипт | что делает | когда нужен |
|---|---|---|
| `probe_matrix.py` | переснимает матрицу портов у настоящего ассемблера e2k и сверяет с `vliw/core/model.py` | после любой правки профиля машины |
| `vliw_gen.py` | генерирует примеры «граф → расписание», расписания через CP-SAT, доказуемо оптимальные | нужны новые данные (требует `ortools`) |
| `validate_jsonl.py` | прогоняет jsonl через настоящий `Schedule.validate()`, печатает сводку | после любой генерации или правки данных |
| `build_split.py` | собирает `train_merged.jsonl` и held-out `eval_wide.jsonl` (4..24 инстр., послойно) | перед обучением |
| `kaggle_prep.py` | собирает `build/kaggle/`: датасет + два ядра-скрипта | перед заливкой |
| `kaggle_push.sh` | заливает и запускает; `pull` забирает дампы обратно | нужен `~/.kaggle/kaggle.json` |
| `report_runs.py` | сводит дампы прогонов в таблицу с дельтами и разбивкой по размеру графа | после прогонов |

## Обычный цикл

```bash
python tools/probe_matrix.py                              # железо не разъехалось
python -m unittest discover -s tests -t .                 # код не разъехался
python tools/validate_jsonl.py train_merged.jsonl         # данные законны
tools/kaggle_push.sh                                      # шаг 0 на Kaggle
tools/kaggle_push.sh pull && python tools/report_runs.py  # результаты в таблицу
```

Порядок прогонов и что каким шагом доказывается — в
[`../docs/RUNBOOK_EOS.md`](../docs/RUNBOOK_EOS.md).

## Что здесь намеренно НЕ так

`vliw_gen.py` импортирует константы из `vliw.core.model`, а
`training/validate_kaggle.py` — дублирует их у себя. Это не недосмотр:
валидатор должен работать на Kaggle, где пакета `vliw` нет, и потому обязан
быть самодостаточным. Расхождение между ними ловит `probe_matrix.py` и
`tests/test_model.py`.
