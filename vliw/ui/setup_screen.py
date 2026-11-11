"""Экран-помощник вместо «урезанного» интерфейса.

Показывается, когда основной полноэкранный экран поднять нельзя, а `--plain`
явно не запрошен. Это не тупиковое сообщение и не справочник: экран ведёт себя
как ассистент. Пользователь пишет обычными словами («запусти», «нет textual»,
«не работает») или выбирает пункт стрелками — ассистент показывает короткий
план с точными командами, спрашивает согласие и сам выполняет безопасные шаги:
ставит недостающие пакеты, проверяет окружение, открывает NEX CLI.

Всё оформление и ввод — stdlib: ANSI-цвета из `vliw.ui.render`, логотип из
`vliw.ui.logo`, ответы — из `vliw.help_answers`. Ни textual, ни rich, ни numpy
здесь не требуются: экран как раз и нужен на чистой машине.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import importlib.util
import os
import platform
import shlex
import subprocess
import sys
from pathlib import Path

from .. import VERSION_LABEL, help_answers, help_nnl
from . import render
from .logo import render_title
from .render import Style, paint

# Фиолетовая композиция экрана запуска. Тема включается только здесь и только
# на время жизни экрана: выход из `welcome()`/`explain()` завершает процесс,
# поэтому full TUI (он стартует отдельным процессом) остаётся в своей теме.
_BOOT_THEME = "nnl-purple"

MIN_TEXTUAL = "8.2"
MIN_RICH = "13"

_VT: bool | None = None


# --------------------------------------------------------------------------
# Что установлено и почему не поднялся основной экран
# --------------------------------------------------------------------------


def _has(module: str) -> bool:
    """Есть ли модуль, не импортируя его (импорт textual заметно медленный)."""
    try:
        return importlib.util.find_spec(module) is not None
    except Exception:  # pragma: no cover - сломанное окружение
        return False


def missing() -> list[str]:
    """Недостающие пакеты в виде спецификаций для pip."""
    out: list[str] = []
    if not _has("textual"):
        out.append(f"textual>={MIN_TEXTUAL}")
    if not _has("rich"):
        out.append(f"rich>={MIN_RICH}")
    return out


def reasons(extra: str | None = None) -> list[str]:
    """Почему полноэкранный режим не поднимается — по пунктам."""
    out: list[str] = []
    if sys.version_info < (3, 10):
        out.append(
            f"Python {platform.python_version()} старше 3.10 — "
            "NEX CLI требует 3.10 или новее"
        )
    if not _has("textual"):
        out.append(
            f"не установлен пакет textual (нужен >= {MIN_TEXTUAL}) — "
            "без него нет полноэкранного интерфейса"
        )
    elif not _has("rich"):
        out.append(
            f"не установлен пакет rich (нужен >= {MIN_RICH}) — "
            "без него нет цветного вывода"
        )
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        out.append(
            "ввод или вывод не подключён к терминалу "
            "(пайп, перенаправление в файл, фоновый запуск)"
        )
    if extra:
        out.append(extra)
    if not out:
        out.append("полноэкранный режим отключён в этом окружении")
    return out


def _exe() -> str:
    """Путь к текущему Python, готовый для вставки в командную строку."""
    return f'"{sys.executable}"' if " " in sys.executable else sys.executable


def _project_dir() -> Path | None:
    """Каталог проекта, если запущены из исходников (есть pyproject.toml)."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    return None


def _store_stub() -> bool:
    """Запущены через заглушку Microsoft Store из WindowsApps."""
    return "WindowsApps" in sys.executable


def _in_venv() -> bool:
    return sys.prefix != getattr(sys, "base_prefix", sys.prefix)


def _version(module: str) -> str:
    try:
        return importlib.metadata.version(module)
    except Exception:
        return "есть" if _has(module) else "нет"


def _tty() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


# --------------------------------------------------------------------------
# Оформление: перенос, рамка, меню
# --------------------------------------------------------------------------


def _ширина() -> int:
    return max(48, min(92, render.term_cols() - 6))


def _обернуть(текст: str, ширина: int) -> list[str]:
    """Перенос строки; строки с отступом в 4 пробела — команды.

    Команды не переносим вставкой `\\n`: терминал сам сделает мягкий перенос,
    а копирование длинной команды останется целым.
    """
    if not текст:
        return [""]
    if текст.startswith("    "):
        return [текст]
    return render.wrap(текст, ширина)


def _рамка(строки: list[str], заголовок: str, ширина: int, роль: str = "border") -> list[str]:
    """Рамка вокруг ПЛОСКОГО текста; ширина — внешняя, в символах."""
    внутренняя = ширина - 4
    тело: list[str] = []
    for строка in строки:
        тело += _обернуть(строка, внутренняя)
    заголовок = заголовок[: max(0, ширина - 6)]
    верх = ("  " + paint(роль, "┌─ ") + paint("accent", заголовок)
            + paint(роль, " " + "─" * max(0, ширина - 5 - len(заголовок)) + "┐"))
    низ = "  " + paint(роль, "└" + "─" * (ширина - 2) + "┘")
    out = [верх]
    for строка in тело:
        out.append("  " + paint(роль, "│ ") + render.pad(строка, внутренняя) + paint(роль, " │"))
    out.append(низ)
    return out


def _заголовок(раздел: str) -> list[str]:
    return ["", "  " + paint("accent", раздел), "  " + Style.dim("─" * min(64, render.term_cols() - 6))]


def _пункт(текст: str) -> str:
    return "    " + Style.dim("•") + " " + текст


def _статус() -> str:
    venv = "venv" if _in_venv() else "без venv"
    textual = _version("textual") if _has("textual") else "нет"
    rich = _version("rich") if _has("rich") else "нет"
    return (f"Python {platform.python_version()} · {platform.system()} "
            f"{platform.release()} · {venv} · textual: {textual} · rich: {rich}")


