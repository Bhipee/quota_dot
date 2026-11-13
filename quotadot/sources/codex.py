"""Codex usage: ChatGPT OAuth token from ~/.codex/auth.json -> wham/usage (same as QuotaBar)."""
from __future__ import annotations

import base64
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import requests

from ..config import env, short_error
from ..registry import Source, source

log = logging.getLogger("quotadot")

# Public client id of the Codex CLI; used only to refresh its own OAuth token.
CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
TOKEN_URL = "https://auth.openai.com/oauth/token"
USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"
PLAN_NAMES = {"prolite": "Pro 5x", "pro": "Pro 20x", "self_serve_business_prolite": "Business Premium"}


@dataclass
class Window:
    label: str                 # "5h" / "7d"
    used_percent: float
    resets_at: datetime | None

    @property
    def left_percent(self) -> float:
        return max(0.0, 100 - self.used_percent)


@dataclass
class CodexReading:
    plan: str | None = None
    windows: list[Window] = field(default_factory=list)
    limit_reached: bool = False
    error: str | None = None


def _jwt_exp(token: str) -> float | None:
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return float(json.loads(base64.urlsafe_b64decode(payload))["exp"])
    except Exception:
        return None


class CodexAuth:
    """Reads auth.json and refreshes the access token in place when it is about to expire."""

    def __init__(self, path: Path):
        self.path = path

    def tokens(self, force_refresh: bool = False) -> tuple[str, str | None]:
        data = json.loads(self.path.read_text())
        tokens = data.get("tokens") or {}
        access = tokens.get("access_token")
        if not access:
            raise RuntimeError(f"no tokens.access_token in {self.path}; run `codex login`")
        exp = _jwt_exp(access)
        if force_refresh or (exp is not None and exp - time.time() < 300):
            access = self._refresh(data)
        return access, (data.get("tokens") or {}).get("account_id")

    def _refresh(self, data: dict) -> str:
        tokens = data["tokens"]
        if not tokens.get("refresh_token"):
            raise RuntimeError("access token expired and no refresh_token; run `codex login`")
        log.info("refreshing Codex access token")
        r = requests.post(TOKEN_URL, json={
            "client_id": CLIENT_ID,
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"],
            "scope": "openid profile email",
        }, timeout=20)
        if r.status_code != 200:
            raise RuntimeError(f"token refresh failed: HTTP {r.status_code} {r.text[:200]}")
        for key in ("access_token", "refresh_token", "id_token"):
            if r.json().get(key):
                tokens[key] = r.json()[key]
        data["last_refresh"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        os.chmod(tmp, 0o600)
        tmp.replace(self.path)
        return tokens["access_token"]


def plan_name(raw: str | None) -> str | None:
    if not raw:
        return None
    return PLAN_NAMES.get(raw.lower()) or " ".join(p.capitalize() for p in raw.split("_"))


def window_label(seconds: int | None) -> str:
    if not seconds:
        return "Usage"
    hours = seconds / 3600
    return f"{hours:g}h" if hours < 24 else f"{hours / 24:g}d"


def parse(body: dict) -> CodexReading:
    rl = body.get("rate_limit") or {}
    reading = CodexReading(
        plan=plan_name(body.get("plan_type")),
        limit_reached=rl.get("limit_reached") is True or rl.get("allowed") is False,
    )
    for key in ("primary_window", "secondary_window"):
        w = rl.get(key)
        if not w or w.get("used_percent") is None:
            continue
        resets = None
        if w.get("reset_at"):
            resets = datetime.fromtimestamp(float(w["reset_at"]), tz=timezone.utc)
        elif w.get("reset_after_seconds") is not None:
            resets = datetime.fromtimestamp(time.time() + w["reset_after_seconds"], tz=timezone.utc)
        reading.windows.append(Window(window_label(w.get("limit_window_seconds")), float(w["used_percent"]), resets))
    return reading


@source
class Codex(Source):
    name = "codex"
    description = "Codex rate-limit windows (CODEX_AUTH_PATH, default ~/.codex/auth.json)"

    def __init__(self) -> None:
        self.path = Path(os.path.expanduser(env("CODEX_AUTH_PATH", "~/.codex/auth.json")))

    def unavailable(self) -> str | None:
        return None if self.path.exists() else f"{self.path} not found"

    def fetch(self) -> CodexReading:
        if not self.path.exists():
            return CodexReading(error=f"missing {self.path.name}")
        auth = CodexAuth(self.path)

        def call(force: bool) -> requests.Response:
            access, account = auth.tokens(force_refresh=force)
            headers = {"Authorization": f"Bearer {access}", "Accept": "application/json", "User-Agent": "QuotaBar"}
            if account:
                headers["ChatGPT-Account-Id"] = account
            return requests.get(USAGE_URL, headers=headers, timeout=20)

        try:
            r = call(False)
            if r.status_code == 401:
                r = call(True)
            r.raise_for_status()
            return parse(r.json())
        except Exception as e:
            log.warning("codex: %s", e)
            return CodexReading(error=short_error(e))
