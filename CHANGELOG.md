# Changelog

## v0.2.0 — 25 Nov 2026

**Print Preflight runs inside Claude** as a hosted MCP App.

Added
- Hosted MCP server (Streamable HTTP, `/mcp`) on Render; files by chunked upload and `file_id`, deleted after 60 minutes.
- Preflight Studio panel in the chat: upload or pick a sample, verdict, interactive preview (hover a number to see the problem), automatic fix with before/after, download, order summary.
- One-click typo changes in the PDF (only when the customer clicks; same font style).
- Order summary from the customer's words ("250 matte business cards").
- English and Dutch, following the language Claude reports.
- Four demo samples (three business cards, one A5 flyer).
- Global limits for a public demo (checks per minute, upload volume, disk).
- Real-world-style evaluation set (20 files) and `scripts/smoke_hosted.py`.

Fixed (found on real-world file structures)
- Crop marks without a TrimBox, or a TrimBox whose background stops at the cut line, were called print-ready.
- MediaBox offsets (Illustrator) and `/Rotate` pages put the cut line in the wrong place.
- Spot colours passed silently; phone photos got a size verdict instead of "can't check".
- Web addresses without `www` (linkedin.com/in/…) were flagged as typos.
- A-size PNGs without bleed were read as "with bleed".
- Fixing very large products could use over 1 GB of memory.

## v0.1 — first version (tag `v0.1-application`)

Checks, automatic fixes, Streamlit web demo and a local MCP server for Claude Desktop.