def _статус_кратко() -> str:
    venv = "venv" if _in_venv() else "без venv"
    textual = "есть" if _has("textual") else "нет"
    rich = "есть" if _has("rich") else "нет"
    tty = "терминал OK" if _tty() else "терминал НЕ TTY"
    return (f"Python {platform.python_version()} · {venv} · textual: {textual} · "
            f"rich: {rich} · {tty}")


def _о_продукте() -> list[str]:
    return [
        "NEX CLI — рабочее место для планирования инструкций под VLIW-машину "
        "Эльбрус e2k. Он показывает, как программа ложится на каналы и порты "
        "машины, где теряются такты и что можно ускорить перестановкой.",
        "",
        "Внутри три режима: КОД — редактор .s и расписание; РАЗБОР — весь граф "
        "и диагноз; АГЕНТ — вопросы к LLM о текущем графе. Планировщик, оракул "
        "и разовые команды работают на чистом Python — им полноэкранные панели "
        "не нужны.",
    ]


def _приветствие() -> list[str]:
    return [
        "Здравствуйте! Я NNL-помощник NEX CLI.",
        "Скажите словами — поставлю недостающее, запущу, разберу ошибку.",
    ]


def _шапка_кратко() -> list[str]:
    """Шапка экрана запуска: LEGO-логотип «NNL» + строка названия.

    Без лишних строк: экран должен целиком влезать в окно в 30 строк,
    чтобы верхняя шляпка кирпичей не уезжала за край.
    """
    out = render_title(indent="  ")
    out += [
        "",
        "  " + paint("title", "NEX CLI") + Style.dim("  ·  ")
        + paint("mountain", "NNL-помощник") + Style.dim("  ·  ")
        + paint("mountain", "Elbrus e2k") + Style.dim("  ·  ")
        + paint("warning", VERSION_LABEL),
    ]
    return out


def _печать_причины(extra: str | None) -> None:
    """Причина сбоя: подпись только у первой строки, продолжения — под ней."""
    ширина = max(24, render.term_cols() - 4)
    for i, причина in enumerate(reasons(extra)):
        подпись = "  Причина: " if i == 0 else "           "
        for j, часть in enumerate(render.wrap(причина, ширина - len(подпись))):
            префикс = подпись if (i == 0 and j == 0) else " " * len(подпись)
            print(префикс + часть)


# --------------------------------------------------------------------------
# Ввод с клавиатуры: стрелки и Enter, без сторонних библиотек
# --------------------------------------------------------------------------


def _vt_доступен() -> bool:
    """Можно ли пользоваться управляющими последовательностями ANSI."""
    global _VT
    if _VT is not None:
        return _VT
    if os.name != "nt":
        _VT = True
        return _VT
    try:
        import ctypes

        k = ctypes.windll.kernel32
        handle = k.GetStdHandle(-11)
        режим = ctypes.c_uint32()
        if not k.GetConsoleMode(handle, ctypes.byref(режим)):
            _VT = False
        else:
            _VT = bool(k.SetConsoleMode(handle, режим.value | 0x0004))
    except Exception:  # pragma: no cover - старый Windows
        _VT = False
    return _VT


def _клавиша() -> str:
    """Одна клавиша: вверх / вниз / ввод / esc или обычный символ."""
    if os.name == "nt":
        import msvcrt

        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):
            return {"H": "вверх", "P": "вниз", "K": "влево", "M": "вправо"}.get(
                msvcrt.getwch(), ""
            )
        if ch == "\r":
            return "ввод"
        if ch == "\x1b":
            return "esc"
        if ch == "\x03":
            raise KeyboardInterrupt
        return ch

    import select
    import termios
    import tty

    fd = sys.stdin.fileno()
    старые = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == "\x1b":
            if not select.select([fd], [], [], 0.05)[0]:
                return "esc"
            if sys.stdin.read(1) != "[":
                return "esc"
            if not select.select([fd], [], [], 0.05)[0]:
                return "esc"
            return {"A": "вверх", "B": "вниз", "C": "вправо", "D": "влево"}.get(
                sys.stdin.read(1), ""
            )
        if ch in ("\r", "\n"):
            return "ввод"
        if ch == "\x03":
            raise KeyboardInterrupt
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, старые)


def _строка_пункта(метка: str, подсказка: str, выбран: bool) -> str:
    указатель = paint("accent", ">") if выбран else " "
    if подсказка:
        # Длинная подсказка на узком терминале переносится и ломает перерисовку
        # стрелками: строка меню должна оставаться одной физической строкой.
        доступно = render.term_cols() - 5 - len(метка)
        if доступно <= 3:
            подсказка = ""
        elif len(подсказка) > доступно:
            подсказка = подсказка[: max(1, доступно - 1)] + "…"
    текст = paint("title", метка) if выбран else метка
    if подсказка:
        текст += "  " + Style.dim(подсказка)
    return "  " + указатель + " " + текст


def _меню_вводом(
    пункты: list[tuple[str, str]],
    заголовок: str,
    подсказка: str,
    приём_текста: bool,
) -> int | str | None:
    """Запасной режим для терминалов без ANSI: цифры и обычный input."""
    if заголовок:
        хвост = ("   " + подсказка) if подсказка else ""
        print("  " + paint("accent", заголовок) + Style.dim(хвост))
    for i, (метка, хвост) in enumerate(пункты, 1):
        строка = f"  {i}. {метка}"
        if хвост:
            строка += "  " + Style.dim(хвост)
        print(строка)
    try:
        ответ = input("  " + paint("prompt", "NNL") + Style.dim(" > ")).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None
    if not ответ:
        return 0
    if ответ.lower() in ("q", "quit", "exit", "выход", "0"):
        return None
    if ответ.isdigit():
        i = int(ответ) - 1
        if 0 <= i < len(пункты):
            return i
    if приём_текста:
        return ответ
    print("  " + Style.dim("Нет такого пункта."))
    return None


