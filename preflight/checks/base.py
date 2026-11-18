"""Shared helpers for checks.

A check is a plain function: check(ctx) -> list[Finding].
It measures, it never changes the file, and it never calls an LLM.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from PIL import Image

from ..loader import render_page_rgb
from ..models import Artwork, Page, Product
from ..specs import tolerances


@dataclass
class Context:
    artwork: Artwork
    product: Product
    _renders: dict = field(default_factory=dict)

    def render(self, page_index: int = 0, dpi: int = 72) -> Image.Image:
        key = (page_index, dpi)
        if key not in self._renders:
            self._renders[key] = render_page_rgb(self.artwork.path, page_index, dpi)
        return self._renders[key]


def oriented(size: tuple[float, float], page: Page) -> tuple[float, float]:
    """Return (w, h) of a product size turned to match the page orientation."""
    w, h = size
    page_landscape = page.width_mm > page.height_mm
    if (w > h) != page_landscape and w != h:
        return (h, w)
    return (w, h)


def close_mm(a: float, b: float) -> bool:
    return abs(a - b) <= tolerances()["size_mm"]


def same_size(page_w: float, page_h: float, target: tuple[float, float]) -> bool:
    return close_mm(page_w, target[0]) and close_mm(page_h, target[1])


def same_shape(page_w: float, page_h: float, target: tuple[float, float]) -> bool:
    rel = tolerances()["aspect_rel"]
    a, b = page_w / page_h, target[0] / target[1]
    return abs(a - b) <= rel * max(a, b)


def content_touches_edge(img: Image.Image, white_level: int = 245, border_px: int = 2) -> bool:
    """True when any pixel in the outer border is not (near) white.

    White borders print fine without bleed; coloured borders need bleed,
    otherwise a thin white line can appear after cutting.
    """
    gray = img.convert("L")
    w, h = gray.size
    strips = [
        gray.crop((0, 0, w, border_px)),
        gray.crop((0, h - border_px, w, h)),
        gray.crop((0, 0, border_px, h)),
        gray.crop((w - border_px, 0, w, h)),
    ]
    return any(s.getextrema()[0] < white_level for s in strips)


def trim_rect_on_page(page: Page, product: Product) -> tuple[tuple[float, float, float, float], float] | None:
    """Where the cut line sits on this page, and the page-mm per real-mm scale.

    Returns None when the page shape does not fit the product at all.
    """
    trim = oriented(product.trim_mm, page)
    full = oriented(product.full_mm, page)
    w, h = page.width_mm, page.height_mm
    if page.trim_box_mm is not None:
        tb = page.trim_box_mm
        return tb, (tb[2] - tb[0]) / trim[0]
    tol = tolerances()["size_mm"]
    if same_size(w, h, trim):
        return (0.0, 0.0, w, h), 1.0
    # Page bigger than trim at real scale (full bleed, or some extra bleed): trim is centred.
    if trim[0] - tol <= w <= trim[0] + 40 and trim[1] - tol <= h <= trim[1] + 40:
        dx, dy = (w - trim[0]) / 2, (h - trim[1]) / 2
        if abs(dx - dy) <= 1.0:
            return (dx, dy, w - dx, h - dy), 1.0
    if same_shape(w, h, trim):
        return (0.0, 0.0, w, h), w / trim[0]
    if same_shape(w, h, full):
        s = w / full[0]
        b = product.spec.bleed_mm * s
        return (b, b, w - b, h - b), s
    return None
