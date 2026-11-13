"""Plugin registry: data sources and pages.

Add a feature by dropping one file into sources/ or pages/:

    @source
    class Weather(Source):
        name = "weather"
        def fetch(self): ...

    @page
    class WeatherPage(Page):
        name = "weather"
        requires = ("weather",)          # optional = (...) for sources the page can do without
        def render(self, data, now): ...

Enable it with PAGES=quota,weather. Per-page settings are read from
PAGE_<NAME>_<KEY>, e.g. PAGE_WEATHER_INTERVAL=1800, PAGE_WEATHER_TASK_KEY=...
"""
from __future__ import annotations

import importlib
import logging
import pkgutil
from datetime import datetime
from typing import Any, ClassVar

from PIL import Image

from .config import env, env_int

log = logging.getLogger("quotadot")

SOURCES: dict[str, type["Source"]] = {}
PAGES: dict[str, type["Page"]] = {}


class Source:
    """A data provider. fetch() reports remote failures inside its result, so one
    bad endpoint shows up on screen instead of stopping the push."""

    name: ClassVar[str]
    description: ClassVar[str] = ""

    def unavailable(self) -> str | None:
        """Why this source cannot run on this machine, or None if it can."""
        return None

    def fetch(self) -> Any:
        raise NotImplementedError


class Page:
    """One 296x152 screen pushed to one Image API item."""

    @classmethod
    def sources(cls) -> tuple[str, ...]:
        return cls.requires + cls.optional

    name: ClassVar[str]
    description: ClassVar[str] = ""
    requires: ClassVar[tuple[str, ...]] = ()      # page is skipped (when auto-selected) without these
    optional: ClassVar[tuple[str, ...]] = ()      # fetched too, but the page draws its own "not configured"
    default_interval: ClassVar[int] = 900

    def opt(self, key: str, default: str | None = None) -> str | None:
        return env(f"PAGE_{self.name.upper()}_{key}", default)

    def opt_int(self, key: str, default: int) -> int:
        return env_int(f"PAGE_{self.name.upper()}_{key}", default)

    @property
    def interval(self) -> int:
        return max(60, self.opt_int("INTERVAL", self.default_interval))

    @property
    def task_type(self) -> str:
        return (self.opt("TASK_TYPE") or env("DOT_TASK_TYPE", "loop")).lower()

    @property
    def task_key(self) -> str | None:
        return self.opt("TASK_KEY")

    @property
    def alias(self) -> str | None:
        return self.opt("ALIAS")

    def render(self, data: dict[str, Any], now: datetime) -> Image.Image:
        raise NotImplementedError


def source(cls: type[Source]) -> type[Source]:
    if cls.name in SOURCES:
        raise ValueError(f"duplicate source name {cls.name!r}")
    SOURCES[cls.name] = cls
    return cls


def page(cls: type[Page]) -> type[Page]:
    if cls.name in PAGES:
        raise ValueError(f"duplicate page name {cls.name!r}")
    PAGES[cls.name] = cls
    return cls


def discover() -> None:
    """Import every module under sources/ and pages/ so their decorators run."""
    for pkg in ("sources", "pages"):
        mod = importlib.import_module(f"{__package__}.{pkg}")
        for info in pkgutil.iter_modules(mod.__path__):
            if not info.name.startswith("_"):
                importlib.import_module(f"{mod.__name__}.{info.name}")


class SourceCache:
    """Fetch each source at most once per tick, shared by the pages due in that tick."""

    def __init__(self) -> None:
        self._instances: dict[str, Source] = {}
        self._data: dict[str, Any] = {}

    def instance(self, name: str) -> Source:
        if name not in SOURCES:
            raise KeyError(f"unknown source {name!r} (have: {', '.join(sorted(SOURCES))})")
        if name not in self._instances:
            self._instances[name] = SOURCES[name]()
        return self._instances[name]

    def get(self, name: str) -> Any:
        if name not in self._data:
            self._data[name] = self.instance(name).fetch()
        return self._data[name]

    def clear(self) -> None:
        self._data.clear()
