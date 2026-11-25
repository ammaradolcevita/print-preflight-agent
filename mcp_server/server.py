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

from mcp_server.common import INSTRUCTIONS, register_catalog_tools, report_payload
from preflight.fixes import fix_artwork as _fix
from preflight.preview import render_preview
from preflight.report import check_after_fix, check_file
from preflight.specs import get_product

server = MCPServer("print-preflight", instructions=INSTRUCTIONS)
register_catalog_tools(server)


@server.tool()
def check_artwork(file_path: str, product_id: str) -> list:
    """Check a print file (PDF, PNG or JPG on this computer) for a product.

    Returns the report (verdict + numbered issues in plain English) and an annotated preview image:
    black line = cut line, red dashed = where bleed must reach, green dashed = safe zone.
    """
    report = check_file(file_path, product_id)
    out: list = [report_payload(report)]
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
        "report_after": report_payload(after),
    }


if __name__ == "__main__":
    server.run()