def _меню(
    пункты: list[tuple[str, str]],
    *,
    заголовок: str = "",
    подсказка: str = "↑/↓ — выбор · Enter — подтвердить",
    приём_текста: bool = False,
) -> int | str | None:
    """Выбор стрелками. Возвращает индекс, текст запроса или None (выход/назад).

    Если `приём_текста`, первая напечатанная буква не выбирает пункт, а
    превращается в начало вопроса — так пользователю не обязательно сначала
    искать «Задать вопрос» в меню.
    """
    if not _tty() or not _vt_доступен():
        return _меню_вводом(пункты, заголовок, подсказка, приём_текста)

    индекс = 0
    высота = 0

    def строки() -> list[str]:
        out: list[str] = []
        if заголовок:
            хвост = ("   " + подсказка) if подсказка else ""
            out.append("  " + paint("accent", заголовок) + Style.dim(хвост))
        for i, (метка, хвост) in enumerate(пункты):
            out.append(_строка_пункта(метка, хвост, i == индекс))
        return out

    def нарисовать(первый: bool = False) -> None:
        nonlocal высота
        новые = строки()
        if not первый:
            sys.stdout.write(f"\033[{высота}A")
        for строка in новые:
            sys.stdout.write("\r\033[2K" + строка + "\n")
        sys.stdout.flush()
        высота = len(новые)

    нарисовать(первый=True)
    while True:
        try:
            k = _клавиша()
        except KeyboardInterrupt:
            print()
            return None
        if k == "вверх":
            индекс = (индекс - 1) % len(пункты)
            нарисовать()
        elif k == "вниз":
            индекс = (индекс + 1) % len(пункты)
            нарисовать()
        elif k in ("ввод", " "):
            print()
            return индекс
        elif k.lower() in ("q", "й") or k == "esc":
            print()
            return None
        elif len(k) == 1 and k.isdigit():
            i = int(k) - 1
            if 0 <= i < len(пункты):
                индекс = i
                нарисовать()
                print()
                return индекс
        elif приём_текста and len(k) == 1 and k.isprintable():
            print()
            try:
                хвост = input("  " + paint("prompt", "NNL") + Style.dim(" > ") + k)
            except (EOFError, KeyboardInterrupt):
                print()
                return None
            return k + хвост


# --------------------------------------------------------------------------
# Планы действий: команды, которые ассистент предлагает выполнить
# --------------------------------------------------------------------------


def _команда_текст(команда: list[str]) -> str:
    """Команда в виде, который можно скопировать в терминал целиком.

    `subprocess.list2cmdline` не экранирует `>` и `|`: спецификация
    `textual>=8.2` в cmd превратилась бы в перенаправление вывода. Поэтому
    метасимволы оболочки здесь quoted явно.
    """
    if os.name == "nt":
        части: list[str] = []
        for аргумент in команда:
            if not аргумент:
                части.append('""')
            elif any(c in аргумент for c in ' \t"<>|&^'):
                части.append('"' + аргумент.replace('"', '\\"') + '"')
            else:
                части.append(аргумент)
        return " ".join(части)
    return " ".join(shlex.quote(x) for x in команда)


def _пакеты_интерфейса() -> list[str]:
    return missing() or [f"textual>={MIN_TEXTUAL}", f"rich>={MIN_RICH}"]


def _команда_установки(пакеты: list[str] | None = None) -> list[str]:
    return [sys.executable, "-m", "pip", "install", "--upgrade",
            *(пакеты or _пакеты_интерфейса())]


def _шаг_установки(пакеты: list[str] | None = None) -> dict:
    пакеты = пакеты or _пакеты_интерфейса()
    return {
        "текст": "Поставить " + ", ".join(пакеты),
        "команда": _команда_установки(пакеты),
        "вид": "установка",
    }


def _шаг_запуска() -> dict:
    return {
        "текст": "Открыть NEX CLI",
        "команда": [sys.executable, "-m", "vliw"],
        "вид": "запуск",
    }


def _план_запуска() -> dict:
    пакеты = missing()
    шаги: list[dict] = []
    резюме: list[str] = []
    if пакеты:
        резюме.append(
            "Сначала поставлю " + " и ".join(пакеты) + ", потом открою NEX CLI. "
            "Это займёт меньше минуты."
        )
        шаги.append(_шаг_установки(пакеты))
    else:
        резюме.append("Всё готово — открываю NEX CLI.")

    if _tty():
        шаги.append(_шаг_запуска())
    else:
        резюме.append(
            "Терминал не интерактивный: полноэкранный интерфейс не откроется. "
            "Запустите эту же команду из PowerShell, Windows Terminal или "
            "обычного терминала Linux."
        )
    if _store_stub():
        резюме.append(
            "Внимание: сейчас используется заглушка Microsoft Store. "
            "Лучше поставить Python с python.org — иначе пакеты могут "
            "устанавливаться не туда."
        )

    if пакеты and _tty():
        название = "Установить интерфейс и открыть NEX CLI"
        кнопка = "Установить и открыть"
    elif пакеты:
        название = "Установить интерфейс"
        кнопка = "Установить"
    else:
        название = "Открыть NEX CLI"
        кнопка = "Открыть NEX CLI"
    return {
        "название": название,
        "тема": "запуск",
        "резюме": резюме,
        "шаги": шаги,
        "можно_выполнить": bool(шаги),
        "кнопка": кнопка,
    }


def _план_починки() -> dict:
    пакеты = missing()
    шаги: list[dict] = []
    резюме = ["Проверю, чего не хватает, поставлю недостающее и попробую открыть NEX CLI заново."]
    if пакеты:
        шаги.append(_шаг_установки(пакеты))
    if _tty():
        шаги.append(_шаг_запуска())
    else:
        резюме.append(
            "Сейчас терминал не интерактивный — сначала откройте настоящее окно "
            "терминала, иначе полноэкранный режим не поднимется."
        )
    if not пакеты and _tty():
        резюме.append("Пакеты на месте. Если окно снова не откроется, покажу, где смотреть traceback.")
    return {
        "название": "Починить запуск",
        "тема": "проблема",
        "резюме": резюме,
        "шаги": шаги,
        "можно_выполнить": bool(шаги),
        "кнопка": "Починить и открыть",
    }


