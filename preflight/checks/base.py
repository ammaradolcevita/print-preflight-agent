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
