"""Loopback URL validator for local LLM servers.

Local servers are restricted to loopback addresses only: `localhost`,
`127.0.0.0/8`, `::1`. Allowing a remote URL in the "local" provider would
silently send conversations to a remote host under a local label. Lives in
its own module so both `openai_compat` and `llm` can import it without
circular dependencies.
"""

from __future__ import annotations

import ipaddress
import urllib.parse

DEFAULT_LOCAL_URL = "http://localhost:11434/v1"


def local_base_url(url: str = DEFAULT_LOCAL_URL) -> str:
    """Return normalized loopback URL or raise ValueError with a clear reason."""
    raw = (url or "").strip()
    if not raw:
        raise ValueError("Local: server URL is not set (NEX_LOCAL_URL)")
    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme != "http":
        raise ValueError("Local: requires an http:// loopback URL")
    host = (parsed.hostname or "").lower()
    if host in ("localhost", "::1"):
        ok = True
    else:
        try:
            ok = ipaddress.ip_address(host).is_loopback
        except ValueError:
            ok = False
    if not ok:
        raise ValueError("Local: loopback addresses only "
                         "(localhost / 127.0.0.0/8 / ::1)")
    if parsed.query or parsed.fragment:
        raise ValueError("Local: unexpected query/fragment in server URL")
    port = f":{parsed.port}" if parsed.port else ""
    path = parsed.path.rstrip("/")
    return f"http://{parsed.hostname}{port}{path}"
