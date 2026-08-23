"""Режим «/»: палитра команд и подстановка аргументов.

Это не украшение. Пока в поле есть ведущий «/», интерфейс в режиме слеша:
фильтр по имени, стрелки по списку, Tab подставляет, пробел открывает
аргументы, Enter выполняет, Esc закрывает.
"""

from __future__ import annotations

from ..core import PROFILES, SCENARIOS

#: Порядок групп команд в справке и палитре. Идентификатор → заголовок.
#: Живёт здесь, а не в cli.py: палитра вставляет заголовки сама и не должна
#: тянуть реестр команд (cli импортирует этот модуль, не наоборот).
GROUPS = [
    ("sched",   "расписание"),
    ("graph",   "граф · диагноз"),
    ("machine", "модель машины"),
    ("runs",    "прогоны"),
    ("agent",   "агент · обучение"),
    ("data",    "данные"),
    ("session", "сессия"),
]

#: Сколько команд должно быть на экране, чтобы появились заголовки групп.
#: Короткий фильтр («/r» → три штуки) читается и без них.
HEADER_THRESHOLD = 8

# Что предлагать после имени команды и пробела.
_ARGS: dict[str, tuple[str, object]] = {
    "run":     ("сценарий", sorted(SCENARIOS)),
    "compare": ("сценарий", sorted(SCENARIOS)),
    "play":    ("кто", ["baseline", "oracle"]),
    "asm":     ("кто", ["baseline", "oracle"]),
    "doctor":  ("кто", ["baseline", "oracle"]),
    "model":   ("профиль", list(PROFILES) + ["measured", "naive"]),
    "theme":   ("тема", None),
    "mode":    ("панель", ["work", "lab", "mind", "code"]),
    "code":    ("действие", ["run", "show", "save", "load", "clear"]),
}


def parse_slash(buf: str) -> tuple[str, str, str] | None:
    """Вернуть (команда, уже набранный аргумент, хвост после /) или None."""
    if not buf.startswith("/"):
        return None
    rest = buf[1:]
    if " " not in rest:
        return rest.strip().lower(), "", rest
    name, _, arg = rest.partition(" ")
    return name.lower(), arg, rest


def command_hits(commands: list[dict], prefix: str) -> list[dict]:
    q = prefix.lower()
    return [c for c in commands if c["name"].startswith(q)]


def _arg_values(spec) -> list[str]:
    label, values = spec
    if values is None and label == "тема":
        from . import theme

        return theme.list_themes()
    if callable(values):
        return list(values())
    return list(values or [])


def arg_hits(command: str, typed: str) -> list[dict]:
    spec = _ARGS.get(command)
    if not spec:
        return []
    label, _raw = spec
    values = _arg_values(spec)
    q = typed.strip()
    out = []
    for v in values:
        if not q or v.startswith(q) or q in v:
            out.append({
                "name": v,
                "arg": "",
                "help": label,
                "kind": "arg",
            })
    return out


def _with_headers(items: list[dict]) -> list[dict]:
    """Вставить заголовки групп в длинный список команд.

    Заголовок — пункт kind="header": палитра рисует его плашкой и не даёт
    выбрать (см. Palette.selected/step). Короткий фильтр остаётся без
    заголовков — там они шумят, а не организуют.
    """
    if len(items) < HEADER_THRESHOLD:
        return items
    titles = dict(GROUPS)
    out: list[dict] = []
    last = None
    for c in items:
        g = c.get("group", "")
        if g != last:
            last = g
            title = titles.get(g)
            # Команды без группы (экранные инструменты вроде /view) идут
            # в хвосте без плашки: заголовок «пусто» хуже отсутствия.
            if title:
                out.append({"name": "", "arg": "", "help": title,
                            "kind": "header"})
        out.append(c)
    return out


def items_for(buf: str, commands: list[dict]) -> list[dict]:
    """Пункты палитры для текущего буфера. Пусто — режим слеша закрыт."""
    parsed = parse_slash(buf)
    if parsed is None:
        return []
    name, arg, rest = parsed
    if " " not in rest:
        hits = command_hits(commands, name)
        return _with_headers([{**c, "kind": "cmd"} for c in hits])
    return arg_hits(name, arg)


def apply_tab(buf: str, selected: dict) -> str:
    """Tab: подставить выбранный пункт, оставить место для аргумента."""
    kind = selected.get("kind", "cmd")
    if kind == "arg":
        cmd = buf[1:].split(" ", 1)[0]
        return f"/{cmd} {selected['name']}"
    name = selected["name"]
    if selected.get("arg"):
        return f"/{name} "
    return f"/{name}"


def apply_enter(buf: str, selected: dict | None) -> str:
    """Enter: готовая команда к запуску."""
    if selected is None:
        return buf.strip()
    if selected.get("kind") == "arg":
        cmd = buf[1:].split(" ", 1)[0]
        return f"/{cmd} {selected['name']}"
    name = selected["name"]
    # если уже дописали аргумент руками — не затирать
    rest = buf[1:]
    if " " in rest and rest.split(" ", 1)[1].strip():
        return buf.strip()
    return f"/{name}"


def complete_plain(buf: str, commands: list[dict]) -> list[str]:
    """Варианты для Tab в построчном режиме (readline)."""
    if " " not in buf:
        bare = buf.lstrip("/")
        return sorted("/" + c["name"] for c in commands if c["name"].startswith(bare))
    head, _, tail = buf.partition(" ")
    cmd = head.lstrip("/")
    spec = _ARGS.get(cmd)
    if not spec:
        return []
    return sorted(f"{head} {v}" for v in _arg_values(spec) if v.startswith(tail))
