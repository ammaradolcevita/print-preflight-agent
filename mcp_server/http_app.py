"""Hosted MCP server: the same checks over Streamable HTTP, for Claude custom connectors.

Differences from the local server (server.py):
- Files are uploaded in chunks (upload_chunk) and referred to by file_id, never by a path.
- Only the products we test best are offered (HOSTED_PRODUCTS).
- Heavy work (render, check, fix) runs one job at a time, so memory stays predictable on a small server.
- The fixed PDF is returned as a short-lived download link.

Run locally:  uvicorn mcp_server.http_app:app --port 8000
Endpoint:     /mcp (MCP), /health, /files/<id>/<name>.pdf (fixed files)
"""

from __future__ import annotations

import base64
import binascii
import io
import logging
import os
import threading

from mcp.server.mcpserver import Image, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response

from mcp_server import storage
from mcp_server.common import INSTRUCTIONS, product_or_error, register_catalog_tools, report_payload
from preflight.fixes import fix_artwork as _fix
from preflight.preview import render_preview
from preflight.report import check_after_fix, check_file

VERSION = "0.2.0"
HOSTED_PRODUCTS = ("business-card", "flyer-a5", "flyer-a6")
MAX_CHUNK_BYTES = 2 * 1024 * 1024  # decoded; ~2.7 MB as base64, well under the request limit
BUSY_TIMEOUT_S = 90
PREVIEW_PX = 900

log = logging.getLogger("print-preflight")
_heavy = threading.Lock()  # sync tools run in worker threads; one render/fix at a time

server = MCPServer(
    "print-preflight",
    instructions=INSTRUCTIONS + (
        " Online demo: upload the file with upload_chunk (base64, in order) to get a file_id, "
        f"then check_artwork(file_id, product_id). Products: {', '.join(HOSTED_PRODUCTS)}."
    ),
)
register_catalog_tools(server, HOSTED_PRODUCTS)


def public_url() -> str:
    return (os.environ.get("PUBLIC_BASE_URL") or os.environ.get("RENDER_EXTERNAL_URL")
            or "http://localhost:8000").rstrip("/")


class _Busy:
    def __enter__(self):
        if not _heavy.acquire(timeout=BUSY_TIMEOUT_S):
            raise ToolError("The checker is busy right now. Please try again in a minute.")

    def __exit__(self, *exc):
        _heavy.release()


def _stored(file_id: str, **kw) -> storage.Stored:
    try:
        return storage.get(file_id, **kw)
    except storage.StorageError as exc:
        raise ToolError(str(exc)) from exc


def _preview(path, product, findings) -> Image | None:
    try:
        img = render_preview(path, product, findings, width_px=PREVIEW_PX)
    except Exception:  # noqa: BLE001 - a preview is a bonus, never a reason to fail
        log.exception("preview failed")
        return None
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return Image(data=buf.getvalue(), format="png")


