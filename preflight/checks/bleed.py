"""Check 4: is there enough bleed (extra design beyond the cut line)?

Printers cut stacks of paper, and the cut is never perfectly exact.
If the background colour stops exactly at the cut line, a thin white
line can appear on the edge. Bleed = extending the design past the line.

Two steps:
1. Room: how much page is there around the cut line (TrimBox, or page size)?
2. Content: does the design actually fill that room? A page can be big enough
   (crop marks, a TrimBox from the template) while the background still stops
   at the cut line. We look at the rendered page just inside and just outside
   the cut line on each side.
"""

from __future__ import annotations

from PIL import Image

from ..models import Finding
from .base import Context, close_mm, content_touches_edge, trim_rect_on_page

NAME = "bleed"
RENDER_DPI = 72
WHITE = 245  # grey level above which a pixel counts as paper white
INK_INSIDE = 0.5  # share of coloured pixels just inside the cut line that means "colour reaches the edge"
INK_OUTSIDE = 0.1  # share of coloured pixels in the bleed below which the bleed is "empty"


def _ink_share(img: Image.Image, box: tuple[int, int, int, int]) -> float:
    hist = img.crop(box).convert("L").histogram()
    total = sum(hist)
    return sum(hist[:WHITE]) / total if total else 0.0


def _sides_without_bleed(img: Image.Image, trim_px: tuple[float, float, float, float], bleed_px: float) -> list[str]:
    """Sides where colour reaches the cut line from inside but does not continue into the bleed."""
    x0, y0, x1, y1 = (round(v) for v in trim_px)
    k = max(1, round(bleed_px / 2))  # sample in the middle of the bleed: crop marks start outside it
    t = 2  # strip thickness in pixels
    w, h = img.size
    if x0 - k - t < 0 or y0 - k - t < 0 or x1 + k + t > w or y1 + k + t > h:
        return []
    sides = {
        "left": ((x0 + 1, y0, x0 + 1 + t, y1), (x0 - k - t, y0, x0 - k, y1)),
        "right": ((x1 - 1 - t, y0, x1 - 1, y1), (x1 + k, y0, x1 + k + t, y1)),
        "top": ((x0, y0 + 1, x1, y0 + 1 + t), (x0, y0 - k - t, x1, y0 - k)),
        "bottom": ((x0, y1 - 1 - t, x1, y1 - 1), (x0, y1 + k, x1, y1 + k + t)),
    }
    return [name for name, (inside, outside) in sides.items()
            if _ink_share(img, inside) >= INK_INSIDE and _ink_share(img, outside) < INK_OUTSIDE]


def check(ctx: Context) -> list[Finding]:
    out: list[Finding] = []
    required = ctx.product.spec.bleed_mm
    for page in ctx.artwork.pages:
        pno = page.index + 1
        detail = {"required_mm": required}
        placed = trim_rect_on_page(page, ctx.product)
        if placed is None:
            out.append(
                Finding(NAME, "info", "Bleed not checked because the page has the wrong shape.", detail, page=pno)
            )
            continue
        (tx0, ty0, tx1, ty1), scale = placed
        bleed = min(tx0, ty0, page.width_mm - tx1, page.height_mm - ty1) / scale  # room, in real mm
        detail["measured_mm"] = round(bleed, 2)

        if bleed >= required - 0.1 or close_mm(bleed, required):
            img = ctx.render(page.index, dpi=RENDER_DPI)
            k = img.width / page.width_mm
            empty = _sides_without_bleed(img, (tx0 * k, ty0 * k, tx1 * k, ty1 * k), required * scale * k)
            if empty:
                detail["sides_without_bleed"] = empty
                out.append(
                    Finding(
                        NAME,
                        "error",
                        f"Your file has room for bleed, but the design stops at the cut line ({', '.join(empty)}). "
                        f"After cutting, a thin white line may show. Extend the background {required:g} mm "
                        "past the cut line.",
                        detail,
                        fixable=True,
                        page=pno,
                    )
                )
            else:
                out.append(
                    Finding(NAME, "pass", f"Bleed is {bleed:.1f} mm (needed: {required:g} mm).", detail, page=pno)
                )
            continue

        touches = content_touches_edge(ctx.render(page.index, dpi=RENDER_DPI))
        detail["content_touches_edge"] = touches
        if bleed <= 0.05:
            if touches:
                out.append(
                    Finding(
                        NAME,
                        "error",
                        f"Your design has no bleed, but colour or images reach the edge. After cutting, "
                        f"a thin white line may show. Extend the design {required:g} mm past each edge.",
                        detail,
                        fixable=True,
                        page=pno,
                    )
                )
            else:
                out.append(
                    Finding(
                        NAME,
                        "info",
                        "No bleed, but the edges are white, so this usually prints fine.",
                        detail,
                        page=pno,
                    )
                )
        else:
            out.append(
                Finding(
                    NAME,
                    "warn" if touches else "info",
                    f"Bleed is only {bleed:.1f} mm; {required:g} mm is needed.",
                    detail,
                    fixable=touches,
                    page=pno,
                )
            )
    return out
