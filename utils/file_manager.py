"""Temporary per-job file management.

Use ``create_job_dir`` as a context manager (or call ``create_job`` and later
``cleanup_job``). Files are isolated in private, automatically named directories.
"""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import shutil
import tempfile
from typing import Iterator

from .security import generated_filename

DEFAULT_TEMP_ROOT = Path(tempfile.gettempdir()) / "zenfile-bot"


def create_job(*, temp_root: str | os.PathLike[str] | None = None) -> Path:
    """Create and return a private temporary job directory."""
    root = Path(temp_root) if temp_root else DEFAULT_TEMP_ROOT
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = Path(tempfile.mkdtemp(prefix="job_", dir=root))
    try: path.chmod(0o700)
    except OSError: pass
    return path


def cleanup_job(job_dir: str | os.PathLike[str]) -> None:
    """Recursively remove a generated ``job_*`` directory, never arbitrary paths."""
    p = Path(job_dir)
    if not p.name.startswith("job_"):
        raise ValueError("cleanup_job only removes directories created with the job_ prefix")
    if p.is_symlink():
        p.unlink(missing_ok=True)
        return
    resolved = p.resolve()
    if resolved == Path(resolved.anchor) or resolved == Path.home() or not resolved.is_dir():
        raise ValueError("Refusing to clean a filesystem root or non-directory")
    shutil.rmtree(resolved, ignore_errors=False)


@contextmanager
def create_job_dir(*, temp_root: str | os.PathLike[str] | None = None) -> Iterator[Path]:
    """Yield a newly created job directory and remove it on context exit."""
    path = create_job(temp_root=temp_root)
    try: yield path
    finally:
        if path.exists() or path.is_symlink(): cleanup_job(path)


def output_path(output_dir: str | os.PathLike[str], original: str | os.PathLike[str], extension: str, *, prefix: str = "") -> Path:
    """Create a collision-resistant safe output path within an existing/new directory."""
    directory = Path(output_dir)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    return directory / generated_filename(original, extension, prefix=prefix)


def copy_into_job(source: str | os.PathLike[str], job_dir: str | os.PathLike[str], *, max_bytes: int | None = None) -> Path:
    """Copy a file into a job directory under a generated safe name."""
    src = Path(source)
    if not src.is_file(): raise ValueError("source must be a regular file")
    if max_bytes is not None and src.stat().st_size > max_bytes: raise ValueError("source exceeds max_bytes")
    extension = src.suffix.lstrip(".") or "bin"
    try: name = generated_filename(src.name, extension, prefix="input")
    except ValueError: name = generated_filename(src.name, "bin", prefix="input")
    dest = Path(job_dir) / name
    shutil.copyfile(src, dest)
    return dest
