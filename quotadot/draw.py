"""Drawing helpers shared by pages: canvas, fonts, text fitting, bars, footer."""
from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .config import env

W, H = 296, 152          # Quote/0 screen, black and white only
PAD = 8
FOOT = H - 15            # top of the inverted footer strip

def _matplotlib_fonts() -> str:
    """DejaVu ships with matplotlib; use it on machines without system DejaVu (e.g. macOS)."""
    try:
        import importlib.util
        spec = importlib.util.find_spec("matplotlib")
        if spec and spec.origin:
            return str(Path(spec.origin).parent / "mpl-data" / "fonts" / "ttf")
    except Exception:
        pass
    return "/nonexistent"


_MPL = _matplotlib_fonts()
FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    f"{_MPL}/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
]
BOLD_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    f"{_MPL}/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
]


@lru_cache(maxsize=None)
def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    override = env("FONT_BOLD_PATH" if bold else "FONT_PATH")
    for path in ([override] if override else []) + (BOLD_CANDIDATES if bold else []) + FONT_CANDIDATES:
        if path and Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)


def canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("L", (W, H), 255)
    d = ImageDraw.Draw(img)
    d.fontmode = "1"     # no anti-aliasing: the screen is 1-bit
    return img, d


def to_1bit(img: Image.Image) -> Image.Image:
    return img.point(lambda v: 0 if v < 160 else 255, mode="1")


def text_right(d: ImageDraw.ImageDraw, x_right: float, y: float, text: str, f, fill: int = 0) -> None:
    d.text((x_right - d.textlength(text, font=f), y), text, font=f, fill=fill)


def fit(d: ImageDraw.ImageDraw, text: str, f, max_w: float) -> str:
    """Trim text with an ellipsis so it fits in max_w pixels."""
    if d.textlength(text, font=f) <= max_w:
        return text
    while text and d.textlength(text + "…", font=f) > max_w:
        text = text[:-1]
    return text + "…"


def wrap(d: ImageDraw.ImageDraw, text: str, f, max_w: float, max_lines: int) -> list[str]:
    """Greedy word wrap; long words are cut, the last line gets an ellipsis if text remains."""
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if d.textlength(trial, font=f) <= max_w:
            cur = trial
            continue
        if cur:
            lines.append(cur)
        cur = word if d.textlength(word, font=f) <= max_w else fit(d, word, f, max_w)
        if len(lines) == max_lines:
            break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    if len(lines) == max_lines and " ".join(lines) != " ".join(text.split()):
        lines[-1] = fit(d, lines[-1] + " …", f, max_w)
    return lines[:max_lines]


def bar(d: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int, fraction: float) -> None:
    """Outlined bar; the filled part is what is left."""
    fraction = min(1.0, max(0.0, fraction))
    d.rectangle([x, y, x + w - 1, y + h - 1], outline=0, width=1)
    inner = int((w - 4) * fraction)
    if inner > 0:
        d.rectangle([x + 2, y + 2, x + 1 + inner, y + h - 3], fill=0)


def footer(d: ImageDraw.ImageDraw, now: datetime, right: str = "quota·dot") -> None:
    """Inverted strip at the bottom with the update time."""
    d.rectangle([0, FOOT, W, H], fill=0)
    d.text((PAD, FOOT + 1), now.strftime("updated %m-%d %H:%M"), font=font(11), fill=255)
    text_right(d, W - PAD, FOOT + 1, right, font(11), fill=255)


def error_block(d: ImageDraw.ImageDraw, x: int, y: int, w: int, title: str, detail: str, lines: int = 5) -> None:
    d.text((x, y), f"! {title}", font=font(11, True), fill=0)
    for i, line in enumerate(wrap(d, detail, font(9), w, lines)):
        d.text((x, y + 18 + i * 12), line, font=font(9), fill=0)


# ---- number formatting

def money(value: float | None, unit: str = "USD") -> str:
    if value is None:
        return "--"
    return f"${value:,.2f}" if unit == "USD" else f"{value:,.2f} {unit}"


def compact(n: float) -> str:
    """20612345 -> 20.6M; 124000000 -> 124M."""
    for unit, div in (("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if n >= div:
            v = n / div
            return f"{v:.0f}{unit}" if v >= 100 else f"{v:.1f}{unit}"
    return f"{n:.0f}"


def until(when: datetime | None, now: datetime) -> str:
    if when is None:
        return ""
    secs = int((when - now).total_seconds())
    if secs <= 0:
        return "now"
    days, rem = divmod(secs, 86400)
    hours, rem = divmod(rem, 3600)
    if days:
        return f"{days}d{hours}h"
    if hours:
        return f"{hours}h{rem // 60}m"
    return f"{rem // 60}m"
