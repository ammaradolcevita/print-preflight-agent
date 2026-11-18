"""Render a page with guide lines and numbered markers for each finding.

- black solid line  = cut line (trim)
- red dashed line   = where the bleed must reach
- green dashed line = safe zone: keep text inside it
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .checks.base import trim_rect_on_page
from .loader import load, render_page_rgb
from .models import Finding, Product

COLOURS = {"error": (214, 40, 40), "warn": (232, 150, 20), "info": (60, 120, 200)}


def _dashed_rect(draw: ImageDraw.ImageDraw, box, colour, width=2, dash=10):
    x0, y0, x1, y1 = box
    for (ax, ay, bx, by) in ((x0, y0, x1, y0), (x1, y0, x1, y1), (x1, y1, x0, y1), (x0, y1, x0, y0)):
        length = max(abs(bx - ax), abs(by - ay))
        steps = max(1, int(length // dash))
        for i in range(0, steps, 2):
            t0, t1 = i / steps, min(1, (i + 1) / steps)
            draw.line([(ax + (bx - ax) * t0, ay + (by - ay) * t0), (ax + (bx - ax) * t1, ay + (by - ay) * t1)],
                      fill=colour, width=width)


def _font(size: int):
    for name in ("DejaVuSans-Bold.ttf", "Arial Bold.ttf", "arialbd.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def render_preview(path: str | Path, product: Product, findings: list[Finding] | None = None,
                   page_index: int = 0, width_px: int = 1000) -> Image.Image:
    artwork = load(path, product)
    page = artwork.pages[page_index]
    base = render_page_rgb(path, page_index, dpi=150)
    # Work on a canvas with a margin, so lines outside the page are visible too.
    px_per_mm = base.width / page.width_mm
    margin = int(8 * px_per_mm)
    canvas = Image.new("RGB", (base.width + 2 * margin, base.height + 2 * margin), (236, 236, 240))
    canvas.paste(base, (margin, margin))
    draw = ImageDraw.Draw(canvas)

    def to_px(box):
        return tuple(margin + v * px_per_mm for v in box)

    placed = trim_rect_on_page(page, product)
    if placed:
        (tx0, ty0, tx1, ty1), scale = placed
        b = product.spec.bleed_mm * scale
        s = product.spec.safe_warn_mm * scale
        draw.rectangle(to_px((tx0, ty0, tx1, ty1)), outline=(0, 0, 0), width=2)
        _dashed_rect(draw, to_px((tx0 - b, ty0 - b, tx1 + b, ty1 + b)), (214, 40, 40), width=2)
        _dashed_rect(draw, to_px((tx0 + s, ty0 + s, tx1 - s, ty1 - s)), (30, 150, 70), width=2)

    font = _font(max(14, int(3.2 * px_per_mm)))
    r = max(10, int(2.6 * px_per_mm))
    items = [(n, f) for n, f in numbered(findings or []) if f.page in (None, page_index + 1)]
    # boxes first (warnings, then errors on top), markers after, so nothing hides a number
    for _, f in sorted(items, key=lambda it: it[1].severity == "error"):
        if f.bbox_mm:
            draw.rectangle(to_px(f.bbox_mm), outline=COLOURS[f.severity], width=3)
    placed_markers: list[tuple[float, float]] = []
    for n, f in items:
        if f.bbox_mm:
            cx, cy = to_px(f.bbox_mm)[:2]
        else:
            cx, cy = margin + r, margin / 2
        while any(abs(cx - px) < 2 * r and abs(cy - py) < 2 * r for px, py in placed_markers):
            cx += 2.2 * r
        placed_markers.append((cx, cy))
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=COLOURS[f.severity], outline=(255, 255, 255), width=2)
        draw.text((cx, cy), str(n), fill=(255, 255, 255), font=font, anchor="mm")

    if canvas.width > width_px:
        canvas = canvas.resize((width_px, int(canvas.height * width_px / canvas.width)), Image.LANCZOS)
    return canvas


def numbered(findings: list[Finding]) -> list[tuple[int, Finding]]:
    """The same numbering the preview uses, for the list next to it."""
    out, n = [], 0
    for f in findings:
        if f.severity in ("warn", "error"):
            n += 1
            out.append((n, f))
    return out
