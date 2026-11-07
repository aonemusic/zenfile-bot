"""Office document conversion through isolated LibreOffice headless processes.

``convert(input_path, output_format, output_dir, **options) -> Path`` supports
doc/docx/odt/rtf/txt and selected ppt/xls families where LibreOffice supports
those exports. Inputs are copied into a private temporary work directory, output
formats are allowlisted, execution uses argv (never a shell), and time is bounded.
PDF-to-DOCX is intentionally not advertised: LibreOffice PDF import is not a
reliable text-document conversion. ``info`` reports basic file metadata only.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import tempfile

from utils.errors import ConversionError, UnsupportedFormatError
from utils.file_detector import detect_file
from utils.file_manager import output_path
from utils.process import require_executable, run_process
from utils.security import check_file_size, safe_filename

_EXPORTS = {
    "doc": {"docx": "docx", "odt": "odt", "rtf": "rtf", "txt": "txt", "pdf": "pdf"},
    "docx": {"doc": "doc", "odt": "odt", "rtf": "rtf", "txt": "txt", "pdf": "pdf"},
    "odt": {"docx": "docx", "doc": "doc", "rtf": "rtf", "txt": "txt", "pdf": "pdf"},
    "rtf": {"docx": "docx", "doc": "doc", "odt": "odt", "txt": "txt", "pdf": "pdf"},
    "txt": {"docx": "docx", "odt": "odt", "rtf": "rtf", "pdf": "pdf"},
    "ppt": {"pptx": "pptx", "pdf": "pdf"}, "pptx": {"ppt": "ppt", "pdf": "pdf"},
    "xls": {"xlsx": "xlsx", "pdf": "pdf", "csv": "csv"}, "xlsx": {"xls": "xls", "pdf": "pdf", "csv": "csv"},
}


def convert(input_path: str | Path, output_format: str, output_dir: str | Path, **options) -> Path:
    """Convert a supported office document with LibreOffice in a temporary profile."""
    src = Path(input_path); check_file_size(src, max_bytes=options.get("max_bytes", 100 * 1024 * 1024))
    detected = detect_file(src); source_fmt = detected.format
    # Extension determines LibreOffice input filter; signature-based detection must agree for OOXML.
    if source_fmt not in _EXPORTS:
        raise UnsupportedFormatError(f"Unsupported LibreOffice input type: {source_fmt}")
    fmt = output_format.lower().lstrip(".")
    if fmt not in _EXPORTS[source_fmt]: raise UnsupportedFormatError(f"{source_fmt} to {fmt} is not supported")
    if source_fmt == "txt" and src.stat().st_size > options.get("max_text_bytes", 10 * 1024 * 1024): raise ConversionError("Text input exceeds conversion limit")
    executable = options.get("executable")
    if executable:
        soffice = require_executable(executable)
    else:
        try: soffice = require_executable("libreoffice")
        except Exception: soffice = require_executable("soffice")
    outdir = Path(output_dir); outdir.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Separate profile and staging directory avoid shared-profile races and path collisions.
    with tempfile.TemporaryDirectory(prefix="zenfile-lo-") as work:
        root = Path(work); stage = root / "in"; stage.mkdir(mode=0o700)
        profile = root / "profile"; profile.mkdir(mode=0o700)
        safe_stem = safe_filename(src.stem, max_length=80, fallback="document")
        staged = stage / f"{safe_stem}.{source_fmt}"
        shutil.copyfile(src, staged)
        args = [soffice, "--headless", "--nologo", "--nodefault", "--nolockcheck", "--norestore", f"-env:UserInstallation={profile.as_uri()}", "--convert-to", f"{fmt}:{_EXPORTS[source_fmt][fmt]}", "--outdir", str(root), str(staged)]
        run_process(args, timeout=int(options.get("timeout", 180)))
        produced = root / f"{safe_stem}.{fmt}"
        if not produced.is_file() or produced.stat().st_size == 0: raise ConversionError("LibreOffice did not produce the expected output")
        dest = output_path(outdir, src, fmt)
        shutil.copyfile(produced, dest)
        return dest


def info(input_path: str | Path) -> dict:
    """Return detected document format, MIME type, byte size and safe filename."""
    src = Path(input_path); size = check_file_size(src)
    found = detect_file(src)
    if found.category != "document": raise UnsupportedFormatError("Input is not a supported document")
    return {"name": safe_filename(src.name), "format": found.format, "mime_type": found.mime_type, "size_bytes": size}
