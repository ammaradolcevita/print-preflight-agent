"""Abuse limits for the public demo server.

Why global and not per IP: requests from claude.ai reach this server from Anthropic's own
IP range, not from the person in the chat, so a per-IP limit would be one shared limit anyway.
What we protect is the server itself: CPU (checks and fixes), upload volume and disk.
All numbers can be changed with environment variables, without a code change.
"""

from __future__ import annotations

import os
import threading
import time
from collections import deque

from mcp.server.mcpserver.exceptions import ToolError

HEAVY_PER_MINUTE = int(os.environ.get("PREFLIGHT_HEAVY_PER_MINUTE", 40))
UPLOAD_MB_PER_10_MIN = int(os.environ.get("PREFLIGHT_UPLOAD_MB_PER_10_MIN", 300))
STORAGE_MAX_MB = int(os.environ.get("PREFLIGHT_STORAGE_MAX_MB", 1024))

BUSY = "The demo is busy right now. Please try again in a few minutes."

_lock = threading.Lock()
_heavy: deque[float] = deque()
_uploads: deque[tuple[float, int]] = deque()


def heavy() -> None:
    """Count one check or fix; refuse when there were too many in the last minute."""
    now = time.monotonic()
    with _lock:
        while _heavy and now - _heavy[0] > 60:
            _heavy.popleft()
        if len(_heavy) >= HEAVY_PER_MINUTE:
            raise ToolError(BUSY)
        _heavy.append(now)


def upload(n_bytes: int) -> None:
    """Count uploaded bytes; refuse when the last 10 minutes are over the limit."""
    now = time.monotonic()
    with _lock:
        while _uploads and now - _uploads[0][0] > 600:
            _uploads.popleft()
        if sum(n for _, n in _uploads) + n_bytes > UPLOAD_MB_PER_10_MIN * 1024 * 1024:
            raise ToolError(BUSY)
        _uploads.append((now, n_bytes))


def disk(used_bytes: int) -> None:
    """Refuse new files when temporary storage is full (old files are removed after 60 minutes)."""
    if used_bytes > STORAGE_MAX_MB * 1024 * 1024:
        raise ToolError(BUSY)


def reset() -> None:
    """For tests."""
    with _lock:
        _heavy.clear()
        _uploads.clear()
