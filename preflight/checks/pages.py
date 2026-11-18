"""Check 2: does the number of pages fit the product (front / back)?"""

from __future__ import annotations

from ..models import Finding
from .base import Context

NAME = "pages"


def check(ctx: Context) -> list[Finding]:
    n = len(ctx.artwork.pages)
    max_pages = ctx.product.max_pages
    detail = {"pages": n, "max_pages": max_pages}
    if n > max_pages:
        return [
            Finding(
                NAME,
                "error",
                f"Your file has {n} pages, but this product has at most {max_pages} printed "
                f"side{'s' if max_pages > 1 else ''}. Please remove the extra pages.",
                detail,
            )
        ]
    if max_pages == 2 and n == 1:
        return [
            Finding(
                NAME,
                "info",
                "Your file has one page, so only the front will be printed. "
                "Add a second page if you want a printed back.",
                detail,
            )
        ]
    return [Finding(NAME, "pass", f"{n} page(s), fits this product.", detail)]