@server.tool()
def upload_chunk(data_base64: str, offset: int = 0, upload_id: str = "", filename: str = "artwork",
                 final: bool = False) -> dict:
    """Upload a print file (PDF, PNG or JPG, max 20 MB) in base64 chunks of at most 2 MB.

    First call: no upload_id, offset 0. Next calls: the upload_id you got and offset = bytes sent so far.
    Set final=true on the last chunk to get the file_id for check_artwork. Files are deleted after 60 minutes.
    """
    try:
        data = base64.b64decode(data_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ToolError("The upload data is not valid base64.") from exc
    if len(data) > MAX_CHUNK_BYTES:
        raise ToolError("This chunk is too large. Send at most 2 MB per chunk.")
    try:
        upload_id, size = storage.append_chunk(upload_id or None, filename, data, offset)
        if not final:
            return {"upload_id": upload_id, "received_bytes": size}
        stored = storage.finish_upload(upload_id)
    except storage.StorageError as exc:
        raise ToolError(str(exc)) from exc
    log.info("upload finished: %s, %d bytes", stored.kind, size)
    return {"file_id": stored.file_id, "file_name": stored.display_name, "kind": stored.kind,
            "size_bytes": size}


@server.tool()
def check_artwork(file_id: str, product_id: str) -> list:
    """Check an uploaded print file (file_id from upload_chunk) for a product.

    Returns the report (verdict + numbered issues in plain English) and an annotated preview image:
    black line = cut line, red dashed = where bleed must reach, green dashed = safe zone.
    """
    product = product_or_error(product_id, HOSTED_PRODUCTS)
    stored = _stored(file_id)
    with _Busy():
        report = check_file(stored.path, product.id)
        payload = report_payload(report)
        payload["file"] = stored.display_name  # never show server paths
        payload["file_id"] = file_id
        out: list = [payload]
        if any(f.check != "file" for f in report.findings):
            img = _preview(stored.path, product, report.findings)
            if img:
                out.append(img)
    log.info("check: %s -> %s in %.2fs", product.id, report.verdict, report.seconds)
    return out


@server.tool()
def fix_artwork(file_id: str, product_id: str) -> list:
    """Automatically fix what is safe to fix (missing bleed, RGB colours, scale) and re-check.

    Returns what changed, what still needs the designer, the new verdict, a preview of the fixed file
    and a download link for the fixed PDF (valid for 60 minutes). The uploaded file is never changed.
    """
    product = product_or_error(product_id, HOSTED_PRODUCTS)
    stored = _stored(file_id)
    with _Busy():
        before = check_file(stored.path, product.id)
        if any(f.check == "file" and f.severity == "error" for f in before.findings):
            raise ToolError(next(f.message for f in before.findings if f.check == "file"))
        work = storage.workdir(file_id)
        result = _fix(stored.path, product.id, output=work / "fixed.pdf")
        if not result.changes:
            raise ToolError("Nothing could be fixed automatically: " + " ".join(result.skipped))
        fixed = storage.store_output(work / "fixed.pdf", f"{stored.display_name}_print-ready")
        after = check_after_fix(before, fixed.path)
        payload = report_payload(after)
        payload["file"] = f"{fixed.display_name}.pdf"
        img = _preview(fixed.path, product, after.findings)
    log.info("fix: %s %s -> %s", product.id, before.verdict, after.verdict)
    out: list = [{
        "fixed_file_id": fixed.file_id,
        "download_url": f"{public_url()}/files/{fixed.file_id}/{fixed.display_name}.pdf",
        "changes": result.changes,
        "skipped": result.skipped,
        "verdict_before": before.verdict,
        "verdict_after": after.verdict,
        "report_after": payload,
    }]
    if img:
        out.append(img)
    return out


@server.custom_route("/health", methods=["GET"])
async def health(request: Request) -> Response:
    return JSONResponse({"status": "ok", "version": VERSION})


@server.custom_route("/files/{file_id}/{name}", methods=["GET"])
async def download(request: Request) -> Response:
    try:
        stored = storage.get(request.path_params["file_id"], output_only=True)
    except storage.StorageError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    return FileResponse(stored.path, media_type="application/pdf",
                        filename=f"{stored.display_name}.pdf",
                        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


def _security() -> TransportSecuritySettings:
    hosts = ["localhost", "localhost:*", "127.0.0.1", "127.0.0.1:*"]
    for h in [os.environ.get("RENDER_EXTERNAL_HOSTNAME", "")] + os.environ.get("ALLOWED_HOSTS", "").split(","):
        if h.strip():
            hosts += [h.strip(), f"{h.strip()}:*"]
    origins = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]
    return TransportSecuritySettings(allowed_hosts=hosts, allowed_origins=origins)


app = server.streamable_http_app(
    stateless_http=True,
    json_response=True,
    max_request_body_size=8 * 1024 * 1024,
    transport_security=_security(),
)
