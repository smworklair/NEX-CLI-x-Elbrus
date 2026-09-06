

## Ошибки и предупреждения

| Слово | Перевод | Где встретилось сегодня |
|---|---|---|
| **error** | ошибка | `SyntaxError`, `ImportError`, `ValueError` |
| **warning** | предупреждение (не ошибка, а просто «на заметку») | `Warning: You are sending unauthenticated requests` |
| **deprecated** | устаревший, скоро уберут | `torch_dtype is deprecated! Use dtype instead` |
| **incompatible** | несовместимый | `Found an incompatible version of torchao` |
| **unauthenticated** | без входа/авторизации | те самые «unauthenticated requests to HF Hub» |
| **mismatch** | несовпадение | `numpy.dtype size changed` (по сути mismatch версий) |
| **missing** | отсутствующий, недостающий | `missing 1 required positional argument` |
| **invalid** | недействительный, неверный | `Invalid requirement: 'dantasets'` (опечатка) |
| **unexpected** | неожиданный | `got an unexpected keyword argument 'tokenizer'` |
| **required** | обязательный, нужный | `--model, required=True` |
| **traceback** | «путь ошибки» — цепочка, где именно упало | то, что печаталось под каждым `Traceback (most recent call last):` |
| **raise / raised** | «бросить» ошибку (сгенерировать её специально) | `raise ImportError(...)` |

## Импорты, версии, зависимости

| Слово | Перевод | Где встретилось |
|---|---|---|
| **import** | подключить библиотеку | `from transformers import ...` |
| **require(s)** | требует(ся) | `requires bitsandbytes: pip install ...` |
| **dependency / dependencies** | зависимость(и) — библиотека, без которой не работает | `pip's dependency resolver` |
| **resolver** | «решатель» — часть pip, которая подбирает совместимые версии | тот же `dependency resolver` |
| **conflict(s)** | конфликт(ы) | `dependency conflicts` (numpy у всех подряд) |
| **version** | версия | почти в каждой второй ошибке сегодня |
| **support(ed)** | поддерживать(ся) | `only versions above 0.16.0 are supported` |
| **available** | доступный | `is_torchao_available()` |
| **pin / pinned** | закрепить версию (не «>=», а ровно такая) | `trl==0.9.6` — это и есть «запиненная» версия |

## Процесс / состояние выполнения

| Слово | Перевод | Где встретилось |
|---|---|---|
| **loading** | загрузка (в память) | `Loading weights: 100%` |
| **downloading** | скачивание (из интернета) | `Downloading (incomplete total...)` |
| **fetching** | получение, забор данных | `Fetching 2 files: 100%` |
| **complete** | завершено | `Download complete: 100%` |
| **running** | выполняется | `Running for 4525.7s` |
| **overwriting** | перезаписывается | `Overwriting train_qlora.py` |
| **session** | сеанс работы | `Draft Session (37m)` |
| **draft** | черновик | тот же `Draft Session` |
| **commit** | здесь: зафиксировать и запустить в фоне | `Save & Run All (Commit)` |

## Обучение модели

| Слово | Перевод | Где встретилось |
|---|---|---|
| **checkpoint** | контрольная точка (сохранённое состояние) | `checkpoint-1200`, `checkpoint-1250` |
| **adapter** | адаптер (маленькая надстройка поверх модели, LoRA) | `qwen-vliw-lora`, `adapter_config.json` |
| **weights** | веса модели (сами числа-параметры) | `adapter_model.safetensors` |
| **tokenizer** | токенизатор (текст → числа) | `AutoTokenizer` |
| **trainable** | обучаемый (какая часть весов реально меняется) | `trainable params: 29,933,568` |
| **quantization** | квантование (сжатие весов, напр. до 4 бит) | `BitsAndBytesConfig(load_in_4bit=True)` |
| **generate / generation** | генерация (модель пишет ответ) | `model.generate(...)` |

## Общие технические слова

| Слово | Перевод | Где встретилось |
|---|---|---|
| **argument** | аргумент (входной параметр функции) | `positional argument`, `keyword argument` |
| **keyword argument** | именованный аргумент (`x=5`, а не просто `5`) | `unexpected keyword argument` |
| **signature** | сигнатура (список параметров функции) | `inspect.signature(Trainer.__init__)` |
| **attribute** | атрибут (поле/свойство объекта) | `AttributeError: object has no attribute` |
| **config / configuration** | настройка(и) | `adapter_config.json` |
| **output** | вывод, результат | `/kaggle/working` output |
| **environment** | окружение (набор установленных пакетов) | `Environment: Latest Container Image` |

---


