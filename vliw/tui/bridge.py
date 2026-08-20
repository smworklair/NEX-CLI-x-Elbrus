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


class EventPump:
    """Сток событий планировщика: из рабочего потока — в главный.

    Зачем отдельная штука, а не просто `call_from_thread` на каждое событие.
    llama.cpp отдаёт вывод ПОСИМВОЛЬНО (`proc.stdout.read(1)`), то есть на
    один прогон приходится несколько тысяч событий `Token`. Переход между
    потоками на каждый символ интерфейс не переживёт — он захлебнётся
    раньше, чем модель допишет расписание.

    Поэтому текст копится до перевода строки и уезжает в интерфейс целыми
    строками, а всё остальное (размещения, починка, вердикт) идёт сразу:
    таких событий единицы, и каждое из них меняет картинку.
    """

    def __init__(self, app, on_text, on_event) -> None:
        self._app = app
        self._on_text = on_text
        self._on_event = on_event
        self._buf: list[str] = []

    def __call__(self, ev) -> None:
        from ..core import Done, Failed, Token

        if isinstance(ev, Token):
            self._buf.append(ev.text)
            if "\n" in ev.text:
                self._flush()
            return
        if isinstance(ev, (Done, Failed)):
            self._flush()            # хвост без перевода строки тоже показать
        self._app.call_from_thread(self._on_event, ev)

    def _flush(self) -> None:
        text = "".join(self._buf).strip("\n")
        self._buf.clear()
        if text:
            self._app.call_from_thread(self._on_text, text)
