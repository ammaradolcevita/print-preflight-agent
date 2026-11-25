"""Hosted MCP server: the same checks over Streamable HTTP, for Claude custom connectors.

Differences from the local server (server.py):
- Files are uploaded in chunks (upload_chunk) and referred to by file_id, never by a path.
- Only the products we test best are offered (HOSTED_PRODUCTS).
- Heavy work (render, check, fix) runs one job at a time, so memory stays predictable on a small server.
- The fixed PDF is returned as a short-lived download link.
- An MCP App, "Preflight Studio" (ui://preflight/studio.html), lets the customer upload, check and fix
  inside the chat. upload_chunk is visible to that app only, not to the model.

Run locally:  uvicorn mcp_server.http_app:app --port 8000
Endpoint:     /mcp (MCP), /health, /files/<id>/<name>.pdf (fixed files)
"""

from __future__ import annotations

import base64
import binascii
import io
import json
import logging
import os
import re
import threading
from pathlib import Path
from typing import Any

import pymupdf
from mcp.server.apps import Apps
from mcp.server.mcpserver import Image, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response

from mcp_server import limits, storage
from mcp_server.common import INSTRUCTIONS, product_or_error, register_catalog_tools, report_payload
from mcp_server.i18n import translate
from preflight.fixes import fix_artwork as _fix
from preflight.matcher import parse_request
from preflight.preview import layout, render_preview
from preflight.report import check_after_fix, check_file
from preflight.specs import get_product
from preflight.textfix import Correction, apply_corrections

VERSION = "0.2.0"
HOSTED_PRODUCTS = ("business-card", "flyer-a5", "flyer-a6")
BETA_PRODUCTS = ("flyer-a5", "flyer-a6")
MAX_CHUNK_BYTES = 2 * 1024 * 1024  # decoded; ~2.7 MB as base64, well under the request limit
BUSY_TIMEOUT_S = 90
PREVIEW_PX = 900
STUDIO_URI = "ui://preflight/studio.html"
UI_DIR = Path(__file__).resolve().parent / "ui"
SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples"
SAMPLES = {  # "Try a sample" in the panel: our own files (preflight/samples.py), no customer file needed
    "print_ready": ("sample_print_ready.pdf", "business-card"),
    "missing_bleed": ("sample_missing_bleed.pdf", "business-card"),
    "with_mistakes": ("sample_with_mistakes.pdf", "business-card"),
    "flyer_a5": ("sample_flyer_a5.pdf", "flyer-a5"),
}

log = logging.getLogger("print-preflight")
_heavy = threading.Lock()  # sync tools run in worker threads; one render/fix at a time


def studio_html() -> str:
    """The Studio page with the MCP Apps SDK inlined (the app iframe may not load external scripts).

    The SDK bundle is an ES module ending in `export{a as B,...}`; we turn that into a global
    (window.McpExtApps) so a plain inline script can use it.
    """
    sdk = (UI_DIR / "vendor" / "ext-apps-2.0.4.js").read_text(encoding="utf-8")
    m = re.search(r"export\{([^}]*)\};?\s*$", sdk)
    if not m:
        raise RuntimeError("Unexpected ext-apps bundle format")
    pairs = [p.strip().split(" as ") for p in m.group(1).split(",")]
    exports = ",".join(f"{alias}:{local}" for local, alias in pairs)
    sdk = sdk[: m.start()] + f"globalThis.McpExtApps={{{exports}}};"
    page = (UI_DIR / "studio.html").read_text(encoding="utf-8")
    page = page.replace("/*__SAMPLES__*/[]", json.dumps(_sample_thumbnails()))
    return page.replace("/*__EXT_APPS_SDK__*/", sdk.replace("</script", "<\\/script"))


def _sample_thumbnails() -> list[dict]:
    """Small previews of the demo files (as cut), so people can see what they pick."""
    out = []
    for sample_id, (name, product_id) in SAMPLES.items():
        with pymupdf.open(SAMPLES_DIR / name) as doc:
            page = doc[0]
            pix = page.get_pixmap(dpi=72 if product_id == "business-card" else 40, clip=page.trimbox)
            thumb = "data:image/png;base64," + base64.b64encode(pix.tobytes("png")).decode()
        out.append({"id": sample_id, "product_id": product_id, "thumb": thumb})
    return out


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


def _localised(payload: dict, lang: str) -> dict:
    """Issue texts in the panel's language (Claude still gets the English findings)."""
    for issue in payload["numbered_issues"]:
        issue["message"] = translate(issue["message"], lang)
    return payload


