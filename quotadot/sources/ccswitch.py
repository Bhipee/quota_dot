"""Daily token use and spend from cc-switch's local SQLite database (read-only).

Recent days live in proxy_request_logs; cc-switch rolls older days into
usage_daily_rollups and deletes the detail rows, so the two never overlap.
"""
from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from ..config import env
from ..registry import Source, source

# App types whose input_tokens already include cache tokens (cc-switch sql_helpers.rs).
CACHE_INCLUSIVE = ("codex", "gemini", "grokbuild")


def fresh_input_sql() -> str:
    """cc-switch's fresh_input_sql: input tokens without cache, per row."""
    apps = ", ".join(f"'{a}'" for a in CACHE_INCLUSIVE)
    return f"""CASE
        WHEN input_token_semantics = 2 THEN input_tokens
        WHEN app_type IN ({apps}) AND input_token_semantics = 1
             AND input_tokens >= cache_read_tokens + cache_creation_tokens
          THEN input_tokens - cache_read_tokens - cache_creation_tokens
        WHEN app_type IN ({apps}) AND input_token_semantics = 0
             AND input_tokens >= cache_read_tokens
          THEN input_tokens - cache_read_tokens
        ELSE input_tokens END"""


@dataclass
class DayUsage:
    tokens: float = 0.0        # fresh input + output + cache read + cache write
    fresh: float = 0.0         # fresh input + output
    cost: float = 0.0          # USD

    def get(self, metric: str) -> float:
        return getattr(self, metric)


@dataclass
class UsageHistory:
    days: dict[date, DayUsage] = field(default_factory=dict)
    error: str | None = None

    def value(self, day: date, metric: str) -> float:
        u = self.days.get(day)
        return u.get(metric) if u else 0.0


@source
class CCSwitch(Source):
    name = "ccswitch"
    description = "Daily tokens/spend from cc-switch (CCSWITCH_DB, default ~/.cc-switch/cc-switch.db)"

    def __init__(self) -> None:
        self.path = Path(os.path.expanduser(env("CCSWITCH_DB", "~/.cc-switch/cc-switch.db")))

    def unavailable(self) -> str | None:
        return None if self.path.exists() else f"{self.path} not found (cc-switch runs on another machine?)"

    def fetch(self) -> UsageHistory:
        fresh = fresh_input_sql()
        cols = (f"SUM(({fresh}) + output_tokens + cache_read_tokens + cache_creation_tokens), "
                f"SUM(({fresh}) + output_tokens), SUM(CAST(total_cost_usd AS REAL))")
        history = UsageHistory()
        try:
            con = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True, timeout=5)
            try:
                queries = (
                    f"SELECT date(created_at, 'unixepoch', 'localtime'), {cols} FROM proxy_request_logs GROUP BY 1",
                    f"SELECT date, {cols} FROM usage_daily_rollups GROUP BY 1",
                )
                for sql in queries:
                    for d, tokens, fresh_out, cost in con.execute(sql):
                        u = history.days.setdefault(date.fromisoformat(d), DayUsage())
                        u.tokens += tokens or 0
                        u.fresh += fresh_out or 0
                        u.cost += cost or 0
            finally:
                con.close()
        except Exception as e:
            history.error = str(e)[:80]
        return history