def _план_проверки() -> dict:
    return {
        "название": "Проверить окружение",
        "тема": "проверка",
        "резюме": ["Проверю Python, pip, textual, rich и терминал. Ничего не изменю."],
        "шаги": [{"текст": "Собрать диагностику", "вид": "проверка"}],
        "можно_выполнить": True,
        "кнопка": "Проверить сейчас",
    }


def _план_обновления() -> dict:
    пакеты = _пакеты_интерфейса()
    return {
        "название": "Обновить интерфейс",
        "тема": "обновление",
        "резюме": ["Обновлю textual и rich до актуальных версий. Сценарии и настройки это не затронет."],
        "шаги": [_шаг_установки(пакеты)],
        "можно_выполнить": True,
        "кнопка": "Обновить",
    }


def _план_venv() -> dict:
    проект = _project_dir()
    if проект is None:
        return {
            "название": "Отдельное окружение .venv",
            "тема": "venv",
            "резюме": [
                "Каталог проекта не найден, поэтому точный путь подставить не могу. "
                "Создайте окружение в папке проекта командами ниже."
            ],
            "шаги": [
                {"текст": "Создать окружение", "команда": [sys.executable, "-m", "venv", ".venv"]},
                {"текст": "Поставить NEX CLI с интерфейсом",
                 "команда": ["python", "-m", "pip", "install", "-e", ".[tui]"]},
            ],
            "можно_выполнить": False,
            "кнопка": "Показать команды",
        }
    cwd = str(проект)
    if os.name == "nt":
        python = str(проект / ".venv" / "Scripts" / "python.exe")
    else:
        python = str(проект / ".venv" / "bin" / "python")
    return {
        "название": "Отдельное окружение .venv",
        "тема": "venv",
        "резюме": [
            "Создам .venv в каталоге проекта, поставлю туда NEX CLI с интерфейсом "
            "и запущу его. Системный Python останется нетронутым."
        ],
        "шаги": [
            {"текст": "Создать окружение .venv",
             "команда": [sys.executable, "-m", "venv", ".venv"], "cwd": cwd},
            {"текст": "Поставить NEX CLI с интерфейсом",
             "команда": [python, "-m", "pip", "install", "-e", ".[tui]"], "cwd": cwd},
            {"текст": "Открыть NEX CLI из .venv",
             "команда": [python, "-m", "vliw"], "cwd": cwd, "вид": "запуск"},
        ],
        "можно_выполнить": True,
        "кнопка": "Создать и открыть",
    }


def _план_удаления() -> dict:
    if os.name == "nt":
        удалить_venv = ["cmd", "/c", "rmdir", "/s", "/q", ".venv"]
    else:
        удалить_venv = ["rm", "-rf", ".venv"]
    return {
        "название": "Удалить NEX CLI",
        "тема": "удаление",
        "резюме": [
            "Покажу безопасный порядок. Сам ничего удалять не буду: это необратимо."
        ],
        "шаги": [
            {"текст": "Убрать пакет NEX CLI",
             "команда": [sys.executable, "-m", "pip", "uninstall", "vliw-ai-scheduler"]},
            {"текст": "Удалить окружение .venv, если создавали", "команда": удалить_venv},
            {"текст": "Удалить каталог проекта вручную, если он больше не нужен"},
        ],
        "можно_выполнить": False,
        "кнопка": "Показать команды",
    }


def _план_для_темы(тема: str) -> dict | None:
    if тема in ("запуск", "установка", "textual", "проблема", "требования",
                "система", "зачем", "данные", "агент"):
        return _план_запуска()
    if тема == "проверка":
        return _план_проверки()
    if тема == "обновление":
        return _план_обновления()
    if тема == "venv":
        return _план_venv()
    if тема == "удаление":
        return _план_удаления()
    return None


def _напечатать_план(план: dict) -> None:
    print()
    print("  " + paint("accent", "NNL · " + план["название"]))
    print("  " + Style.dim("─" * min(64, render.term_cols() - 6)))
    ширина = render.term_cols() - 6
    for абзац in план.get("резюме", []):
        for часть in _обернуть(абзац, ширина):
            print("  " + часть if часть else "")
    print("  " + Style.dim("Сейчас: " + _статус_кратко()))
    print()
    print("  " + Style.dim("План:"))
    for i, шаг in enumerate(план.get("шаги", []), 1):
        print("   " + paint("accent", str(i)) + ". " + шаг["текст"])
        if шаг.get("cwd"):
            print("      " + Style.dim("cd " + шаг["cwd"]))
        if шаг.get("команда"):
            print("      " + paint("success", _команда_текст(шаг["команда"])))
    print()


def _напечатать_команды(план: dict) -> None:
    print()
    print("  " + paint("accent", "NNL · команды"))
    print("  " + Style.dim("─" * min(64, render.term_cols() - 6)))
    for i, шаг in enumerate(план.get("шаги", []), 1):
        print()
        print("  " + Style.dim(f"{i}. {шаг['текст']}"))
        if шаг.get("cwd"):
            print("    " + Style.dim("cd " + шаг["cwd"]))
        if шаг.get("команда"):
            print("    " + paint("success", _команда_текст(шаг["команда"])))
        elif not шаг.get("вид"):
            print("    " + Style.dim("выполняется вручную"))
    print()


def _выполнить(команда: list[str], cwd: str | None = None) -> int:
    print()
    print("  " + Style.dim("$ " + _команда_текст(команда)))
    try:
        return subprocess.call(команда, cwd=cwd)
    except OSError as e:
        print("  " + paint("error", f"не удалось запустить: {e}"))
        return 1


