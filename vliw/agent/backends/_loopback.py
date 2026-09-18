"""Loopback-валидатор адреса local-сервера.

Local-сервер — только замкнутая петля: `localhost`, `127.0.0.0/8`, `::1`.
Remote URL в «локальном» провайдере означал бы, что разговор уходит чужому
серверу под видом локального. Живёт отдельным файлом: его подключает и
`openai_compat`, и `llm` (пока `models.local_base_url` не добавит главный
агент), без цикла импорта.
"""

from __future__ import annotations

import ipaddress
import urllib.parse

DEFAULT_LOCAL_URL = "http://localhost:11434/v1"


def local_base_url(url: str = DEFAULT_LOCAL_URL) -> str:
    """Нормализованный loopback-адрес или ValueError с человеческой причиной."""
    raw = (url or "").strip()
    if not raw:
        raise ValueError("Local: адрес сервера не задан (NEX_LOCAL_URL)")
    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme != "http":
        raise ValueError("Local: нужен http:// адрес на loopback")
    host = (parsed.hostname or "").lower()
    if host in ("localhost", "::1"):
        ok = True
    else:
        try:
            ok = ipaddress.ip_address(host).is_loopback
        except ValueError:
            ok = False
    if not ok:
        raise ValueError("Local: только loopback-адреса "
                         "(localhost / 127.0.0.0/8 / ::1)")
    if parsed.query or parsed.fragment:
        raise ValueError("Local: лишние query/fragment в адресе сервера")
    port = f":{parsed.port}" if parsed.port else ""
    path = parsed.path.rstrip("/")
    return f"http://{parsed.hostname}{port}{path}"
