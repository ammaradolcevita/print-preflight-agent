"""Tools and helpers shared by the local (stdio) and the hosted (HTTP) server."""

from __future__ import annotations

from collections.abc import Collection

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from preflight.matcher import find_products, parse_request
from preflight.preview import numbered
from preflight.specs import get_product, load_specs

SOURCES = [
    "https://www.helloprint.com/en-ie/always-a-perfect-design",
    "https://www.helloprint.com/en-ie/blog/how-to-set-up-a-file-for-print",
]

INSTRUCTIONS = (
    "Checks print artwork (PDF/PNG/JPG) against product print specs before ordering. "
    "Typical flow: find_product for the customer's request, check_artwork on their file, explain the "
    "findings in plain language, offer fix_artwork for fixable problems, then build_product_link. "
    "Never claim the file is print-ready when the report verdict is 'fail'. "
    "Unofficial prototype: it does not place orders."
)


def report_payload(report) -> dict:
    data = report.to_dict()
    data["numbered_issues"] = [
        {"n": n, "check": f.check, "severity": f.severity, "message": f.message, "fixable": f.fixable}
        for n, f in numbered(report.findings)
    ]
    return data


def product_or_error(product_id: str, products: Collection[str] | None = None):
    """The product, or a ToolError the customer can read (unknown id, or not in this demo)."""
    try:
        p = get_product(product_id)
    except Exception as exc:  # noqa: BLE001 - unknown id
        raise ToolError(f"Unknown product '{product_id}'. Use list_products to see the options.") from exc
    if products is not None and p.id not in products:
        raise ToolError(f"'{p.name}' is not available in this online demo. Available: {', '.join(products)}.")
    return p


def register_catalog_tools(server: MCPServer, products: Collection[str] | None = None) -> None:
    """find_product, get_specs, build_product_link, list_products. `products` limits the catalogue."""

    def allowed(product_id: str):
        return product_or_error(product_id, products)

    @server.tool()
    def find_product(request: str) -> dict:
        """Find the best matching print product for a customer's request, e.g. '250 matte business cards'."""
        candidates = [m.to_dict() for m in find_products(request)]
        if products is not None:
            candidates = [c for c in candidates if c.get("product_id") in products]
        return {"request": request, "parsed": parse_request(request), "candidates": candidates}

    @server.tool()
    def get_specs(product_id: str) -> dict:
        """Print specifications (trim size, bleed, safe margin, minimum dpi) for a product, with sources."""
        p = allowed(product_id)
        return {
            "product_id": p.id,
            "name": p.name,
            "trim_mm": list(p.trim_mm),
            "bleed_mm": p.spec.bleed_mm,
            "safe_margin_mm": p.spec.safe_warn_mm,
            "min_dpi": p.spec.dpi_min,
            "max_pages": p.max_pages,
            "sources": SOURCES,
        }

    @server.tool()
    def build_product_link(product_id: str) -> dict:
        """Public product page where the customer can order (no cart or order is created)."""
        p = allowed(product_id)
        return {"product_id": p.id, "name": p.name, "url": p.url}

    @server.tool()
    def list_products() -> list[dict]:
        """All products this server can check, with their names."""
        return [{"product_id": p["id"], "name": p["name"]} for p in load_specs()["products"]
                if products is None or p["id"] in products]
