"""Check 5: are pictures sharp enough at the size they are printed?

"Effective dpi" = pixels of the picture / inches it covers on paper.
A 600-pixel-wide logo printed 50 mm wide has 600 / (50 / 25.4) = 305 dpi.
The same logo stretched to 100 mm has only 152 dpi and looks blurry.
"""

from __future__ import annotations

from ..models import Finding
from ..specs import tolerances
from .base import Context

NAME = "dpi"


def check(ctx: Context) -> list[Finding]:
    spec = ctx.product.spec
    tol = tolerances()
    min_mm = tol["min_image_mm"]
    slack = 1 - tol["dpi_rel"]
    out: list[Finding] = []
    checked = 0
    for page in ctx.artwork.pages:
        pno = page.index + 1
        for img in page.images:
            w_mm = img.bbox_mm[2] - img.bbox_mm[0]
            h_mm = img.bbox_mm[3] - img.bbox_mm[1]
            if w_mm < min_mm or h_mm < min_mm:
                continue
            checked += 1
            dpi = img.effective_dpi
            detail = {
                "effective_dpi": round(dpi),
                "required_dpi": spec.dpi_min,
                "pixels": [img.width_px, img.height_px],
                "printed_mm": [round(w_mm, 1), round(h_mm, 1)],
            }
            if dpi < spec.dpi_error * slack:
                out.append(
                    Finding(
                        NAME,
                        "error",
                        f"A picture ({img.width_px} x {img.height_px} px printed {w_mm:.0f} x {h_mm:.0f} mm) "
                        f"has only {dpi:.0f} dpi and will look blurry. Use a larger image or a vector logo "
                        f"(at least {spec.dpi_min:g} dpi).",
                        detail,
                        page=pno,
                        bbox_mm=img.bbox_mm,
                    )
                )
            elif dpi < spec.dpi_min * slack:
                out.append(
                    Finding(
                        NAME,
                        "warn",
                        f"A picture has {dpi:.0f} dpi; {spec.dpi_min:g} dpi is recommended. "
                        "It may look slightly soft in print.",
                        detail,
                        page=pno,
                        bbox_mm=img.bbox_mm,
                    )
                )
    if not out:
        msg = (
            f"All {checked} picture(s) are sharp enough."
            if checked
            else "No pictures found (text and vector shapes print sharp at any size)."
        )
        out.append(Finding(NAME, "pass", msg, {"images_checked": checked}))
    return out
