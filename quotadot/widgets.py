"""Reusable blocks that pages compose: usage header, contribution grid, compact quota rows."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from PIL import Image, ImageDraw

from .draw import PAD, W, bar, compact, error_block, fit, font, money, text_right, until, wrap
from .sources.ccswitch import UsageHistory
from .sources.codex import CodexReading
from .sources.relays import RelayReading

# ---------------------------------------------------------------- usage grid

CELL, GAP = 9, 2
STEP = CELL + GAP
LABEL_W = 14          # M/W/F/S column left of the grid
METRICS = {"tokens": "TOKENS", "fresh": "TOKENS (in+out)", "cost": "SPEND"}

# Shade levels 0..4: empty, 25%, 50%, 75%, solid. The screen has no gray, only dot density.
PATTERNS = [
    None,
    lambda x, y: x % 2 == 0 and y % 2 == 0,
    lambda x, y: (x + y) % 2 == 0,
    lambda x, y: not (x % 2 == 1 and y % 2 == 1),
    lambda x, y: True,
]


def check_metric(page_name: str, metric: str) -> str:
    metric = metric.lower()
    if metric not in METRICS:
        raise ValueError(f"PAGE_{page_name.upper()}_METRIC={metric!r}; use one of {', '.join(METRICS)}")
    return metric


def fmt_metric(v: float, metric: str) -> str:
    if metric == "cost":
        return f"${v:,.0f}" if v >= 100 else f"${v:,.2f}"
    return compact(v)


def quantile_cuts(values: list[float]) -> list[float]:
    """Three cut points over non-zero days, so the four shades are used evenly (as GitHub does)."""
    nz = sorted(v for v in values if v > 0)
    if not nz:
        return [1, 2, 3]
    return [nz[min(len(nz) - 1, int(f * len(nz)))] for f in (0.25, 0.5, 0.75)]


def level(v: float, cuts: list[float]) -> int:
    if v <= 0:
        return 0
    return next((i for i, c in enumerate(cuts, start=1) if v <= c), 4)


def draw_cell(img: Image.Image, d: ImageDraw.ImageDraw, x: int, y: int, lvl: int, today: bool = False) -> None:
    if lvl == 0:
        img.putpixel((x + CELL // 2, y + CELL // 2), 0)      # empty day: one centre dot
    else:
        fn = PATTERNS[lvl]
        for yy in range(CELL):                              # cell-local, so every cell of a level matches
            for xx in range(CELL):
                if fn(xx, yy):
                    img.putpixel((x + xx, y + yy), 0)
    if today:                                               # today is still running
        d.rectangle([x - 2, y - 2, x + CELL + 1, y + CELL + 1], outline=0)


def grid_width(weeks: int) -> int:
    """Pixels from the M/W/F label column to the last cell."""
    return LABEL_W + weeks * STEP - GAP


def max_weeks(width: int) -> int:
    return (width - LABEL_W + GAP) // STEP


def first_monday(today: date, weeks: int) -> date:
    return today - timedelta(days=today.weekday(), weeks=weeks - 1)


def days_shown(today: date, weeks: int) -> list[date]:
    start = first_monday(today, weeks)
    return [start + timedelta(days=i) for i in range((today - start).days + 1)]


def draw_usage_header(d: ImageDraw.ImageDraw, history: UsageHistory, metric: str, today: date,
                      weeks: int, subtitle: str, total_label: str = "total") -> None:
    """Title + subtitle on the left; today / 7d / period total on the right (rows 0..28)."""
    f9, f11b, f13b = font(9), font(11, True), font(13, True)
    d.text((PAD, 4), METRICS[metric], font=f11b, fill=0)
    d.text((PAD, 17), subtitle, font=f9, fill=0)
    total = sum(history.value(day, metric) for day in days_shown(today, weeks))
    week = sum(history.value(today - timedelta(days=i), metric) for i in range(7))
    x1 = W - PAD
    for label, val in ((total_label, total), ("7d", week), ("today", history.value(today, metric))):
        txt = fmt_metric(val, metric)
        tw, lw = d.textlength(txt, font=f13b), d.textlength(label, font=f9)
        d.text((x1 - tw, 2), txt, font=f13b, fill=0)
        d.text((x1 - tw / 2 - lw / 2, 18), label, font=f9, fill=0)
        x1 -= max(tw, lw) + 12


def draw_usage_grid(img: Image.Image, d: ImageDraw.ImageDraw, history: UsageHistory, metric: str,
                    today: date, x: int, top: int, weeks: int, legend_right: int | None = None) -> None:
    """Contribution grid with day labels at x, month labels above `top`, legend below.

    Occupies x .. x + grid_width(weeks), top - 13 .. top + 7 * STEP + 13.
    """
    f9 = font(9)
    start = first_monday(today, weeks)
    cuts = quantile_cuts([history.value(day, metric) for day in days_shown(today, weeks)])
    gx = x + LABEL_W
    for wi in range(weeks):
        for di in range(7):
            day = start + timedelta(weeks=wi, days=di)
            if day <= today:
                draw_cell(img, d, gx + wi * STEP, top + di * STEP,
                          level(history.value(day, metric), cuts), today=day == today)
    for di, lab in ((0, "M"), (2, "W"), (4, "F"), (6, "S")):
        d.text((x, top + di * STEP - 1), lab, font=f9, fill=0)

    last_m, last_x = None, -99                      # month labels above the grid
    for wi in range(weeks):
        monday = start + timedelta(weeks=wi)
        if monday.month != last_m:
            mx = gx + wi * STEP
            if mx - last_x >= 24:
                d.text((mx, top - 13), monday.strftime("%b"), font=f9, fill=0)
                last_x = mx
            last_m = monday.month

    right = legend_right if legend_right is not None else gx + weeks * STEP - GAP
    gy = top + 7 * STEP + 2                         # legend: less . [] [] [] [] more
    swatches = 5 * (CELL + 2)
    words = d.textlength("less", font=f9) + d.textlength("more", font=f9) + 8
    if right - swatches - words >= x:               # narrow grids keep the swatches only
        lx = int(right - swatches - d.textlength("more", font=f9) - 4)
        d.text((lx - d.textlength("less", font=f9) - 4, gy), "less", font=f9, fill=0)
        text_right(d, right, gy, "more", f9)
    else:
        lx = int(right - swatches + 2)
    for i in range(5):
        draw_cell(img, d, lx + i * (CELL + 2), gy + 1, i)


# ---------------------------------------------------------------- compact quota rows


def draw_quota_rows(d: ImageDraw.ImageDraw, x0: int, x1: int, y0: int, y1: int,
                    codex: CodexReading | None, relays: list[RelayReading] | None, now: datetime) -> None:
    """One row per quota (Codex first, then each relay): name, big value, bar, detail line.

    Rows shrink to fit y0..y1: the detail line goes first, then the bar.
    """
    f9, f11, f13b = font(9), font(11), font(13, True)
    rows: list[tuple[str, str | None, float | None, str, str]] = []   # name, value, fraction, detail, detail_right
    if codex is not None:
        if codex.error or not codex.windows:
            rows.append(("Codex", None, None, codex.error or "no rate-limit windows", ""))
        else:
            w = codex.windows[0]
            name = f"Codex {w.label}" + (" LIMIT" if codex.limit_reached else "")
            rows.append((name, f"{w.left_percent:.0f}%", w.left_percent / 100,
                         f"reset {until(w.resets_at, now) or '--'}",
                         f"{codex.windows[1].label} {codex.windows[1].left_percent:.0f}%" if len(codex.windows) > 1 else ""))
    for r in relays or []:
        if r.error:
            rows.append((r.name, None, None, r.error, ""))
        elif r.remaining is None:
            rows.append((r.name, money(r.used, r.unit), None, "spent · no budget", ""))
        else:
            frac = max(0.0, r.remaining) / r.limit if r.limit else None
            rows.append((r.name, money(r.remaining, r.unit), frac,
                         f"of {money(r.limit, r.unit)}" if r.limit else "remaining",
                         f"{frac * 100:.0f}% left" if frac is not None else ""))
    if not rows:
        error_block(d, x0, y0, x1 - x0, "no quota", "set CODEX_AUTH_PATH and NEXUS_* / COMPANY_*")
        return

    row_h = min(38, (y1 - y0) // len(rows))
    show_bar, show_detail = row_h >= 24, row_h >= 34
    y = y0
    for name, value, frac, detail, detail_right in rows:
        if value is None:                               # failed: name + "! error", reason as detail
            d.text((x0, y), fit(d, name, f11, x1 - x0 - 50), font=f11, fill=0)
            text_right(d, x1, y, "! error", font(11, True))
            if row_h >= 24:
                lines = wrap(d, detail, f9, x1 - x0, max(1, (row_h - 16) // 11))
                for i, line in enumerate(lines):
                    d.text((x0, y + 15 + i * 11), line, font=f9, fill=0)
        else:
            vw = d.textlength(value, font=f13b)
            d.text((x0, y), fit(d, name, f11, x1 - x0 - vw - 6), font=f11, fill=0)
            text_right(d, x1, y - 1, value, f13b)
            if show_bar and frac is not None:
                bar(d, x0, y + 16, x1 - x0, 7, frac)
            if show_detail:
                dy = y + 25 if frac is not None else y + 16
                d.text((x0, dy), fit(d, detail, f9, x1 - x0 - 50), font=f9, fill=0)
                if detail_right:
                    text_right(d, x1, dy, detail_right, f9)
        y += row_h
