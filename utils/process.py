"""Safe external-process wrapper: argv lists only, bounded timeout, captured output."""
from __future__ import annotations

import shutil
import subprocess
from collections.abc import Sequence

from .errors import ConversionError, DependencyUnavailableError


def require_executable(name: str) -> str:
    """Return executable path or raise a user-readable optional-dependency error."""
    path = shutil.which(name)
    if not path: raise DependencyUnavailableError(f"Required executable '{name}' is not installed")
    return path


def run_process(args: Sequence[str], *, timeout: int = 120, cwd: str | None = None, max_stderr: int = 2000) -> subprocess.CompletedProcess[str]:
    """Run a command safely without a shell; raise ConversionError on failure/timeout."""
    if not args or any(not isinstance(a, str) for a in args): raise ValueError("args must be a non-empty sequence of strings")
    try:
        result = subprocess.run(list(args), cwd=cwd, shell=False, check=False, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise ConversionError(f"Process timed out after {timeout} seconds") from exc
    except OSError as exc:
        raise ConversionError(f"Could not run external tool: {exc}") from exc
    if result.returncode:
        detail = (result.stderr or result.stdout or "").strip()[-max_stderr:]
        raise ConversionError(f"External tool failed (exit {result.returncode}): {detail}")
    return result
