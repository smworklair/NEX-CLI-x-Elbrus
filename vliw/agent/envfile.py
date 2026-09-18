"""Чтение и запись `.env` в корне проекта — только stdlib.

Файл в `.gitignore` и никогда не коммитится: это единственное место, куда
CLI-команды (`/ai`, `/key`) сохраняют ключи. Формат — `ИМЯ=значение`,
`#` — комментарий. Сохранение бережное: комментарии, порядок строк и чужие
переменные не трогаются, меняется только нужная строка (или дописывается
в конец). Значение `None` — удалить строку.
"""

from __future__ import annotations

import os
from pathlib import Path


def load(path: str | Path) -> dict[str, str]:
    """Разбор `.env`: `ИМЯ=значение`, `#` — комментарий, кавычки снимаются."""
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
    """Применить изменения к `.env`. Возвращает имена реально записанных ключей.

    Ключ со значением `None` удаляется. Файл создаётся, если его не было.
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
                lines[i] = f"# {k}= (удалён {__name__})"
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
    """Показать ключ так, чтобы его нельзя было скопировать из вывода."""
    v = (value or "").strip()
    if len(v) <= 8:
        return f"•×{len(v)}"
    return f"{v[:3]}…{v[-2:]} (длина {len(v)})"


def persist(path: str | Path, updates: dict[str, str | None]) -> None:
    """Сохранить настройки: сразу в процесс и в `.env` (вне git).

    Единая точка для `/ai`, `/key` и вставки ключа в АГЕНТЕ: иначе три места
    рассинхронизируются (одно пишет файл, другое забывает окружение).
    """
    save(path, updates)
    for k, v in updates.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
