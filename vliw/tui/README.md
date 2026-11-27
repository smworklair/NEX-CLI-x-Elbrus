# TUI: Code Map for Edits

Fullscreen workspace built on [Textual](https://github.com/Textualize/textual).
Single process, single app (`NexApp`), four modes inside: CODE, LAB, AGENT, CORE.
Screens only read already computed data.

User-facing behavior: [`docs/CODE_MODE.md`](../../docs/CODE_MODE.md) and [`docs/LAB_MODE.md`](../../docs/LAB_MODE.md). This file maps where everything lives in code.

## File Map

```text
vliw/tui/
  app.py             NexApp: entry point and mode switching
  bridge.py          background computation so the UI never freezes
  palette.py         theme color roles
  widgets.py         reusable panels, chips, toolbars
  nex.tcss           all styling, no inline styles
  screens/
    base.py          ModeScreen: Esc ladder, panel expand, compact layouts
    picker.py        mode selection screen (1–4)
    code_screen.py   CODE
    lab_screen.py    LAB
    core_screen.py   CORE
    agent_screen.py  AGENT
```

## Entry Point

`NexApp.__init__` receives `session`, the `execute` callback, and the command list from `cli.py`.
`open_mode(name)` mounts a screen by name (`code` / `lab` / `mind` / `work`) and keeps one instance per session. CODE opens first; other modes are exit points via `Ctrl+O`.

## Shared Contract

All screens inherit from `ModeScreen`, which provides:

- the `Esc` ladder: hint → expanded panel → exit mode;
- double-click to expand any panel;
- three terminal compactness classes (`.narrow`, `.tight`, `.low`).

Subclass `ModeScreen` for any new screen rather than building layout mechanics from scratch.

## Boundary with the Core

No screen invokes a scheduler directly. The single place where `GreedyListScheduler` / `OracleScheduler` are instantiated and `.schedule()` is called is `Session.results()` in `vliw/cli.py`, outside both `core/` and `tui/`. Screens read `session.dag_obj`, `session.results()`, and the finished `Schedule`.

**Practical takeaway:** a new panel, zoom view, theme, or layout belongs in `tui/`. Changing how a scheduler chooses a schedule belongs in `core/`, which is a separate task.

## Safe to Modify

- **Colors and themes** — `palette.py` and `vliw/ui/themes/*.json`.
- **Layout and styling** — `nex.tcss`.
- **New panel** — copy `Panel(...)` from `lab_screen.py` and read data from `session`.
- **New screen** — subclass `ModeScreen`, register it in `app.py:open_mode` and `picker.py`.

## Safe to Remove

Modes are independent: `_modes` is a dictionary, not a fixed-length list. Removing CORE or AGENT means removing the entry from `picker.py` and omitting its registration in `app.py:open_mode`. Everything else keeps working.

## Do Not Touch

`vliw/core/` — the scheduling algorithm — is intentionally closed to casual edits. The project's negative result was measured on this exact pair of schedulers; changing it without care invalidates those measurements. Plug in a custom scheduler via the contract in [`../core/api.py`](../core/api.py).
