"""Archive inspection, conversion and secure extraction.

``convert(input_path, output_format, output_dir, **options) -> Path`` converts
ZIP/TAR/TAR.GZ/GZIP (GZIP produces a TAR only when its payload is a valid TAR).
``extract(input_path, output_dir, **limits) -> list[Path]`` extracts ZIP/TAR with
path traversal, symlink, file-count and expanded-size checks. Defaults can be
raised per call, but extraction always validates member paths before writing.
"""
from __future__ import annotations

import gzip
import os
from pathlib import Path
import shutil
import tarfile
import tempfile
import zipfile

from utils.errors import ConversionError, UnsupportedFormatError
from utils.file_detector import detect_file
from utils.file_manager import output_path
from utils.security import DEFAULT_MAX_ARCHIVE_FILES, DEFAULT_MAX_ARCHIVE_TOTAL, check_file_size, safe_filename, validate_archive_path


def _format(src: Path) -> str:
    fmt = detect_file(src).format
    if fmt not in {"zip", "tar", "tar.gz", "gz"}: raise UnsupportedFormatError("Input is not a supported archive")
    return fmt


def extract(input_path: str | Path, output_dir: str | Path, *, max_files: int = DEFAULT_MAX_ARCHIVE_FILES, max_total_bytes: int = DEFAULT_MAX_ARCHIVE_TOTAL, max_input_bytes: int = 100 * 1024 * 1024) -> list[Path]:
    """Securely extract regular files from ZIP/TAR; links and special files are rejected."""
    src = Path(input_path); check_file_size(src, max_bytes=max_input_bytes); fmt = _format(src)
    dest = Path(output_dir).resolve(); dest.mkdir(mode=0o700, parents=True, exist_ok=True)
    written = []; total = 0; count = 0
    def reserve(name: str, size: int) -> Path:
        nonlocal total, count
        count += 1; total += size
        if count > max_files: raise ConversionError(f"Archive exceeds file-count limit ({max_files})")
        if size < 0 or total > max_total_bytes: raise ConversionError(f"Archive exceeds expanded-size limit ({max_total_bytes} bytes)")
        return validate_archive_path(name, dest)
    def reserve_directory(name: str) -> Path:
        nonlocal count
        count += 1
        if count > max_files: raise ConversionError(f"Archive exceeds file-count limit ({max_files})")
        return validate_archive_path(name, dest)
    try:
        if fmt == "zip":
            with zipfile.ZipFile(src) as zf:
                for member in zf.infolist():
                    if member.is_dir():
                        target = reserve_directory(member.filename); target.mkdir(mode=0o700, parents=True, exist_ok=True); continue
                    mode = member.external_attr >> 16
                    if mode and (mode & 0o170000) == 0o120000: raise ConversionError("ZIP symlinks are not allowed")
                    target = reserve(member.filename, member.file_size)
                    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                    written.append(target)
                    with zf.open(member, "r") as inp, target.open("xb") as out:
                        remaining = member.file_size
                        while True:
                            chunk = inp.read(min(1024 * 1024, remaining + 1))
                            if not chunk: break
                            remaining -= len(chunk)
                            if remaining < 0: raise ConversionError("ZIP entry exceeds declared size")
                            out.write(chunk)
                    if remaining != 0: raise ConversionError("ZIP entry size did not match metadata")
        elif fmt in {"tar", "tar.gz"}:
            with tarfile.open(src, mode="r:*" if fmt == "tar.gz" else "r:") as tf:
                for member in tf:
                    if member.isdir():
                        reserve_directory(member.name).mkdir(mode=0o700, parents=True, exist_ok=True); continue
                    if not member.isfile(): raise ConversionError("Archive links and special files are not allowed")
                    target = reserve(member.name, member.size); target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                    stream = tf.extractfile(member)
                    if stream is None: raise ConversionError("Unable to read archive member")
                    written.append(target)
                    with stream, target.open("xb") as out:
                        copied = 0
                        while chunk := stream.read(1024 * 1024):
                            copied += len(chunk)
                            if copied > member.size or copied > max_total_bytes: raise ConversionError("Archive member exceeds declared/allowed size")
                            out.write(chunk)
                    if copied != member.size: raise ConversionError("TAR entry size did not match metadata")
        else:
            out_name = src.name[:-3] if src.name.lower().endswith(".gz") else f"{src.stem}.out"
            target = validate_archive_path(out_name or "decompressed.bin", dest)
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            written.append(target)
            total = 0
            with gzip.open(src, "rb") as inp, target.open("xb") as out:
                while chunk := inp.read(1024 * 1024):
                    total += len(chunk)
                    if total > max_total_bytes: raise ConversionError("GZIP expanded size exceeds limit")
                    out.write(chunk)
        return written
    except Exception:
        # Do not remove destination as a whole (it may be caller-owned); remove only files created here.
        for path in reversed(written):
            try: path.unlink(missing_ok=True)
            except OSError: pass
        raise


