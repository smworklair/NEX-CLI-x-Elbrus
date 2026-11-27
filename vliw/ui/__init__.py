"""Visualization: turns `vliw.core` data into colored terminal output.

Performs no scheduling logic — formatting only. Raw ANSI by default; uses
`rich` panels when installed (graceful fallback).

  render.py         colors, width, borders, tables, panels (foundation)
  theme.py          palette loader from themes/*.json
  logo.py           workstation banner, status line
  tables.py         tables for scenarios/results/matrix/sweep/selfcheck
  schedule_view.py  wide-instruction boxes, verdict, bounds, critical path, explain
  context.py        session context (also `/status`)
  panes.py          three workstation panes: core / lab / agent

The full-screen TUI lives in a separate package `vliw.tui` (Textual).
"""

from . import context, logo, panes, render, schedule_view, tables, theme

__all__ = ["render", "theme", "logo", "tables", "schedule_view", "context", "panes"]
