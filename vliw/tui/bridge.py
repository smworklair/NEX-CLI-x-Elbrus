"""Bridge to the core: execute a command and capture its text output.

`vliw.cli` commands print pre-formatted ANSI strings to stdout — their reports
(tables, frames, schedules) are already debugged and reused here as is. This
bridge has one job: intercept that stream and hand it to a widget.

Anything the UI renders with its own widgets (schedule grid, interpreter
memory, dialog tape) bypasses this bridge and reads directly from `vliw.core`.
The bridge is only for commands whose output is a text report.
"""

from __future__ import annotations

import contextlib
import io

from ..ui import render


class Capture(io.TextIOBase):
    """stdout sink that accumulates a command's entire output."""

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
    """Run a command line through the core and return `(output, error)`.

    Report width (`render.W`) is temporarily matched to the destination pane so
    tables and frames lay out cleanly instead of wrapping to a stale terminal
    width.
    """
    cap = Capture()
    old_w = render.W
    render.W = max(render.W_MIN, min(render.W_MAX, width))
    err = ""
    try:
        with contextlib.redirect_stdout(cap):
            execute(line)
    except KeyboardInterrupt:
        err = "interrupted"
    except SystemExit as e:
        err = str(e)
    except Exception as e:  # a command error must never crash the UI
        err = f"{type(e).__name__}: {e}"
    finally:
        render.W = old_w
    return cap.value, err


class EventPump:
    """Scheduler event sink: marshals events from a worker thread to the UI.

    Why a dedicated pump instead of `call_from_thread` per event:
    llama.cpp streams output one character at a time (`proc.stdout.read(1)`),
    producing thousands of `Token` events per run. Crossing threads per
    character would flood the UI loop before the model finishes writing the
    schedule.

    Text is therefore buffered until a newline and delivered line by line,
    while structural events (placements, repair, verdict) go straight through
    since there are only a handful and each updates the display.
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
            self._flush()            # also show any trailing partial line
        self._app.call_from_thread(self._on_event, ev)

    def _flush(self) -> None:
        text = "".join(self._buf).strip("\n")
        self._buf.clear()
        if text:
            self._app.call_from_thread(self._on_text, text)