def convert(input_path: str | Path, output_format: str, output_dir: str | Path, **options) -> Path:
    """Convert archive containers; extraction is available separately via ``extract``."""
    src = Path(input_path); check_file_size(src, max_bytes=options.get("max_input_bytes", 100 * 1024 * 1024))
    detected_source = detect_file(src).format
    target = output_format.lower().lstrip(".")
    if target == "tgz": target = "tar.gz"
    if target not in {"zip", "tar", "tar.gz", "gz"}: raise UnsupportedFormatError(f"Unsupported archive target: {target}")
    if detected_source == target: raise ConversionError("Source and target archive formats are identical")
    max_files = int(options.get("max_files", DEFAULT_MAX_ARCHIVE_FILES)); max_total = int(options.get("max_total_bytes", DEFAULT_MAX_ARCHIVE_TOTAL))
    dest = output_path(output_dir, src, target)
    try:
        if target == "gz":
            # GZIP compresses a single input stream; it is valid for ordinary files
            # as well as existing archive containers.
            with src.open("rb") as inp, gzip.open(dest, "wb", compresslevel=6) as out:
                copied = 0
                while chunk := inp.read(1024 * 1024):
                    copied += len(chunk)
                    if copied > options.get("max_input_bytes", 100 * 1024 * 1024): raise ConversionError("GZIP input exceeds configured limit")
                    out.write(chunk)
            return dest
        source = _format(src)
        if target == "gz":
            # GZIP is a stream wrapper, not a general multi-file archive. Compress
            # the source bytes rather than disguising a TAR as a .gz file.
            with src.open("rb") as inp, gzip.open(dest, "wb", compresslevel=6) as out:
                copied = 0
                while chunk := inp.read(1024 * 1024):
                    copied += len(chunk)
                    if copied > options.get("max_input_bytes", 100 * 1024 * 1024): raise ConversionError("GZIP input exceeds configured limit")
                    out.write(chunk)
            return dest
        if source == "gz":
            # Decompress one GZIP payload to a private staged file, then archive it.
            with tempfile.TemporaryDirectory(prefix="zenfile-gzip-") as work:
                scratch = Path(work)
                inner_name = src.name[:-3] if src.name.lower().endswith(".gz") else "decompressed.bin"
                safe_name = Path(inner_name).name or "decompressed.bin"
                inner = scratch / safe_name
                expanded = 0
                with gzip.open(src, "rb") as inp, inner.open("xb") as out:
                    while chunk := inp.read(1024 * 1024):
                        expanded += len(chunk)
                        if expanded > max_total: raise ConversionError("GZIP expanded size exceeds limit")
                        out.write(chunk)
                if target == "zip":
                    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf: zf.write(inner, safe_name)
                else:
                    with tarfile.open(dest, "w:gz" if target == "tar.gz" else "w") as tf:
                        tf.add(inner, arcname=safe_name, recursive=False, filter=_safe_tarinfo)
            return dest
        # Convert ZIP/TAR/TAR.GZ through a private, securely extracted staging tree.
        with tempfile.TemporaryDirectory(prefix="zenfile-archive-") as work:
            scratch = Path(work) / "unpacked"
            scratch.mkdir(mode=0o700)
            files = extract(src, scratch, max_files=max_files, max_total_bytes=max_total, max_input_bytes=options.get("max_input_bytes", 100 * 1024 * 1024))
            if target == "zip":
                with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
                    for path in files: zf.write(path, path.relative_to(scratch).as_posix())
            else:
                with tarfile.open(dest, "w:gz" if target == "tar.gz" else "w") as tf:
                    for path in files:
                        rel = path.relative_to(scratch).as_posix()
                        tf.add(path, arcname=rel, recursive=False, filter=_safe_tarinfo)
            return dest
    except Exception:
        dest.unlink(missing_ok=True)
        raise


