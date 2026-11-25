"""Temporary file storage for the hosted server.

- Every file lives in its own folder named by a random, unguessable id.
- Everything is deleted after TTL_SECONDS (checked on every access, no background job).
- Max MAX_BYTES per file; only PDF, PNG and JPG, recognised by their first bytes, not by the name.
- Uploads arrive in chunks with an explicit offset, so a retried chunk is harmless
  and a missing chunk is detected instead of silently producing a broken file.
- File contents and names are never logged.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

TTL_SECONDS = int(os.environ.get("PREFLIGHT_TTL_SECONDS", 3600))
MAX_BYTES = int(os.environ.get("PREFLIGHT_MAX_BYTES", 20 * 1024 * 1024))
ROOT = Path(os.environ.get("PREFLIGHT_STORAGE", Path(tempfile.gettempdir()) / "print-preflight"))

MAGIC = {b"%PDF-": "pdf", b"\x89PNG\r\n\x1a\n": "png", b"\xff\xd8\xff": "jpg"}
_ID = re.compile(r"^[A-Za-z0-9_-]{20,64}$")
_lock = threading.Lock()


class StorageError(Exception):
    """A customer-friendly message about an upload or a file id."""


@dataclass
class Stored:
    file_id: str
    path: Path
    kind: str  # "pdf" | "png" | "jpg"
    display_name: str  # the customer's file name, for messages only


def _dir(file_id: str) -> Path:
    if not _ID.match(file_id or ""):
        raise StorageError("This file id is not valid. Please upload the file again.")
    return ROOT / file_id


def _meta(folder: Path) -> dict:
    try:
        return json.loads((folder / "meta.json").read_text())
    except (OSError, ValueError):
        return {}


def _write_meta(folder: Path, meta: dict) -> None:
    (folder / "meta.json").write_text(json.dumps(meta))


def sweep(now: float | None = None) -> int:
    """Delete everything older than the TTL. Returns how many folders were removed."""
    now = now or time.time()
    removed = 0
    if not ROOT.exists():
        return 0
    for folder in ROOT.iterdir():
        created = _meta(folder).get("created", 0)
        if now - created > TTL_SECONDS:
            shutil.rmtree(folder, ignore_errors=True)
            removed += 1
    return removed


def _safe_name(name: str) -> str:
    stem = Path(name or "artwork").stem
    return re.sub(r"[^A-Za-z0-9._ -]", "_", stem)[:60] or "artwork"


def append_chunk(upload_id: str | None, filename: str, data: bytes, offset: int) -> tuple[str, int]:
    """Add bytes at `offset` to an upload (a new one when upload_id is empty). Returns (upload_id, size)."""
    sweep()
    with _lock:
        if not upload_id:
            if offset != 0:
                raise StorageError("A new upload must start at offset 0.")
            upload_id = secrets.token_urlsafe(24)
            folder = ROOT / upload_id
            folder.mkdir(parents=True)
            _write_meta(folder, {"created": time.time(), "name": _safe_name(filename), "state": "uploading"})
        folder = _dir(upload_id)
        meta = _meta(folder)
        if meta.get("state") != "uploading":
            raise StorageError("This upload has expired or is already finished. Please upload the file again.")
        part = folder / "upload.part"
        size = part.stat().st_size if part.exists() else 0
        if offset < size and offset + len(data) <= size:
            return upload_id, size  # a retried chunk we already have
        if offset != size:
            raise StorageError(f"A part of the upload is missing (expected offset {size}). Please try again.")
        if size + len(data) > MAX_BYTES:
            shutil.rmtree(folder, ignore_errors=True)
            raise StorageError(f"This file is too large. The maximum is {MAX_BYTES // (1024 * 1024)} MB.")
        with open(part, "ab") as f:
            f.write(data)
        return upload_id, size + len(data)


def finish_upload(upload_id: str) -> Stored:
    """Check the file type and turn the upload into a stored file."""
    folder = _dir(upload_id)
    with _lock:
        meta = _meta(folder)
        part = folder / "upload.part"
        if meta.get("state") != "uploading" or not part.exists():
            raise StorageError("This upload has expired or is already finished. Please upload the file again.")
        with open(part, "rb") as f:
            head = f.read(8)
        kind = next((k for magic, k in MAGIC.items() if head.startswith(magic)), None)
        if kind is None:
            shutil.rmtree(folder, ignore_errors=True)
            raise StorageError("This is not a PDF, PNG or JPG file. Please upload one of those.")
        path = folder / f"artwork.{kind}"
        part.rename(path)
        meta.update(state="ready", kind=kind)
        _write_meta(folder, meta)
    return Stored(upload_id, path, kind, meta["name"])


def _store(source: Path, display_name: str, *, output: bool, move: bool) -> Stored:
    sweep()
    file_id = secrets.token_urlsafe(24)
    folder = ROOT / file_id
    folder.mkdir(parents=True)
    path = folder / "artwork.pdf"
    (shutil.move if move else shutil.copyfile)(str(source), path)
    _write_meta(folder, {"created": time.time(), "name": _safe_name(display_name), "state": "ready",
                         "kind": "pdf", "output": output})
    return Stored(file_id, path, "pdf", _safe_name(display_name))


def store_output(source: Path, display_name: str) -> Stored:
    """Keep a generated file (the fixed PDF) under a new id so it can be downloaded."""
    return _store(source, display_name, output=True, move=True)


def store_copy(source: Path, display_name: str) -> Stored:
    """A copy of one of our own PDFs (a demo sample), treated like an upload: checkable, not downloadable."""
    return _store(source, display_name, output=False, move=False)


def get(file_id: str, *, output_only: bool = False) -> Stored:
    """A stored file by id, or StorageError when unknown, expired or still uploading."""
    sweep()
    folder = _dir(file_id)
    meta = _meta(folder)
    if meta.get("state") != "ready" or (output_only and not meta.get("output")):
        raise StorageError("This file is no longer available (files are deleted after 60 minutes). "
                           "Please upload it again.")
    return Stored(file_id, folder / f"artwork.{meta['kind']}", meta["kind"], meta["name"])


def workdir(file_id: str) -> Path:
    """A scratch folder inside the file's own folder (deleted with it)."""
    d = _dir(file_id) / "work"
    d.mkdir(exist_ok=True)
    return d
