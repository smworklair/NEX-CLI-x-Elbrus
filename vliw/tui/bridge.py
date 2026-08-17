"""Мост к ядру: выполнить команду и забрать её вывод как текст.

Команды `vliw.cli` печатают в stdout готовые ANSI-строки — их отчёты (таблицы,
рамки, расписания) уже отлажены и переиспользуются здесь как есть. Задача
моста ровно одна: перехватить этот поток и отдать его виджету.

Всё, что интерфейс рисует СВОИМИ виджетами (сетка расписания, память
интерпретатора, лента диалога), через мост не ходит — там данные берутся из
`vliw.core` напрямую. Мост нужен для команд, у которых вывод — отчёт.
"""

from __future__ import annotations

import contextlib
import io

from ..ui import render


class Capture(io.TextIOBase):
    """stdout-приёмник: копит вывод команды целиком."""

    def __init__(self) -> None:
        self._parts: list[str] = []

    def write(self, s: str) -> int:
        self._parts.append(s)
        return len(s)

    def writable(self) -> bool:
        return True

    def flush(self) -> None:
        pass

    @property
    def value(self) -> str:
        return "".join(self._parts)


def run_command(execute, line: str, width: int) -> tuple[str, str]:
    """Выполнить строку ядром. Вернуть (вывод, ошибка).

    Ширина отчётов (`render.W`) выставляется под ту панель, куда вывод поедет:
    иначе таблицы и рамки сверстаются под старую ширину терминала и поедут.
    """
    cap = Capture()
    old_w = render.W
    render.W = max(render.W_MIN, min(render.W_MAX, width))
    err = ""
    try:
        with contextlib.redirect_stdout(cap):
            execute(line)
    except KeyboardInterrupt:
        err = "прервано"
    except SystemExit as e:
        err = str(e)
    except Exception as e:  # ошибка команды не должна ронять интерфейс
        err = f"{type(e).__name__}: {e}"
    finally:
        render.W = old_w
    return cap.value, err