def _safe_tarinfo(info: tarfile.TarInfo) -> tarfile.TarInfo:
    info.uid = info.gid = 0; info.uname = info.gname = ""; info.mtime = 0; info.mode &= 0o644
    return info


def create_archive(input_paths, output_dir: str | Path, archive_format: str = "zip", *, names=None, max_files: int = DEFAULT_MAX_ARCHIVE_FILES, max_total_bytes: int = DEFAULT_MAX_ARCHIVE_TOTAL) -> Path:
    """Create a flat archive from regular files with safe, unique member names."""
    paths = [Path(p) for p in input_paths]
    fmt = archive_format.lower().lstrip(".")
    if fmt not in {"zip", "tar", "tar.gz"}: raise UnsupportedFormatError("Archive output must be ZIP, TAR, or TAR.GZ")
    if not paths or len(paths) > max_files: raise ConversionError("Archive input file count is outside configured limits")
    labels = list(names) if names is not None else [p.name for p in paths]
    if len(labels) != len(paths): raise ConversionError("Each archive input requires one filename")
    total = 0
    for path in paths:
        if path.is_symlink(): raise ConversionError("Symlink inputs are not allowed")
        total += check_file_size(path, max_bytes=max_total_bytes)
    if total > max_total_bytes: raise ConversionError("Combined input size exceeds archive limit")
    unique_names = []
    seen = set()
    for raw in labels:
        name = safe_filename(raw)
        stem, suffix = Path(name).stem, Path(name).suffix
        candidate, n = name, 2
        while candidate.casefold() in seen:
            candidate = f"{stem}_{n}{suffix}"
            n += 1
        seen.add(candidate.casefold())
        unique_names.append(candidate)
    dest = output_path(output_dir, paths[0], fmt, prefix="archive")
    try:
        if fmt == "zip":
            with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
                for path, name in zip(paths, unique_names): zf.write(path, arcname=name)
        else:
            with tarfile.open(dest, "w:gz" if fmt == "tar.gz" else "w") as tf:
                for path, name in zip(paths, unique_names): tf.add(path, arcname=name, recursive=False, filter=_safe_tarinfo)
        return dest
    except Exception:
        dest.unlink(missing_ok=True)
        raise


def info(input_path: str | Path, *, max_files: int = DEFAULT_MAX_ARCHIVE_FILES) -> dict:
    """Return archive format, member count and expanded size without extracting."""
    src = Path(input_path); size = check_file_size(src); fmt = _format(src)
    if fmt == "zip":
        with zipfile.ZipFile(src) as zf:
            entries = zf.infolist()
            if len(entries) > max_files: raise ConversionError("Archive exceeds file-count limit")
            return {"format": fmt, "size_bytes": size, "members": len(entries), "expanded_bytes": sum(x.file_size for x in entries)}
    if fmt in {"tar", "tar.gz"}:
        with tarfile.open(src, "r:*") as tf:
            entries = tf.getmembers()
            if len(entries) > max_files: raise ConversionError("Archive exceeds file-count limit")
            return {"format": fmt, "size_bytes": size, "members": len(entries), "expanded_bytes": sum(x.size for x in entries if x.isfile())}
    return {"format": fmt, "size_bytes": size, "members": 1, "expanded_bytes": None}