def _выполнить_план(план: dict, только_установка: bool = False) -> int | None:
    """Выполнить шаги плана после согласия. 0 — полноэкранный интерфейс открылся."""
    шаги = план.get("шаги", [])
    for i, шаг in enumerate(шаги, 1):
        if только_установка and шаг.get("вид") == "запуск":
            break
        print()
        print("  " + paint("accent", f"[{i}/{len(шаги)}] {шаг['текст']}"))
        if шаг.get("вид") == "проверка":
            _проверить(пауза=False)
            continue
        команда = шаг.get("команда")
        if not команда:
            print("  " + Style.dim("этот шаг выполняется вручную"))
            continue

        код = _выполнить(команда, шаг.get("cwd"))
        if шаг.get("вид") == "установка":
            if код != 0 and not _has("pip"):
                print()
                print("  " + paint("warning", "pip не найден — ставлю его через ensurepip"))
                _выполнить([sys.executable, "-m", "ensurepip", "--upgrade"])
                код = _выполнить(команда, шаг.get("cwd"))
            importlib.invalidate_caches()
            if код == 0 and missing():
                print()
                print("  " + paint("warning", "pip завершился успешно, но модули не видны."))
                print("  " + Style.dim("Похоже, пакеты поставлены другому Python. "
                                       "Запустите установку тем же интерпретатором, что и NEX CLI."))
                _пауза()
                return None
        if код != 0:
            print()
            print("  " + paint("error", f"шаг не выполнен (код {код})."))
            print("  " + Style.dim("Проверьте интернет и права. Если pip недоступен:"))
            print("    " + paint("success", f"{_exe()} -m ensurepip --upgrade"))
            _пауза()
            return None
        if шаг.get("вид") == "запуск":
            return 0 if код == 0 else None

    print()
    print("  " + paint("success", "готово"))
    if план.get("тема") == "обновление":
        print("  " + Style.dim("Если проект установлен из исходников, обновите и его: git pull, "
                               "затем pip install -e \".[tui]\"."))
    _пауза()
    return None


def _показать_план(план: dict) -> int | None:
    """Карточка плана: команды, согласие и выполнение."""
    _напечатать_план(план)
    кнопка = план.get("кнопка", "Выполнить")
    можно = план.get("можно_выполнить", False)
    есть_запуск = any(ш.get("вид") == "запуск" for ш in план.get("шаги", []))
    есть_установка = any(ш.get("вид") == "установка" for ш in план.get("шаги", []))

    while True:
        пункты: list[tuple[str, str]] = []
        if можно:
            пункты.append((кнопка, "выполню шаги за вас"))
            if есть_установка and есть_запуск:
                пункты.append(("Только установить", "без запуска интерфейса"))
        else:
            пункты.append(("Показать команды", "скопировать и выполнить вручную"))
        if можно:
            пункты.append(("Показать команды", "что именно будет выполнено"))
        if план.get("тема"):
            пункты.append(("Подробнее", "полное объяснение"))
        пункты.append(("Назад", "вернуться в меню"))

        выбор = _меню(пункты, заголовок="Что делаем?")
        if выбор is None:
            return None
        метка = пункты[выбор][0]
        if метка == кнопка and можно:
            return _выполнить_план(план)
        if метка == "Только установить":
            return _выполнить_план(план, только_установка=True)
        if метка == "Показать команды":
            _напечатать_команды(план)
            _пауза()
        elif метка == "Подробнее":
            _печать_ответа(план["тема"], полный=True)
            _пауза()
        else:
            return None


# --------------------------------------------------------------------------
# Ответы ассистента
# --------------------------------------------------------------------------


def _печать_ответа(тема: str, полный: bool = False) -> None:
    текст = help_answers.ответ(тема) if полный else help_answers.кратко(тема)
    if not текст:
        return
    заголовок = help_answers.ЗАГОЛОВКИ.get(тема, тема)
    print()
    print("  " + paint("accent", f"NNL · {заголовок}"))
    print("  " + Style.dim("─" * min(64, render.term_cols() - 6)))
    ширина = render.term_cols() - 6
    for строка in текст:
        for часть in _обернуть(строка, ширина):
            if not часть:
                print()
            elif часть.startswith("    "):
                print("  " + paint("success", часть))
            else:
                print("  " + часть)
    print()


def _показать_кратко(тема: str) -> int | None:
    """Короткий ответ и одно очевидное действие вместо стены справки."""
    _печать_ответа(тема)
    план = _план_для_темы(тема)
    while True:
        пункты: list[tuple[str, str]] = []
        if план is not None:
            пункты.append((план.get("кнопка", "Подготовить"), "покажу команды и спрошу согласие"))
        пункты.append(("Подробнее", "полное объяснение"))
        пункты.append(("Назад", "вернуться в меню"))
        выбор = _меню(пункты, заголовок="Что дальше?")
        if выбор is None:
            return None
        метка = пункты[выбор][0]
        if план is not None and метка == план.get("кнопка", "Подготовить"):
            return _показать_план(план)
        if метка == "Подробнее":
            _печать_ответа(тема, полный=True)
            _пауза()
        else:
            return None


