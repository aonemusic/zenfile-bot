from pathlib import Path
import gzip
import zipfile
import pytest
from converters.archive_converter import convert, create_archive, extract, info
from utils.errors import ConversionError


def test_zip_to_tar_round_trip(tmp_path: Path):
    source = tmp_path / "files.zip"
    with zipfile.ZipFile(source, "w") as zf:
        zf.writestr("docs/a.txt", "hello")
    tar = convert(source, "tar", tmp_path / "out")
    assert tar.is_file() and info(tar)["members"] == 1
    files = extract(tar, tmp_path / "extracted")
    assert len(files) == 1 and files[0].read_text() == "hello"


def test_zip_slip_rejected(tmp_path: Path):
    source = tmp_path / "evil.zip"
    with zipfile.ZipFile(source, "w") as zf:
        zf.writestr("../../outside.txt", "bad")
    destination = tmp_path / "destination"
    with pytest.raises(ConversionError):
        extract(source, destination)
    assert not (tmp_path / "outside.txt").exists()


def test_create_archive_sanitizes_duplicate_names(tmp_path: Path):
    first, second = tmp_path / "one.txt", tmp_path / "two.txt"
    first.write_text("one")
    second.write_text("two")
    archive = create_archive([first, second], tmp_path / "made", names=["../same.txt", "same.txt"])
    with zipfile.ZipFile(archive) as zf:
        assert set(zf.namelist()) == {"same.txt", "same_2.txt"}


def test_gzip_decompression_is_size_bounded(tmp_path: Path):
    source = tmp_path / "payload.txt.gz"
    with gzip.open(source, "wb") as stream:
        stream.write(b"hello")
    extracted = extract(source, tmp_path / "gzip-out", max_total_bytes=10)
    assert len(extracted) == 1 and extracted[0].read_bytes() == b"hello"
    with pytest.raises(ConversionError):
        extract(source, tmp_path / "too-small", max_total_bytes=3)