def _interactive_preview(path, product, findings) -> tuple[Image | None, list[dict]]:
    """A clean preview (guide lines, no numbers) and where each numbered marker goes, in % of the image.

    The panel draws the markers itself, so hovering a number can highlight its issue (and back).
    """
    try:
        canvas, markers, r = layout(path, product, findings)
    except Exception:  # noqa: BLE001 - a preview is a bonus, never a reason to fail
        log.exception("preview failed")
        return None, []
    w, h = canvas.size

    def pct(v: float, total: float) -> float:
        return round(v / total * 100, 3)

    spots = [{
        "n": m.n, "severity": m.finding.severity,
        "x": pct(m.centre[0], w), "y": pct(m.centre[1], h),
        "box": [pct(m.box[0], w), pct(m.box[1], h), pct(m.box[2] - m.box[0], w), pct(m.box[3] - m.box[1], h)]
        if m.box else None,
    } for m in markers]
    if w > PREVIEW_PX * 1.4:
        canvas = canvas.resize((int(PREVIEW_PX * 1.4), int(h * PREVIEW_PX * 1.4 / w)))
    buf = io.BytesIO()
    canvas.save(buf, "PNG", optimize=True)
    return Image(data=buf.getvalue(), format="png"), spots


def _preview(path, product, findings) -> Image | None:
    try:
        img = render_preview(path, product, findings, width_px=PREVIEW_PX)
    except Exception:  # noqa: BLE001 - a preview is a bonus, never a reason to fail
        log.exception("preview failed")
        return None
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return Image(data=buf.getvalue(), format="png")


# ---------------------------------------------------------------- MCP App: Preflight Studio

apps = Apps()
apps.add_html_resource(
    STUDIO_URI,
    studio_html(),
    title="Print Preflight",
    description="Upload a print file, see the check and the preview, fix it and download the result.",
    prefers_border=True,
)


@apps.tool(resource_uri=STUDIO_URI, title="Open Print Preflight", structured_output=True)
def open_preflight_studio(product_id: str = "business-card", request: str = "") -> dict[str, Any]:
    """Open Print Preflight, an interactive panel in the chat where the customer uploads a print file
    (PDF, PNG or JPG) and sees the check, an annotated preview, an automatic fix and an order summary.

    Use this whenever the customer wants to check or fix a design file: they cannot attach files to
    this tool any other way. Call find_product first if the product is unclear.
    request: the customer's own words about the order, e.g. "250 matte business cards", so the panel can
    show the quantity and finish in its order summary. Nothing is ordered: the customer continues on the shop.
    """
    p = product_or_error(product_id, HOSTED_PRODUCTS)
    parsed = parse_request(request) if request else {}
    return {
        "product_id": p.id,
        "order": {"quantity": parsed.get("quantity"), "finish": parsed.get("finish"), "url": p.url},
        "products": [
            {"product_id": q.id, "name": q.name, "trim_mm": list(q.trim_mm), "bleed_mm": q.spec.bleed_mm,
             "safe_margin_mm": q.spec.safe_warn_mm, "min_dpi": q.spec.dpi_min, "beta": q.id in BETA_PRODUCTS}
            for q in map(get_product, HOSTED_PRODUCTS)
        ],
        "max_upload_mb": storage.MAX_BYTES // (1024 * 1024),
        "note": "The panel is open and already shows the specs. Reply in one short sentence asking the customer "
                "to upload their file above (no spec table); the results are shared with you when the check is done. "
                "If the customer cannot see the panel (the Claude mobile app does not show interactive panels yet), "
                "tell them to open this chat in Claude on a computer or at claude.ai in a browser.",
    }


@apps.tool(resource_uri=STUDIO_URI, visibility=["app"], structured_output=True)
def upload_chunk(data_base64: str, offset: int = 0, upload_id: str = "", filename: str = "artwork",
                 final: bool = False) -> dict[str, Any]:
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
    if not upload_id:
        limits.disk(storage.used_bytes())
    limits.upload(len(data))
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


@apps.tool(resource_uri=STUDIO_URI, visibility=["app"], structured_output=True)
def load_sample(sample: str = "missing_bleed") -> dict[str, Any]:
    """Load a demo file (print_ready, missing_bleed, with_mistakes, flyer_a5) as if it was uploaded."""
    if sample not in SAMPLES:
        raise ToolError(f"Unknown sample. Choose one of: {', '.join(SAMPLES)}.")
    limits.disk(storage.used_bytes())
    name, product_id = SAMPLES[sample]
    stored = storage.store_copy(SAMPLES_DIR / name, Path(name).stem)
    return {"file_id": stored.file_id, "file_name": name, "product_id": product_id}


# ---------------------------------------------------------------- server and tools

server = MCPServer(
    "print-preflight",
    instructions=INSTRUCTIONS + (
        " Online demo: to check a customer's file, call open_preflight_studio (pass the customer's words about "
        "the order as `request`, e.g. '250 matte business cards'); the customer uploads the file in that panel, "
        "the results are shared with you, and the panel ends with an order summary. You never place orders. "
        f"Products: {', '.join(HOSTED_PRODUCTS)}. "
        "Style: the panel already shows the specs, the preview and every issue, so keep your chat replies "
        "short and friendly. After opening the panel, say in one sentence that they can upload their file "
        "above. After a check or a fix, give the verdict and the single most important next step in one or "
        "two sentences, then offer to explain any point in more detail. No tables or spec lists unless the "
        "customer asks for them. If the customer cannot see the panel (for example in the Claude mobile app, "
        "which does not show interactive panels yet), tell them to open the chat on a computer or at claude.ai."
    ),
    extensions=[apps],
)
register_catalog_tools(server, HOSTED_PRODUCTS)


