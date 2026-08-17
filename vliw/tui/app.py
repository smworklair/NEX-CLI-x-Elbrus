"""Приложение NEX: выбор режима и три рабочих места.

Переключения режимов на лету нет. Из режима выходят через `/clear` (или ^O) —
и снова выбирают, чем заняться. Это осознанное решение: ядро, разбор и агент —
разные занятия с разной раскладкой экрана, а не три вкладки одного окна.
Побочная выгода — вся клавиатура, включая цифры, принадлежит строке ввода.
"""

from __future__ import annotations

from pathlib import Path

from textual.app import App

from . import palette

CSS_FILE = Path(__file__).parent / "nex.tcss"


class NexApp(App):
    """Оболочка: держит сессию ядра и меняет экраны."""

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

    # --- палитра ----------------------------------------------------------

    def get_css_variables(self) -> dict[str, str]:
        base = super().get_css_variables()
        base.update(palette.variables())
        return base

    def set_mode_theme(self, mode: str) -> None:
        """Акцент под режим: одна поверхность, разный цвет активного."""
        name = f"nex-{mode}"
        self.register_theme(palette.make_theme(mode))
        if self.theme != name:
            self.theme = name

    def reload_palette(self) -> None:
        """Перечитать цвета после `/theme`: тема меняет весь инструмент."""
        from ..ui import render

        if render.THEME.name == self._theme_source:
            return
        self._theme_source = render.THEME.name
        mode = getattr(self.screen, "mode", "lab")
        self.register_theme(palette.make_theme(mode))
        self.refresh_css()
        # Пересобирать экран нельзя: заново собранный compose() потеряет всё,
        # что смонтировано и нарисовано по ходу работы. Вместо этого экран
        # перерисовывает своё содержимое — цвета он берёт из палитры в момент
        # отрисовки, поэтому новая тема применяется сама.
        repaint = getattr(self.screen, "repaint", None)
        if callable(repaint):
            repaint()

    # --- экраны -----------------------------------------------------------

    def on_mount(self) -> None:
        from ..ui import render

        self._theme_source = render.THEME.name
        if self.start_mode:
            self.open_mode(self.start_mode)
        else:
            self.to_picker()

    def _go(self, screen) -> None:
        """Первый экран кладём на стек, дальше — заменяем: стек не растёт."""
        if self._entered:
            self.switch_screen(screen)
        else:
            self._entered = True
            self.push_screen(screen)

    def to_picker(self) -> None:
        from .screens.picker import MODES, PickerScreen

        current = getattr(self.screen, "mode", None)
        index = next((i for i, m in enumerate(MODES) if m["id"] == current), 1)
        self.set_mode_theme("lab")
        self._go(PickerScreen(selected=index))

    def open_mode(self, mode: str) -> None:
        if mode == "work":
            from .screens.core_screen import CoreScreen as cls
        elif mode == "mind":
            from .screens.agent_screen import AgentScreen as cls
        else:
            from .screens.lab_screen import LabScreen as cls
            mode = "lab"
        self.session.focus = mode
        self.session.mode = "chat" if mode == "mind" else "explore"
        self._go(cls())
