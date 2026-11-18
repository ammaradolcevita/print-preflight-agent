"""MCP server: lets an AI assistant (Claude Desktop, etc.) check and fix print files.

Example in Claude Desktop:
  "I need 250 matte business cards. Here is my design: /Users/me/Desktop/card.pdf"
The assistant calls find_product -> check_artwork -> (fix_artwork) -> build_product_link.

Read-only towards the shop: no carts, no orders, no logins.
Run:  python mcp_server/server.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server.mcpserver import Image, MCPServer

from preflight.fixes import fix_artwork as _fix
from preflight.matcher import find_products, parse_request
from preflight.preview import numbered, render_preview
from preflight.report import check_after_fix, check_file
from preflight.specs import get_product, load_specs

server = MCPServer(
    "print-preflight",
    instructions=(
        "Checks print artwork (PDF/PNG/JPG) against product print specs before ordering. "
        "Typical flow: find_product for the customer's request, check_artwork on their file, explain the "
        "findings in plain language, offer fix_artwork for fixable problems, then build_product_link. "
        "Never claim the file is print-ready when the report verdict is 'fail'. "
        "Unofficial prototype: it does not place orders."
    ),
)


def _report_payload(report) -> dict:
    data = report.to_dict()
    data["numbered_issues"] = [
        {"n": n, "check": f.check, "severity": f.severity, "message": f.message, "fixable": f.fixable}
        for n, f in numbered(report.findings)
    ]
    return data


@server.tool()
def find_product(request: str) -> dict:
    """Find the best matching print product for a customer's request, e.g. '250 matte business cards'."""
    return {
        "request": request,
        "parsed": parse_request(request),
        "candidates": [m.to_dict() for m in find_products(request)],
    }


@server.tool()
def get_specs(product_id: str) -> dict:
    """Print specifications (trim size, bleed, safe margin, minimum dpi) for a product, with sources."""
    p = get_product(product_id)
    return {
        "product_id": p.id,
        "name": p.name,
        "trim_mm": list(p.trim_mm),
        "bleed_mm": p.spec.bleed_mm,
        "safe_margin_mm": p.spec.safe_warn_mm,
        "min_dpi": p.spec.dpi_min,
        "max_pages": p.max_pages,
        "sources": [
            "https://www.helloprint.com/en-ie/always-a-perfect-design",
            "https://www.helloprint.com/en-ie/blog/how-to-set-up-a-file-for-print",
        ],
    }


@server.tool()
def check_artwork(file_path: str, product_id: str) -> list:
    """Check a print file (PDF, PNG or JPG on this computer) for a product.

    Returns the report (verdict + numbered issues in plain English) and an annotated preview image:
    black line = cut line, red dashed = where bleed must reach, green dashed = safe zone.
    """
    report = check_file(file_path, product_id)
    out: list = [_report_payload(report)]
    if report.verdict != "fail" or any(f.check != "file" for f in report.findings):
        try:
            preview = render_preview(file_path, get_product(product_id), report.findings, width_px=900)
            png = Path(file_path).with_name(Path(file_path).stem + "_preflight.png")
            preview.save(png)
            out.append(Image(path=str(png)))
        except Exception:  # noqa: BLE001 - a preview is a bonus, never a reason to fail
            pass
    return out


@server.tool()
def fix_artwork(file_path: str, product_id: str) -> dict:
    """Automatically fix what is safe to fix (missing bleed, RGB colours, scale) and re-check.

    Writes '<name>_print-ready.pdf' next to the original; the original is never changed.
    Problems that need the designer (blurry pictures, text near the edge, typos) are kept in the report.
    """
    before = check_file(file_path, product_id)
    result = _fix(file_path, product_id)
    after = check_after_fix(before, result.output)
    return {
        "fixed_file": result.output,
        "changes": result.changes,
        "skipped": result.skipped,
        "verdict_before": before.verdict,
        "verdict_after": after.verdict,
        "report_after": _report_payload(after),
    }


@server.tool()
def build_product_link(product_id: str) -> dict:
    """Public product page where the customer can order (no cart or order is created)."""
    p = get_product(product_id)
    return {"product_id": p.id, "name": p.name, "url": p.url}


@server.tool()
def list_products() -> list[dict]:
    """All products this prototype knows, with their trim sizes."""
    return [{"product_id": p["id"], "name": p["name"]} for p in load_specs()["products"]]


if __name__ == "__main__":
    server.run()
