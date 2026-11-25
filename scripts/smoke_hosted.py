"""Smoke test for the hosted server: upload -> check -> fix -> download, like Claude does.

Usage:
  python scripts/smoke_hosted.py https://<service>.onrender.com path/to/card.pdf [product_id]

Uses only the standard library. Prints each step and exits non-zero on the first problem.
"""

from __future__ import annotations

import base64
import json
import sys
import time
import urllib.request
from pathlib import Path

CHUNK = 1_500_000


def rpc(base: str, method: str, params: dict) -> dict:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(f"{base}/mcp", data=body, method="POST", headers={
        "Content-Type": "application/json", "Accept": "application/json, text/event-stream",
        "Mcp-Protocol-Version": "2025-06-18"})
    with urllib.request.urlopen(req, timeout=120) as r:
        msg = json.loads(r.read())
    if "error" in msg:
        sys.exit(f"protocol error: {msg['error']}")
    return msg["result"]


def tool(base: str, name: str, args: dict) -> list:
    res = rpc(base, "tools/call", {"name": name, "arguments": args})
    if res.get("isError"):
        sys.exit(f"{name} failed: {res['content'][0]['text']}")
    return res["content"]


def main() -> None:
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    base, path = sys.argv[1].rstrip("/"), Path(sys.argv[2])
    product = sys.argv[3] if len(sys.argv) > 3 else "business-card"

    with urllib.request.urlopen(f"{base}/health", timeout=30) as r:
        print("health:", json.loads(r.read()))
    tools = [t["name"] for t in rpc(base, "tools/list", {})["tools"]]
    print("tools:", ", ".join(tools))

    data, offset, upload_id = path.read_bytes(), 0, ""
    t = time.perf_counter()
    while True:
        part = data[offset:offset + CHUNK]
        final = offset + len(part) >= len(data)
        out = json.loads(tool(base, "upload_chunk", {"data_base64": base64.b64encode(part).decode(),
                                                     "offset": offset, "upload_id": upload_id,
                                                     "filename": path.name, "final": final})[0]["text"])
        if final:
            break
        upload_id, offset = out["upload_id"], out["received_bytes"]
    print(f"upload: {len(data)} bytes in {time.perf_counter() - t:.1f}s -> file_id {out['file_id'][:8]}...")

    content = tool(base, "check_artwork", {"file_id": out["file_id"], "product_id": product})
    report = json.loads(content[0]["text"])
    print(f"check: {report['verdict_text']} ({report['seconds']}s), preview image: {len(content) > 1}")
    for issue in report["numbered_issues"]:
        print(f"  {issue['n']}. [{issue['severity']}] {issue['message']}")

    if report["verdict"] == "pass":
        print("print-ready, nothing to fix")
        return
    fixed = json.loads(tool(base, "fix_artwork", {"file_id": out["file_id"], "product_id": product})[0]["text"])
    print(f"fix: {fixed['verdict_before']} -> {fixed['verdict_after']}")
    for c in fixed["changes"]:
        print("  -", c)
    with urllib.request.urlopen(fixed["download_url"], timeout=60) as r:
        pdf = r.read()
    ok = pdf.startswith(b"%PDF-")
    print(f"download: {len(pdf)} bytes, valid PDF: {ok}")
    if not ok:
        sys.exit(1)
    print("OK")


if __name__ == "__main__":
    main()