def _объяснить_установки() -> int | None:
    """Почему помощник просит доустановить пакеты — без запуска установки."""
    пакеты = missing()
    ширина = render.term_cols() - 6
    print()
    print("  " + paint("accent", "NNL · зачем нужны дополнительные установки"))
    print("  " + Style.dim("─" * min(64, ширина)))
    print("  Планировщик, оракул и разовые команды работают на чистом Python.")
    print("  Дополнительные пакеты нужны только для полноэкранного интерфейса:")
    print("    " + paint("success", "textual") + " — панели, вкладки и экраны "
          "КОД / РАЗБОР / АГЕНТ;")
    print("    " + paint("success", "rich") + " — цвет, таблицы и рамки внутри них.")
    print()
    if пакеты:
        print("  Сейчас не хватает: " + paint("warning", ", ".join(пакеты)) + ".")
        print("  Без них вместо панелей открывается этот экран — данные и "
              "команды те же.")
    else:
        print("  Сейчас " + paint("success", "оба пакета на месте")
              + " — полный интерфейс доступен.")
    print()

    пункты: list[tuple[str, str]] = []
    if пакеты:
        пункты.append(("Поставить и открыть",
                       "покажу команды и спрошу согласие"))
    пункты.append(("Подробнее", "полное объяснение требований"))
    пункты.append(("Назад", "вернуться в меню"))
    выбор = _меню(пункты, заголовок="Что дальше?")
    if выбор is None:
        return None
    метка = пункты[выбор][0]
    if пакеты and метка == "Поставить и открыть":
        return _показать_план(_план_запуска())
    if метка == "Подробнее":
        _печать_ответа("требования", полный=True)
        _пауза()
    return None


def _беседа(вопрос: str) -> bool:
    """Приветствие/благодарность/прощание. True — пора выходить."""
    низ = " ".join(вопрос.lower().replace("ё", "е").strip("!?.,;: ").split())
    if низ.startswith(("спасибо", "благодар")):
        print()
        print("  " + paint("accent", "NNL · всегда пожалуйста"))
        print("  " + Style.dim("─" * min(64, render.term_cols() - 6)))
        print("  Если понадобится помощь с запуском — я рядом.")
        print()
        return False
    if низ in ("пока", "до свидания", "до встречи", "хорошего дня"):
        print()
        print("  " + paint("accent", "NNL · до встречи"))
        print("  " + Style.dim("─" * min(64, render.term_cols() - 6)))
        print("  Запустить снова: " + paint("success", f"{_exe()} -m vliw"))
        print()
        return True
    _печать_ответа("беседа")
    return False


def _не_понял() -> None:
    print()
    print("  " + paint("warning", "NNL · не понял вопрос"))
    print("  " + Style.dim("Я помогаю только с NEX CLI: запуск, установка, ошибки и режимы."))
    print("  " + Style.dim("Скажите иначе или выберите пункт в меню ниже."))
    print()


def _проверка_строки() -> list[tuple[str, str, str]]:
    """(пункт, значение, статус) — статус: ok / нет / инфо."""
    py_ok = sys.version_info >= (3, 10)
    tty_ok = _tty()
    pip_ok = _has("pip")
    textual_ok = _has("textual")
    rich_ok = _has("rich")
    проект = _project_dir()
    строки = [
        ("Python", f"{platform.python_version()} · "
                   f"{'64 бита' if sys.maxsize > 2 ** 32 else '32 бита'}",
         "OK" if py_ok else "НУЖЕН 3.10+"),
        ("терминал", f"{sys.stdin.isatty()} {sys.stdout.isatty()}",
         "OK" if tty_ok else "НЕ TTY"),
        ("pip", "есть" if pip_ok else "нет — нужен ensurepip",
         "OK" if pip_ok else "НЕТ"),
        ("venv", "активен" if _in_venv() else "не активен (не обязателен)", "инфо"),
        ("textual", _version("textual") if textual_ok else "нет", "OK" if textual_ok else "НЕТ"),
        ("rich", _version("rich") if rich_ok else "нет", "OK" if rich_ok else "НЕТ"),
        ("проект", str(проект) if проект else "каталог с pyproject.toml не найден", "инфо"),
    ]
    if _store_stub():
        строки.append(("Python", "заглушка Microsoft Store (WindowsApps)", "ВНИМАНИЕ"))
    return строки


def _проверить(пауза: bool = True) -> None:
    print()
    print("  " + paint("accent", "Проверка окружения"))
    print("  " + Style.dim("─" * min(64, render.term_cols() - 6)))
    for имя, значение, статус in _проверка_строки():
        if len(значение) > 46:
            значение = значение[:43] + "..."
        метка = {"OK": paint("success", "OK"), "НЕТ": paint("error", "НЕТ"),
                 "НЕ TTY": paint("warning", "НЕ TTY"),
                 "ВНИМАНИЕ": paint("warning", "ВНИМАНИЕ"),
                 "НУЖЕН 3.10+": paint("error", "НУЖЕН 3.10+"),
                 "инфо": Style.dim("—")}.get(статус, статус)
        print("  " + render.pad(имя, 10) + render.pad(значение, 46) + " " + метка)

    print()
    if not _has("textual"):
        print("  " + paint("warning", "Полноэкранный интерфейс не поднимется без textual."))
        print("  " + Style.dim("Ассистент может поставить его и открыть NEX CLI."))
    elif not _tty():
        print("  " + paint("warning", "Пакеты на месте, но терминал не интерактивный."))
        print("  " + Style.dim("Откройте PowerShell / Windows Terminal / обычный "
                               "терминал Linux и запустите снова."))
    else:
        print("  " + paint("success", "Всё нужное на месте — можно открывать NEX CLI."))
    if пауза:
        _пауза()


def _пауза() -> None:
    try:
        input("\n  " + Style.dim("Enter — назад в меню "))
    except (EOFError, KeyboardInterrupt):
        print()


# --------------------------------------------------------------------------
# Понимание запроса и главный цикл
# --------------------------------------------------------------------------


