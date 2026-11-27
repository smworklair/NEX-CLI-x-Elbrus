"""NEX application: the CODE workspace and the screens branched from it.

Opens into CODE — the e2k assembly editor with its bottom dock. Other screens
(LAB, AGENT, full-screen CORE) are no longer co-equal starting modes: you
navigate to them via `/clear` (or ^O) rather than starting in them. See
`NexApp.HOME` for the rationale.

There are still no global hotkeys for switching screens: the entire keyboard,
including digits, belongs to the editor and input line.
"""

from __future__ import annotations

from pathlib import Path

from textual.app import App
from textual.scrollbar import ScrollBarRender

from . import palette

#: Textual scrollbars draw caps with thin block glyphs (▁▂▃…); in fonts lacking
#: those glyphs, every cell turns into a replacement box. The full block █ is
#: present in every console font — we trade sub-cell cap smoothness for
#: guaranteed readability.
ScrollBarRender.VERTICAL_BARS = ["█"]
ScrollBarRender.HORIZONTAL_BARS = ["█"]

CSS_FILE = Path(__file__).parent / "nex.tcss"


class NexApp(App):
    """App shell: holds the core session and switches between screens."""

    CSS_PATH = CSS_FILE
    ENABLE_COMMAND_PALETTE = False

    def __init__(self, session, execute, commands, start_mode: str | None = None):
        super().__init__()
        self.session = session
        self.execute = execute
        self.commands = commands
        self.start_mode = start_mode
        self._theme_source = ""
        self._entered = False
        #: Installed mode screens: mode id -> Textual screen name. Each screen
        #: lives as a single instance per session; see `_mode_screen`.
        self._modes: dict[str, str] = {}
        #: Where Esc returns from an opened pane; None returns to the mode picker.
        self.back_to: str | None = None

    # --- palette ----------------------------------------------------------

    def get_css_variables(self) -> dict[str, str]:
        base = super().get_css_variables()
        base.update(palette.variables())
        return base

    def set_mode_theme(self, mode: str) -> None:
        """Apply mode-specific accent: same surfaces, distinct active color."""
        name = f"nex-{mode}"
        self.register_theme(palette.make_theme(mode))
        if self.theme != name:
            self.theme = name

    def reload_palette(self) -> None:
        """Reload colors after `/theme`: the theme restyles the entire tool."""
        from ..ui import render

        if render.THEME.name == self._theme_source:
            return
        self._theme_source = render.THEME.name
        mode = getattr(self.screen, "mode", "lab")
        self.register_theme(palette.make_theme(mode))
        self.refresh_css()
        # Do not rebuild the screen: re-running compose() would wipe everything
        # mounted and drawn during the session. Instead, ask the screen to
        # repaint — it reads colors from the palette at draw time, so the new
        # theme takes effect automatically.
        repaint = getattr(self.screen, "repaint", None)
        if callable(repaint):
            repaint()

    # --- screens ----------------------------------------------------------

    #: Default destination when launching the tool.
    #:
    #: Previously this was a four-card picker, which caused layout bloat across
    #: the entire UI. When all modes are equal, each has to act as a standalone
    #: app — packing editor, schedule, inspect, git, and console into CODE all
    #: at once. The screen felt cramped not from bad layout, but because it
    #: tried to be everything at once.
    #:
    #: CODE is the one screen where users bring their own input: real `.s`
    #: assembly from lcc. Everything else is a view onto that code, now living
    #: as tabs in its bottom dock (schedule, inspect, issues, output, core).
    #: Full-screen LAB and AGENT still exist, but as destinations you jump to
    #: from work rather than co-equal quarters of a main menu.
    HOME = "code"

    #: What screen opens on launch — separate from which screen is primary.
    #: CODE remains the primary workspace conceptually, but launching straight
    #: into it hid the other three screens since ^O was not surfaced anywhere.
    #: The mode picker costs one keypress and immediately shows what exists.
    START_AT_PICKER = True

    def on_mount(self) -> None:
        from ..ui import render

        self._theme_source = render.THEME.name
        if self.start_mode:
            self.open_mode(self.start_mode)
        elif self.START_AT_PICKER:
            self.to_picker()
        else:
            self.open_mode(self.HOME)

    def _go(self, screen) -> None:
        """Push the first screen, then switch in place so the stack stays flat."""
        if self._entered:
            self.switch_screen(screen)
        else:
            self._entered = True
            self.push_screen(screen)

    def _mode_screen(self, mode: str, cls) -> str:
        """Return the installed screen name for a mode (one instance per session).

        Previously each transition rebuilt the screen from scratch, so leaving
        CODE wiped open file tabs, cursor position, computed schedules, and
        dialog history. Only the active buffer survived in `session.code_text`,
        meaning returning restored one file instead of three and forced
        re-running already computed schedules.

        `install_screen` keeps the instance alive across switches: the screen
        goes off-stage without being torn down, and returning restores exact
        state. That makes double-clicking a tab a cheap gesture.
        """
        name = self._modes.get(mode)
        if name is None:
            name = f"mode-{mode}"
            self.install_screen(cls(), name=name)
            self._modes[mode] = name
        return name

    def to_picker(self) -> None:
        from .screens.picker import MODES, PickerScreen

        current = getattr(self.screen, "mode", None)
        index = next((i for i, m in enumerate(MODES) if m["id"] == current), 0)
        # Going through the picker leaves the previous context completely rather
        # than peeking into a sub-view: clear the return target so Esc from the
        # newly chosen mode does not bounce back to CODE unexpectedly.
        self.back_to = None
        self.set_mode_theme("lab")
        self._go(PickerScreen(selected=index))

    def warm_model(self, mode: str) -> None:
        """Warm up the local model in the background while the user reads.

        The first question in a session is slow not because of generation: the
        server takes ~7 s to start, and the 1451-token agent system prompt has
        to be evaluated on CPU. Both are one-time costs. Doing them on demand
        makes the user wait a minute on "hello"; doing them ahead of time is
        essentially free while the user reads hints and types.

        Local provider only: cloud providers need no warmup, and hitting the
        network unasked on screen open is out of bounds.
        """
        from ..agent import llm

        if not llm.is_local():
            return
        # Only prefill the system prompt where it will actually be used (dialog).
        # LAB uses a different prompt (graph, not facts); they only share the
        # server process itself.
        system = None
        if mode == "mind":
            from ..agent import context

            try:
                system = context.system_prompt(self.session, False)
            except Exception:
                system = None
        self._warm_worker(system)

    def _warm_worker(self, system) -> None:
        import threading

        from ..agent import local

        threading.Thread(target=local.warmup, args=(system,),
                         daemon=True).start()

    def open_mode(self, mode: str, back_to: str | None = None) -> None:
        """Open a mode screen. `back_to` sets where the top-level Esc returns."""
        if mode == "work":
            from .screens.core_screen import CoreScreen as cls
        elif mode == "mind":
            from .screens.agent_screen import AgentScreen as cls
        elif mode == "code":
            from .screens.code_screen import CodeScreen as cls
        else:
            from .screens.lab_screen import LabScreen as cls
            mode = "lab"
        self.session.focus = mode
        self.session.mode = "chat" if mode == "mind" else "explore"
        self.back_to = back_to
        self._go(self._mode_screen(mode, cls))
        if mode in ("mind", "lab"):
            self.warm_model(mode)

    def back_out(self) -> None:
        """Top-level Esc from a mode screen: return to the mode picker.

        `back_to` is set by callers that detour the user out of their current
        workspace and must return them there. Currently panes expand in place
        without switching screens, but the hook remains as the single decision
        point for where top-level Esc goes.
        """
        if self.back_to:
            target, self.back_to = self.back_to, None
            self.open_mode(target)
            return
        self.to_picker()
