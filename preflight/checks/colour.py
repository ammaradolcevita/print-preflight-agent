"""Check 6: are pictures in CMYK (print colours) or RGB (screen colours)?

Screens mix red, green and blue light (RGB). Printers mix cyan, magenta,
yellow and black ink (CMYK). Some bright RGB colours, especially vivid
blues and greens, cannot be printed and come out duller.

Limitation: this check looks at pictures, not at vector colours.
"""

from __future__ import annotations

from ..models import Finding
from .base import Context

NAME = "colour"


def check(ctx: Context) -> list[Finding]:
    rgb = []
    for page in ctx.artwork.pages:
        for img in page.images:
            if img.colour == "RGB":
                rgb.append((page.index + 1, img))
    if rgb:
        pages = sorted({p for p, _ in rgb})
        return [
            Finding(
                NAME,
                "warn",
                f"{len(rgb)} picture(s) use RGB (screen colours) instead of CMYK (print colours). "
                "Very bright colours may print duller than on your screen.",
                {"rgb_images": len(rgb), "pages": pages},
                fixable=True,
                page=pages[0],
                bbox_mm=rgb[0][1].bbox_mm,
            )
        ]
    total = sum(len(p.images) for p in ctx.artwork.pages)
    msg = "All pictures use print colours (CMYK or grayscale)." if total else "No pictures to check."
    return [Finding(NAME, "pass", msg, {"images": total})]
