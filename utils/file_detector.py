"""Signature-first file identification and conversion target registry.

Public API: ``detect_file(path) -> FileType`` and ``supported_targets(format)``.
Extensions are a fallback hint only; the signature is authoritative whenever known.
"""
from __future__ import annotations

from dataclasses import dataclass
import mimetypes
from pathlib import Path
import zipfile

from .errors import ConversionError


@dataclass(frozen=True)
class FileType:
    format: str
    mime_type: str
    category: str
    detected_by: str
    extension: str

    @property
    def mime(self) -> str:
        return self.mime_type


# Destination formats available through the conversion layer. Runtime tool/library
# availability is checked by each converter, not implied by this registry.
CONVERSION_TARGETS: dict[str, tuple[str, ...]] = {
    "pdf": ("png", "jpg", "jpeg", "txt"),
    "png": ("jpg", "jpeg", "webp", "bmp", "tiff", "pdf"),
    "jpg": ("png", "webp", "bmp", "tiff", "pdf"),
    "jpeg": ("png", "webp", "bmp", "tiff", "pdf"),
    "webp": ("png", "jpg", "jpeg", "pdf"),
    "bmp": ("png", "jpg", "jpeg", "webp", "pdf"),
    "tiff": ("png", "jpg", "jpeg", "pdf"),
    "gif": ("mp4", "webp", "png", "jpg"),
    "mp3": ("wav", "ogg", "flac", "m4a"),
    "wav": ("mp3", "ogg", "flac", "m4a"),
    "ogg": ("mp3", "wav", "flac", "m4a"),
    "flac": ("mp3", "wav", "ogg", "m4a"),
    "m4a": ("mp3", "wav", "ogg", "flac"),
    "mp4": ("mp3", "wav", "webm", "mkv", "mov", "gif"),
    "mov": ("mp4", "webm", "mkv", "mp3", "wav", "gif"),
    "mkv": ("mp4", "webm", "mov", "mp3", "wav", "gif"),
    "webm": ("mp4", "mkv", "mov", "mp3", "wav", "gif"),
    "avi": ("mp4", "webm", "mkv", "mp3", "wav", "gif"),
    "zip": ("tar", "tar.gz", "gz"),
    "tar": ("zip", "tar.gz", "gz"),
    "tar.gz": ("zip", "tar", "gz"),
    "gz": ("zip", "tar", "tar.gz"),
    "doc": ("docx", "odt", "rtf", "txt", "pdf"),
    "docx": ("pdf", "odt", "rtf", "txt"),
    "odt": ("docx", "pdf", "rtf", "txt"),
    "rtf": ("docx", "pdf", "odt", "txt"),
    "txt": ("pdf", "docx", "odt", "rtf"),
    "ppt": ("pptx", "pdf"), "pptx": ("pdf",),
    "xls": ("xlsx", "pdf", "csv"), "xlsx": ("pdf", "csv"),
}

_MIME = {
    "pdf": "application/pdf", "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
    "gif": "image/gif", "webp": "image/webp", "bmp": "image/bmp", "tiff": "image/tiff",
    "mp3": "audio/mpeg", "wav": "audio/wav", "flac": "audio/flac", "ogg": "audio/ogg",
    "m4a": "audio/mp4", "mp4": "video/mp4", "mov": "video/quicktime", "mkv": "video/x-matroska",
    "webm": "video/webm", "avi": "video/x-msvideo", "zip": "application/zip",
    "tar": "application/x-tar", "gz": "application/gzip", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "doc": "application/msword", "odt": "application/vnd.oasis.opendocument.text", "rtf": "application/rtf",
    "txt": "text/plain", "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "ppt": "application/vnd.ms-powerpoint", "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xls": "application/vnd.ms-excel", "epub": "application/epub+zip",
}


def supported_targets(source_format: str) -> tuple[str, ...]:
    """Return registered output formats for a source format (case-insensitive)."""
    return CONVERSION_TARGETS.get(source_format.lower().lstrip("."), ())