@server.tool()
def check_artwork(file_id: str, product_id: str, lang: str = "en", interactive: bool = False) -> list:
    """Check an uploaded print file (file_id from the Print Preflight panel) for a product.

    Returns the report (verdict + numbered issues in plain English) and an annotated preview image:
    black line = cut line, red dashed = where bleed must reach, green dashed = safe zone.
    lang: "en" (default) or "nl" for the issue texts shown in the panel.
    interactive: used by the panel; returns a preview without numbers plus marker positions.
    """
    product = product_or_error(product_id, HOSTED_PRODUCTS)
    stored = _stored(file_id)
    limits.heavy()
    with _Busy():
        report = check_file(stored.path, product.id)
        payload = _localised(report_payload(report), lang)
        payload["file"] = stored.display_name  # never show server paths
        payload["file_id"] = file_id
        out: list = [payload]
        if any(f.check != "file" for f in report.findings):
            if interactive:
                img, payload["markers"] = _interactive_preview(stored.path, product, report.findings)
            else:
                img = _preview(stored.path, product, report.findings)
            if img:
                out.append(img)
    log.info("check: %s -> %s in %.2fs", product.id, report.verdict, report.seconds)
    return out


@server.tool()
def fix_artwork(file_id: str, product_id: str, lang: str = "en", interactive: bool = False) -> list:
    """Automatically fix what is safe to fix (missing bleed, RGB colours, scale) and re-check.

    Returns what changed, what still needs the designer, the new verdict, a preview of the fixed file
    and a download link for the fixed PDF (valid for 60 minutes). The uploaded file is never changed.
    lang: "en" (default) or "nl" for the texts shown in the panel.
    """
    product = product_or_error(product_id, HOSTED_PRODUCTS)
    stored = _stored(file_id)
    limits.heavy()
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
        payload = _localised(report_payload(after), lang)
        payload["file"] = f"{fixed.display_name}.pdf"
        if interactive:
            img, payload["markers"] = _interactive_preview(fixed.path, product, after.findings)
        else:
            img = _preview(fixed.path, product, after.findings)
    log.info("fix: %s %s -> %s", product.id, before.verdict, after.verdict)
    out: list = [{
        "fixed_file_id": fixed.file_id,
        "download_url": f"{public_url()}/files/{fixed.file_id}/{fixed.display_name}.pdf",
        "changes": [translate(c, lang) for c in result.changes],
        "skipped": [translate(c, lang) for c in result.skipped],
        "verdict_before": before.verdict,
        "verdict_after": after.verdict,
        "report_after": payload,
    }]
    if img:
        out.append(img)
    return out


@server.tool()
def fix_typos(file_id: str, product_id: str, corrections: list[dict[str, Any]], lang: str = "en",
              interactive: bool = False) -> list:
    """Change words the customer accepted (typos) directly in the PDF, then check the new file.

    corrections: [{"word": "scientst", "replacement": "scientist", "page": 1}], only words the check reported
    as possible typos. Position, size and colour stay the same. Returns the new report (with a new file_id,
    used for the next steps), what changed and a download link. Only for PDFs with live text.
    """
    product = product_or_error(product_id, HOSTED_PRODUCTS)
    stored = _stored(file_id)
    if stored.kind != "pdf":
        raise ToolError("Text can only be corrected in PDF files.")
    if not corrections or len(corrections) > 20:
        raise ToolError("Send between 1 and 20 corrections.")
    limits.heavy()
    with _Busy():
        report = check_file(stored.path, product.id)
        reported = {(f.detail.get("word"), f.page or 1) for f in report.findings
                    if f.check == "text" and f.detail.get("kind") == "spelling"}
        chosen = []
        for c in corrections:
            word, new = str(c.get("word", "")), str(c.get("replacement", "")).strip()
            page = int(c.get("page") or 1)
            if (word, page) not in reported:
                raise ToolError(f'"{word}" is not one of the possible typos in this file.')
            if not new or len(new) > 40:
                raise ToolError("A replacement must be 1 to 40 characters.")
            chosen.append(Correction(page, word, new))
        work = storage.workdir(file_id)
        result = apply_corrections(stored.path, chosen, output=work / "corrected.pdf")
        if not result.changes:
            raise ToolError("These words could not be changed in this file.")
        fixed = storage.store_output(work / "corrected.pdf", stored.display_name)
        new_report = check_file(fixed.path, product.id)
        payload = _localised(report_payload(new_report), lang)
        payload["file"] = stored.display_name
        payload["file_id"] = fixed.file_id
        payload["text_changes"] = [translate(c, lang) for c in result.changes]
        payload["download_url"] = f"{public_url()}/files/{fixed.file_id}/{fixed.display_name}.pdf"
        if interactive:
            img, payload["markers"] = _interactive_preview(fixed.path, product, new_report.findings)
        else:
            img = _preview(fixed.path, product, new_report.findings)
    log.info("typos: %d changed", len(result.changes))
    out: list = [payload]
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
