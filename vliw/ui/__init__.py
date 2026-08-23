"""Визуализация: превращает данные из `vliw.core` в цветной вывод для терминала.

Ничего не считает про планирование — только форматирует. Голый ANSI по
умолчанию; с установленным `rich` — панели оформляются им (graceful fallback).

  render.py         цвет, ширина, рамки, таблицы, панели (фундамент)
  theme.py          загрузка палитры из themes/*.json
  logo.py           марка workstation, статус-строка
  tables.py         таблицы сценариев/результатов/матрицы/sweep/selfcheck
  schedule_view.py  пачки-рамки, вердикт, границы, критический путь, разбор
  context.py        контекст сессии (она же /status)
  panes.py          три панели workstation: ядро / разбор / агент

Полноэкранный интерфейс живёт в отдельном пакете `vliw.tui` (Textual).
"""

from . import context, logo, panes, render, schedule_view, tables, theme

__all__ = ["render", "theme", "logo", "tables", "schedule_view", "context", "panes"]
