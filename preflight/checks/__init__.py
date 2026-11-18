"""All deterministic checks, in the order they run."""

from __future__ import annotations

from . import bleed, colour, dpi, fonts, pages, safezone, size, text
from .base import Context

CHECKS = [pages, size, bleed, dpi, colour, safezone, fonts, text]

__all__ = ["CHECKS", "Context"]
