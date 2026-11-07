from pathlib import Path
import pytest

fitz = pytest.importorskip("fitz")
from converters.pdf_converter import convert, compress_pdf, merge_pdfs, extract_pages, info


def _make_pdf(path: Path, text: str):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    doc.save(path)
    doc.close()


def test_pdf_to_text_and_png(tmp_path: Path):
    source = tmp_path / "source.pdf"
    _make_pdf(source, "ZENFILE test")
    text = convert(source, "txt", tmp_path / "out")
    assert "ZENFILE test" in text.read_text()
    image = convert(source, "png", tmp_path / "out")
    assert image.exists() and image.suffix == ".png"


def test_pdf_merge_and_extract_pages(tmp_path: Path):
    a, b = tmp_path / "a.pdf", tmp_path / "b.pdf"
    _make_pdf(a, "Page A")
    _make_pdf(b, "Page B")
    merged = merge_pdfs([a, b], tmp_path / "merged")
    assert info(merged)["pages"] == 2
    pages = extract_pages(merged, "2", tmp_path / "split")
    assert len(pages) == 1 and info(pages[0])["pages"] == 1


def test_pdf_lossless_repack(tmp_path: Path):
    source = tmp_path / "source.pdf"
    _make_pdf(source, "PDF compression test")
    output = compress_pdf(source, tmp_path / "compressed")
    assert output.is_file()
    assert info(output)["pages"] == 1


def test_multiple_images_to_pdf(tmp_path: Path):
    from PIL import Image
    first, second = tmp_path / "one.png", tmp_path / "two.png"
    Image.new("RGB", (20, 20), "red").save(first)
    Image.new("RGB", (20, 20), "blue").save(second)
    output = convert(first, "pdf", tmp_path / "multi", images=[first, second])
    assert info(output)["pages"] == 2
