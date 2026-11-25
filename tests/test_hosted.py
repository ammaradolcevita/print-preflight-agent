"""Hosted server: temp storage rules and the full HTTP flow (upload -> check -> fix -> download)."""

from __future__ import annotations

import base64
import json
import time

import pytest
from starlette.testclient import TestClient

from mcp_server import http_app, storage
from preflight.fixtures import make_pdf
from preflight.report import check_file

H = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json",
     "Mcp-Protocol-Version": "2025-06-18"}


@pytest.fixture(autouse=True)
def _reset_limits():
    from mcp_server import limits
    limits.reset()  # the counters are global; every test starts from zero


@pytest.fixture(autouse=True)
def tmp_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "ROOT", tmp_path / "store")
    return tmp_path / "store"


@pytest.fixture
def card(tmp_path):
    """Business card without bleed, colour to the edge: fails, and is fixable."""
    return make_pdf(tmp_path / "card.pdf", (85, 55), background=(0.15, 0.4, 0.8),
                    texts=[{"text": "Sam Jansen", "at_mm": (12, 20)}])


@pytest.fixture(scope="module")
def client():
    # one app lifespan per module: the SDK's session manager can only be started once
    with TestClient(http_app.app, base_url="http://localhost") as c:
        yield c


def call(client, name, args) -> dict:
    r = client.post("/mcp", headers=H, json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                             "params": {"name": name, "arguments": args}})
    assert r.status_code == 200, r.text
    return r.json()["result"]


def first_json(result) -> dict:
    return json.loads(result["content"][0]["text"])


def upload(client, data: bytes, chunk=300_000, name="card.pdf") -> dict:
    upload_id, offset = "", 0
    while True:
        part = data[offset:offset + chunk]
        final = offset + len(part) >= len(data)
        res = call(client, "upload_chunk", {"data_base64": base64.b64encode(part).decode(), "offset": offset,
                                            "upload_id": upload_id, "filename": name, "final": final})
        assert not res.get("isError"), res
        out = first_json(res)
        if final:
            return out
        upload_id, offset = out["upload_id"], out["received_bytes"]


# ---------------------------------------------------------------- storage rules


def test_chunked_upload_and_retry(card):
    data = card.read_bytes()
    uid, size = storage.append_chunk(None, "card.pdf", data[:1000], 0)
    assert size == 1000
    assert storage.append_chunk(uid, "card.pdf", data[:1000], 0) == (uid, 1000)  # retried chunk: no change
    with pytest.raises(storage.StorageError, match="missing"):
        storage.append_chunk(uid, "card.pdf", data[2000:3000], 2000)
    storage.append_chunk(uid, "card.pdf", data[1000:], 1000)
    stored = storage.finish_upload(uid)
    assert stored.kind == "pdf" and stored.path.read_bytes() == data


def test_too_large(monkeypatch):
    monkeypatch.setattr(storage, "MAX_BYTES", 1000)
    uid, _ = storage.append_chunk(None, "x.pdf", b"%PDF-" + b"0" * 900, 0)
    with pytest.raises(storage.StorageError, match="too large"):
        storage.append_chunk(uid, "x.pdf", b"0" * 200, 905)


def test_wrong_type_by_content_not_name():
    uid, _ = storage.append_chunk(None, "looks-like.pdf", b"PK\x03\x04 a word file", 0)
    with pytest.raises(storage.StorageError, match="not a PDF, PNG or JPG"):
        storage.finish_upload(uid)


def test_expired_file(card, monkeypatch):
    uid, _ = storage.append_chunk(None, "card.pdf", card.read_bytes(), 0)
    storage.finish_upload(uid)
    storage.get(uid)
    monkeypatch.setattr(time, "time", lambda: 10**12)
    with pytest.raises(storage.StorageError, match="no longer available"):
        storage.get(uid)


@pytest.mark.parametrize("bad", ["../etc", "short", "a/b" * 10, ""])
def test_invalid_ids(bad):
    with pytest.raises(storage.StorageError):
        storage.get(bad)


def test_uploads_are_not_downloadable(card, client):
    uid, _ = storage.append_chunk(None, "card.pdf", card.read_bytes(), 0)
    storage.finish_upload(uid)
    assert client.get(f"/files/{uid}/card.pdf").status_code == 404


