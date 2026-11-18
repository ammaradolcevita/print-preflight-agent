"""Turn a chat request ("250 matte business cards by Friday") into a product.

Deterministic first: keywords + fuzzy matching (rapidfuzz) handle typical
requests in English and Dutch without any API key. Inside an AI assistant
(MCP), the assistant itself can refine the choice from the top 3.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from rapidfuzz import fuzz

from .models import Product
from .specs import all_products

FINISHES = ("matte", "matt", "mat", "glossy", "gloss", "glans", "uncoated", "soft-touch", "soft touch", "linen")
SIZE_TOKENS = ("a2", "a3", "a4", "a5", "a6")


@dataclass
class Match:
    product: Product
    score: float  # 0..100

    def to_dict(self) -> dict:
        p = self.product
        return {
            "product_id": p.id,
            "name": p.name,
            "confidence": round(self.score / 100, 2),
            "trim_mm": list(p.trim_mm),
            "bleed_mm": p.spec.bleed_mm,
            "min_dpi": p.spec.dpi_min,
            "url": p.url,
        }


def parse_request(text: str) -> dict:
    t = text.lower()
    qty = re.search(r"\b(\d{1,3}(?:[.,]\d{3})+|\d+)\s*(?:x\b|pcs|pieces|stuks|st\b)?", t)
    quantity = int(re.sub(r"[.,]", "", qty.group(1))) if qty else None
    finish = next((f for f in FINISHES if re.search(rf"\b{re.escape(f)}\b", t)), None)
    return {"quantity": quantity, "finish": finish}


def find_products(request: str, top: int = 3) -> list[Match]:
    t = request.lower()
    sizes = [s for s in SIZE_TOKENS if re.search(rf"\b{s}\b", t)]
    matches = []
    for p in all_products():
        score = max(fuzz.partial_ratio(k, t) for k in p.keywords)
        # a size in the request ("A5") must agree with the product
        product_size = next((s for s in SIZE_TOKENS if s in p.id), None)
        if sizes and product_size:
            score += 10 if product_size in sizes else -25
        matches.append(Match(p, max(0.0, min(100.0, score))))
    matches.sort(key=lambda m: m.score, reverse=True)
    return matches[:top]
