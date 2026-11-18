"""Automatic fixes for problems that are safe to fix.

How it works, in plain words:
1. Render each page at 300 dpi and cut out the trimmed area (the part that ends up on paper).
2. Bleed: grow the picture by mirroring its outer edges outwards. Mirroring
   continues backgrounds and gradients naturally, so the cut never shows a white line.
3. Colour: convert the pixels from RGB (screen) to CMYK (print).
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
from PIL import Image, ImageOps

from .checks.base import oriented, trim_rect_on_page
from .loader import load, render_page_rgb
from .specs import get_product, mm_to_pt

RENDER_DPI = 300


@dataclass
class FixResult:
    output: str
    changes: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def _mirror_extend(img: Image.Image, pad_x: int, pad_y: int) -> Image.Image:
    """Grow an image by pad pixels on each side by mirroring its edges."""
    w, h = img.size
    out = Image.new(img.mode, (w + 2 * pad_x, h + 2 * pad_y))
    out.paste(img, (pad_x, pad_y))
    flip_x = ImageOps.mirror(img)
    flip_y = ImageOps.flip(img)
    flip_xy = ImageOps.flip(flip_x)
    # sides
    out.paste(flip_x.crop((w - pad_x, 0, w, h)), (0, pad_y))
    out.paste(flip_x.crop((0, 0, pad_x, h)), (pad_x + w, pad_y))
    out.paste(flip_y.crop((0, h - pad_y, w, h)), (pad_x, 0))
    out.paste(flip_y.crop((0, 0, w, pad_y)), (pad_x, pad_y + h))
    # corners
    out.paste(flip_xy.crop((w - pad_x, h - pad_y, w, h)), (0, 0))
    out.paste(flip_xy.crop((0, h - pad_y, pad_x, h)), (pad_x + w, 0))
    out.paste(flip_xy.crop((w - pad_x, 0, w, pad_y)), (0, pad_y + h))
    out.paste(flip_xy.crop((0, 0, pad_x, pad_y)), (pad_x + w, pad_y + h))
    return out


def fix_artwork(path: str | Path, product_id: str, output: str | Path | None = None,
                fixes: tuple[str, ...] = ("bleed", "colour", "size")) -> FixResult:
    path = Path(path)
    product = get_product(product_id)
    artwork = load(path, product)
    output = Path(output) if output else path.with_name(f"{path.stem}_print-ready.pdf")
    result = FixResult(output=str(output))

    doc = pymupdf.open()
    for page in artwork.pages:
        placed = trim_rect_on_page(page, product)
        if placed is None:
            result.skipped.append(f"Page {page.index + 1}: wrong shape for this product, cannot fix safely.")
            continue
        (tx0, ty0, tx1, ty1), _scale = placed
        render = render_page_rgb(path, page.index, dpi=RENDER_DPI)
        k = render.width / page.width_mm  # pixels per page-mm
        trimmed = render.crop((round(tx0 * k), round(ty0 * k), round(tx1 * k), round(ty1 * k)))

        trim_w, trim_h = oriented(product.trim_mm, page)
        bleed = product.spec.bleed_mm
        # resample the trimmed area to exactly the product size at 300 dpi
        target_px = (round(trim_w / 25.4 * RENDER_DPI), round(trim_h / 25.4 * RENDER_DPI))
        if trimmed.size != target_px:
            trimmed = trimmed.resize(target_px, Image.LANCZOS)
            if "size" in fixes and abs(_scale - 1) > 0.01:
                result.changes.append(f"Page {page.index + 1}: scaled to {trim_w:g} x {trim_h:g} mm.")
        pad = round(bleed / 25.4 * RENDER_DPI)
        full = _mirror_extend(trimmed, pad, pad) if "bleed" in fixes else trimmed
        if "bleed" in fixes:
            result.changes.append(f"Page {page.index + 1}: added {bleed:g} mm bleed by mirroring the edges.")

        buf = io.BytesIO()
        if "colour" in fixes:
            full.convert("CMYK").save(buf, "JPEG", quality=95, dpi=(RENDER_DPI, RENDER_DPI))
            result.changes.append(f"Page {page.index + 1}: converted to CMYK (approximate, no colour profile).")
        else:
            full.save(buf, "PNG", dpi=(RENDER_DPI, RENDER_DPI))

        page_w = trim_w + (2 * bleed if "bleed" in fixes else 0)
        page_h = trim_h + (2 * bleed if "bleed" in fixes else 0)
        pg = doc.new_page(width=mm_to_pt(page_w), height=mm_to_pt(page_h))
        pg.insert_image(pg.rect, stream=buf.getvalue())
        if "bleed" in fixes:
            b = mm_to_pt(bleed)
            pg.set_trimbox(pymupdf.Rect(b, b, pg.rect.width - b, pg.rect.height - b))

    if doc.page_count:
        output.parent.mkdir(parents=True, exist_ok=True)
        doc.save(output, deflate=True)
        result.changes.append("Pages are now 300-dpi images: text is no longer editable in this file.")
    doc.close()
    return result
