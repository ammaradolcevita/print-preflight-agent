"""Plain data classes shared by every module.

Everything is measured in millimetres (mm) unless the name says otherwise,
so the checks never have to think about PDF points or pixels.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

Severity = Literal["pass", "info", "warn", "error"]
Box = tuple[float, float, float, float]  # x0, y0, x1, y1 in mm, origin top-left


@dataclass
class ClassSpec:
    """Numbers for a product class ("small" or "large")."""

    bleed_mm: float
    safe_error_mm: float
    safe_warn_mm: float
    dpi_min: float
    dpi_error: float


@dataclass
class Product:
    id: str
    name: str
    product_class: str
    trim_mm: tuple[float, float]
    max_pages: int
    url: str
    keywords: list[str]
    spec: ClassSpec

    @property
    def full_mm(self) -> tuple[float, float]:
        """Trim size plus bleed on every side: the ideal page size."""
        b = self.spec.bleed_mm
        return (self.trim_mm[0] + 2 * b, self.trim_mm[1] + 2 * b)


@dataclass
class ImageInfo:
    """One picture placed on a page."""

    width_px: int
    height_px: int
    bbox_mm: Box
    colour: str  # "RGB", "CMYK", "Gray" or "Other"

    @property
    def effective_dpi(self) -> float:
        """Pixels per inch at the size the picture is actually printed."""
        w_in = (self.bbox_mm[2] - self.bbox_mm[0]) / 25.4
        h_in = (self.bbox_mm[3] - self.bbox_mm[1]) / 25.4
        if w_in <= 0 or h_in <= 0:
            return float("inf")
        return min(self.width_px / w_in, self.height_px / h_in)


@dataclass
class TextSpan:
    text: str
    bbox_mm: Box
    size_pt: float
    font: str


@dataclass
class FontInfo:
    name: str
    embedded: bool


@dataclass
class Page:
    index: int
    width_mm: float
    height_mm: float
    trim_box_mm: Box | None = None  # set only when the PDF defines a TrimBox smaller than the page
    images: list[ImageInfo] = field(default_factory=list)
    text: list[TextSpan] = field(default_factory=list)
    fonts: list[FontInfo] = field(default_factory=list)


@dataclass
class Artwork:
    """A loaded file in one internal shape, whether it was a PDF or a PNG/JPG."""

    path: str
    kind: Literal["pdf", "raster"]
    pages: list[Page]
    spot_colours: list[str] = field(default_factory=list)  # named inks (Separation/DeviceN), e.g. PANTONE 286 C


@dataclass
class Finding:
    check: str
    severity: Severity
    message: str  # plain English for the customer, max two sentences
    detail: dict = field(default_factory=dict)  # measured vs required numbers
    fixable: bool = False
    page: int | None = None  # 1-based page number for people
    bbox_mm: Box | None = None  # where on the page, for the preview overlay

    def to_dict(self) -> dict:
        return asdict(self)
