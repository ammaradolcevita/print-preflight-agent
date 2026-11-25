"""Open a PDF, PNG or JPG and turn it into one internal Artwork model.

Why one model: every check can then be written once, without caring
whether the customer uploaded a PDF from InDesign or a PNG from Canva.
"""

from __future__ import annotations

import re
from pathlib import Path

import pymupdf
from PIL import Image

from .models import Artwork, Box, FontInfo, ImageInfo, Page, Product, TextSpan
from .specs import pt_to_mm, tolerances

RASTER_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff"}


class LoadError(Exception):
    """The file cannot be read as print artwork. The message is customer-friendly."""


def load(path: str | Path, product: Product) -> Artwork:
    path = Path(path)
    if not path.exists():
        raise LoadError(f"File not found: {path.name}")
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _load_pdf(path)
    if suffix in RASTER_SUFFIXES:
        return _load_raster(path, product)
    raise LoadError(
        f"'{suffix}' files are not supported here. Please upload a PDF, PNG or JPG."
    )


# ---------------------------------------------------------------- PDF


def _colour_from_components(n: int) -> str:
    return {1: "Gray", 3: "RGB", 4: "CMYK"}.get(n, "Other")


def _rect_to_mm(rect, page_rect) -> Box:
    # PyMuPDF already uses a top-left origin; shift by the page origin for safety.
    return (
        pt_to_mm(rect[0] - page_rect.x0),
        pt_to_mm(rect[1] - page_rect.y0),
        pt_to_mm(rect[2] - page_rect.x0),
        pt_to_mm(rect[3] - page_rect.y0),
    )


def _load_pdf(path: Path) -> Artwork:
    try:
        doc = pymupdf.open(path)
    except Exception as exc:
        raise LoadError("This PDF could not be opened. It may be damaged.") from exc
    if doc.needs_pass:
        raise LoadError("This PDF is password-protected. Please upload an unlocked file.")
    if doc.page_count == 0:
        raise LoadError("This PDF has no pages.")

    pages: list[Page] = []
    for i, pg in enumerate(doc):
        rect = pg.rect  # the visible page (CropBox), in points, already turned by /Rotate
        # TrimBox, text and image positions come in unrotated page coordinates; turn them like the page.
        rot = pg.rotation_matrix

        def to_mm(r, rot=rot, rect=rect) -> Box:
            return _rect_to_mm(pymupdf.Rect(r) * rot, rect)

        trim_box = None
        # pg.trimbox is in MediaBox space (x keeps a MediaBox offset, as Illustrator writes);
        # text and images are relative to the visible page, so move the TrimBox there first.
        tb, cb = pg.trimbox, pg.cropbox
        trim = pymupdf.Rect(tb.x0 - cb.x0, tb.y0 - cb.y0, tb.x1 - cb.x0, tb.y1 - cb.y0) * rot
        if abs(trim.width - rect.width) > 0.5 or abs(trim.height - rect.height) > 0.5:
            trim_box = _rect_to_mm(trim, rect)

        images = []
        for info in pg.get_image_info(xrefs=True):
            bbox = to_mm(info["bbox"])
            images.append(
                ImageInfo(
                    width_px=int(info["width"]),
                    height_px=int(info["height"]),
                    bbox_mm=bbox,
                    colour=_colour_from_components(int(info.get("colorspace", 0))),
                )
            )

        spans = []
        for block in pg.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    if span["text"].strip():
                        spans.append(
                            TextSpan(
                                text=span["text"],
                                bbox_mm=to_mm(span["bbox"]),
                                size_pt=float(span["size"]),
                                font=span["font"],
                            )
                        )

        fonts = []
        for f in pg.get_fonts(full=True):
            # f = (xref, ext, type, basefont, name, encoding, referencer)
            xref, ext, basefont = f[0], f[1], f[3]
            fonts.append(FontInfo(name=basefont, embedded=bool(xref) and ext != "n/a"))

        pages.append(
            Page(
                index=i,
                width_mm=pt_to_mm(rect.width),
                height_mm=pt_to_mm(rect.height),
                trim_box_mm=trim_box,
                images=images,
                text=spans,
                fonts=fonts,
            )
        )
    spots = _spot_colours(doc)
    doc.close()
    return Artwork(path=str(path), kind="pdf", pages=pages, spot_colours=spots)


