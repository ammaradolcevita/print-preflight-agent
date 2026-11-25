"""Check 6: are pictures in CMYK (print colours) or RGB (screen colours)?

Screens mix red, green and blue light (RGB). Printers mix cyan, magenta,
yellow and black ink (CMYK). Some bright RGB colours, especially vivid
blues and greens, cannot be printed and come out duller.

Spot colours (named inks such as PANTONE) are reported too: a standard print run
uses CMYK, so a spot colour is converted and may look different.

Limitation: this check looks at pictures and spot colours, not at RGB vector colours.
"""

from __future__ import annotations

from ..models import Finding
from .base import Context

NAME = "colour"


def _spot_finding(spots: list[str]) -> Finding:
    names = ", ".join(spots[:3]) + (" ..." if len(spots) > 3 else "")
    return Finding(
        NAME,
        "warn",
        f"Your file uses spot colour(s) ({names}). Standard printing uses CMYK, so they will be converted "
        "and may look slightly different. Ask your designer if the exact colour matters.",
        {"spot_colours": spots},
    )


def check(ctx: Context) -> list[Finding]:
    out = [_spot_finding(ctx.artwork.spot_colours)] if ctx.artwork.spot_colours else []
    return out + _image_colours(ctx)


def _image_colours(ctx: Context) -> list[Finding]:
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
