"""Reading and writing `.env` at the project root — stdlib only.

The file is in `.gitignore` and never committed: it is the only place where
CLI commands (`/ai`, `/key`) persist keys. Format: `NAME=value`, `#` starts
a comment. Edits are surgical: comments, line order, and unrelated variables
are preserved; only the target line is updated (or appended at the end).
Setting a value to `None` removes the line.
"""

from __future__ import annotations

import os
from pathlib import Path


def load(path: str | Path) -> dict[str, str]:
    """Parse `.env`: `NAME=value`, `#` comment, strips surrounding quotes."""
    out: dict[str, str] = {}
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return out
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _quote(value: str) -> str:
    if any(c in value for c in " \t#\"'"):
        return '"' + value.replace('"', "") + '"'
    return value


def save(path: str | Path, updates: dict[str, str | None]) -> list[str]:
    """Apply updates to `.env`. Returns names of keys actually written.

    Keys mapped to `None` are removed. Creates the file if missing.
    """
    p = Path(path)
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    pending = dict(updates)
    out: list[str] = []
    for i, line in enumerate(lines):
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, _ = s.partition("=")
        k = k.strip()
        if k in pending:
            v = pending.pop(k)
            if v is None:
                lines[i] = f"# {k}= (removed by {__name__})"
            else:
                lines[i] = f"{k}={_quote(v)}"
                out.append(k)
    for k, v in pending.items():
        if v is None:
            continue
        lines.append(f"{k}={_quote(v)}")
        out.append(k)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def mask(value: str) -> str:
    """Display a key so it cannot be copied from terminal output."""
    v = (value or "").strip()
    if len(v) <= 8:
        return f"•×{len(v)}"
    return f"{v[:3]}…{v[-2:]} (len {len(v)})"


def persist(path: str | Path, updates: dict[str, str | None]) -> None:
    """Persist settings: immediately in process env and in `.env` (outside git).

    Single entry point for `/ai`, `/key`, and pasting a key in AGENT mode so
    all three stay in sync.
    """
    save(path, updates)
    for k, v in updates.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
