"""Audio conversion using ffmpeg/ffprobe with argv-only subprocesses.

``convert(input_path, output_format, output_dir, **options) -> Path`` supports
MP3, WAV, OGG, FLAC and M4A. Options include ``timeout``, ``max_bytes``,
``bitrate`` (validated e.g. ``192k``), ``sample_rate`` and ``channels``.
"""
from __future__ import annotations

import json
from pathlib import Path
import re

from utils.errors import ConversionError, UnsupportedFormatError
from utils.file_detector import detect_file
from utils.file_manager import output_path
from utils.process import require_executable, run_process
from utils.security import check_file_size

_FORMATS = {"mp3": "libmp3lame", "wav": "pcm_s16le", "ogg": "libvorbis", "flac": "flac", "m4a": "aac"}
_AUDIO = {"mp3", "wav", "ogg", "flac", "m4a"}


def convert(input_path: str | Path, output_format: str, output_dir: str | Path, **options) -> Path:
    """Convert an audio file to the selected audio container/codec."""
    src = Path(input_path); check_file_size(src, max_bytes=options.get("max_bytes", 100 * 1024 * 1024))
    detected = detect_file(src)
    if detected.category != "audio": raise UnsupportedFormatError("Input is not an audio file")
    fmt = output_format.lower().lstrip(".")
    if fmt not in _FORMATS: raise UnsupportedFormatError(f"Unsupported audio target: {fmt}")
    bitrate = str(options.get("bitrate", "192k"))
    if not re.fullmatch(r"\d{2,4}k", bitrate): raise ConversionError("bitrate must use a value such as 192k")
    sample_rate = options.get("sample_rate")
    if sample_rate is not None and (not isinstance(sample_rate, int) or not 8000 <= sample_rate <= 192000): raise ConversionError("sample_rate must be between 8000 and 192000")
    channels = options.get("channels")
    if channels is not None and channels not in (1, 2): raise ConversionError("channels must be 1 or 2")
    ffmpeg = require_executable("ffmpeg")
    dest = output_path(output_dir, src, fmt)
    args = [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), "-vn", "-c:a", _FORMATS[fmt]]
    if fmt in {"mp3", "ogg", "m4a"}: args += ["-b:a", bitrate]
    if sample_rate: args += ["-ar", str(sample_rate)]
    if channels: args += ["-ac", str(channels)]
    args += ["-f", fmt, str(dest)]
    try:
        run_process(args, timeout=int(options.get("timeout", 300)))
        if not dest.is_file() or dest.stat().st_size == 0: raise ConversionError("ffmpeg produced no audio output")
        return dest
    except Exception:
        dest.unlink(missing_ok=True); raise


def info(input_path: str | Path, *, timeout: int = 30) -> dict:
    """Return audio stream and duration metadata from ffprobe."""
    src = Path(input_path); check_file_size(src)
    if detect_file(src).category != "audio": raise UnsupportedFormatError("Input is not an audio file")
    probe = require_executable("ffprobe")
    result = run_process([probe, "-v", "error", "-show_entries", "format=duration,format_name,size:stream=codec_name,codec_type,sample_rate,channels,bit_rate", "-of", "json", str(src)], timeout=timeout)
    try: return json.loads(result.stdout)
    except json.JSONDecodeError as exc: raise ConversionError("ffprobe returned invalid metadata") from exc
