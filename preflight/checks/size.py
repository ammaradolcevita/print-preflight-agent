"""Check 3: is the page the right size and shape for the product?

Accepted (pass):  trim size, trim + bleed, or a TrimBox that equals the trim size.
Same shape (warn, fixable): the design only needs to be scaled.
Different shape (error): printing would crop or stretch the design.
"""

from __future__ import annotations

from ..models import Finding
from .base import Context, oriented, same_shape, same_size, trim_rect_on_page

NAME = "size"


def check(ctx: Context) -> list[Finding]:
    out: list[Finding] = []
    for page in ctx.artwork.pages:
        trim = oriented(ctx.product.trim_mm, page)
        full = oriented(ctx.product.full_mm, page)
        w, h = page.width_mm, page.height_mm
        detail = {
            "page_mm": [round(w, 1), round(h, 1)],
            "trim_mm": list(trim),
            "with_bleed_mm": list(full),
        }
        pno = page.index + 1

        if page.trim_box_mm is not None:
            tb = page.trim_box_mm
            tw, th = tb[2] - tb[0], tb[3] - tb[1]
            detail["trim_box_mm"] = [round(tw, 1), round(th, 1)]
            if same_size(tw, th, trim):
                out.append(Finding(NAME, "pass", "Trim size matches the product.", detail, page=pno))
                continue

        placed = trim_rect_on_page(page, ctx.product)
        if same_size(w, h, trim) or same_size(w, h, full) or (placed and abs(placed[1] - 1) < 0.01):
            # exact trim, trim + bleed, or trim centred with some (maybe too little) bleed:
            # the size is right; the bleed check judges the amount of bleed.
            out.append(Finding(NAME, "pass", "Page size matches the product.", detail, page=pno))
        elif same_shape(w, h, trim) or same_shape(w, h, full):
            out.append(
                Finding(
                    NAME,
                    "warn",
                    f"Your page is {w:.0f} x {h:.0f} mm, but the product is {trim[0]:g} x {trim[1]:g} mm. "
                    "The shape is right, so it can be scaled to fit.",
                    detail,
                    fixable=True,
                    page=pno,
                )
            )
        else:
            out.append(
                Finding(
                    NAME,
                    "error",
                    f"Your page is {w:.0f} x {h:.0f} mm, but the product is {trim[0]:g} x {trim[1]:g} mm "
                    "with a different shape. Printing it would crop or stretch your design.",
                    detail,
                    page=pno,
                )
            )
    return out
