"""Format-family compatibility mappings shared by bot routing and converters.

``can_convert(source, target)`` indicates a registered implementation path, not
that optional runtime dependencies (such as ffmpeg) are installed.
"""
from __future__ import annotations

from .file_detector import CONVERSION_TARGETS

ALIASES = {"jpeg": "jpg", "tif": "tiff", "wave": "wav", "mpeg": "mp3", "m4v": "mp4", "tgz": "tar.gz"}


def normalize_format(fmt: str) -> str:
    """Normalize a requested extension/format token."""
    value = fmt.lower().strip().lstrip(".")
    return ALIASES.get(value, value)


def can_convert(source: str, target: str) -> bool:
    """Return whether a source-target pair has a registered conversion route."""
    src, dst = normalize_format(source), normalize_format(target)
    return dst in CONVERSION_TARGETS.get(src, ())


def supported_formats(source: str) -> tuple[str, ...]:
    """Return registered targets for a source format."""
    return CONVERSION_TARGETS.get(normalize_format(source), ())


CONVERSION_MAP = CONVERSION_TARGETS
