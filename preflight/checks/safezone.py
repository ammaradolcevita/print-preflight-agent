"""Check 7: is any text too close to the cut line?

The cut can move by a millimetre or two. Text closer than the safe margin
can be cut off or look cramped. Backgrounds and full-bleed photos are fine
at the edge; this check looks at text only.
"""

from __future__ import annotations

from ..models import Finding
from .base import Context, trim_rect_on_page

NAME = "safezone"
MAX_FINDINGS = 5


def check(ctx: Context) -> list[Finding]:
    spec = ctx.product.spec
    out: list[Finding] = []
    any_text = False
    for page in ctx.artwork.pages:
        pno = page.index + 1
        placed = trim_rect_on_page(page, ctx.product)
        if placed is None or not page.text:
            continue
        any_text = True
        (tx0, ty0, tx1, ty1), scale = placed
        for span in page.text:
            x0, y0, x1, y1 = span.bbox_mm
            # distance from the text box to the nearest cut line, in real mm
            d = min(x0 - tx0, y0 - ty0, tx1 - x1, ty1 - y1) / scale
            detail = {"distance_mm": round(d, 1), "text": span.text.strip()[:40], "safe_mm": spec.safe_warn_mm}
            if d < spec.safe_error_mm:
                sev, msg = "error", (
                    f"\"{span.text.strip()[:30]}\" is {max(d, 0):.1f} mm from the cut line and may be cut off. "
                    f"Move it at least {spec.safe_warn_mm:g} mm inside."
                )
            elif d < spec.safe_warn_mm:
                sev, msg = "warn", (
                    f"\"{span.text.strip()[:30]}\" is {d:.1f} mm from the cut line; "
                    f"{spec.safe_warn_mm:g} mm is safer."
                )
            else:
                continue
            out.append(Finding(NAME, sev, msg, detail, page=pno, bbox_mm=span.bbox_mm))
    if out:
        order = {"error": 0, "warn": 1}
        out.sort(key=lambda f: (order[f.severity], f.detail["distance_mm"]))
        return out[:MAX_FINDINGS]
    if ctx.artwork.kind == "raster":
        return [Finding(NAME, "info", "Text inside pictures cannot be measured; check the margins yourself.")]
    msg = f"All text is at least {spec.safe_warn_mm:g} mm inside the cut line." if any_text else "No text found."
    return [Finding(NAME, "pass", msg)]
