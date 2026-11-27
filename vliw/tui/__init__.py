"""Full-screen NEX interface built on Textual.

The sole full-screen UI: if Textual is not installed, `vliw.cli` falls back to
line-oriented mode (or directly to `--plain`). Scheduling logic does not live
here: this package handles presentation only, while data still comes from
`vliw.core`.
"""

from __future__ import annotations

import os
import sys

# Terminals known to support 24-bit color. WSL and most Linux distributions set
# TERM=xterm-256color without setting COLORTERM — the output library then
# assumes 256 colors and collapses UI surfaces (canvas, panel, active panel)
# into one near-black shade, since #0b0d12 and #141822 map to the same 256-color
# palette entry.
_TRUECOLOR_HINTS = ("256color", "kitty", "alacritty", "wezterm", "ghostty",
                    "contour", "foot", "truecolor", "direct")


def prefer_truecolor() -> None:
    """Enable 24-bit color when the terminal appears to support it.

    Does nothing if COLORTERM is already set (the user or terminal has already
    decided) or if TERM does not look modern: on the Linux console or `dumb`,
    24-bit escape sequences would only corrupt output.
    """
    if os.environ.get("COLORTERM"):
        return
    term = os.environ.get("TERM", "").lower()
    if os.environ.get("WT_SESSION") or any(h in term for h in _TRUECOLOR_HINTS):
        os.environ["COLORTERM"] = "truecolor"


def available() -> bool:
    """Return whether the full-screen interface can start in this environment."""
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
