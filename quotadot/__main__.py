"""quota·dot runner.

  python -m quotadot list                      # every source/page and whether it can run here
  python -m quotadot render [--out DIR]        # render enabled pages to PNG, no push
  python -m quotadot push [PAGE ...]           # render and push once
  python -m quotadot run                       # loop forever, each page on its own interval

Pages to use: PAGES=quota,heatmap (default: every page whose sources are available here).
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

from . import registry
from .config import env, env_list, load_env_file
from .dot import push_image
from .registry import PAGES, SOURCES, Page, SourceCache

log = logging.getLogger("quotadot")


def now_local() -> datetime:
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo(env("TZ_NAME", "Asia/Shanghai")))


def select_pages(cache: SourceCache, names: list[str] | None) -> list[Page]:
    """Pages from the CLI, else PAGES, else every page whose sources are available here."""
    explicit = bool(names) or bool(env("PAGES"))
    wanted = names or env_list("PAGES") or sorted(PAGES)
    pages: list[Page] = []
    for name in wanted:
        if name not in PAGES:
            raise SystemExit(f"unknown page {name!r} (have: {', '.join(sorted(PAGES))})")
        pg = PAGES[name]()
        missing = {s: cache.instance(s).unavailable() for s in pg.requires}
        missing = {s: why for s, why in missing.items() if why}
        # An explicitly enabled page still runs and shows the problem on screen;
        # only auto-selected pages are skipped quietly.
        if missing and not explicit:
            log.info("page %s skipped: %s", name, "; ".join(f"{s}: {w}" for s, w in missing.items()))
            continue
        for s, why in missing.items():
            log.warning("page %s: source %s unavailable: %s", name, s, why)
        pages.append(pg)
    task_keys = [p.task_key for p in pages]
    if len(pages) > 1 and len(set(task_keys)) < len(pages):
        log.warning("%d pages share an Image API item (set PAGE_<NAME>_TASK_KEY for each); "
                    "they will overwrite each other", len(pages))
    return pages


def render_page(pg: Page, cache: SourceCache):
    data = {s: cache.get(s) for s in pg.sources()}
    return pg.render(data, now_local())


def do_list(cache: SourceCache) -> int:
    print("sources:")
    for name in sorted(SOURCES):
        why = cache.instance(name).unavailable()
        print(f"  {name:10} {'ok' if not why else 'unavailable: ' + why}")
        print(f"  {'':10} {SOURCES[name].description}")
    print("pages:")
    enabled = env_list("PAGES")
    for name in sorted(PAGES):
        pg = PAGES[name]()
        flag = "on " if (not enabled or name in enabled) else "off"
        opt = f" (+{', '.join(pg.optional)})" if pg.optional else ""
        print(f"  [{flag}] {name:8} every {pg.interval}s  needs {', '.join(pg.requires)}{opt}"
              f"  task_key={pg.task_key or '(first Image API item)'}")
        print(f"  {'':14} {pg.description}")
    return 0


def do_render(cache: SourceCache, names: list[str] | None, out: Path, push: bool) -> int:
    out.mkdir(parents=True, exist_ok=True)
    failed = 0
    for pg in select_pages(cache, names):
        try:
            img = render_page(pg, cache)
            path = out / f"{pg.name}.png"
            img.save(path)
            log.info("%s: wrote %s", pg.name, path)
            if push:
                msg = push_image(img, task_type=pg.task_type, task_key=pg.task_key, alias=pg.alias)
                log.info("%s: pushed: %s", pg.name, msg)
        except Exception as e:
            failed += 1
            log.error("%s: %s", pg.name, e)
    return 1 if failed else 0


def do_run(cache: SourceCache, names: list[str] | None, out: Path | None) -> int:
    pages = select_pages(cache, names)
    if not pages:
        log.error("no page to run")
        return 1
    log.info("running %s", ", ".join(f"{p.name} every {p.interval}s" for p in pages))
    due = {p.name: 0.0 for p in pages}
    while True:
        tick = time.time()
        cache.clear()          # fresh data each tick, shared by the pages due in it
        for pg in pages:
            if due[pg.name] > tick:
                continue
            try:
                img = render_page(pg, cache)
                if out:
                    out.mkdir(parents=True, exist_ok=True)
                    img.save(out / f"{pg.name}.png")
                msg = push_image(img, task_type=pg.task_type, task_key=pg.task_key, alias=pg.alias)
                log.info("%s: pushed: %s", pg.name, msg)
            except Exception as e:
                log.error("%s: %s", pg.name, e)
            due[pg.name] = tick + pg.interval
        wait = max(5.0, min(due.values()) - time.time())
        log.info("next push in %ds", wait)
        time.sleep(wait)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m quotadot", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--env-file", default=".env", help="loaded if present; real env vars win (default: .env)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="show sources and pages")
    for cmd, help_ in (("render", "render to PNG only"), ("push", "render and push once")):
        sp = sub.add_parser(cmd, help=help_)
        sp.add_argument("pages", nargs="*", help="page names (default: PAGES or all available)")
        sp.add_argument("--out", type=Path, default=Path("out"), help="PNG folder (default: out/)")
    sp = sub.add_parser("run", help="loop forever")
    sp.add_argument("pages", nargs="*")
    sp.add_argument("--out", type=Path, help="also keep the latest PNG of each page here")
    args = ap.parse_args(argv)

    load_env_file(args.env_file)
    logging.basicConfig(level=env("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s")
    registry.discover()
    cache = SourceCache()
    if args.cmd == "list":
        return do_list(cache)
    if args.cmd == "run":
        return do_run(cache, args.pages or None, args.out)
    return do_render(cache, args.pages or None, args.out, push=args.cmd == "push")


if __name__ == "__main__":
    sys.exit(main())
