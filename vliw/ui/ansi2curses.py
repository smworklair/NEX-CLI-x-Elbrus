"""Мост между обычным выводом и полноэкранным режимом.

Все отрисовщики проекта (`schedule_view`, `tables`, …) выдают обычные строки
с ANSI-кодами — так они работают в построчном режиме. curses же про ANSI
ничего не знает: у него свои пары цветов и битовые атрибуты.

Этот модуль разбирает строку с ANSI-кодами на куски «текст + оформление» и
переводит оформление в атрибуты curses. Благодаря ему полноэкранный режим
переиспользует ВСЕ существующие отрисовщики без единой правки — иначе
пришлось бы писать вторую копию всей визуализации.

Поддерживается ровно то подмножество SGR, которое проект реально использует:
сброс (0), жирный (1), тусклый (2), подчёркивание (4), инверсия (7),
256-цветный текст (38;5;N) и базовые цвета 30–37.
"""

from __future__ import annotations

import re

_SGR = re.compile(r"\x1b\[([0-9;]*)m")

# Кэш пар цветов curses: цвет текста -> номер пары. Пар в терминале ограниченное
# число, поэтому переиспользуем уже заведённые.
_pairs: dict[int, int] = {}
_next_pair = 1
_has_color = False
_max_pairs = 0
_max_colors = 0


def init(curses_mod) -> None:
    """Подготовить цветовую подсистему curses. Вызывать после initscr()."""
    global _has_color, _next_pair, _max_pairs, _max_colors
    _pairs.clear()
    _bg_pairs.clear()
    _next_pair = 1
    try:
        curses_mod.start_color()
        try:
            # Прозрачный фон: терминал сохраняет свой (обычно чёрный) фон,
            # и наш вывод не «выбивается» из общей темы окна.
            curses_mod.use_default_colors()
            bg = -1
        except Exception:
            bg = curses_mod.COLOR_BLACK
        _has_color = curses_mod.has_colors()
        _max_pairs = getattr(curses_mod, "COLOR_PAIRS", 64)
        _max_colors = getattr(curses_mod, "COLORS", 8)
        _pairs["__bg__"] = bg  # type: ignore[index]
    except Exception:
        _has_color = False


def _pair_for(curses_mod, color: int) -> int:
    """Номер пары curses для цвета текста; заводит новую при необходимости."""
    global _next_pair
    if not _has_color:
        return 0
    if color >= _max_colors:
        color = color % max(1, _max_colors)
    if color in _pairs:
        return _pairs[color]
    if _next_pair >= max(2, _max_pairs):
        return 0  # пары кончились — рисуем без цвета, но не падаем
    bg = _pairs.get("__bg__", -1)  # type: ignore[arg-type]
    try:
        curses_mod.init_pair(_next_pair, color, bg)
    except Exception:
        return 0
    _pairs[color] = _next_pair
    _next_pair += 1
    return _pairs[color]


def _attr_from_codes(curses_mod, codes: list[int], attr: int, color: int | None):
    """Применить один набор SGR-кодов к текущему оформлению."""
    i = 0
    while i < len(codes):
        code = codes[i]
        if code == 0:
            attr, color = 0, None
        elif code == 1:
            attr |= curses_mod.A_BOLD
        elif code == 2:
            attr |= curses_mod.A_DIM
        elif code == 4:
            attr |= curses_mod.A_UNDERLINE
        elif code == 7:
            attr |= curses_mod.A_REVERSE
        elif code == 38 and i + 2 < len(codes) and codes[i + 1] == 5:
            color = codes[i + 2]
            i += 2
        elif 30 <= code <= 37:
            color = code - 30
        elif 90 <= code <= 97:
            color = code - 90 + 8
        i += 1
    return attr, color


def parse(curses_mod, line: str, bg: int | None = None) -> list[tuple[str, int]]:
    """Разобрать строку с ANSI на куски `(текст, атрибут curses)`.

    `bg` — фон, на котором текст печатается. В ANSI-строках фона нет (наши
    отрисовщики задают только цвет букв), поэтому без этого параметра текст
    ложится на фон терминала. На залитой панели это давало рваные светлые
    обрывки: заливка оставалась только там, где текста не было.
    """
    out: list[tuple[str, int]] = []
    attr = 0
    color: int | None = None
    pos = 0
    for m in _SGR.finditer(line):
        if m.start() > pos:
            out.append((line[pos:m.start()], _compose(curses_mod, attr, color, bg)))
        body = m.group(1)
        codes = [int(x) for x in body.split(";") if x.isdigit()] or [0]
        attr, color = _attr_from_codes(curses_mod, codes, attr, color)
        pos = m.end()
    if pos < len(line):
        out.append((line[pos:], _compose(curses_mod, attr, color, bg)))
    return out


def _compose(curses_mod, attr: int, color: int | None, bg: int | None = None) -> int:
    # Пока цветовая подсистема не поднята (init() не звали или терминал
    # монохромный), к color_pair даже не прикасаемся: до initscr() он бросает
    # исключение. Начертание (жирный/тусклый) при этом продолжает работать.
    if not _has_color:
        return attr
    if bg is not None:
        # Явный фон панели: текст обязан лечь на него, иначе получится «дыра».
        return attr | pair_fg_bg(curses_mod, color if color is not None else 7, bg)
    if color is None:
        return attr
    pair = _pair_for(curses_mod, color)
    if not pair:
        return attr
    try:
        return attr | curses_mod.color_pair(pair)
    except Exception:
        return attr


_bg_pairs: dict[tuple[int, int], int] = {}


def pair_fg_bg(curses_mod, fg: int, bg: int) -> int:
    """Атрибут для пары «цвет текста на цветном фоне».

    Нужен панелям (поле ввода, подсветка выбранного пункта): у них фон
    отличается от фона терминала, а обычный разбор ANSI знает только цвет
    текста.
    """
    if not _has_color:
        return 0
    key = (fg, bg)
    if key in _bg_pairs:
        return curses_mod.color_pair(_bg_pairs[key])
    global _next_pair
    if _next_pair >= max(2, _max_pairs):
        return 0
    try:
        curses_mod.init_pair(_next_pair, fg, bg)
    except Exception:
        return 0
    _bg_pairs[key] = _next_pair
    _next_pair += 1
    return curses_mod.color_pair(_bg_pairs[key])


def plain_len(line: str) -> int:
    """Видимая длина строки (без ANSI-кодов)."""
    return len(_SGR.sub("", line))


def strip(line: str) -> str:
    return _SGR.sub("", line)


def addstr(curses_mod, win, y: int, x: int, line: str, max_width: int,
           bg: int | None = None) -> None:
    """Напечатать ANSI-строку в окно curses, обрезав по ширине.

    Все исключения гасятся: curses бросает ошибку при печати в самую последнюю
    ячейку окна, и это нормальная ситуация, а не повод падать.
    """
    col = x
    for text, attr in parse(curses_mod, line, bg=bg):
        if col >= x + max_width:
            break
        chunk = text[: max(0, x + max_width - col)]
        if not chunk:
            continue
        try:
            win.addstr(y, col, chunk, attr)
        except Exception:
            pass
        col += len(chunk)