_ПРИЗНАКИ_ПОЧИНКИ = (
    "не работает", "не запускается", "не открывается", "не установ",
    "сломал", "ошибк", "traceback", "падает", "черный экран", "чёрный экран",
    "зависа", "не отвечает", "закрывается сразу",
)
_ПРИЗНАКИ_УДАЛЕНИЯ = ("удал", "снести", "деинстал", "uninstall", "стереть установку")
_ПРИЗНАКИ_ОБНОВЛЕНИЯ = ("обнов", "upgrade", "git pull", "новая версия", "свежую версию")
_ПРИЗНАКИ_VENV = ("venv", "виртуал", "ensurepip", "pip не найден", "нет pip", "без pip")
_ПРИЗНАКИ_ПРОВЕРКИ = ("проверь", "провер", "диагност", "doctor", "selfcheck", "тест")
_ПРИЗНАКИ_ЗАПУСКА = ("запуст", "открой", "открыть", "старт", "включи", "launch", " run ")
_ПРИЗНАКИ_УСТАНОВКИ = ("установ", "поставь", "поставить", "инсталл", "install",
                       "скачай", "подготовь", "настрой")


def _намерение(текст: str) -> str | None:
    """Что человек хочет сделать — до попытки угадать тему NNL-блоком."""
    низ = " " + текст.lower().replace("ё", "е") + " "
    if any(с in низ for с in _ПРИЗНАКИ_ПОЧИНКИ):
        return "починка"
    if any(с in низ for с in _ПРИЗНАКИ_УДАЛЕНИЯ):
        return "удаление"
    if any(с in низ for с in _ПРИЗНАКИ_ОБНОВЛЕНИЯ):
        return "обновление"
    if any(с in низ for с in _ПРИЗНАКИ_VENV):
        return "venv"
    if any(с in низ for с in _ПРИЗНАКИ_ПРОВЕРКИ):
        return "проверка"
    if any(с in низ for с in _ПРИЗНАКИ_ЗАПУСКА):
        return "запуск"
    if any(с in низ for с in _ПРИЗНАКИ_УСТАНОВКИ):
        return "установка"
    return None


# Вопросы, которые нельзя выполнять как команду. «зачем нужны доп установки»
# содержит корень «установ» и раньше попадало в «установка» → запускался план
# установки. Вопросительное слово важнее действия: сначала объясняем.
_ВОПРОСНЫЕ = (
    "зачем", "почему", "отчего", "для чего", "что такое", "что это",
    "что значит", "что за ", "чем полез", "в чем смысл", "в чём смысл",
    "как работает", "как устроен", "как устроена", "как устроено",
    "как запустить", "как запускается", "как установить", "как ставится",
    "как настроить", "как пользоваться", "как обновить", "как удалить",
    "как проверить", "как создать", "как включить",
    "нужно ли", "надо ли", "обязательно ли", "можно ли", "стоит ли",
    "есть ли", "какие", "какой", "какая", "каких", "каким", "какую",
    "где ", "когда", "сколько",
)


def _это_вопрос(текст: str) -> bool:
    """Вопрос ли это, а не команда. Спрашивают — объясняем, не запускаем."""
    низ = " " + текст.lower().replace("ё", "е") + " "
    return any(слово in низ for слово in _ВОПРОСНЫЕ)


def _спросили_зачем_установки(текст: str) -> bool:
    """«Зачем/почему нужны доп установки» — это вопрос о требованиях."""
    низ = " " + текст.lower().replace("ё", "е") + " "
    зачем = ("зачем", "почему", "для чего", "нужно ли", "надо ли",
             "обязательно ли", "стоит ли")
    про_пакеты = ("установ", "постав", "пакет", "textual", "rich", "доп")
    return any(м in низ for м in зачем) and any(м in низ for м in про_пакеты)


def _задать_вопрос(extra: str | None = None) -> int | None:
    try:
        текст = input("  " + paint("prompt", "NNL") + Style.dim(" > ")).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None
    if not текст:
        return None
    return _обработать_запрос(текст, extra)


def _обработать_запрос(текст: str, extra: str | None = None) -> int | None:
    """Запрос обычными словами → действие или короткий ответ. 0 — TUI открылся."""
    текст = текст.strip()
    if not текст:
        return None
    if текст in ("?", "？"):
        return _задать_вопрос(extra)

    if _спросили_зачем_установки(текст):
        return _объяснить_установки()

    # Вопрос — это не команда: «зачем нужны доп установки» не должно ставить
    # пакеты, даже если в нём есть корень «установ».
    вид = None if _это_вопрос(текст) else _намерение(текст)
    if вид == "починка":
        return _показать_план(_план_починки())
    if вид == "удаление":
        return _показать_план(_план_удаления())
    if вид == "обновление":
        return _показать_план(_план_обновления())
    if вид == "venv":
        return _показать_план(_план_venv())
    if вид == "проверка":
        return _показать_план(_план_проверки())
    if вид in ("запуск", "установка"):
        return _показать_план(_план_запуска())

    if not help_nnl.доступно():
        print()
        print("  " + paint("warning", "NNL-блок помощи не найден."))
        print("  " + Style.dim("Похоже, каталог nnl_vliw или vliw/help_weights.json "
                               "не попал в установку."))
        print("  " + Style.dim("Пока покажу готовые шаги установки."))
        _печать_ответа("установка", полный=True)
        return None

    результат = help_nnl.спросить(текст)
    if результат is None:
        _не_понял()
        return None
    тема, _ = результат
    if тема == help_nnl.БЕСЕДА:
        return 1 if _беседа(текст) else None
    return _показать_кратко(тема)


def _главное_меню() -> int | str | None:
    пакеты = missing()
    первый = "Установить и запустить" if пакеты else "Запустить NEX CLI"
    return _меню(
        [
            (первый, "поставить недостающее и открыть"),
            ("Проверить окружение", "Python, пакеты, терминал"),
            ("Что такое NEX CLI", "коротко о планировщике"),
            ("Задать вопрос", "написать обычными словами"),
            ("Выход", ""),
        ],
        заголовок="Чем помочь?",
        подсказка="↑/↓ — выбор · Enter — подтвердить",
        приём_текста=True,
    )


