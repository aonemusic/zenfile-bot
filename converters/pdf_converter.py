"""PDF conversion and manipulation APIs.

``convert(input_path, output_format, output_dir, **options)`` supports PDF to
PNG/JPEG/text and raster image(s) to PDF. Multi-page rendering returns a list of
paths (single-page/text/PDF conversions return a path). Extra APIs are
``merge_pdfs(paths, output_dir)``, ``split_pdf(input_path, output_dir, pages=None)``,
``extract_pages(input_path, pages, output_dir)`` and ``info(input_path)``.
Requires PyMuPDF (fitz) for PDF rendering/text and pypdf or fitz for structural
operations; Pillow is required for image-to-PDF. No PDF-to-DOCX claim is made.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

from utils.errors import ConversionError, DependencyUnavailableError, UnsupportedFormatError
from utils.file_detector import detect_file
from utils.file_manager import output_path
from utils.security import check_file_size, parse_page_ranges
from config import settings

MAX_PDF_PAGES = settings.max_pdf_pages


def _fitz():
    try:
        import pymupdf
        return pymupdf
    except ImportError:
        try:
            import fitz
            return fitz
        except ImportError as exc:
            raise DependencyUnavailableError("PyMuPDF is required for PDF rendering") from exc


def _pypdf():
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError: return None, None
    return PdfReader, PdfWriter


def _page_indices(pages, total: int) -> list[int]:
    if total > MAX_PDF_PAGES: raise ConversionError(f"PDF page count exceeds configured limit ({MAX_PDF_PAGES})")
    nums = parse_page_ranges(pages, page_count=total)
    if pages is None: return list(range(total))
    return [n - 1 for n in nums]


def convert(input_path: str | Path, output_format: str, output_dir: str | Path, **options):
    """Convert a PDF to images/text or one or more raster images to PDF."""
    src = Path(input_path)
    check_file_size(src, max_bytes=options.get("max_bytes", 100 * 1024 * 1024))
    fmt = output_format.lower().lstrip(".")
    detected = detect_file(src)
    outdir = Path(output_dir)
    if detected.format == "pdf":
        if fmt not in {"png", "jpg", "jpeg", "txt"}:
            raise UnsupportedFormatError(f"PDF to {fmt} is not supported by pdf_converter")
        fitz = _fitz()
        try: doc = fitz.open(src)
        except Exception as exc: raise ConversionError(f"Unable to open PDF: {exc}") from exc
        try:
            indexes = _page_indices(options.get("pages"), len(doc))
            if fmt == "txt":
                dest = output_path(outdir, src, "txt", prefix="text")
                dest.write_text("\n\n".join(doc[i].get_text("text") for i in indexes), encoding="utf-8")
                return dest
            extension = "jpg" if fmt == "jpeg" else fmt
            paths = []
            scale = float(options.get("scale", 2.0))
            if not (0.25 <= scale <= 4.0): raise ConversionError("PDF render scale must be between 0.25 and 4")
            matrix = fitz.Matrix(scale, scale)
            for ordinal, i in enumerate(indexes, 1):
                dest = output_path(outdir, src, extension, prefix=f"page_{i + 1}")
                pix = doc[i].get_pixmap(matrix=matrix, alpha=False)
                pix.save(str(dest))
                paths.append(dest)
            return paths[0] if len(paths) == 1 else paths
        finally: doc.close()
    if detected.category == "image" and fmt == "pdf":
        try: from PIL import Image, ImageOps
        except ImportError as exc: raise DependencyUnavailableError("Pillow is required for image-to-PDF conversion") from exc
        paths = [Path(p) for p in (options.get("images") or [src])]
        if not paths or len(paths) > 100: raise ConversionError("Image-to-PDF input count must be 1 to 100")
        images = []
        try:
            for path in paths:
                check_file_size(path, max_bytes=options.get("max_bytes", 100 * 1024 * 1024))
                if detect_file(path).category != "image": raise UnsupportedFormatError(f"Not an image: {path.name}")
                with Image.open(path) as im:
                    im.seek(0)
                    frame = ImageOps.exif_transpose(im.copy())
                    if frame.mode in ("RGBA", "LA") or "transparency" in frame.info:
                        rgba = frame.convert("RGBA")
                        matte = Image.new("RGBA", rgba.size, options.get("background", "white"))
                        frame.close()
                        frame = Image.alpha_composite(matte, rgba).convert("RGB")
                        rgba.close(); matte.close()
                    elif frame.mode != "RGB":
                        converted = frame.convert("RGB")
                        frame.close(); frame = converted
                    images.append(frame)
            if not images: raise ConversionError("No images supplied")
            dest = output_path(outdir, src, "pdf")
            images[0].save(dest, "PDF", save_all=True, append_images=images[1:])
            return dest
        except ConversionError: raise
        except Exception as exc: raise ConversionError(f"Image-to-PDF conversion failed: {exc}") from exc
        finally:
            for im in images: im.close()
    raise UnsupportedFormatError(f"Cannot convert {detected.format} to {fmt} with pdf_converter")


def merge_pdfs(input_paths: Iterable[str | Path], output_dir: str | Path, *, max_bytes: int = 250 * 1024 * 1024) -> Path:
    """Merge up to 100 PDFs into one generated-name PDF."""
    paths = [Path(p) for p in input_paths]
    if not paths or len(paths) > 100: raise ConversionError("Provide between 1 and 100 PDFs")
    total = 0
    for p in paths:
        total += check_file_size(p, max_bytes=max_bytes)
        if detect_file(p).format != "pdf": raise UnsupportedFormatError(f"Not a PDF: {p.name}")
    if total > max_bytes: raise ConversionError("Combined PDF size exceeds limit")
    _, Writer = _pypdf()
    dest = output_path(output_dir, paths[0], "pdf", prefix="merged")
    try:
        if Writer:
            writer = Writer()
            for p in paths:
                reader = _pypdf()[0](str(p), strict=True)
                if len(reader.pages) > MAX_PDF_PAGES: raise ConversionError("PDF page count exceeds limit")
                for page in reader.pages: writer.add_page(page)
            with dest.open("wb") as f: writer.write(f)
        else:
            fitz = _fitz(); merged = fitz.open()
            try:
                for p in paths:
                    with fitz.open(p) as doc:
                        if len(doc) + len(merged) > MAX_PDF_PAGES: raise ConversionError("Merged page count exceeds limit")
                        merged.insert_pdf(doc)
                merged.save(dest)
            finally: merged.close()
    except ConversionError: dest.unlink(missing_ok=True); raise
    except Exception as exc: dest.unlink(missing_ok=True); raise ConversionError(f"PDF merge failed: {exc}") from exc
    return dest


def extract_pages(input_path: str | Path, pages, output_dir: str | Path) -> list[Path]:
    """Write selected 1-based pages as separate single-page PDFs."""
    src = Path(input_path); check_file_size(src)
    if detect_file(src).format != "pdf": raise UnsupportedFormatError("Input must be PDF")
    PdfReader, Writer = _pypdf()
    fitz = None if Writer else _fitz()
    outputs = []
    if Writer:
        reader = PdfReader(str(src), strict=True); indexes = _page_indices(pages, len(reader.pages))
        for n in indexes:
            writer = Writer(); writer.add_page(reader.pages[n]); dest = output_path(output_dir, src, "pdf", prefix=f"page_{n+1}")
            with dest.open("wb") as f: writer.write(f)
            outputs.append(dest)
    else:
        doc = fitz.open(src)
        try:
            indexes = _page_indices(pages, len(doc))
            for n in indexes:
                one = fitz.open(); one.insert_pdf(doc, from_page=n, to_page=n)
                dest = output_path(output_dir, src, "pdf", prefix=f"page_{n+1}")
                try: one.save(dest)
                finally: one.close()
                outputs.append(dest)
        finally: doc.close()
    return outputs


def split_pdf(input_path: str | Path, output_dir: str | Path, pages=None) -> list[Path]:
    """Split selected pages (all by default) into individual PDF files."""
    return extract_pages(input_path, pages, output_dir)


def info(input_path: str | Path) -> dict:
    """Return page count, geometry, metadata and encryption status for a PDF."""
    src = Path(input_path); check_file_size(src)
    if detect_file(src).format != "pdf": raise UnsupportedFormatError("Input must be PDF")
    try:
        fitz = _fitz()
        with fitz.open(src) as doc:
            return {"path": str(src), "pages": len(doc), "encrypted": bool(doc.is_encrypted), "metadata": dict(doc.metadata or {}), "page_sizes": [{"width": round(p.rect.width, 2), "height": round(p.rect.height, 2)} for p in list(doc)[:MAX_PDF_PAGES]]}
    except DependencyUnavailableError:
        Reader, _ = _pypdf()
        if not Reader: raise
        r = Reader(str(src)); return {"path": str(src), "pages": len(r.pages), "encrypted": r.is_encrypted, "metadata": dict(r.metadata or {})}


def compress_pdf(input_path: str | Path, output_dir: str | Path, **options) -> Path:
    """Repack a PDF with object cleanup and stream deflation; this may not reduce size."""
    src = Path(input_path)
    check_file_size(src, max_bytes=options.get("max_bytes", 100 * 1024 * 1024))
    if detect_file(src).format != "pdf": raise UnsupportedFormatError("Input must be a PDF")
    fitz = _fitz()
    try:
        doc = fitz.open(src)
    except Exception as exc:
        raise ConversionError(f"Unable to open PDF: {exc}") from exc
    try:
        if doc.is_encrypted:
            raise ConversionError("Encrypted PDFs cannot be recompressed without a password")
        if len(doc) > MAX_PDF_PAGES:
            raise ConversionError(f"PDF page count exceeds configured limit ({MAX_PDF_PAGES})")
        dest = output_path(output_dir, src, "pdf", prefix="compressed")
        try:
            doc.save(dest, garbage=4, deflate=True, clean=True)
        except Exception as exc:
            dest.unlink(missing_ok=True)
            raise ConversionError(f"PDF recompression failed: {exc}") from exc
        return dest
    finally:
        doc.close()
