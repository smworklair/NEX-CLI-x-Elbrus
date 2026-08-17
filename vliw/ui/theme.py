"""Темы оформления: загрузка палитры из JSON.

Тема — это чёрный фон плюс набор именованных ролей («акцент», «рамка»,
«приглашение», …) и цветов операций. Один и тот же файл темы обслуживает оба
режима вывода:

  * обычный построчный режим — роль превращается в ANSI-код (`38;5;N`);
  * полноэкранный TUI на curses — роль превращается в пару (номер цвета,
    атрибуты curses).

Поэтому цвета в JSON заданы индексами 256-цветной палитры терминала: это
единственное представление, которое одинаково понимают и ANSI, и curses.

Цвета операций (DIV/MUL/ADD/…) вынесены в отдельный раздел `ops` намеренно:
это не декор, а ДАННЫЕ. По ним в расписании видно, куда попало деление —
единственная монополия машины (порт `,5`) — и как разошлись остальные
операции по своим каналам. Тема может их перекрашивать, но обязана оставлять
различимыми.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

THEMES_DIR = Path(__file__).parent / "themes"
DEFAULT_THEME = "nex-dark"

# Имя атрибута -> (код ANSI SGR, имя атрибута curses)
_ATTRS = {
    "bold": ("1", "A_BOLD"),
    "dim": ("2", "A_DIM"),
    "underline": ("4", "A_UNDERLINE"),
    "reverse": ("7", "A_REVERSE"),
}


@dataclass(frozen=True)
class Style:
    """Один стиль: цвет из 256-цветной палитры + атрибуты начертания."""

    color: int = 7
    attrs: tuple[str, ...] = ()

    @property
    def ansi(self) -> str:
        """Тело ANSI-кода SGR, например `1;38;5;75`."""
        parts = [_ATTRS[a][0] for a in self.attrs if a in _ATTRS]
        parts.append(f"38;5;{self.color}")
        return ";".join(parts)

    def curses_attr(self, curses_mod) -> int:
        """Битовая маска атрибутов curses (без цвета — цвет задаётся парой)."""
        flag = 0
        for a in self.attrs:
            name = _ATTRS.get(a, (None, None))[1]
            if name:
                flag |= getattr(curses_mod, name, 0)
        return flag


def _parse_style(raw) -> Style:
    if raw is None:
        return Style()
    if isinstance(raw, int):
        return Style(color=raw)
    return Style(
        color=int(raw.get("color", 7)),
        attrs=tuple(raw.get("attrs", ())),
    )


@dataclass
class Theme:
    name: str
    description: str = ""
    roles: dict[str, Style] = field(default_factory=dict)
    ops: dict[str, Style] = field(default_factory=dict)

    def role(self, name: str) -> Style:
        """Стиль роли; неизвестная роль тихо превращается в нейтральный текст."""
        return self.roles.get(name) or self.roles.get("text") or Style()

    def op(self, name: str) -> Style:
        return self.ops.get(name) or self.role("text")

    def ansi(self, role_name: str) -> str:
        return self.role(role_name).ansi

    def op_ansi(self, op_name: str) -> str:
        return self.op(op_name).ansi


def list_themes() -> list[str]:
    """Имена доступных тем (по именам файлов в themes/)."""
    if not THEMES_DIR.is_dir():
        return []
    return sorted(p.stem for p in THEMES_DIR.glob("*.json"))


def load_theme(name: str = DEFAULT_THEME) -> Theme:
    """Загрузить тему по имени. При любой проблеме — встроенная запасная.

    Тема — украшение: битый или отсутствующий JSON не должен ронять
    инструмент, поэтому здесь всё падение гасится в безопасный дефолт.
    """
    path = THEMES_DIR / f"{name}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _fallback_theme(name)

    try:
        return Theme(
            name=data.get("name", name),
            description=data.get("description", ""),
            roles={k: _parse_style(v) for k, v in data.get("roles", {}).items()},
            ops={k: _parse_style(v) for k, v in data.get("ops", {}).items()},
        )
    except Exception:
        return _fallback_theme(name)


def _fallback_theme(name: str) -> Theme:
    """Минимальная тема на базовых цветах — если JSON недоступен или битый."""
    return Theme(
        name=f"{name} (запасная)",
        description="Встроенная запасная палитра на базовых 8 цветах.",
        roles={
            "text": Style(7),
            "dim": Style(7, ("dim",)),
            "faint": Style(7, ("dim",)),
            "accent": Style(6, ("bold",)),
            "accent_soft": Style(6),
            "accent2": Style(3, ("bold",)),
            "accent2_soft": Style(3),
            "success": Style(2),
            "warning": Style(3),
            "error": Style(1, ("bold",)),
            "banner": Style(4, ("bold",)),
            "banner_alt": Style(6, ("bold",)),
            "mountain": Style(6),
            "snow": Style(7, ("bold",)),
            "border": Style(6),
            "border_hi": Style(6, ("bold",)),
            "title": Style(7, ("bold",)),
            "prompt": Style(6, ("bold",)),
            "selection": Style(7, ("reverse",)),
            "sidebar_head": Style(6, ("bold",)),
            "sidebar_key": Style(7, ("dim",)),
            "sidebar_val": Style(7),
            "crit": Style(3, ("bold", "underline")),
            "diverge": Style(1, ("bold",)),
            "work": Style(4, ("bold",)),
            "work_soft": Style(4),
            "lab": Style(6, ("bold",)),
            "lab_soft": Style(6),
            "mind": Style(4, ("bold",)),
            "mind_soft": Style(6),
            "hud": Style(7, ("dim",)),
            "dock": Style(7),
        },
        ops={
            "DIV": Style(5, ("bold",)),
            "MUL": Style(6, ("bold",)),
            "ADD": Style(2),
            "SUB": Style(2),
            "LOAD": Style(3),
            "STORE": Style(3),
            "AND": Style(6, ("dim",)),
            "SHL": Style(6, ("dim",)),
        },
    )
