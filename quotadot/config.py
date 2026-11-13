"""Environment-based settings, shared by every plugin."""
from __future__ import annotations

import os
from pathlib import Path


def env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value.strip() if isinstance(value, str) and value.strip() else default


def env_int(name: str, default: int) -> int:
    raw = env(name)
    try:
        return int(raw) if raw is not None else default
    except ValueError:
        raise ValueError(f"{name}={raw!r} is not a whole number") from None


def env_list(name: str, default: str = "") -> list[str]:
    return [p.strip().lower() for p in (env(name) or default).split(",") if p.strip()]


def load_env_file(path: str | Path) -> bool:
    """Read KEY=VALUE lines into os.environ without overriding variables already set.

    Accepts `export KEY=...`, comments, and single- or double-quoted values
    (so RELAYS='[...]' keeps its JSON quotes).
    """
    p = Path(path)
    if not p.is_file():
        return False
    for line in p.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("export "):
            s = s[7:].lstrip()
        key, sep, value = s.partition("=")
        if not sep:
            continue
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        else:
            value = value.split(" #", 1)[0].strip()
        os.environ.setdefault(key, value)
    return True


def short_error(e: Exception) -> str:
    """One readable line for the screen, instead of urllib3's full repr."""
    import requests
    from urllib.parse import urlparse

    if isinstance(e, requests.HTTPError) and e.response is not None:
        host = urlparse(e.response.url).hostname or ""
        return f"HTTP {e.response.status_code} {e.response.reason or ''} from {host}".strip()
    if isinstance(e, (requests.ConnectionError, requests.Timeout)):
        url = getattr(getattr(e, "request", None), "url", "") or ""
        host = urlparse(url).hostname or "server"
        kind = "timed out" if isinstance(e, requests.Timeout) else "unreachable"
        if "SSL" in str(e):
            kind = "TLS error (proxy?)"
        return f"{host} {kind}"
    if isinstance(e, ValueError) and "JSON" in type(e).__name__ + str(e):
        return "response is not JSON"
    return str(e)[:80]
