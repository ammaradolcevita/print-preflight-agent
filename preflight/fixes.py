"""Automatic fixes for problems that are safe to fix.

How it works, in plain words:
1. Render each page at 300 dpi and cut out the trimmed area (the part that ends up on paper).
2. Bleed: grow the picture by stretching its outermost pixels outwards. Only the edge
   colour is continued, so the cut never shows a white line and no text is copied.
3. Colour: convert the pixels from RGB (screen) to CMYK (print) with MuPDF's colour
   management, so dark brand colours keep their look.
4. Size: the result is always placed at exactly trim + bleed for this product,
   which also scales a design that has the right shape but the wrong size.

Honest limitation: the output is a 300-dpi image per page, so text is no
longer "live" text. That is fine for printing, but the best result is still
re-exporting from the design tool with bleed.

Never fixed automatically: blurry pictures, text too close to the edge,
missing fonts, typos. Those need the designer's decision.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf
from PIL import Image

from .checks.base import oriented, trim_rect_on_page
from .loader import load, render_page_rgb
from .specs import get_product, mm_to_pt

RENDER_DPI = 300
EDGE_INSET_PX = 3
# Memory guard: a roll-up banner at 300 dpi is ~240 megapixels (~700 MB RGB + CMYK) and crashes a
# small server. Large products are printed at 100-150 dpi anyway, so we render them lower.
MAX_PIXELS = 40_000_000


def fix_dpi(trim_mm: tuple[float, float], bleed_mm: float, min_dpi: float) -> int:
    """300 dpi, or lower for very large products, but never below the product's minimum dpi."""
    w_in, h_in = ((v + 2 * bleed_mm) / 25.4 for v in trim_mm)
    fit = int((MAX_PIXELS / (w_in * h_in)) ** 0.5)
    return max(int(min_dpi), min(RENDER_DPI, fit))


@dataclass
class FixResult:
    output: str
    changes: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def _stretch_edges(img: Image.Image, pad_x: int, pad_y: int) -> Image.Image:
    """Grow an image by pad pixels on each side by stretching its outermost pixel row/column.

    Only the colour at the very edge is continued, so text or logos near the edge are
    never copied into the bleed (mirroring did that: a phone number showed up upside down).
    """
    w, h = img.size
    k = min(EDGE_INSET_PX, w // 4, h // 4)  # sample slightly inside: the outermost row is often anti-aliased
    out = Image.new(img.mode, (w + 2 * pad_x, h + 2 * pad_y))
    out.paste(img, (pad_x, pad_y))
    # sides: a 1-pixel strip stretched outwards
    out.paste(img.crop((k, 0, k + 1, h)).resize((pad_x, h)), (0, pad_y))
    out.paste(img.crop((w - 1 - k, 0, w - k, h)).resize((pad_x, h)), (pad_x + w, pad_y))
    out.paste(img.crop((0, k, w, k + 1)).resize((w, pad_y)), (pad_x, 0))
    out.paste(img.crop((0, h - 1 - k, w, h - k)).resize((w, pad_y)), (pad_x, pad_y + h))
    # corners: the colour near each corner
    for (cx, cy), (ox, oy) in (((k, k), (0, 0)), ((w - 1 - k, k), (pad_x + w, 0)),
                               ((k, h - 1 - k), (0, pad_y + h)), ((w - 1 - k, h - 1 - k), (pad_x + w, pad_y + h))):
        out.paste(img.getpixel((cx, cy)), (ox, oy, ox + pad_x, oy + pad_y))
    return out


def fix_artwork(path: str | Path, product_id: str, output: str | Path | None = None,
                fixes: tuple[str, ...] = ("bleed", "colour", "size")) -> FixResult:
    path = Path(path)
    product = get_product(product_id)
    artwork = load(path, product)
    output = Path(output) if output else path.with_name(f"{path.stem}_print-ready.pdf")
    result = FixResult(output=str(output))

    dpi = fix_dpi(product.trim_mm, product.spec.bleed_mm, product.spec.dpi_min)
    doc = pymupdf.open()
    for page in artwork.pages:
        placed = trim_rect_on_page(page, product)
        if placed is None:
            result.skipped.append(f"Page {page.index + 1}: wrong shape for this product, cannot fix safely.")
            continue
        (tx0, ty0, tx1, ty1), _scale = placed
        render = render_page_rgb(path, page.index, dpi=dpi)
        k = render.width / page.width_mm  # pixels per page-mm
        trimmed = render.crop((round(tx0 * k), round(ty0 * k), round(tx1 * k), round(ty1 * k)))

        trim_w, trim_h = oriented(product.trim_mm, page)
        bleed = product.spec.bleed_mm
        # resample the trimmed area to exactly the product size at 300 dpi
        target_px = (round(trim_w / 25.4 * dpi), round(trim_h / 25.4 * dpi))
        if trimmed.size != target_px:
            trimmed = trimmed.resize(target_px, Image.LANCZOS)
            if "size" in fixes and abs(_scale - 1) > 0.01:
                result.changes.append(f"Page {page.index + 1}: scaled to {trim_w:g} x {trim_h:g} mm.")
        pad = round(bleed / 25.4 * dpi)
        full = _stretch_edges(trimmed, pad, pad) if "bleed" in fixes else trimmed
        if "bleed" in fixes:
            result.changes.append(f"Page {page.index + 1}: added {bleed:g} mm bleed by extending the edge colours.")

        if "colour" in fixes:
            # MuPDF's colour management keeps the look (a naive RGB->CMYK formula shifted dark blue to grey)
            rgb = pymupdf.Pixmap(pymupdf.csRGB, full.width, full.height, full.convert("RGB").tobytes(), False)
            image_kwargs = {"pixmap": pymupdf.Pixmap(pymupdf.csCMYK, rgb)}
            result.changes.append(f"Page {page.index + 1}: converted to CMYK (colour-managed, no printer profile).")
        else:
            buf = io.BytesIO()
            full.save(buf, "PNG", dpi=(dpi, dpi))
            image_kwargs = {"stream": buf.getvalue()}

        page_w = trim_w + (2 * bleed if "bleed" in fixes else 0)
        page_h = trim_h + (2 * bleed if "bleed" in fixes else 0)
        pg = doc.new_page(width=mm_to_pt(page_w), height=mm_to_pt(page_h))
        pg.insert_image(pg.rect, **image_kwargs)
        if "bleed" in fixes:
            b = mm_to_pt(bleed)
            pg.set_trimbox(pymupdf.Rect(b, b, pg.rect.width - b, pg.rect.height - b))

    if doc.page_count:
        output.parent.mkdir(parents=True, exist_ok=True)
        doc.save(output, deflate=True)
        result.changes.append(f"Pages are now {dpi}-dpi images: text is no longer editable in this file.")
    doc.close()
    return result