# ---------------------------------------------------------------- HTTP flow


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_unknown_host_is_refused(client):
    r = client.post("/mcp", headers={**H, "Host": "evil.example"},
                    json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
    assert r.status_code == 421


def test_only_hosted_products(client):
    listed = call(client, "list_products", {})["structuredContent"]["result"]
    assert {p["product_id"] for p in listed} == set(http_app.HOSTED_PRODUCTS)
    res = call(client, "check_artwork", {"file_id": "x" * 32, "product_id": "rollup-85x200"})
    assert res["isError"] and "not available in this online demo" in res["content"][0]["text"]


def test_check_by_file_id_matches_local(card, client):
    up = upload(client, card.read_bytes())
    res = call(client, "check_artwork", {"file_id": up["file_id"], "product_id": "business-card"})
    report = first_json(res)
    local = check_file(card, "business-card")
    assert report["verdict"] == local.verdict == "fail"
    assert [f["message"] for f in report["findings"]] == [f.message for f in local.findings]
    assert report["file"] == "card" and "/" not in report["file"]  # no server paths
    assert res["content"][1]["type"] == "image"


def test_fix_and_download(card, client):
    up = upload(client, card.read_bytes())
    res = call(client, "fix_artwork", {"file_id": up["file_id"], "product_id": "business-card"})
    out = first_json(res)
    assert out["verdict_before"] == "fail" and out["verdict_after"] in ("pass", "warn")
    path = out["download_url"].split("://", 1)[1].split("/", 1)[1]
    r = client.get("/" + path)
    assert r.status_code == 200 and r.content.startswith(b"%PDF-")
    assert "attachment" in r.headers["content-disposition"]


def test_expired_file_id_gives_clear_error(client):
    res = call(client, "check_artwork", {"file_id": "A" * 32, "product_id": "business-card"})
    assert res["isError"] and "no longer available" in res["content"][0]["text"]


# ---------------------------------------------------------------- MCP App (Preflight Studio)


def rpc(client, method, params) -> dict:
    r = client.post("/mcp", headers=H, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    assert r.status_code == 200, r.text
    return r.json()["result"]


def test_studio_tools_metadata(client):
    tools = {t["name"]: t for t in rpc(client, "tools/list", {})["tools"]}
    assert tools["open_preflight_studio"]["_meta"]["ui"]["resourceUri"] == http_app.STUDIO_URI
    assert tools["upload_chunk"]["_meta"]["ui"]["visibility"] == ["app"]  # hidden from the model


def test_studio_resource_is_self_contained(client):
    content = rpc(client, "resources/read", {"uri": http_app.STUDIO_URI})["contents"][0]
    html = content["text"]
    assert content["mimeType"] == "text/html;profile=mcp-app"
    assert "globalThis.McpExtApps=" in html and "/*__EXT_APPS_SDK__*/" not in html
    assert "export{" not in html  # the module export was turned into a global
    assert "<script src" not in html and "https://" not in html.split("<script>", 1)[0]  # no external loads
    assert "Prototype by Ammar Sodikov" in html
    assert "https://github.com/ammaradolcevita/print-preflight-agent" in html  # "Code on GitHub" link


def test_open_studio_returns_products(client):
    res = call(client, "open_preflight_studio", {"product_id": "flyer-a6"})
    data = res["structuredContent"]
    assert data["product_id"] == "flyer-a6"
    assert [p["product_id"] for p in data["products"]] == list(http_app.HOSTED_PRODUCTS)
    assert res["content"][0]["type"] == "text"  # text fallback for hosts without MCP Apps


def test_instructions_ask_for_short_replies(client):
    init = rpc(client, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                      "clientInfo": {"name": "t", "version": "1"}})
    text = init["instructions"]
    assert "open_preflight_studio" in text and "keep your chat replies short" in text
    assert "No tables" in text


@pytest.mark.parametrize("sample,product,verdict", [("missing_bleed", "business-card", "fail"),
                                                    ("with_mistakes", "business-card", "fail"),
                                                    ("print_ready", "business-card", "pass"),
                                                    ("flyer_a5", "flyer-a5", "fail")])
def test_try_a_sample(client, sample, product, verdict):
    tools = {t["name"]: t for t in rpc(client, "tools/list", {})["tools"]}
    assert tools["load_sample"]["_meta"]["ui"]["visibility"] == ["app"]
    loaded = call(client, "load_sample", {"sample": sample})["structuredContent"]
    assert loaded["product_id"] == product
    report = first_json(call(client, "check_artwork", {"file_id": loaded["file_id"], "product_id": product}))
    assert report["verdict"] == verdict
    assert client.get(f"/files/{loaded['file_id']}/x.pdf").status_code == 404  # samples are not "downloads"


def test_unknown_sample(client):
    res = call(client, "load_sample", {"sample": "../../etc/passwd"})
    assert res["isError"] and "Unknown sample" in res["content"][0]["text"]


# ---------------------------------------------------------------- limits and phone fallback


@pytest.fixture
def fresh_limits(monkeypatch):
    from mcp_server import limits
    limits.reset()
    yield limits
    limits.reset()


def test_heavy_limit(client, card, fresh_limits, monkeypatch):
    monkeypatch.setattr(fresh_limits, "HEAVY_PER_MINUTE", 1)
    up = upload(client, card.read_bytes())
    assert not call(client, "check_artwork", {"file_id": up["file_id"], "product_id": "business-card"}).get("isError")
    res = call(client, "check_artwork", {"file_id": up["file_id"], "product_id": "business-card"})
    assert res["isError"] and "busy" in res["content"][0]["text"]


def test_upload_volume_and_disk_limits(client, card, fresh_limits, monkeypatch):
    monkeypatch.setattr(fresh_limits, "UPLOAD_MB_PER_10_MIN", 0)
    res = call(client, "upload_chunk", {"data_base64": base64.b64encode(card.read_bytes()).decode(), "final": True})
    assert res["isError"] and "busy" in res["content"][0]["text"]
    monkeypatch.setattr(fresh_limits, "UPLOAD_MB_PER_10_MIN", 300)
    monkeypatch.setattr(fresh_limits, "STORAGE_MAX_MB", -1)  # "disk full"
    res = call(client, "load_sample", {"sample": "missing_bleed"})
    assert res["isError"] and "busy" in res["content"][0]["text"]


def test_phone_fallback_is_explained(client):
    res = call(client, "open_preflight_studio", {})
    assert "mobile app" in res["structuredContent"]["note"]


def test_open_studio_carries_the_order(client):
    data = call(client, "open_preflight_studio", {"request": "I need 250 matte business cards"})["structuredContent"]
    assert data["order"]["quantity"] == 250 and data["order"]["finish"] == "matte"
    assert data["order"]["url"].startswith("https://www.helloprint.com/")
    empty = call(client, "open_preflight_studio", {})["structuredContent"]["order"]
    assert empty["quantity"] is None  # no request words: the panel shows the product only


def test_sample_picker_is_in_the_page(client):
    html = rpc(client, "resources/read", {"uri": http_app.STUDIO_URI})["contents"][0]["text"]
    assert "/*__SAMPLES__*/" not in html
    for sample_id in http_app.SAMPLES:
        assert f'"id": "{sample_id}"' in html
    assert html.count('"thumb": "data:image/png;base64,') == len(http_app.SAMPLES)


def test_interactive_preview_has_markers(client):
    loaded = call(client, "load_sample", {"sample": "with_mistakes"})["structuredContent"]
    args = {"file_id": loaded["file_id"], "product_id": "business-card"}
    plain = first_json(call(client, "check_artwork", args))
    assert "markers" not in plain  # Claude gets the picture with the numbers burned in
    res = call(client, "check_artwork", {**args, "interactive": True})
    report = first_json(res)
    numbers = {i["n"] for i in report["numbered_issues"]}
    assert report["markers"] and {m["n"] for m in report["markers"]} <= numbers
    for m in report["markers"]:
        assert 0 <= m["x"] <= 100 and 0 <= m["y"] <= 100
    assert res["content"][1]["type"] == "image"
    fixed = first_json(call(client, "fix_artwork", {**args, "interactive": True}))
    assert {m["n"] for m in fixed["report_after"]["markers"]} <= {i["n"] for i in fixed["report_after"]["numbered_issues"]}


def test_fix_typos_changes_only_reported_typos(client):
    loaded = call(client, "load_sample", {"sample": "with_mistakes"})["structuredContent"]
    args = {"file_id": loaded["file_id"], "product_id": "business-card"}
    typos = [i["typo"] for i in first_json(call(client, "check_artwork", args))["numbered_issues"] if "typo" in i]
    assert {t["word"] for t in typos} == {"scientst", "enginer"}
    res = first_json(call(client, "fix_typos", {**args, "corrections": [
        {"word": t["word"], "replacement": t["suggestion"], "page": t["page"]} for t in typos]}))
    assert res["file_id"] != loaded["file_id"] and len(res["text_changes"]) == 2
    assert not any("typo" in i for i in res["numbered_issues"])  # both words are now correct
    assert "(set in" not in " ".join(res["text_changes"])  # same font family, so no note
    path = res["download_url"].split("://", 1)[1].split("/", 1)[1]
    assert client.get("/" + path).content.startswith(b"%PDF-")
    bad = call(client, "fix_typos", {**args, "corrections": [{"word": "Ammar", "replacement": "Someone"}]})
    assert bad["isError"] and "not one of the possible typos" in bad["content"][0]["text"]
