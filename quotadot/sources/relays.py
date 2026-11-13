"""Relay balances. Each relay has a `type`; add a new type by decorating a fetch function with
@relay_type("name", required_fields...). Configure with RELAYS (JSON) or the NEXUS_* / COMPANY_* groups.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

import requests

from ..config import env, short_error
from ..registry import Source, source

log = logging.getLogger("quotadot")
BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")


@dataclass
class RelayReading:
    name: str
    remaining: float | None = None     # None when the relay has no budget
    limit: float | None = None
    used: float | None = None
    unit: str = "USD"
    expires_at: datetime | None = None
    error: str | None = None


RelayFetch = Callable[[str, dict], RelayReading]
RELAY_TYPES: dict[str, tuple[tuple[str, ...], RelayFetch]] = {}


def relay_type(kind: str, *fields: str) -> Callable[[RelayFetch], RelayFetch]:
    def register(fn: RelayFetch) -> RelayFetch:
        RELAY_TYPES[kind] = (fields, fn)
        return fn
    return register


def _root(base: str) -> str:
    text = base.strip().rstrip("/")
    return text if "://" in text else "https://" + text


def _iso(value: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None
    except ValueError:
        return None


# ---- type: nexus (and other relays answering {base}/v1/usage, as in QuotaBar)

def nexus_usage_url(base: str) -> str:
    text = _root(base)
    if text.endswith("/v1/usage"):
        return text
    return text + ("/usage" if text.endswith("/v1") else "/v1/usage")


def parse_nexus(name: str, body: dict) -> RelayReading:
    quota = body.get("quota") or {}
    limit, used = quota.get("limit"), quota.get("used")
    remaining = quota.get("remaining", body.get("remaining"))
    if used is None and limit is not None and remaining is not None:
        used = limit - remaining
    if remaining is None and limit is not None and used is not None:
        remaining = max(0.0, limit - used)
    if remaining is None:
        raise ValueError("response has no remaining balance")
    return RelayReading(
        name=name, remaining=float(remaining),
        limit=float(limit) if limit is not None else None,
        used=float(used) if used is not None else None,
        unit=(quota.get("unit") or body.get("unit") or "USD").upper(),
        expires_at=_iso(body.get("expires_at")),
    )


@relay_type("nexus", "base", "key")
def fetch_nexus(name: str, cfg: dict) -> RelayReading:
    r = requests.get(nexus_usage_url(cfg["base"]), headers={
        "Authorization": f"Bearer {cfg['key']}", "Accept": "application/json",
        "User-Agent": BROWSER_UA,      # the relay's edge rejects bare clients with a browser check
    }, timeout=20)
    r.raise_for_status()
    return parse_nexus(name, r.json())


# ---- type: litellm (company API: your own spend inside a LiteLLM team, cc-switch extractor rules)

def parse_litellm_team(name: str, body: dict, user_id: str) -> RelayReading:
    me = next((m for m in body.get("team_memberships") or [] if m.get("user_id") == user_id), None)
    used = budget = None
    if me:
        used = me.get("spend")
        budget = (me.get("litellm_budget_table") or {}).get("max_budget")
    if used is None:
        used = sum(k.get("spend") or 0 for k in body.get("keys") or [] if k.get("user_id") == user_id)
        if me is None and used == 0:
            log.warning("relay %s: user_id %s is not in team_memberships and owns no team keys", name, user_id)
    used = float(used or 0)
    return RelayReading(
        name=name, used=used, unit="USD",
        limit=float(budget) if budget is not None else None,
        remaining=float(budget) - used if budget is not None else None,
    )


@relay_type("litellm", "base", "key", "team_id", "user_id")
def fetch_litellm(name: str, cfg: dict) -> RelayReading:
    root = _root(cfg["base"])
    if root.endswith("/v1"):          # /team/info lives at the root, not under /v1
        root = root[:-3]
    r = requests.get(f"{root}/team/info", params={"team_id": cfg["team_id"]}, headers={
        "Authorization": f"Bearer {cfg['key']}", "User-Agent": "cc-switch/1.0", "Accept": "application/json",
    }, timeout=20)
    r.raise_for_status()
    return parse_litellm_team(name, r.json(), cfg["user_id"])


# ---- configuration

ENV_GROUPS = [   # (type, env prefix, default display name, {field: env var})
    ("nexus", "NEXUS", "Nexus", {"base": "NEXUS_BASE", "key": "NEXUS_KEY"}),
    ("litellm", "COMPANY", "Company", {"base": "COMPANY_BASE", "key": "COMPANY_KEY",
                                       "team_id": "COMPANY_TEAM_ID", "user_id": "COMPANY_USER_ID"}),
]


def load_configs() -> list[dict]:
    raw = env("RELAYS")
    if raw:
        try:
            out = []
            for i, item in enumerate(json.loads(raw)):
                kind = (item.get("type") or "nexus").lower()
                if kind not in RELAY_TYPES:
                    raise ValueError(f"item {i}: unknown type {kind!r} (have: {', '.join(RELAY_TYPES)})")
                missing = [f for f in RELAY_TYPES[kind][0] if not item.get(f)]
                if missing:
                    raise ValueError(f"item {i} ({kind}): missing {', '.join(missing)}")
                out.append({**item, "type": kind, "name": item.get("name") or kind.capitalize()})
        except (ValueError, TypeError, AttributeError) as e:
            log.warning("RELAYS is set but invalid (%s). Quote the JSON in single quotes in .env", e)
            return []
        if not out:
            log.warning("RELAYS is an empty list; no relay will be shown")
        return out
    out = []
    for kind, prefix, default_name, fields in ENV_GROUPS:
        values = {f: env(var) for f, var in fields.items()}
        if all(values.values()):
            out.append({"type": kind, "name": env(f"{prefix}_NAME", default_name), **values})
        elif any(values.values()):
            missing = [var for f, var in fields.items() if not values[f]]
            log.warning("%s relay half-configured: %s not set", default_name, ", ".join(missing))
    return out


@source
class Relays(Source):
    name = "relays"
    description = "Relay balances: RELAYS json, or NEXUS_* / COMPANY_* groups"

    def unavailable(self) -> str | None:
        return None if load_configs() else "no relay configured (NEXUS_* / COMPANY_* / RELAYS)"

    def fetch(self) -> list[RelayReading]:
        readings = []
        for cfg in load_configs():
            try:
                readings.append(RELAY_TYPES[cfg["type"]][1](cfg["name"], cfg))
            except Exception as e:
                log.warning("relay %s: %s", cfg["name"], e)
                readings.append(RelayReading(name=cfg["name"], error=short_error(e)))
        return readings
