"""Slash ('/') mode: command palette and argument completion.

While the input buffer starts with '/', the UI stays in slash mode:
prefix filtering, arrow navigation, Tab completion, Space for arguments,
Enter to execute, Esc to dismiss.
"""

from __future__ import annotations

from ..core import PROFILES, SCENARIOS

#: Group order in help and the command palette: group id -> display title.
GROUPS = [
    ("sched",   "schedule"),
    ("graph",   "graph · diagnostics"),
    ("machine", "machine model"),
    ("runs",    "benchmarks"),
    ("agent",   "agent · learned"),
    ("data",    "data"),
    ("session", "session"),
]

#: Minimum number of visible commands before group headers are inserted.
HEADER_THRESHOLD = 8

# Argument suggestions after command name + space.
_ARGS: dict[str, tuple[str, object]] = {
    "run":     ("scenario", sorted(SCENARIOS)),
    "compare": ("scenario", sorted(SCENARIOS)),
    "play":    ("which", ["baseline", "oracle"]),
    "asm":     ("which", ["baseline", "oracle"]),
    "doctor":  ("which", ["baseline", "oracle"]),
    "model":   ("profile", list(PROFILES) + ["measured", "naive"]),
    "theme":   ("theme", None),
    "mode":    ("pane", ["work", "lab", "mind", "code"]),
    "code":    ("action", ["run", "show", "save", "load", "clear"]),
}


def parse_slash(buf: str) -> tuple[str, str, str] | None:
    """Return (command, typed_arg, tail_after_slash) or None."""
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
    if values is None and label == "theme":
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
    """Insert non-selectable kind='header' rows into long command lists."""
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
            if title:
                out.append({"name": "", "arg": "", "help": title,
                            "kind": "header"})
        out.append(c)
    return out


def items_for(buf: str, commands: list[dict]) -> list[dict]:
    """Palette entries for the current buffer. Empty closes slash mode."""
    parsed = parse_slash(buf)
    if parsed is None:
        return []
    name, arg, rest = parsed
    if " " not in rest:
        hits = command_hits(commands, name)
        return _with_headers([{**c, "kind": "cmd"} for c in hits])
    return arg_hits(name, arg)


def apply_tab(buf: str, selected: dict) -> str:
    """Tab: insert selected entry and leave room for an argument."""
    kind = selected.get("kind", "cmd")
    if kind == "arg":
        cmd = buf[1:].split(" ", 1)[0]
        return f"/{cmd} {selected['name']}"
    name = selected["name"]
    if selected.get("arg"):
        return f"/{name} "
    return f"/{name}"


def apply_enter(buf: str, selected: dict | None) -> str:
    """Enter: finalize command string for execution."""
    if selected is None:
        return buf.strip()
    if selected.get("kind") == "arg":
        cmd = buf[1:].split(" ", 1)[0]
        return f"/{cmd} {selected['name']}"
    name = selected["name"]
    # Do not overwrite an argument the user already typed manually.
    rest = buf[1:]
    if " " in rest and rest.split(" ", 1)[1].strip():
        return buf.strip()
    return f"/{name}"


def complete_plain(buf: str, commands: list[dict]) -> list[str]:
    """Tab completions for plain line-by-line mode (readline)."""
    if " " not in buf:
        bare = buf.lstrip("/")
        return sorted("/" + c["name"] for c in commands if c["name"].startswith(bare))
    head, _, tail = buf.partition(" ")
    cmd = head.lstrip("/")
    spec = _ARGS.get(cmd)
    if not spec:
        return []
    return sorted(f"{head} {v}" for v in _arg_values(spec) if v.startswith(tail))
