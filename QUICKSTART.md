# Быстрый старт

> Этап 1 из 13 · [Маршрут](docs/README.md) · [CLI →](docs/CLI.md)

Запуск за пару минут. Нужен только **Python 3.10+**; компилятор `lcc`, QEMU и железо не требуются.

## 1. Получить код

```bash
git clone https://github.com/smworklair/NEX-CLI-x-Elbrus
cd NEX-CLI-x-Elbrus
python3 --version        # на Windows: python --version или py --version
```

## 2. Установить

Для ядра и построчного режима зависимостей нет:

```bash
pip install -e .
```

Для полноэкранного рабочего места (рекомендуется):

```bash
pip install -e ".[tui]"  # rich + textual
```

После установки доступна команда `vliw`; без установки работает `python -m vliw` из папки проекта.

## 3. Запустить

```bash
python -m vliw                 # экран выбора: КОД / РАЗБОР / АГЕНТ / ЯДРО
python -m vliw run slotclash   # один сценарий и выход
python -m vliw compare         # жадный и точный поиск рядом
python -m vliw all             # сводка по всем 17 сценариям
python -m vliw --plain         # построчный режим без полноэкранных панелей
```

Внутри рабочего места команды пишутся со слэшем: `/run slotclash`, `/compare`, `/doctor`, `/tiny`.
Список всех команд — `/help` или `python -m vliw --help`.

## 4. Свой `.s`-файл

Откройте режим **КОД** (`1` на экране выбора или `--mode code`), загрузите файл:

```text
/load examples/probe.s
```

и нажмите `F5`. Будет разобран настоящий вывод `lcc`: расписание, замечания и сравнение с точным поиском.
Подробно — [`docs/CODE_MODE.md`](docs/CODE_MODE.md).

## 5. Проверить

```bash
python -m unittest discover -s tests
```

Пропуски без `torch` (обученная LLM) и без `textual` (полноэкранный интерфейс) — норма, а не ошибка.
Полный набор зависимостей: `pip install -e ".[tui,learned]"`.

## Если что-то не так

| симптом | что делать |
|---|---|
| `No module named vliw` | запускать из папки проекта или выполнить `pip install -e .` |
| `python3` не найден | на Windows используйте `python` или `py` |
| вместо интерфейса — экран-помощник | не установлен `textual`; помощник поставит его после согласия |
| квадраты вместо кириллицы | обновите репозиторий: UTF-8 включается автоматически |
| агент отвечает без модели | это норма: без ключа он отвечает по посчитанным числам |

Остальное — [`docs/CLI.md`](docs/CLI.md) и [`docs/WINDOWS.md`](docs/WINDOWS.md).
