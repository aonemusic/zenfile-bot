"""Safe cleanup helpers for temporary conversion artifacts.

``cleanup_file`` removes a specified regular file/symlink; ``cleanup_stale_jobs``
only removes old ``job_*`` folders under a caller-selected temp root.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import time


def cleanup_file(path: str | os.PathLike[str], *, missing_ok: bool = True) -> None:
    """Remove a regular temporary file or symlink, never recursively delete a directory."""
    p = Path(path)
    try:
        if p.is_symlink() or p.is_file(): p.unlink()
        elif p.exists(): raise ValueError("cleanup_file refuses to remove directories")
        elif not missing_ok: raise FileNotFoundError(p)
    except FileNotFoundError:
        if not missing_ok: raise


def cleanup_stale_jobs(temp_root: str | os.PathLike[str], *, older_than_seconds: int = 24 * 3600, now: float | None = None) -> int:
    """Delete old real directories named job_* directly beneath ``temp_root``."""
    root = Path(temp_root).resolve()
    if root == Path(root.anchor) or root == Path.home(): raise ValueError("Refusing unsafe temp root")
    cutoff = (time.time() if now is None else now) - older_than_seconds
    removed = 0
    if not root.is_dir(): return 0
    for child in root.iterdir():
        try:
            if child.name.startswith("job_") and child.is_dir() and not child.is_symlink() and child.stat().st_mtime < cutoff:
                shutil.rmtree(child)
                removed += 1
        except FileNotFoundError: continue
    return removed
