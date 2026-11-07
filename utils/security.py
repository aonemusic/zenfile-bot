"""Security helpers for untrusted filenames, resource limits and archive paths.

Public API: ``safe_filename``, ``check_file_size``, ``parse_page_ranges`` and
``validate_archive_path``. Limits are configurable per call and default conservatively.
"""
from __future__ import annotations

import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import secrets
import unicodedata

from .errors import SecurityValidationError

DEFAULT_MAX_FILE_SIZE = 100 * 1024 * 1024
DEFAULT_MAX_ARCHIVE_TOTAL = 500 * 1024 * 1024
DEFAULT_MAX_ARCHIVE_FILES = 1000


def safe_filename(name: str | os.PathLike[str], *, max_length: int = 120, fallback: str = "file") -> str:
    """Return a sanitized basename; strips paths/control chars and limits length."""
    raw = os.fspath(name).replace("\\", "/").split("/")[-1]
    raw = unicodedata.normalize("NFKC", raw)
    raw = "".join(c for c in raw if c.isprintable() and c not in "<>:\"|?*" and ord(c) >= 32)
    raw = raw.strip(" .\t\r\n")
    raw = re.sub(r"\s+", "_", raw)
    raw = re.sub(r"[^\w.()\-]+", "_", raw, flags=re.UNICODE).strip("._")
    if raw in {"", ".", ".."}: raw = fallback
    # Avoid Windows device names, even if files are later moved to another OS.
    stem = raw.split(".", 1)[0].upper()
    if stem in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
        raw = f"_{raw}"
    if len(raw) > max_length:
        suffix = Path(raw).suffix
        raw = raw[:max(1, max_length - len(suffix))] + suffix[:max_length - 1]
    return raw or fallback


def generated_filename(original: str | os.PathLike[str], extension: str, *, prefix: str = "") -> str:
    """Create a non-user-controlled output name using a safe stem and random token."""
    stem = safe_filename(Path(os.fspath(original)).stem, max_length=64, fallback="converted")
    ext = extension.lower().lstrip(".")
    if not re.fullmatch(r"[a-z0-9][a-z0-9.+_-]{0,15}", ext):
        raise SecurityValidationError("Invalid output extension")
    pre = safe_filename(prefix, max_length=24, fallback="") if prefix else ""
    return f"{pre + '_' if pre else ''}{stem}_{secrets.token_hex(5)}.{ext}"


def check_file_size(path: str | os.PathLike[str], *, max_bytes: int = DEFAULT_MAX_FILE_SIZE) -> int:
    """Ensure path is a regular file and within ``max_bytes``; return byte size."""
    p = Path(path)
    if max_bytes <= 0: raise ValueError("max_bytes must be positive")
    try:
        if not p.is_file(): raise SecurityValidationError("Input is not a regular file")
        size = p.stat().st_size
    except OSError as exc: raise SecurityValidationError(f"Cannot stat input file: {exc}") from exc
    if size > max_bytes: raise SecurityValidationError(f"File exceeds size limit ({size} > {max_bytes} bytes)")
    return size


def parse_page_ranges(ranges: str | int | list[int] | tuple[int, ...] | None, *, page_count: int | None = None) -> list[int]:
    """Parse 1-based pages or expressions like ``1-3,5`` into unique page numbers."""
    if ranges is None: return list(range(1, page_count + 1)) if page_count is not None else []
    if isinstance(ranges, int): values = [ranges]
    elif isinstance(ranges, (list, tuple)):
        values = []
        for item in ranges:
            if isinstance(item, bool) or not isinstance(item, int): raise SecurityValidationError("Page numbers must be integers")
            values.append(item)
    elif isinstance(ranges, str):
        values = []
        for part in ranges.split(","):
            part = part.strip()
            if not part: raise SecurityValidationError("Empty page-range component")
            match = re.fullmatch(r"(\d+)(?:\s*-\s*(\d+))?", part)
            if not match: raise SecurityValidationError(f"Invalid page range: {part}")
            start = int(match.group(1)); end = int(match.group(2) or start)
            if end < start: raise SecurityValidationError("Page range end precedes start")
            if end - start > 10000: raise SecurityValidationError("Page range is too large")
            values.extend(range(start, end + 1))
    else: raise SecurityValidationError("Unsupported page range input")
    result = sorted(set(values))
    if any(n < 1 for n in result): raise SecurityValidationError("Page numbers are 1-based")
    if page_count is not None and any(n > page_count for n in result): raise SecurityValidationError(f"Page number exceeds document page count ({page_count})")
    return result


def validate_archive_path(member_name: str, destination: str | os.PathLike[str]) -> Path:
    """Resolve an archive member under destination, rejecting traversal/absolute paths."""
    if not isinstance(member_name, str) or not member_name or "\0" in member_name:
        raise SecurityValidationError("Invalid archive member path")
    # Reject both POSIX and Windows absolute/drive paths, regardless of host OS.
    posix = PurePosixPath(member_name.replace("\\", "/"))
    win = PureWindowsPath(member_name)
    if posix.is_absolute() or win.is_absolute() or win.drive or any(part == ".." for part in posix.parts):
        raise SecurityValidationError(f"Unsafe archive member path: {member_name!r}")
    root = Path(destination).resolve()
    target = (root / Path(*posix.parts)).resolve()
    try: target.relative_to(root)
    except ValueError as exc: raise SecurityValidationError(f"Archive member escapes destination: {member_name!r}") from exc
    return target
