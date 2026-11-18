"""Generate synthetic artwork files with known problems.

Used by the tests and by eval/make_fixtures.py. Because we create each
file ourselves, we know the right answer ("label") for every check.
"""

from __future__ import annotations

import io
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw

from .specs import mm_to_pt


def _pattern(px: tuple[int, int], mode: str) -> Image.Image:
    """A simple coloured test picture with some detail."""
    img = Image.new("RGB", px, (40, 110, 200))
    d = ImageDraw.Draw(img)
    w, h = px
    for i in range(0, w, max(4, w // 20)):
        d.line([(i, 0), (w - i, h)], fill=(250, 200, 40), width=max(1, w // 200))
    d.ellipse([w * 0.3, h * 0.3, w * 0.7, h * 0.7], fill=(220, 40, 60))
    return img.convert(mode) if mode != "RGB" else img


def image_bytes(px: tuple[int, int], mode: str = "CMYK") -> bytes:
    buf = io.BytesIO()
    img = _pattern(px, mode)
    if mode == "CMYK":
        img.save(buf, "JPEG", quality=90)
    else:
        img.save(buf, "PNG")
    return buf.getvalue()


def make_pdf(
    path: str | Path,
    page_mm: tuple[float, float],
    *,
    pages: int = 1,
    background: tuple[float, float, float] | None = None,
    images: list[dict] | None = None,
    texts: list[dict] | None = None,
    trim_box_mm: tuple[float, float, float, float] | None = None,
) -> Path:
    """Create a PDF.

    images: [{"px": (w, h), "rect_mm": (x0, y0, x1, y1), "mode": "CMYK" | "RGB"}]
    texts:  [{"text": "...", "at_mm": (x, y), "size": 9, "fontfile": None | path}]
            without fontfile, Helvetica is used and is NOT embedded.
    background: RGB 0..1 fill for the whole page, or None for white.
    """
    path = Path(path)
    doc = pymupdf.open()
    w_pt, h_pt = mm_to_pt(page_mm[0]), mm_to_pt(page_mm[1])
    for _ in range(pages):
        page = doc.new_page(width=w_pt, height=h_pt)
        if background is not None:
            page.draw_rect(page.rect, color=None, fill=background)
        for im in images or []:
            x0, y0, x1, y1 = (mm_to_pt(v) for v in im["rect_mm"])
            page.insert_image(pymupdf.Rect(x0, y0, x1, y1), stream=image_bytes(im["px"], im.get("mode", "CMYK")))
        for t in texts or []:
            x, y = (mm_to_pt(v) for v in t["at_mm"])
            kwargs = {"fontsize": t.get("size", 9)}
            if t.get("fontfile"):
                kwargs.update(fontname="embedded", fontfile=str(t["fontfile"]))
            else:
                kwargs.update(fontname="helv")
            page.insert_text(pymupdf.Point(x, y), t["text"], **kwargs)
        if trim_box_mm is not None:
            page.set_trimbox(pymupdf.Rect(*(mm_to_pt(v) for v in trim_box_mm)))
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(path)
    doc.close()
    return path


def make_raster(path: str | Path, px: tuple[int, int], mode: str = "RGB") -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    img = _pattern(px, mode)
    if path.suffix.lower() in (".jpg", ".jpeg"):
        img.save(path, "JPEG", quality=90)
    else:
        img.save(path)
    return path


def px_for(mm: float, dpi: float) -> int:
    """How many pixels a picture needs to cover `mm` at `dpi`."""
    return round(mm / 25.4 * dpi)
