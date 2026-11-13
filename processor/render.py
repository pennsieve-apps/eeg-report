"""
The HTML page and the PDF, from one Jinja template.

index.html: inline CSS, no scripts, no external resources; figures are PNG files in figures/ next
to it (relative links), so the folder opens offline. report.pdf: the same template rendered with
pdf=True (everything expanded, no <details>) by WeasyPrint, figures converted to JPEG at most
PDF_MAX_PX wide in TMPDIR first so the PDF stays a reasonable size.
"""
from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from processor.model import duration, fmt

log = logging.getLogger("eeg-report")
TEMPLATES = Path(__file__).parent / "templates"
PDF_MAX_PX = 1200
PDF_JPEG_QUALITY = 85


def mb(v: Any) -> str:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "–"
    return f"{v / 1024:.1f} GB" if v >= 1024 else f"{v:.0f} MB"


def refs(ns: list[int]) -> str:
    """[1, 2, 3, 5] -> [1–3, 5]"""
    ns = sorted(set(int(n) for n in ns or []))
    if not ns:
        return ""
    parts, start, prev = [], ns[0], ns[0]
    for n in ns[1:] + [None]:
        if n is not None and n == prev + 1:
            prev = n
            continue
        parts.append(f"{start}–{prev}" if prev > start + 1 else (f"{start}, {prev}" if prev == start + 1 else f"{start}"))
        if n is not None:
            start = prev = n
    return "[" + ", ".join(parts) + "]"


def plain(v: Any) -> str:
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, bool):
        return "true" if v else "false"
    return "" if v is None else str(v)


def environment() -> Environment:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=select_autoescape(["html", "j2"]),
                      trim_blocks=True, lstrip_blocks=True)
    env.filters.update(duration=duration, mb=mb, refs=refs, plain=plain, num=fmt)
    return env


def html(model: dict[str, Any], pdf: bool = False) -> str:
    return environment().get_template("report.html.j2").render(m=model, pdf=pdf)


def image_size(path: Path) -> tuple[int, int] | None:
    """(width, height) of a readable image, else None (a corrupt or non-image file)."""
    from PIL import Image

    try:
        with Image.open(path) as im:
            im.verify()
        with Image.open(path) as im:
            return im.size
    except Exception:  # noqa: BLE001 - an unreadable figure is reported, never fatal
        return None


def pdf_images(model: dict[str, Any], scratch: Path) -> None:
    """Copies of the shown figures for the PDF (f['pdf_src'], a file URI): at most PDF_MAX_PX wide,
    flattened on white and stored as JPEG (quality PDF_JPEG_QUALITY), which keeps a report with a
    hundred and more figures to tens of MB. The HTML keeps the original PNGs."""
    from PIL import Image

    scratch.mkdir(parents=True, exist_ok=True)
    k = 0
    for sec in model["sections"]:
        for f in sec["figures"]:
            if not f.get("ok"):
                continue
            src = Path(f["out_path"])
            k += 1
            dst = scratch / f"fig{k:04d}.jpg"
            try:
                with Image.open(src) as im:
                    im = im.convert("RGBA")
                    if im.width > PDF_MAX_PX:
                        im.thumbnail((PDF_MAX_PX, int(PDF_MAX_PX * im.height / im.width) + 1), Image.LANCZOS)
                    flat = Image.new("RGB", im.size, (255, 255, 255))
                    flat.paste(im, mask=im.getchannel("A"))
                    flat.save(dst, "JPEG", quality=PDF_JPEG_QUALITY, optimize=True)
                f["pdf_src"] = dst.resolve().as_uri()
            except Exception as exc:  # noqa: BLE001
                log.warning("could not convert %s for the PDF (%s): using it as is", src, exc)
                f["pdf_src"] = src.resolve().as_uri()


def write_pdf(model: dict[str, Any], path: Path) -> None:
    from weasyprint import HTML

    with tempfile.TemporaryDirectory(prefix="eeg-report-pdf-") as tmp:
        pdf_images(model, Path(tmp))
        HTML(string=html(model, pdf=True), base_url=str(path.parent)).write_pdf(str(path))
