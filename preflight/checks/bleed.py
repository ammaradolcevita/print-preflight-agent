"""Check 4: is there enough bleed (extra design beyond the cut line)?

Printers cut stacks of paper, and the cut is never perfectly exact.
If the background colour stops exactly at the cut line, a thin white
line can appear on the edge. Bleed = extending the design past the line.
"""

from __future__ import annotations

from ..models import Finding
from .base import Context, close_mm, content_touches_edge, oriented, same_shape, same_size

NAME = "bleed"


def _measured_bleed(page, trim, full) -> float | None:
    """Smallest bleed on any side in mm, or None when the page size is not usable."""
    if page.trim_box_mm is not None:
        x0, y0, x1, y1 = page.trim_box_mm
        return min(x0, y0, page.width_mm - x1, page.height_mm - y1)
    w, h = page.width_mm, page.height_mm
    if same_size(w, h, trim):
        return 0.0
    if same_size(w, h, full) or (w > trim[0] and h > trim[1]):
        return min((w - trim[0]) / 2, (h - trim[1]) / 2)
    # Scaled artwork: judge by shape.
    if same_shape(w, h, full) and not same_shape(w, h, trim):
        return (full[0] - trim[0]) / 2
    if same_shape(w, h, trim):
        return 0.0
    return None


def check(ctx: Context) -> list[Finding]:
    out: list[Finding] = []
    required = ctx.product.spec.bleed_mm
    for page in ctx.artwork.pages:
        pno = page.index + 1
        trim = oriented(ctx.product.trim_mm, page)
        full = oriented(ctx.product.full_mm, page)
        bleed = _measured_bleed(page, trim, full)
        detail = {"required_mm": required}
        if bleed is None:
            out.append(
                Finding(NAME, "info", "Bleed not checked because the page has the wrong shape.", detail, page=pno)
            )
            continue
        detail["measured_mm"] = round(bleed, 2)

        if bleed >= required - 0.1 or close_mm(bleed, required):
            out.append(Finding(NAME, "pass", f"Bleed is {bleed:.1f} mm (needed: {required:g} mm).", detail, page=pno))
            continue

        touches = content_touches_edge(ctx.render(page.index, dpi=72))
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
