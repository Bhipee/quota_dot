"""Quota page: Codex window on the left, relay balance(s) on the right."""
from __future__ import annotations

from datetime import datetime

from ..draw import (FOOT, PAD, W, bar, canvas, error_block, fit, font, footer, money, text_right,
                    to_1bit, until)
from ..registry import Page, page
from ..sources.codex import CodexReading
from ..sources.relays import RelayReading

SPLIT = 118     # x of the column divider
TOP = 8


def draw_codex(d, codex: CodexReading, now: datetime) -> None:
    f9, f11b, f26b = font(9), font(11, True), font(26, True)
    d.text((PAD, TOP), "CODEX", font=f11b, fill=0)
    if codex.plan:
        text_right(d, SPLIT - 8, TOP + 2, fit(d, codex.plan, f9, SPLIT - PAD - 50), f9)
    if codex.error or not codex.windows:
        error_block(d, PAD, TOP + 28, SPLIT - PAD - 10,
                    "fetch failed" if codex.error else "no data", codex.error or "no rate-limit windows")
        return
    # Same grid as the relay column: caption, big number, bar, secondary line.
    main, cw = codex.windows[0], SPLIT - PAD - 10
    d.text((PAD, TOP + 22), f"{main.label} left", font=f9, fill=0)
    d.text((PAD - 1, TOP + 32), f"{main.left_percent:.0f}%", font=f26b, fill=0)
    if codex.limit_reached:
        d.rectangle([SPLIT - 42, TOP + 22, SPLIT - 10, TOP + 34], fill=0)
        d.text((SPLIT - 39, TOP + 22), "LIMIT", font=f9, fill=255)
    bar(d, PAD, TOP + 70, cw, 10, main.left_percent / 100)
    d.text((PAD, TOP + 84), "reset", font=f9, fill=0)
    text_right(d, PAD + cw, TOP + 84, until(main.resets_at, now) or "--", f9)
    if len(codex.windows) > 1:      # e.g. 5h + 7d plans: second window on the bottom line
        w2 = codex.windows[1]
        line = f"{w2.label} {w2.left_percent:.0f}% · {until(w2.resets_at, now)}"
        d.text((PAD, FOOT - 14), fit(d, line, f9, cw), font=f9, fill=0)


def draw_relays(d, relays: list[RelayReading]) -> None:
    f9, f11, f11b, f13b, f20b, f26b = font(9), font(11), font(11, True), font(13, True), font(20, True), font(26, True)
    x0, x1 = SPLIT + 10, W - PAD
    cw = x1 - x0
    if not relays:
        d.text((x0, TOP), "RELAY", font=f11b, fill=0)
        error_block(d, x0, TOP + 30, cw, "not configured", "set NEXUS_* / COMPANY_* or RELAYS (see README)")
        return
    if len(relays) == 1:
        r = relays[0]
        d.text((x0, TOP), fit(d, r.name.upper(), f11b, cw - 60), font=f11b, fill=0)
        text_right(d, x1, TOP + 2, r.unit, f9)
        if r.error:
            error_block(d, x0, TOP + 28, cw, "fetch failed", r.error)
            return
        no_budget = r.remaining is None
        d.text((x0, TOP + 22), "spent" if no_budget else "remaining", font=f9, fill=0)
        amount = money(r.used if no_budget else r.remaining, r.unit)
        big = f26b if d.textlength(amount, font=f26b) <= cw else f20b
        d.text((x0 - 1, TOP + 32), fit(d, amount, big, cw), font=big, fill=0)
        if no_budget:
            d.text((x0, TOP + 84), "no budget set", font=f9, fill=0)
        elif r.limit:
            frac = max(0.0, r.remaining) / r.limit
            bar(d, x0, TOP + 70, cw, 10, frac)
            d.text((x0, TOP + 84), f"of {money(r.limit, r.unit)}", font=f9, fill=0)
            text_right(d, x1, TOP + 84, f"{frac * 100:.0f}% left", f9)
        if r.expires_at:
            d.text((x0, FOOT - 14), "exp " + r.expires_at.astimezone().strftime("%Y-%m-%d"), font=f9, fill=0)
        return
    d.text((x0, TOP), "RELAYS", font=f11b, fill=0)
    y, row_h = TOP + 20, 26
    for r in relays[: max(1, (FOOT - y) // row_h)]:
        d.text((x0, y), fit(d, r.name, f11, cw - 70), font=f11, fill=0)
        if r.error:
            text_right(d, x1, y, "! error", f11b)
        elif r.remaining is None:
            spent = money(r.used, r.unit)
            text_right(d, x1, y - 1, spent, f13b)
            text_right(d, x1 - d.textlength(spent, font=f13b) - 4, y + 2, "spent", f9)
        else:
            text_right(d, x1, y - 1, money(r.remaining, r.unit), f13b)
            if r.limit:
                bar(d, x0, y + 15, cw, 6, max(0.0, r.remaining) / r.limit)
        y += row_h


@page
class QuotaPage(Page):
    name = "quota"
    description = "Codex window + relay balances, two columns"
    requires = ("codex",)
    optional = ("relays",)
    default_interval = 900

    def render(self, data, now):
        img, d = canvas()
        draw_codex(d, data["codex"], now)
        for yy in range(TOP, FOOT - 2, 3):          # dotted column divider
            d.point((SPLIT, yy), fill=0)
        draw_relays(d, data["relays"])
        footer(d, now)
        return to_1bit(img)
