from pathlib import Path
import pytest

from utils.file_detector import detect_file, supported_targets
from utils.security import parse_page_ranges, safe_filename, validate_archive_path
from utils.errors import SecurityValidationError, ConversionError


def test_png_detection_uses_signature(tmp_path: Path):
    p = tmp_path / "misleading.txt"
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"not-a-real-image")
    info = detect_file(p)
    assert info.format == "png"
    assert info.detected_by == "signature"
    assert "webp" in supported_targets("png")
    assert "docx" not in supported_targets("pdf")


def test_text_signature_heuristic(tmp_path: Path):
    p = tmp_path / "note.txt"
    p.write_text("hello", encoding="utf-8")
    assert detect_file(p).format == "txt"


def test_unknown_binary_rejected(tmp_path: Path):
    p = tmp_path / "blob.bin"
    p.write_bytes(b"\x00\xff\x81")
    with pytest.raises(ConversionError):
        detect_file(p)


def test_parse_page_ranges():
    assert parse_page_ranges("1-3, 5, 7-8", page_count=8) == [1, 2, 3, 5, 7, 8]
    with pytest.raises(SecurityValidationError):
        parse_page_ranges("1-3,0", page_count=8)
    with pytest.raises(SecurityValidationError):
        parse_page_ranges("1-3,9", page_count=8)


def test_safe_filename_strips_paths_and_controls():
    assert safe_filename("../../a\x00b.txt") == "ab.txt"


def test_zip_slip_rejected(tmp_path: Path):
    with pytest.raises(SecurityValidationError):
        validate_archive_path("../../outside.txt", tmp_path)
    with pytest.raises(SecurityValidationError):
        validate_archive_path("C:\\Windows\\bad.txt", tmp_path)


def test_archive_path_stays_inside_destination(tmp_path: Path):
    target = validate_archive_path("docs/report.txt", tmp_path)
    assert target.is_relative_to(tmp_path.resolve())
