"""Обучающий пайплайн для будущего vliw/learned/LearnedScheduler.

Отдельно от основного пакета `vliw` НАМЕРЕННО: `vliw` работает на голом
Python без зависимостей (см. README, раздел про rich), а здесь появятся
torch/transformers/peft — тяжёлые ML-зависимости, которые демо-инструменту
не нужны. `generate_dataset.py` и `encode.py` используют только `vliw.core`
и стандартную библиотеку — их можно гонять где угодно, включая CPU-задачи
на Deepnote. `train_qlora.py` и `validate.py` требуют GPU — им место на
Kaggle. Подробный порядок действий — в training/README.md.
"""