def _signature(head: bytes, path: Path) -> tuple[str, str] | None:
    if head.startswith(b"%PDF-"): return "pdf", "signature"
    if head.startswith(b"\x89PNG\r\n\x1a\n"): return "png", "signature"
    if head.startswith((b"\xff\xd8\xff",)): return "jpg", "signature"
    if head.startswith((b"GIF87a", b"GIF89a")): return "gif", "signature"
    if head.startswith(b"BM"): return "bmp", "signature"
    if head.startswith(b"II*\x00") or head.startswith(b"MM\x00*"): return "tiff", "signature"
    if head.startswith(b"RIFF") and head[8:12] == b"WEBP": return "webp", "signature"
    if head.startswith(b"RIFF") and head[8:12] == b"WAVE": return "wav", "signature"
    if head.startswith(b"fLaC"): return "flac", "signature"
    if head.startswith(b"OggS"): return "ogg", "signature"
    if head.startswith(b"ID3") or (len(head) >= 2 and head[0] == 0xff and head[1] & 0xe0 == 0xe0): return "mp3", "signature"
    if head.startswith(b"\x1aE\xdf\xa3"): return "webm", "signature"
    if len(head) >= 12 and head[4:8] == b"ftyp":
        brand = head[8:12]
        return ("m4a", "signature") if brand in {b"M4A ", b"M4B ", b"M4P ", b"F4A ", b"F4B ", b"mp4a"} else ("mp4", "signature")
    if head.startswith(b"RIFF") and head[8:12] == b"AVI ": return "avi", "signature"
    if head.startswith(b"PK\x03\x04") or head.startswith(b"PK\x05\x06"):
        try:
            with zipfile.ZipFile(path) as zf:
                names = set(zf.namelist())
                if "mimetype" in names:
                    try:
                        if zf.read("mimetype")[:64] == b"application/epub+zip": return "epub", "container"
                    except (OSError, KeyError, zipfile.BadZipFile): pass
                for prefix, fmt in (("word/", "docx"), ("ppt/", "pptx"), ("xl/", "xlsx"), ("content.xml", "odt")):
                    if any(n.startswith(prefix) for n in names): return fmt, "container"
        except (OSError, zipfile.BadZipFile): pass
        return "zip", "signature"
    if len(head) >= 262 and head[257:262] == b"ustar": return "tar", "signature"
    if head.startswith(b"Rar!\x1a\x07"): return "rar", "signature"
    if head.startswith(b"\x1f\x8b"):
        if path.name.lower().endswith((".tar.gz", ".tgz")): return "tar.gz", "extension+signature"
        return "gz", "signature"
    return None


def detect_file(path: str | Path, *, allow_text: bool = True) -> FileType:
    """Identify a regular file using byte signatures before its filename suffix.

    Raise ``ConversionError`` for missing/non-file inputs or unknown binary files.
    Plain text is accepted only when it is valid UTF-8 and contains no NUL bytes.
    """
    p = Path(path)
    if not p.is_file(): raise ConversionError(f"Input is not a regular file: {p}")
    try:
        with p.open("rb") as f: head = f.read(4096)
    except OSError as exc: raise ConversionError(f"Cannot read input file: {exc}") from exc
    found = _signature(head, p)
    if found:
        fmt, by = found
    elif allow_text and head and b"\0" not in head:
        try:
            head.decode("utf-8")
            fmt, by = "txt", "text-heuristic"
        except UnicodeDecodeError:
            fmt, by = "", ""
    else:
        fmt, by = "", ""
    if not fmt:
        ext = p.suffix.lower().lstrip(".")
        if ext in ("tar.gz", "tgz"): ext = "tar.gz"
        if ext in _MIME: fmt, by = ext, "extension-fallback"
        else: raise ConversionError(f"Unrecognized file type: {p.name}")
    ext = "tar.gz" if fmt == "tar.gz" else fmt
    mime = _MIME.get(fmt) or mimetypes.guess_type(f"x.{ext}")[0] or "application/octet-stream"
    category = "image" if fmt in {"png","jpg","jpeg","gif","webp","bmp","tiff"} else "audio" if fmt in {"mp3","wav","flac","ogg","m4a"} else "video" if fmt in {"mp4","mov","mkv","webm","avi"} else "archive" if fmt in {"zip","tar","tar.gz","gz"} else "document" if fmt in {"pdf","doc","docx","odt","rtf","txt","ppt","pptx","xls","xlsx","epub"} else "unknown"
    return FileType(fmt, mime, category, by, ext)


def get_file_type(path: str | Path) -> str:
    """Compatibility helper returning only the detected canonical format."""
    return detect_file(path).format
