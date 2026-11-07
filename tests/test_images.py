from pathlib import Path
import pytest
from PIL import Image
from converters.image_converter import convert, info
from utils.errors import ConversionError


def test_png_to_webp(tmp_path: Path):
    source = tmp_path / "source.png"
    Image.new("RGB", (24, 16), "cyan").save(source)
    result = convert(source, "webp", tmp_path / "out")
    assert result.is_file() and result.suffix == ".webp"
    assert info(result)["width"] == 24


def test_transparency_is_not_silently_discarded(tmp_path: Path):
    source = tmp_path / "alpha.png"
    Image.new("RGBA", (2, 2), (255, 0, 0, 100)).save(source)
    with pytest.raises(ConversionError):
        convert(source, "jpg", tmp_path / "out")
    result = convert(source, "jpg", tmp_path / "out", background="#ffffff")
    assert result.is_file()


def test_resize_preserves_aspect_ratio(tmp_path: Path):
    source = tmp_path / "wide.png"
    Image.new("RGB", (1600, 800), "violet").save(source)
    result = convert(source, "png", tmp_path / "resized", resize=(400, 400))
    with Image.open(result) as resized:
        assert resized.size == (400, 200)
