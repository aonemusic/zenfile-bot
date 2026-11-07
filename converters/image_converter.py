"""Image format conversion with explicit safeguards against lossy frame/alpha drops.

``convert(input_path, output_format, output_dir, **options) -> Path``. Options:
``background`` (matte color for alpha-to-JPEG), ``frame_index`` (select one frame),
``allow_loss`` (explicitly permit dropping animation/alpha), ``max_pixels`` and
``preserve_exif``. Uses Pillow and raises a clear dependency error if unavailable.
"""
from __future__ import annotations

from pathlib import Path

from utils.errors import ConversionError, DependencyUnavailableError, UnsupportedFormatError
from utils.file_detector import detect_file
from utils.file_manager import output_path
from utils.security import check_file_size

_FORMATS = {"jpg": "JPEG", "jpeg": "JPEG", "png": "PNG", "webp": "WEBP", "bmp": "BMP", "tif": "TIFF", "tiff": "TIFF", "gif": "GIF"}


def convert(input_path: str | Path, output_format: str, output_dir: str | Path, **options) -> Path:
    """Convert one image while retaining animation/alpha whenever the target supports it."""
    src = Path(input_path); check_file_size(src, max_bytes=options.get("max_bytes", 100 * 1024 * 1024))
    if detect_file(src).category != "image": raise UnsupportedFormatError("Input is not a supported image")
    fmt = output_format.lower().lstrip(".")
    if fmt not in _FORMATS: raise UnsupportedFormatError(f"Unsupported image target: {fmt}")
    try: from PIL import Image, ImageOps, ImageSequence
    except ImportError as exc: raise DependencyUnavailableError("Pillow is required for image conversion") from exc
    max_pixels = int(options.get("max_pixels", 80_000_000))
    if max_pixels <= 0: raise ConversionError("max_pixels must be positive")
    try:
        with Image.open(src) as image:
            if image.width * image.height > max_pixels: raise ConversionError("Image exceeds max_pixels limit")
            frames = int(getattr(image, "n_frames", 1))
            animated = frames > 1
            target_fmt = _FORMATS[fmt]
            supports_animation = target_fmt in {"GIF", "WEBP"}
            frame_index = options.get("frame_index")
            allow_loss = bool(options.get("allow_loss", False))
            if animated and not supports_animation and frame_index is None and not allow_loss:
                raise ConversionError("Target format cannot preserve animation; specify frame_index or allow_loss=True")
            if frame_index is not None:
                try: frame_index = int(frame_index)
                except (ValueError, TypeError) as exc: raise ConversionError("frame_index must be an integer") from exc
                if frame_index < 0 or frame_index >= frames: raise ConversionError("frame_index is outside the image")
                image.seek(frame_index)
                selected = [ImageOps.exif_transpose(image.copy())]
            elif animated and supports_animation:
                selected = []
                durations = []
                for frame in ImageSequence.Iterator(image):
                    if frame.width * frame.height > max_pixels: raise ConversionError("Animation frame exceeds max_pixels limit")
                    selected.append(ImageOps.exif_transpose(frame.copy().convert("RGBA" if "A" in frame.getbands() else "RGB")))
                    durations.append(int(frame.info.get("duration", 100)))
            else:
                image.seek(0); selected = [ImageOps.exif_transpose(image.copy())]
            has_alpha = any(im.mode in ("RGBA", "LA") or "transparency" in im.info for im in selected)
            background = options.get("background")
            if target_fmt in {"JPEG", "BMP"} and has_alpha:
                if background is None and not allow_loss:
                    raise ConversionError("Target format cannot preserve transparency; supply background='#ffffff' or allow_loss=True")
                color = background or "white"
                flattened = []
                for im in selected:
                    rgba = im.convert("RGBA")
                    matte = Image.new("RGBA", rgba.size, color)
                    flattened.append(Image.alpha_composite(matte, rgba).convert("RGB"))
                for im in selected: im.close()
                selected = flattened
            elif target_fmt == "JPEG":
                selected = [im.convert("RGB") for im in selected]
            elif target_fmt == "BMP" and any(im.mode not in {"RGB", "L"} for im in selected):
                selected = [im.convert("RGB") for im in selected]
            resize = options.get("resize")
            if resize is not None:
                if not isinstance(resize, (tuple, list)) or len(resize) != 2:
                    raise ConversionError("resize must be a (width, height) pair")
                width, height = resize
                if any(not isinstance(value, int) or value < 1 or value > 12000 for value in (width, height)):
                    raise ConversionError("Resize dimensions must be between 1 and 12000 pixels")
                if width * height > int(options.get("max_pixels", 80_000_000)):
                    raise ConversionError("Requested resize exceeds the pixel limit")
                resized = [ImageOps.contain(im, (width, height), method=Image.Resampling.LANCZOS) for im in selected]
                for im in selected: im.close()
                selected = resized
            dest = output_path(output_dir, src, "jpg" if target_fmt == "JPEG" else fmt)
            save_opts = {}
            if target_fmt in {"GIF", "WEBP"} and len(selected) > 1:
                if "durations" not in locals(): durations = [int(image.info.get("duration", 100))] * len(selected)
                save_opts.update(save_all=True, append_images=selected[1:], duration=durations, loop=int(image.info.get("loop", 0)), optimize=True)
            elif target_fmt == "JPEG": save_opts.update(quality=max(1, min(100, int(options.get("quality", 90)))), optimize=True)
            elif target_fmt == "WEBP": save_opts.update(quality=max(1, min(100, int(options.get("quality", 90)))), method=4)
            if options.get("optimize") and target_fmt in {"PNG", "GIF", "TIFF", "BMP"}:
                save_opts["optimize"] = True
            if options.get("preserve_exif") and "exif" in image.info: save_opts["exif"] = image.info["exif"]
            try: selected[0].save(dest, format=target_fmt, **save_opts)
            except Exception as exc:
                dest.unlink(missing_ok=True)
                if isinstance(exc, (ValueError, OSError)): raise ConversionError(f"Image conversion failed: {exc}") from exc
                raise
            finally:
                for im in selected: im.close()
            return dest
    except ConversionError: raise
    except Exception as exc: raise ConversionError(f"Image conversion failed: {exc}") from exc


def info(input_path: str | Path) -> dict:
    """Return basic image dimensions, mode, format and animation metadata."""
    src = Path(input_path); check_file_size(src)
    try: from PIL import Image
    except ImportError as exc: raise DependencyUnavailableError("Pillow is required for image inspection") from exc
    try:
        with Image.open(src) as im:
            return {"path": str(src), "format": im.format, "width": im.width, "height": im.height, "mode": im.mode, "frames": int(getattr(im, "n_frames", 1)), "animated": int(getattr(im, "n_frames", 1)) > 1, "has_transparency": "A" in im.getbands() or "transparency" in im.info}
    except Exception as exc: raise ConversionError(f"Unable to inspect image: {exc}") from exc
