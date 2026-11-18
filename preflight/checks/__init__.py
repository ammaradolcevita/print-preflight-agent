"""All deterministic checks, in the order they run."""

from __future__ import annotations

from . import bleed, colour, dpi, pages, size
from .base import Context

CHECKS = [pages, size, bleed, dpi, colour]

__all__ = ["CHECKS", "Context"]
