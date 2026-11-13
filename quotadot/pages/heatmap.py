"""Heatmap page: GitHub-style grid of daily usage from cc-switch, shaded with dot patterns."""
from __future__ import annotations

from ..draw import PAD, W, canvas, error_block, font, to_1bit
from ..registry import Page, page
from ..sources.ccswitch import UsageHistory
from ..widgets import METRICS, check_metric, draw_usage_grid, draw_usage_header, max_weeks

GRID_TOP = 44         # header 0..28, month row 31..41


@page
class HeatmapPage(Page):
    name = "heatmap"
    description = "GitHub-style daily usage grid (PAGE_HEATMAP_METRIC=tokens|fresh|cost, PAGE_HEATMAP_WEEKS)"
    requires = ("ccswitch",)
    default_interval = 3600

    def render(self, data, now):
        history: UsageHistory = data["ccswitch"]
        metric = check_metric(self.name, self.opt("METRIC", "tokens"))
        img, d = canvas()
        if history.error:
            d.text((PAD, 4), METRICS[metric], font=font(11, True), fill=0)
            error_block(d, PAD, 40, W - 2 * PAD, "cc-switch read failed", history.error)
            return to_1bit(img)

        today = now.date()
        fit_weeks = max_weeks(W - 2 * PAD)
        weeks = min(self.opt_int("WEEKS", fit_weeks), fit_weeks)
        draw_usage_header(d, history, metric, today, weeks, f"{weeks} weeks · cc-switch")
        draw_usage_grid(img, d, history, metric, today, PAD, GRID_TOP, weeks, legend_right=W - PAD)
        return to_1bit(img)
