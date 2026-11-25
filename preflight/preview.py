"""Render a page with guide lines and numbered markers for each finding.

- black solid line  = cut line (trim)
- red dashed line   = where the bleed must reach
- green dashed line = safe zone: keep text inside it

`layout()` returns the page with guide lines plus marker positions, so a web page can
draw interactive markers on top. `render_preview()` burns the markers into a PNG
(for the README, the MCP server and the CLI).
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .checks.base import trim_rect_on_page
from .loader import load, render_page_rgb
from .models import Finding, Product

COLOURS = {"error": (214, 40, 40), "warn": (232, 150, 20), "info": (60, 120, 200)}
TARGET_PX = 1600  # rendered width of the page: sharp on retina screens
MARGIN_MM = 8


@dataclass
class Marker:
    n: int
    finding: Finding
    box: tuple[float, float, float, float] | None  # pixels on the layout image
    centre: tuple[float, float]  # pixels on the layout image


def numbered(findings: list[Finding]) -> list[tuple[int, Finding]]:
    """The same numbering the preview uses, for the list next to it."""
    out, n = [], 0
    for f in findings:
        if f.severity in ("warn", "error"):
            n += 1
            out.append((n, f))
    return out


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
    try:  # servers often have no system fonts: use FiraGO Bold from pymupdf-fonts (a dependency)
        import pymupdf

        return ImageFont.truetype(io.BytesIO(pymupdf.Font("figbo").buffer), size)
    except Exception:  # noqa: BLE001
        return ImageFont.load_default(size)


def layout(path: str | Path, product: Product, findings: list[Finding] | None = None,
           page_index: int = 0) -> tuple[Image.Image, list[Marker], float]:
    """Page + guide lines (no markers), the marker positions, and the marker radius in pixels."""
    artwork = load(path, product)
    page = artwork.pages[page_index]
    page_w_in = (page.width_mm + 2 * MARGIN_MM) / 25.4
    dpi = max(36, min(400, TARGET_PX / page_w_in))  # sharp for business cards, light for banners
    base = render_page_rgb(path, page_index, dpi=int(dpi))
    px_per_mm = base.width / page.width_mm
    margin = int(MARGIN_MM * px_per_mm)
    canvas = Image.new("RGB", (base.width + 2 * margin, base.height + 2 * margin), (238, 238, 241))
    canvas.paste(base, (margin, margin))
    draw = ImageDraw.Draw(canvas)
    line = max(2, round(canvas.width / 600))

    def to_px(box):
        return tuple(margin + v * px_per_mm for v in box)

    placed = trim_rect_on_page(page, product)
    if placed:
        (tx0, ty0, tx1, ty1), scale = placed
        b = product.spec.bleed_mm * scale
        s = product.spec.safe_warn_mm * scale
        dash = 6 * line
        draw.rectangle(to_px((tx0, ty0, tx1, ty1)), outline=(0, 0, 0), width=line)
        _dashed_rect(draw, to_px((tx0 - b, ty0 - b, tx1 + b, ty1 + b)), (214, 40, 40), width=line, dash=dash)
        _dashed_rect(draw, to_px((tx0 + s, ty0 + s, tx1 - s, ty1 - s)), (30, 150, 70), width=line, dash=dash)

    r = max(12, canvas.width / 42)  # also the spacing between neighbouring markers
    markers: list[Marker] = []
    taken: list[tuple[float, float]] = []
    for n, f in numbered(findings or []):
        if f.page not in (None, page_index + 1):
            continue
        box = to_px(f.bbox_mm) if f.bbox_mm else None
        cx, cy = (box[0], box[1]) if box else (margin + r, margin / 2)
        while any(abs(cx - px) < 2 * r and abs(cy - py) < 2 * r for px, py in taken):
            cx += 2.3 * r
        taken.append((cx, cy))
        markers.append(Marker(n, f, box, (cx, cy)))
    return canvas, markers, r


def render_preview(path: str | Path, product: Product, findings: list[Finding] | None = None,
                   page_index: int = 0, width_px: int = 1000) -> Image.Image:
    canvas, markers, r = layout(path, product, findings, page_index)
    draw = ImageDraw.Draw(canvas)
    width = max(3, round(canvas.width / 400))
    for m in sorted(markers, key=lambda m: m.finding.severity == "error"):
        if m.box:
            draw.rectangle(m.box, outline=COLOURS[m.finding.severity], width=width)
    font = _font(int(r * 1.15))
    for m in markers:
        cx, cy = m.centre
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=COLOURS[m.finding.severity],
                     outline=(255, 255, 255), width=width)
        draw.text((cx, cy), str(m.n), fill=(255, 255, 255), font=font, anchor="mm")
    if canvas.width > width_px:
        canvas = canvas.resize((width_px, int(canvas.height * width_px / canvas.width)), Image.LANCZOS)
    return canvas