# Separation names that are not real inks: "All" is the registration colour crop marks use.
_NOT_INKS = {"All", "None", "Cyan", "Magenta", "Yellow", "Black"}
_SEPARATION = re.compile(r"/Separation\s*/([^\s/\[\]<>()]+)")
_DEVICE_N = re.compile(r"/DeviceN\s*\[([^\]]*)\]")


def _pdf_name(raw: str) -> str:
    return re.sub(r"#([0-9A-Fa-f]{2})", lambda m: chr(int(m.group(1), 16)), raw)


def _spot_colours(doc) -> list[str]:
    """Named spot inks used anywhere in the PDF (they print in CMYK unless agreed otherwise)."""
    names: set[str] = set()
    for xref in range(1, doc.xref_length()):
        try:
            obj = doc.xref_object(xref, compressed=True)
        except Exception:  # noqa: BLE001 - a damaged object is not a reason to fail the whole check
            continue
        names.update(_pdf_name(n) for n in _SEPARATION.findall(obj))
        for group in _DEVICE_N.findall(obj):
            names.update(_pdf_name(n) for n in re.findall(r"/([^\s/\[\]]+)", group))
    return sorted(names - _NOT_INKS)


# ---------------------------------------------------------------- PNG / JPG


def _close(a: float, b: float, rel: float) -> bool:
    return abs(a - b) <= rel * max(a, b)


def _load_raster(path: Path, product: Product) -> Artwork:
    """A picture has pixels but no physical size, so we place it on the product.

    - same shape as trim + bleed  -> it is the full page including bleed
    - same shape as trim          -> it is the trimmed page, without bleed
    - otherwise                   -> stretch to the trim width; the size check reports it
    """
    try:
        with Image.open(path) as img:
            img.load()
            w_px, h_px = img.size
            mode = img.mode
            camera = _camera(img)
    except Exception as exc:
        raise LoadError("This image could not be opened. It may be damaged.") from exc
    if camera:
        raise LoadError(
            f"This looks like a camera photo ({camera}), not a design file. A photo of a printed card "
            "can't be checked reliably. Please upload the file you designed (PDF, or a PNG/JPG export)."
        )

    colour = {"RGB": "RGB", "RGBA": "RGB", "P": "RGB", "CMYK": "CMYK", "L": "Gray", "1": "Gray"}.get(
        mode, "Other"
    )
    rel = tolerances()["aspect_rel"]
    aspect = w_px / h_px

    tw, th = product.trim_mm
    fw, fh = product.full_mm
    candidates = [(fw, fh), (tw, th), (fh, fw), (th, tw)]  # allow either orientation
    # Take the CLOSEST shape, not the first that fits: for A-sizes "with bleed" (154 x 216 = 0.713)
    # and "without bleed" (148 x 210 = 0.705) are both within tolerance of a 0.707 export.
    fitting = [(abs(aspect - cw / ch), cw, ch) for cw, ch in candidates if _close(aspect, cw / ch, rel)]
    if fitting:
        _, page_w, page_h = min(fitting)
    else:
        page_w = tw if w_px >= h_px or tw >= th else th
        page_h = page_w / aspect

    image = ImageInfo(width_px=w_px, height_px=h_px, bbox_mm=(0, 0, page_w, page_h), colour=colour)
    page = Page(index=0, width_mm=page_w, height_mm=page_h, images=[image])
    return Artwork(path=str(path), kind="raster", pages=[page])


# EXIF tags only a camera writes: ExposureTime, FNumber, ISO (in the Exif sub-IFD).
_CAMERA_TAGS = (33434, 33437, 34855)


def _camera(img: Image.Image) -> str | None:
    """'Apple iPhone 15' when the picture was taken with a camera, else None."""
    try:
        exif = img.getexif()
        shot = exif.get_ifd(0x8769)
    except Exception:  # noqa: BLE001
        return None
    if not any(t in shot for t in _CAMERA_TAGS):
        return None
    return " ".join(str(exif.get(t, "")).strip() for t in (271, 272)).strip() or "camera"


def render_page_rgb(path: str | Path, page_index: int = 0, dpi: int = 72) -> Image.Image:
    """Render one page to a PIL image (used for edge detection and previews)."""
    path = Path(path)
    if path.suffix.lower() == ".pdf":
        with pymupdf.open(path) as doc:
            pix = doc[page_index].get_pixmap(dpi=dpi, colorspace=pymupdf.csRGB, alpha=False)
            return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    with Image.open(path) as img:
        return img.convert("RGB")
