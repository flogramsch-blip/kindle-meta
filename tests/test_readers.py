"""Tests für das Einlesen von EPUB und PDF."""

from kindle_meta.readers import UnsupportedFormat, read_metadata

import pytest


def test_read_epub(sample_epub):
    meta = read_metadata(sample_epub)
    assert meta.title == "Der Testtitel"
    assert meta.authors == ["Erika Muster"]
    assert meta.publisher == "Testverlag"
    assert meta.published == "2021"
    assert meta.language == "de"
    assert meta.has_cover()
    assert "Kapitel" in (meta.sample_text or "")
    assert meta.source_path == sample_epub


def test_read_pdf(sample_pdf):
    meta = read_metadata(sample_pdf)
    assert meta.title == "PDF Titel"
    assert meta.authors == ["Max Mustermann"]
    assert meta.page_count == 1


def test_unsupported(tmp_path):
    f = tmp_path / "x.txt"
    f.write_text("hi")
    with pytest.raises(UnsupportedFormat):
        read_metadata(str(f))
