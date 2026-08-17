"""Полноэкранный интерфейс NEX на Textual.

Пакет заменяет прежний curses-интерфейс (`vliw.ui.tui`), но не удаляет его:
если Textual не установлен, `vliw.cli` откатывается на старый экран, а с
`--plain` — на построчный режим. Логика планирования сюда не переезжает:
здесь только интерфейс, данные по-прежнему приходят из `vliw.core`.
"""

from __future__ import annotations

import os
import sys

# Терминалы, про которые известно, что 24-битный цвет они понимают. WSL и
# большинство дистрибутивов выставляют TERM=xterm-256color и НЕ выставляют
# COLORTERM — библиотека вывода из-за этого честно считает, что цветов 256,
# и сводит поверхности интерфейса (полотно, панель, активная панель) в один
# почти чёрный: между #0b0d12 и #141822 в палитре из 256 цветов разницы нет.
_TRUECOLOR_HINTS = ("256color", "kitty", "alacritty", "wezterm", "ghostty",
                    "contour", "foot", "truecolor", "direct")


def prefer_truecolor() -> None:
    """Разрешить 24-битный цвет, если терминал на него похож.

    Ничего не делает, если COLORTERM уже задан (пользователь или терминал
    сказали своё слово) или если TERM не похож на современный: на линуксовой
    консоли и в `dumb` 24-битные последовательности только испортят вывод.
    """
    if os.environ.get("COLORTERM"):
        return
    term = os.environ.get("TERM", "").lower()
    if os.environ.get("WT_SESSION") or any(h in term for h in _TRUECOLOR_HINTS):
        os.environ["COLORTERM"] = "truecolor"


def available() -> bool:
    """Можно ли поднять полноэкранный интерфейс в этом окружении."""
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return False
    try:
        import textual  # noqa: F401
    except Exception:
        return False
    return True


def run(session, execute, commands, start_mode: str | None = None) -> int:
    prefer_truecolor()
    from .app import NexApp

    app = NexApp(session, execute, commands, start_mode=start_mode)
    app.run()
    return app.return_code or 0
