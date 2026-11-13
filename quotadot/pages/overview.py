"""Overview page: TOKENS header across the top, quotas on the left, a short usage grid on the right."""
from __future__ import annotations

from ..draw import H, PAD, W, canvas, error_block, font, to_1bit
from ..registry import Page, page
from ..sources.ccswitch import UsageHistory
from ..widgets import (METRICS, check_metric, draw_quota_rows, draw_usage_grid, draw_usage_header,
                       grid_width, max_weeks)

GRID_TOP = 44         # same header band as the heatmap page: rows 0..28, month labels 31..41
BODY_TOP = 34
DEFAULT_WEEKS = 10    # about two and a half months
MAX_WEEKS = 13        # beyond this the quota column gets too narrow to read


@page
class OverviewPage(Page):
    name = "overview"
    description = ("Quotas left, recent daily usage grid right, TOKENS header on top "
                   "(PAGE_OVERVIEW_WEEKS, PAGE_OVERVIEW_METRIC)")
    requires = ("ccswitch",)
    optional = ("codex", "relays")
    default_interval = 900

    def render(self, data, now):
        history: UsageHistory = data["ccswitch"]
        metric = check_metric(self.name, self.opt("METRIC", "tokens"))
        weeks = max(4, min(self.opt_int("WEEKS", DEFAULT_WEEKS), MAX_WEEKS, max_weeks(W - 2 * PAD)))
        img, d = canvas()
        today = now.date()

        # right: grid flush with the right edge
        grid_x = W - PAD - grid_width(weeks)
        split = grid_x - 8                         # dotted divider between the two columns
        if history.error:
            d.text((PAD, 4), METRICS[metric], font=font(11, True), fill=0)
            d.text((PAD, 17), f"updated {now:%H:%M}", font=font(9), fill=0)
            error_block(d, split + 8, BODY_TOP + 4, W - PAD - split - 8, "cc-switch read failed", history.error)
        else:
            draw_usage_header(d, history, metric, today, weeks,
                              f"{weeks}w · updated {now:%H:%M}", total_label=f"{weeks}w")
            draw_usage_grid(img, d, history, metric, today, grid_x, GRID_TOP, weeks, legend_right=W - PAD)

        for y in range(BODY_TOP, H - 4, 3):
            d.point((split, y), fill=0)

        # left: one row per quota
        draw_quota_rows(d, PAD, split - 8, BODY_TOP, H - 2, data.get("codex"), data.get("relays"), now)
        return to_1bit(img)
