"""Video conversion and inspection using ffmpeg/ffprobe without shell execution.

``convert(input_path, output_format, output_dir, **options) -> Path`` supports
MP4, WebM, MKV, MOV, AVI, GIF and audio extraction to MP3/WAV. Options are
validated: ``timeout``, ``max_bytes``, ``video_codec``, ``audio_codec``,
``crf`` (0-51), ``preset`` from a fixed set, ``width``/``height`` (even values),
``start_time`` and ``duration``. No arbitrary ffmpeg argument injection.
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

_VIDEO = {"mp4", "webm", "mkv", "mov", "avi", "gif"}
_AUDIO = {"mp3", "wav"}
_PRESETS = {"ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"}
_CODEC = {"mp4": "libx264", "mkv": "libx264", "mov": "libx264", "avi": "mpeg4", "webm": "libvpx-vp9", "gif": "gif"}


def _time(value, key):
    if value is None: return None
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0: return str(value)
    if isinstance(value, str) and re.fullmatch(r"\d+(?:\.\d{1,3})?", value): return value
    raise ConversionError(f"{key} must be a non-negative number of seconds")


def convert(input_path: str | Path, output_format: str, output_dir: str | Path, **options) -> Path:
    """Convert video container/codec, create a GIF, or extract an audio track."""
    src = Path(input_path); check_file_size(src, max_bytes=options.get("max_bytes", 250 * 1024 * 1024))
    detected = detect_file(src)
    if detected.category not in {"video", "image"}: raise UnsupportedFormatError("Input is not video or an animated image")
    fmt = output_format.lower().lstrip(".")
    if fmt not in _VIDEO | _AUDIO: raise UnsupportedFormatError(f"Unsupported video/audio target: {fmt}")
    if fmt in _VIDEO and detected.category != "video" and not (detected.format == "gif" and fmt in {"mp4", "webm"}):
        raise UnsupportedFormatError("This target requires a video input")
    if fmt in _AUDIO and detected.category != "video":
        raise UnsupportedFormatError("Audio extraction requires a video input")
    ffmpeg = require_executable("ffmpeg")
    dest = output_path(output_dir, src, fmt)
    args = [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y"]
    start = _time(options.get("start_time"), "start_time")
    duration = _time(options.get("duration"), "duration")
    if start is not None: args += ["-ss", start]
    args += ["-i", str(src)]
    if duration is not None:
        if float(duration) <= 0: raise ConversionError("duration must be greater than zero")
        args += ["-t", duration]
    if fmt in _AUDIO:
        args += ["-vn", "-c:a", "libmp3lame" if fmt == "mp3" else "pcm_s16le"]
        if fmt == "mp3":
            bitrate = str(options.get("bitrate", "192k"))
            if not re.fullmatch(r"\d{2,4}k", bitrate): raise ConversionError("bitrate must use a value such as 192k")
            args += ["-b:a", bitrate]
    else:
        codec = str(options.get("video_codec", _CODEC[fmt]))
        allowed = {"libx264", "libx265", "mpeg4", "libvpx-vp9", "libvpx", "gif"}
        if codec not in allowed: raise ConversionError("Unsupported video_codec")
        args += ["-c:v", codec]
        if fmt == "gif":
            args += ["-an"]
        else:
            default_audio = "aac" if fmt in {"mp4", "mov"} else "libopus" if fmt == "webm" else "libmp3lame" if fmt == "avi" else "copy"
            acodec = str(options.get("audio_codec", default_audio))
            if acodec not in {"aac", "libopus", "libmp3lame", "copy", "flac"}: raise ConversionError("Unsupported audio_codec")
            args += ["-c:a", acodec]
        crf = options.get("crf")
        if crf is not None:
            if not isinstance(crf, int) or not 0 <= crf <= 51: raise ConversionError("crf must be an integer from 0 to 51")
            args += ["-crf", str(crf)]
        preset = options.get("preset")
        if preset:
            if preset not in _PRESETS: raise ConversionError("Unsupported encoder preset")
            args += ["-preset", preset]
        width, height = options.get("width"), options.get("height")
        if (width is None) != (height is None): raise ConversionError("width and height must be set together")
        if width is not None:
            if any(not isinstance(v, int) or v < 2 or v > 7680 or v % 2 for v in (width, height)): raise ConversionError("width/height must be even integers between 2 and 7680")
            args += ["-vf", f"scale={width}:{height}"]
        if fmt == "mp4": args += ["-movflags", "+faststart"]
    args += ["-f", "mp4" if fmt == "mov" else fmt, str(dest)]
    try:
        run_process(args, timeout=int(options.get("timeout", 600)))
        if not dest.is_file() or dest.stat().st_size == 0: raise ConversionError("ffmpeg produced no output")
        return dest
    except Exception:
        dest.unlink(missing_ok=True); raise


def info(input_path: str | Path, *, timeout: int = 30) -> dict:
    """Return stream and container metadata from ffprobe."""
    src = Path(input_path); check_file_size(src)
    if detect_file(src).category != "video": raise UnsupportedFormatError("Input is not a video file")
    probe = require_executable("ffprobe")
    result = run_process([probe, "-v", "error", "-show_entries", "format=duration,format_name,size:stream=codec_name,codec_type,width,height,avg_frame_rate,bit_rate", "-of", "json", str(src)], timeout=timeout)
    try: return json.loads(result.stdout)
    except json.JSONDecodeError as exc: raise ConversionError("ffprobe returned invalid metadata") from exc
