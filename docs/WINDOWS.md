# Windows

> Ответвление от этапа 2 · [← CLI](CLI.md) · [Маршрут](README.md)

Инструмент работает на Windows целиком, включая полноэкранное рабочее место.
Здесь только отличия от [`CLI.md`](CLI.md).

## Python

Нужен Python 3.10+. Проверка:

```powershell
py --version
```

Если команды нет — установите с [python.org](https://www.python.org/downloads/) (галка **Add python.exe to PATH**)
или через `winget`:

```powershell
winget install Python.Python.3.12
```

На Windows команда обычно называется `python` или `py`; `python3`, как правило, не существует.
В остальной документации вместо `python3` подставляйте `python`.

## Установка

```powershell
git clone <ссылка-на-репозиторий>
cd NEX-CLI-x-Elbrus
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[tui]"
```

Если PowerShell блокирует активацию (`running scripts is disabled`), разрешите её только для текущего окна:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

В `cmd.exe` активация другая: `.venv\Scripts\activate.bat`.

## Запуск

```powershell
python -m vliw run slotclash
python -m vliw                 # экран выбора режимов
python -m vliw --mode code     # сразу КОД
python -m vliw --plain         # построчный режим
```

После `pip install -e .` доступна короткая форма `vliw`.

Если `textual` не установлен, `python -m vliw` открывает экран-помощник: он объясняет причину,
показывает команды и после согласия ставит `textual`/`rich`.

## Две особенности

**Кириллица.** Инструмент сам переключает консоль на UTF-8 и VT-режим. Если видите квадраты —
обновите репозиторий.

**История команд.** Модуля `readline` в стандартном Python для Windows нет. Это касается только
построчного режима (`--plain`, пайпы, скрипты): стрелка вверх там не листает историю.
В полноэкранном рабочем месте свой ввод, и это не мешает.

## Агент

Без ключа агент отвечает офлайн по посчитанным числам — это норма, а не поломка.
Ключ вставляется в диалоге или командой:

```text
/ai deepseek key=sk-...
/ai gigachat key=<client_id>:<client_secret>
/ai yandex folder=... key=...
/ai local-server url=http://localhost:11434/v1 model=qwen2.5:3b
```

Ключ живёт только в памяти сессии. Поддерживаются 17 провайдеров; полный список — в
[`AGENT_PROMPTS.md`](AGENT_PROMPTS.md) и [`.env.example`](../.env.example).
Для скриптов без терминала используйте переменные окружения: `NEX_PROVIDER`, `NEX_API_KEY`,
`NEX_MODEL`, `NEX_BASE_URL`.

## Если что-то не так

| симптом | решение |
|---|---|
| `No module named vliw` | запускать из папки проекта или `pip install -e .` |
| активация `.venv` запрещена | `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` |
| квадраты вместо текста | обновить репозиторий |
| нет истории в `--plain` | это ограничение Windows, не ошибка |
| `verify` не находит ассемблер | задать `E2K_AS` или добавить `lcc` в `PATH` |

Общие проблемы — в [`CLI.md`](CLI.md#частые-проблемы).