def welcome(extra: str | None = None) -> int:
    """Экран-помощник: запрос → план → согласие → выполнение.

    Код 0 — полноэкранный интерфейс открылся; 1 — пользователь вышел.
    """
    render.apply_theme(_BOOT_THEME)
    # Прямой вызов (не через cli.main) не проходил setup_output: в свежем
    # cmd оставались cp866 и выключенный VT, и экран выглядел сломанным.
    render.utf8_console()
    if render.Style.enabled:
        render.enable_vt()
    ширина = _ширина()
    for строка in _шапка_кратко():
        print(строка)
    print()
    for строка in _рамка(_приветствие(), "NNL-помощник", ширина):
        print(строка)
    print()
    _печать_причины(extra)
    print("  " + Style.dim(_статус()))
    print()
    print("  " + Style.dim("Можно сразу напечатать запрос: «запусти», «нет textual», «не работает»."))
    print()

    while True:
        выбор = _главное_меню()
        if выбор is None:
            print("  " + Style.dim("До встречи. Запустить снова: "
                                   + f"{_exe()} -m vliw"))
            return 1
        if isinstance(выбор, str):
            код = _обработать_запрос(выбор, extra)
        elif выбор == 0:
            код = _показать_план(_план_запуска())
        elif выбор == 1:
            код = _показать_план(_план_проверки())
        elif выбор == 2:
            код = _показать_кратко("зачем")
        elif выбор == 3:
            код = _задать_вопрос(extra)
        else:
            print("  " + Style.dim("До встречи. Запустить снова: "
                                   + f"{_exe()} -m vliw"))
            return 1
        if код == 0:
            return 0
        if код == 1:
            return 1
        print()


# --------------------------------------------------------------------------
# Статический вывод для пайпов, CI и тестов
# --------------------------------------------------------------------------


def lines(extra: str | None = None) -> list[str]:
    """Готовые строки экрана (без печати) — удобно проверять в тестах."""
    exe = _exe()
    out: list[str] = [""]
    out += render_title(indent="  ")
    out += [
        "",
        "  " + paint("warning", "полноэкранный интерфейс не запустился")
        + Style.dim("  ·  экран приветствия и установки"),
    ]

    out += _заголовок("Почему открылся этот экран")
    for r in reasons(extra):
        out.append(_пункт(r))
    out.append("    " + Style.dim(_статус()))

    out += [""]
    out += _рамка(_приветствие(), "NNL-помощник", _ширина())

    out += _заголовок("Что это за программа")
    for строка in _о_продукте():
        out.append("  " + строка)

    missing_pkgs = missing()
    if missing_pkgs:
        out += _заголовок("Установить (Windows / macOS / Linux)")
        out.append("    " + paint("success", f"{exe} -m pip install "
                                            + " ".join(f'"{p}"' for p in missing_pkgs)))
        project = _project_dir()
        if project is not None:
            out += [
                "",
                "  " + paint("accent", "Или из каталога проекта (заодно ставит сам NEX CLI):"),
                "    " + Style.dim(f"cd {project}"),
                "    " + paint("success", f'{exe} -m pip install -e ".[tui]"'),
            ]
        out += [
            "",
            "  " + paint("accent", "Пошагово, с отдельным окружением:"),
            "    " + Style.dim(f"cd {project if project else 'путь/к/каталогу/проекта'}"),
            "    " + paint("success", f"{exe} -m venv .venv"),
            "    " + Style.dim(".venv\\Scripts\\activate        (Windows)"
                                   "   /   source .venv/bin/activate   (Linux, macOS)"),
            "    " + paint("success", "python -m pip install --upgrade pip"),
            "    " + paint("success", 'python -m pip install "textual>=8.2" "rich>=13"'),
            "",
            "  " + paint("accent", "Проверить, что встало:"),
            "    " + paint("success",
                          f'{exe} -c "import textual, rich; '
                          f'print(textual.__version__, rich.__version__)"'),
        ]

    out += [
        "",
        "  " + paint("accent", "Запустить:"),
        "    " + paint("success", f"{exe} -m vliw"),
        "",
        "  " + Style.dim("В терминале этот экран умеет сам поставить недостающее "
                          "и открыть NEX CLI — без ручного ввода команд."),
        "",
        "  " + Style.dim("Работает и без установки:"),
        "    " + Style.dim(f"{exe} -m vliw run slotclash"),
        "    " + Style.dim(f"{exe} -m vliw compare"),
        "    " + Style.dim(f"{exe} -m vliw --help"),
        "",
        "  " + Style.dim("Совсем без панелей, построчно:"),
        "    " + Style.dim(f"{exe} -m vliw --plain"),
    ]

    out += _заголовок("Если окно не открывается")
    out += [
        "    " + Style.dim("Запускайте из настоящего окна терминала: PowerShell, cmd,"),
        "    " + Style.dim("Windows Terminal или обычный терминал Linux — не из пайпа,"),
        "    " + Style.dim("не из перенаправленного вывода и не из встроенной консоли IDE."),
        "    " + Style.dim(f'{exe} -c "import sys; '
                          'print(sys.stdin.isatty(), sys.stdout.isatty())"'),
        "    " + Style.dim("должно напечатать: True True"),
    ]

    if missing_pkgs:
        out += [
            "",
            "  " + Style.dim("Нет pip?"),
            "    " + Style.dim(f"{exe} -m ensurepip --upgrade"),
        ]

    out += [
        "",
        "  " + Style.dim("Окружение:"),
        "    " + Style.dim(_статус()),
        "    " + Style.dim(sys.executable),
    ]
    if _store_stub():
        out += [
            "",
            "  " + paint("error", "внимание: это заглушка Microsoft Store (WindowsApps)."),
            "  " + Style.dim("поставьте Python с python.org или используйте полный путь к python.exe"),
        ]
    out.append("")
    return out


def explain(extra: str | None = None) -> int:
    """Показать экран. В терминале — интерактивно, в пайпе — статически."""
    if _tty():
        return welcome(extra)
    render.apply_theme(_BOOT_THEME)
    for line in lines(extra):
        print(line)
    return 1
