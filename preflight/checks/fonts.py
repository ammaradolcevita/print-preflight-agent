"""Check 8: are all fonts embedded in the PDF?

If a font is not inside the file, the print shop's computer replaces it
with another font, and the text can change shape or break.
"""

from __future__ import annotations

from ..models import Finding
from .base import Context

NAME = "fonts"


def check(ctx: Context) -> list[Finding]:
    if ctx.artwork.kind == "raster":
        return [Finding(NAME, "pass", "Images have no fonts to embed.")]
    missing: dict[str, int] = {}
    total = set()
    for page in ctx.artwork.pages:
        for f in page.fonts:
            total.add(f.name)
            if not f.embedded:
                missing.setdefault(f.name, page.index + 1)
    if missing:
        names = ", ".join(sorted(missing))
        # point at the first line of text set in a missing font, so the preview can show where it is
        where = next(
            ((page.index + 1, span.bbox_mm) for page in ctx.artwork.pages for span in page.text
             if any(span.font.split("+")[-1].startswith(m.split("+")[-1][:12]) for m in missing)),
            (min(missing.values()), None),
        )
        return [
            Finding(
                NAME,
                "error",
                f"Font(s) not embedded: {names}. The printer may swap them for another font. "
                "Export the PDF with fonts embedded, or convert text to outlines.",
                {"missing": sorted(missing)},
                page=where[0],
                bbox_mm=where[1],
            )
        ]
    msg = f"All {len(total)} font(s) are embedded." if total else "No fonts used."
    return [Finding(NAME, "pass", msg)]
